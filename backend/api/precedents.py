"""Precedent library management (admin) + gestora-siloed listing."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile

from api import client_ip, now_iso, validate_upload
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
from services import audit, db as dbmod, docx_html, rag, storage

router = APIRouter(prefix="/api/precedents", tags=["precedents"])

_GLOBAL_SOURCES = {PrecedentSource.slp_curated.value, PrecedentSource.platform_base.value}

# Active rag_weight per source (SPEC fallback chain). gestora_model shares the
# in-silo active weight (1.0); modelos outrank precedents by LEVEL (RAG Level 0a
# vs 0b), not by rag_weight.
_ACTIVE_WEIGHTS = {
    PrecedentSource.manual_upload.value: 1.0,
    PrecedentSource.validated_output.value: 1.0,
    PrecedentSource.gestora_model.value: 1.0,
    PrecedentSource.slp_curated.value: 0.7,
    PrecedentSource.platform_base.value: 0.4,
}

_TEMPLATE_FOLDER = {
    PrecedentSource.slp_curated.value: "slp-curated",
    PrecedentSource.platform_base.value: "platform-base",
}



def _version_path(precedent: dict[str, Any], version_number: int, filename: str) -> str:
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".docx"
    versioned = f"{precedent['id']}-v{version_number}{extension}"
    if precedent["source"] in _GLOBAL_SOURCES:
        folder = _TEMPLATE_FOLDER[precedent["source"]]
        return f"lol-ai-lo-templates/{folder}/{precedent['language']}/{versioned}"
    # Gestora master templates go to modelos/; regular precedents to precedentes/.
    if precedent["source"] == PrecedentSource.gestora_model.value:
        return storage.modelos_path(precedent["gestora_id"], versioned)
    return storage.precedentes_path(precedent["gestora_id"], versioned)


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
    document_date: Optional[str] = Form(None),
    user: User = Depends(require_admin),
) -> Any:
    """Admin uploads a precedent (creates the precedent + version 1, status draft).

    ``source=gestora_model`` uploads a gestora MASTER TEMPLATE: gestora-scoped
    (gestora_id required), stored under modelos/, versioned + activated exactly
    like a precedent. In RAG it outranks regular precedents as the generation
    base (Level 0a). Both kinds remain HARD-filtered by gestora_id (isolation).
    """
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
            # Fecha del documento (022): eje año/trimestre de la biblioteca.
            "document_date": document_date or None,
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
            ip_address=client_ip(http_request),
        )
    return {"precedent": precedent, "version": version}


def _with_versions(db: dbmod.Database, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Embed each precedent's version list (the admin library UI and the
    tabular-review document picker consume versions with the precedent).

    One bulk query + in-memory grouping instead of a per-precedent select —
    the interface has no IN-filter, and N+1 round-trips to Supabase made the
    listing take seconds. Isolation holds: versions are only attached to the
    already-scoped precedent rows; the rest are discarded."""
    if not rows:
        return []
    wanted = {p["id"] for p in rows}
    versions_by_precedent: dict[str, list[dict[str, Any]]] = {}
    for v in db.unscoped_select("precedent_versions"):
        if v["precedent_id"] in wanted:
            versions_by_precedent.setdefault(v["precedent_id"], []).append(v)
    return [{**p, "versions": versions_by_precedent.get(p["id"], [])} for p in rows]


@router.get("", response_model=list[PrecedentOut])
async def list_precedents(
    gestora_id: Optional[str] = None,
    user: User = Depends(get_current_user),
) -> Any:
    """List precedents (with embedded versions). Clients only ever see their
    own silo + global templates; the gestora_id query param is honoured for
    admin/counsel only."""
    db = dbmod.get_db()
    if user.role in (UserRole.admin, UserRole.counsel):
        if gestora_id:
            return _with_versions(db, db.select("precedents", gestora_id=gestora_id))
        return _with_versions(db, db.unscoped_select("precedents"))
    own = db.select("precedents", gestora_id=user.gestora_id)
    global_templates = [
        p for p in db.select("precedents", gestora_id=None) if p["source"] in _GLOBAL_SOURCES
    ]
    return _with_versions(db, own + global_templates)


@router.get("/versions/{version_id}/html")
async def view_version_html(
    version_id: str,
    user: User = Depends(get_current_user),
) -> Any:
    """Render a precedent version as safe HTML (citas clicables del chat y
    biblioteca del cliente, 022). Mismo control de acceso que el resto de la
    biblioteca (assert_precedent_access: silo propio o plantillas globales;
    404-no-leak). Solo .docx — un PDF devuelve 409 y el frontend enseña el
    snippet de la cita en su lugar."""
    db = dbmod.get_db()
    version = db.get("precedent_versions", version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    precedent = db.get("precedents", version["precedent_id"])
    if precedent is None:
        raise HTTPException(status_code=404, detail="Version not found")
    assert_precedent_access(db, user, precedent)
    if not str(version.get("file_path", "")).lower().endswith(".docx"):
        raise HTTPException(status_code=409, detail="Only .docx versions render as HTML")
    rendered = docx_html.docx_to_html(storage.read(version["file_path"]))
    return {**rendered, "doc_type": precedent["doc_type"], "version_id": version_id}


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
        ip_address=client_ip(http_request),
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
            ip_address=client_ip(http_request),
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
        ip_address=client_ip(http_request),
    )

    # Re-index the affected silo (or the global pool for SLP/base templates).
    if precedent.get("gestora_id"):
        rag.reindex_gestora(precedent["gestora_id"], precedent["id"])
    else:
        rag.reindex_global(precedent["id"])
    return version


@router.post("/versions/{version_id}/supersede")
async def supersede_version(
    version_id: str,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Admin manually supersedes an ACTIVE version without activating another
    (kept in the index with rag_weight 0.3, per the same re-index rules)."""
    db = dbmod.get_db()
    version = db.get("precedent_versions", version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    precedent = db.get("precedents", version["precedent_id"])
    if precedent is None:
        raise HTTPException(status_code=404, detail="Precedent not found")
    if version["status"] != PrecedentVersionStatus.active.value:
        raise HTTPException(status_code=409, detail="Only an active version can be superseded")

    version = db.update(
        "precedent_versions",
        version_id,
        {
            "status": PrecedentVersionStatus.superseded.value,
            "rag_weight": 0.3,
            "superseded_at": now_iso(),
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.precedent_superseded,
        resource_type=AuditResourceType.precedent_version,
        resource_id=version_id,
        gestora_id=precedent.get("gestora_id"),
        metadata={"rag_weight": 0.3, "manual": True},
        ip_address=client_ip(http_request),
    )

    if precedent.get("gestora_id"):
        rag.reindex_gestora(precedent["gestora_id"], precedent["id"])
    else:
        rag.reindex_global(precedent["id"])
    return version
