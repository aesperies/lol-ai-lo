"""Precedent library management (admin) + gestora-siloed listing."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile

from api import now_iso, validate_upload
from auth import assert_precedent_access, get_current_user, require_admin
from models.schema import (
    AuditAction,
    AuditResourceType,
    PrecedentOut,
    PrecedentSource,
    PrecedentVersionOut,
    PrecedentVersionStatus,
    User,
    UserRole,
)
from services import audit, db as dbmod, rag, storage

router = APIRouter(prefix="/api/precedents", tags=["precedents"])

_GLOBAL_SOURCES = {PrecedentSource.slp_curated.value, PrecedentSource.platform_base.value}

# Active rag_weight per source (SPEC fallback chain).
_ACTIVE_WEIGHTS = {
    PrecedentSource.manual_upload.value: 1.0,
    PrecedentSource.validated_output.value: 1.0,
    PrecedentSource.slp_curated.value: 0.7,
    PrecedentSource.platform_base.value: 0.4,
}

_TEMPLATE_FOLDER = {
    PrecedentSource.slp_curated.value: "slp-curated",
    PrecedentSource.platform_base.value: "platform-base",
}


def _ip(http_request: Request) -> Optional[str]:
    return http_request.client.host if http_request.client else None


def _version_path(precedent: dict[str, Any], version_number: int, filename: str) -> str:
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".docx"
    if precedent["source"] in _GLOBAL_SOURCES:
        folder = _TEMPLATE_FOLDER[precedent["source"]]
        return (
            f"lol-ai-lo-templates/{folder}/{precedent['language']}/"
            f"{precedent['id']}-v{version_number}{extension}"
        )
    return f"gestoras/{precedent['gestora_id']}/precedents/{precedent['id']}-v{version_number}{extension}"


# .docx = generation base; .pdf = RAG reference only (guardrail 7).
# Extension + max size + magic bytes enforced via api.validate_upload
# (improvement #9 upload hardening).
_PRECEDENT_EXTENSIONS = (".docx", ".pdf")


@router.post("", status_code=201)
async def upload_precedent(
    http_request: Request,
    file: UploadFile,
    doc_type: str = Form(...),
    language: str = Form(...),
    source: PrecedentSource = Form(PrecedentSource.manual_upload),
    gestora_id: Optional[str] = Form(None),
    fund_id: Optional[str] = Form(None),
    user: User = Depends(require_admin),
) -> Any:
    """Admin uploads a precedent (creates the precedent + version 1, status draft)."""
    db = dbmod.get_db()
    if source.value not in _GLOBAL_SOURCES and not gestora_id:
        raise HTTPException(status_code=422, detail="gestora_id is required for non-global precedents")
    if gestora_id and db.get("gestoras", gestora_id) is None:
        raise HTTPException(status_code=404, detail="Gestora not found")
    data = await file.read()
    validate_upload(file.filename or "", data, _PRECEDENT_EXTENSIONS)

    precedent = db.insert(
        "precedents",
        {
            "gestora_id": gestora_id if source.value not in _GLOBAL_SOURCES or gestora_id else None,
            "fund_id": fund_id,
            "doc_type": doc_type,
            "language": language,
            "source": source.value,
        },
    )
    key = storage.save(_version_path(precedent, 1, file.filename or "precedent.docx"), data)
    version = db.insert(
        "precedent_versions",
        {
            "precedent_id": precedent["id"],
            "version_number": 1,
            "file_path": key,
            "status": PrecedentVersionStatus.draft.value,
            "rag_weight": 0.0,
            "created_by": user.id,
        },
    )
    for action, resource_type, resource_id in (
        (AuditAction.precedent_uploaded, AuditResourceType.precedent, precedent["id"]),
        (AuditAction.precedent_version_created, AuditResourceType.precedent_version, version["id"]),
    ):
        audit.log_action(
            db,
            user=user,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            gestora_id=gestora_id,
            metadata={"doc_type": doc_type, "language": language, "source": source.value,
                      "filename": file.filename},
            ip_address=_ip(http_request),
        )
    return {"precedent": precedent, "version": version}


@router.get("", response_model=list[PrecedentOut])
async def list_precedents(
    gestora_id: Optional[str] = None,
    user: User = Depends(get_current_user),
) -> Any:
    """List precedents. Clients only ever see their own silo + global templates;
    the gestora_id query param is honoured for admin/counsel only."""
    db = dbmod.get_db()
    if user.role in (UserRole.admin, UserRole.counsel):
        if gestora_id:
            return db.select("precedents", gestora_id=gestora_id)
        return db.select("precedents")
    own = db.select("precedents", gestora_id=user.gestora_id)
    global_templates = [
        p for p in db.select("precedents", gestora_id=None) if p["source"] in _GLOBAL_SOURCES
    ]
    return own + global_templates


@router.get("/{precedent_id}/versions", response_model=list[PrecedentVersionOut])
async def list_versions(precedent_id: str, user: User = Depends(get_current_user)) -> Any:
    db = dbmod.get_db()
    precedent = db.get("precedents", precedent_id)
    if precedent is None:
        raise HTTPException(status_code=404, detail="Precedent not found")
    assert_precedent_access(db, user, precedent)
    return db.select("precedent_versions", precedent_id=precedent_id)


@router.post("/{precedent_id}/versions", status_code=201)
async def add_version(
    precedent_id: str,
    file: UploadFile,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Admin adds a new version (status draft until activated)."""
    db = dbmod.get_db()
    precedent = db.get("precedents", precedent_id)
    if precedent is None:
        raise HTTPException(status_code=404, detail="Precedent not found")
    data = await file.read()
    validate_upload(file.filename or "", data, _PRECEDENT_EXTENSIONS)

    existing = db.select("precedent_versions", precedent_id=precedent_id)
    next_number = max((v["version_number"] for v in existing), default=0) + 1
    key = storage.save(
        _version_path(precedent, next_number, file.filename or "precedent.docx"), data
    )
    version = db.insert(
        "precedent_versions",
        {
            "precedent_id": precedent_id,
            "version_number": next_number,
            "file_path": key,
            "status": PrecedentVersionStatus.draft.value,
            "rag_weight": 0.0,
            "created_by": user.id,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.precedent_version_created,
        resource_type=AuditResourceType.precedent_version,
        resource_id=version["id"],
        gestora_id=precedent.get("gestora_id"),
        metadata={"version_number": next_number, "filename": file.filename},
        ip_address=_ip(http_request),
    )
    return version


@router.post("/versions/{version_id}/activate")
async def activate_version(
    version_id: str,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Admin activates a version; any previously active version is superseded
    (kept in the index with rag_weight 0.3 per SPEC)."""
    db = dbmod.get_db()
    version = db.get("precedent_versions", version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    precedent = db.get("precedents", version["precedent_id"])
    if precedent is None:
        raise HTTPException(status_code=404, detail="Precedent not found")
    if version["status"] == PrecedentVersionStatus.active.value:
        raise HTTPException(status_code=409, detail="Version is already active")

    superseded_ids: list[str] = []
    for other in db.select(
        "precedent_versions",
        precedent_id=version["precedent_id"],
        status=PrecedentVersionStatus.active.value,
    ):
        db.update(
            "precedent_versions",
            other["id"],
            {
                "status": PrecedentVersionStatus.superseded.value,
                "rag_weight": 0.3,
                "superseded_at": now_iso(),
            },
        )
        superseded_ids.append(other["id"])
        audit.log_action(
            db,
            user=user,
            action=AuditAction.precedent_superseded,
            resource_type=AuditResourceType.precedent_version,
            resource_id=other["id"],
            gestora_id=precedent.get("gestora_id"),
            metadata={"superseded_by": version_id, "rag_weight": 0.3},
            ip_address=_ip(http_request),
        )

    active_weight = _ACTIVE_WEIGHTS.get(precedent["source"], 1.0)
    version = db.update(
        "precedent_versions",
        version_id,
        {
            "status": PrecedentVersionStatus.active.value,
            "rag_weight": active_weight,
            "activated_at": now_iso(),
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.precedent_activated,
        resource_type=AuditResourceType.precedent_version,
        resource_id=version_id,
        gestora_id=precedent.get("gestora_id"),
        metadata={"rag_weight": active_weight, "superseded": superseded_ids},
        ip_address=_ip(http_request),
    )

    # Re-index the affected silo (or the global pool for SLP/base templates).
    if precedent.get("gestora_id"):
        rag.reindex_gestora(precedent["gestora_id"])
    else:
        rag.reindex_global()
    return version
