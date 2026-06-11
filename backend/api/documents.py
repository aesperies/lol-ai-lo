"""Document endpoints: generation, redline, downloads, counsel edits."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile

from api import (
    DOCX_MEDIA_TYPE,
    get_request_or_404,
    latest_document,
    require_status,
    transition,
)
from auth import assert_request_access, get_current_user, require_counsel
from config import ServiceNotConfiguredError, get_settings
from models.schema import (
    AuditAction,
    AuditResourceType,
    CounselInlineEditBody,
    DocumentVersionType,
    RequestStatus,
    UsageEventType,
    User,
    UserRole,
)
from services import (
    audit,
    db as dbmod,
    docx_renderer,
    generator,
    rag,
    redline as redline_service,
    storage,
    usage,
)

router = APIRouter(prefix="/api", tags=["documents"])

_DOWNLOAD_AUDIT = {
    DocumentVersionType.draft: AuditAction.draft_downloaded,
    DocumentVersionType.redline: AuditAction.redline_downloaded,
    DocumentVersionType.final: AuditAction.final_downloaded,
}


def _ip(http_request: Request) -> Optional[str]:
    return http_request.client.host if http_request.client else None


@router.post("/requests/{request_id}/generate")
async def generate(
    request_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Generate draft + redline for a confirmed request.

    Guardrail 2: refuses unless status is 'confirmed' (client confirmation)
    AND parsed_params.generation_ready is true.
    """
    db = dbmod.get_db()
    settings = get_settings()
    if user.role == UserRole.counsel:
        raise HTTPException(status_code=403, detail="Counsel cannot trigger generation")

    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.confirmed)

    params = row.get("parsed_params") or {}
    if not params.get("generation_ready"):
        raise HTTPException(status_code=409, detail="parsed_params.generation_ready must be true")

    # Fail fast BEFORE mutating status so a 503 leaves the request re-runnable.
    if not settings.anthropic_configured:
        raise ServiceNotConfiguredError("anthropic", "Set ANTHROPIC_API_KEY.")

    fund = db.get("funds", row["fund_id"]) or {}
    gestora = db.get("gestoras", gestora_id) or {}
    language = row.get("language") or params.get("language") or "es"

    row = transition(db, row, RequestStatus.generating)

    # RAG: hard gestora_id + doc_type pre-filter, then fallback chain.
    retrieval = rag.retrieve(
        db,
        gestora_id=gestora_id,
        doc_type=row["doc_type"],
        language=language,
        query_text=row["freetext"],
    )
    if retrieval.requires_counsel:
        # Level 3 ALWAYS forces Exit B (guardrail 10).
        db.update("requests", request_id, {"requires_counsel": True})
        row["requires_counsel"] = True

    text = generator.generate_document(
        doc_type=row["doc_type"],
        language=language,
        fund_name=fund.get("name", ""),
        gestora_name=gestora.get("name", ""),
        jurisdiction=params.get("jurisdiction") or fund.get("jurisdiction", ""),
        governing_law=params.get("governing_law", ""),
        parties=params.get("parties", []),
        key_terms=params.get("key_terms", []),
        freetext=row["freetext"],
        precedent_text=retrieval.base_text,
    )
    if retrieval.warning:
        text = f"{text}\n\n{retrieval.warning}"

    base_path = f"gestoras/{gestora_id}/funds/{row['fund_id']}/documents/{request_id}"
    draft_key = storage.save(f"{base_path}/draft.docx", docx_renderer.render_docx(text))
    draft_doc = db.insert(
        "documents",
        {
            "request_id": request_id,
            "version_type": DocumentVersionType.draft.value,
            "file_path": draft_key,
            "precedent_version_id": retrieval.base_version_id,
            "uploaded_by": None,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.document_generated,
        resource_type=AuditResourceType.document,
        resource_id=draft_doc["id"],
        gestora_id=gestora_id,
        metadata={
            "request_id": request_id,
            "doc_type": row["doc_type"],
            "language": language,
            "rag_level": retrieval.level,
            "precedent_version_id": retrieval.base_version_id,
            "model": settings.claude_model,
        },
        ip_address=_ip(http_request),
    )
    usage.record_usage(
        db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.document_generated
    )

    redline_doc = None
    if retrieval.base_text is not None:
        redline_key = storage.save(
            f"{base_path}/redline.docx",
            redline_service.build_redline(retrieval.base_text, text),
        )
        redline_doc = db.insert(
            "documents",
            {
                "request_id": request_id,
                "version_type": DocumentVersionType.redline.value,
                "file_path": redline_key,
                "precedent_version_id": retrieval.base_version_id,
                "uploaded_by": None,
            },
        )
        audit.log_action(
            db,
            user=user,
            action=AuditAction.redline_generated,
            resource_type=AuditResourceType.document,
            resource_id=redline_doc["id"],
            gestora_id=gestora_id,
            metadata={
                "request_id": request_id,
                "base_precedent_version_id": retrieval.base_version_id,
                "author": redline_service.REDLINE_AUTHOR,
            },
            ip_address=_ip(http_request),
        )

    row = transition(db, row, RequestStatus.review_pending)
    return {
        "request": row,
        "draft": draft_doc,
        "redline": redline_doc,
        "rag_level": retrieval.level,
        "requires_counsel": row.get("requires_counsel", False),
        "warning": retrieval.warning,
    }


@router.get("/requests/{request_id}/documents/{version_type}/download")
async def download_document(
    request_id: str,
    version_type: DocumentVersionType,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Download draft / redline / final (.docx). counsel_edit is internal-only."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)

    if version_type not in _DOWNLOAD_AUDIT:
        raise HTTPException(status_code=404, detail="Version type not downloadable")
    if version_type == DocumentVersionType.final:
        require_status(row, RequestStatus.validated, RequestStatus.delivered)

    doc = latest_document(db, request_id, version_type)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No {version_type.value} document for this request")
    data = storage.read(doc["file_path"])

    audit.log_action(
        db,
        user=user,
        action=_DOWNLOAD_AUDIT[version_type],
        resource_type=AuditResourceType.document,
        resource_id=doc["id"],
        gestora_id=gestora_id,
        metadata={"request_id": request_id, "version_type": version_type.value},
        ip_address=_ip(http_request),
    )

    # Exit B final delivery: first client download closes the workflow.
    if (
        version_type == DocumentVersionType.final
        and row["status"] == RequestStatus.validated.value
        and user.role == UserRole.client
    ):
        transition(db, row, RequestStatus.delivered)

    return Response(
        content=data,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{request_id}-{version_type.value}.docx"'
        },
    )


# ---------------------------------------------------------------------------
# Counsel edits (Exit B review)
# ---------------------------------------------------------------------------

@router.post("/requests/{request_id}/counsel/edit")
async def counsel_edit_inline(
    request_id: str,
    body: CounselInlineEditBody,
    http_request: Request,
    user: User = Depends(require_counsel),
) -> Any:
    """Inline (rich text) counsel edit: rendered server-side to a counsel_edit .docx."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.counsel_review)

    edits = db.select("documents", request_id=request_id, version_type=DocumentVersionType.counsel_edit.value)
    path = (
        f"gestoras/{gestora_id}/funds/{row['fund_id']}/documents/{request_id}/"
        f"counsel_edit_v{len(edits) + 1}.docx"
    )
    key = storage.save(path, docx_renderer.render_docx(body.text))
    doc = db.insert(
        "documents",
        {
            "request_id": request_id,
            "version_type": DocumentVersionType.counsel_edit.value,
            "file_path": key,
            "precedent_version_id": None,
            "uploaded_by": user.id,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.counsel_edit_inline,
        resource_type=AuditResourceType.document,
        resource_id=doc["id"],
        gestora_id=gestora_id,
        metadata={"request_id": request_id, "comment": body.comment},
        ip_address=_ip(http_request),
    )
    return doc


@router.post("/requests/{request_id}/counsel/upload")
async def counsel_edit_upload(
    request_id: str,
    file: UploadFile,
    http_request: Request,
    user: User = Depends(require_counsel),
) -> Any:
    """Counsel uploads an edited .docx (download/edit/upload flow)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.counsel_review)

    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=422, detail="Counsel uploads must be .docx")

    edits = db.select("documents", request_id=request_id, version_type=DocumentVersionType.counsel_edit.value)
    path = (
        f"gestoras/{gestora_id}/funds/{row['fund_id']}/documents/{request_id}/"
        f"counsel_edit_v{len(edits) + 1}.docx"
    )
    key = storage.save(path, await file.read())
    doc = db.insert(
        "documents",
        {
            "request_id": request_id,
            "version_type": DocumentVersionType.counsel_edit.value,
            "file_path": key,
            "precedent_version_id": None,
            "uploaded_by": user.id,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.counsel_edit_uploaded,
        resource_type=AuditResourceType.document,
        resource_id=doc["id"],
        gestora_id=gestora_id,
        metadata={"request_id": request_id, "filename": file.filename},
        ip_address=_ip(http_request),
    )
    return doc
