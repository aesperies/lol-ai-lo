"""Document endpoints: generation (async job), redline, downloads, counsel edits."""
from __future__ import annotations

import asyncio
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
    GenerationJobOut,
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
    jobs,
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


def _run_generation_pipeline(
    db: dbmod.Database,
    request_id: str,
    gestora_id: str,
    user: User,
    ip_address: Optional[str],
) -> None:
    """The generation pipeline (RAG -> Claude -> docx -> redline), unchanged
    from the previous synchronous endpoint. Runs inside a generation job
    (services/jobs.py); raising makes the job runner retry."""
    settings = get_settings()
    row = db.get("requests", request_id)
    if row is None:
        raise RuntimeError(f"Request {request_id} disappeared during generation")
    params = row.get("parsed_params") or {}
    fund = db.get("funds", row["fund_id"]) or {}
    gestora = db.get("gestoras", gestora_id) or {}
    language = row.get("language") or params.get("language") or "es"

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
        ip_address=ip_address,
    )
    usage.record_usage(
        db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.document_generated
    )

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
            ip_address=ip_address,
        )

    # On success the workflow continues exactly as before.
    transition(db, db.get("requests", request_id), RequestStatus.review_pending)


@router.post("/requests/{request_id}/generate", status_code=202)
async def generate(
    request_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Enqueue draft + redline generation for a confirmed request (202).

    All guardrails are validated synchronously BEFORE any job is created.
    Guardrail 2: refuses unless status is 'confirmed' (client confirmation)
    AND parsed_params.generation_ready is true. The pipeline itself runs as
    an async generation job; poll GET .../generation-job for its state.
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

    transition(db, row, RequestStatus.generating)
    ip_address = _ip(http_request)

    def on_final_failure(exc: Exception) -> None:
        # Revert to 'confirmed' so the client can retry, and record the
        # failure in the audit log (enum is fixed: document_generated with
        # failed=true metadata marks a failed generation).
        current = db.get("requests", request_id)
        if current is not None and current["status"] == RequestStatus.generating.value:
            transition(db, current, RequestStatus.confirmed)
        audit.log_action(
            db,
            user=user,
            action=AuditAction.document_generated,
            resource_type=AuditResourceType.request,
            resource_id=request_id,
            gestora_id=gestora_id,
            metadata={"failed": True, "error": str(exc)},
            ip_address=ip_address,
        )

    job = jobs.get_runner().enqueue(
        db,
        request_id=request_id,
        # to_thread: the pipeline is blocking (LLM call, docx render); a fresh
        # coroutine is produced per attempt so retries re-run it cleanly.
        factory=lambda: asyncio.to_thread(
            _run_generation_pipeline, db, request_id, gestora_id, user, ip_address
        ),
        on_final_failure=on_final_failure,
    )
    return {"job_id": job["id"], "status": job["status"]}


@router.get("/requests/{request_id}/generation-job", response_model=GenerationJobOut)
async def get_generation_job(
    request_id: str,
    user: User = Depends(get_current_user),
) -> Any:
    """Latest generation job for a request (poll target for the 202 flow)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    job = jobs.latest_job(db, request_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No generation job for this request")
    return GenerationJobOut(
        id=job["id"],
        status=job["status"],
        attempts=job.get("attempts", 0),
        last_error=job.get("last_error"),
    )


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
