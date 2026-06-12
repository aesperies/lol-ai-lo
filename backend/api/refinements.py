"""Iterative refinement endpoints (improvement #4).

After generation, while the request sits in 'review_pending', the client can
ask for targeted natural-language adjustments ("cambia el plazo de preaviso a
15 días"). Each applied refinement re-runs the LLM on the CURRENT draft and
produces a new draft iteration plus a redline regenerated against the SAME
original precedent base — the redline always shows the cumulative change vs
the precedent. Limit: settings.max_refinements (default 3); beyond that the
client is directed to Exit B (Solicitar Validación).

An ambiguous instruction yields a verbatim [REFINEMENT-UNCLEAR: reason]
output: the refinement is marked 'failed' with the reason surfaced to the
client, NO new documents are created, and the request returns to
'review_pending' with the previous iteration intact.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from api import (
    get_request_or_404,
    latest_document,
    now_iso,
    require_status,
    transition,
)
from auth import assert_request_access, get_current_user, require_client
from config import ServiceNotConfiguredError, get_settings
from models.schema import (
    AuditAction,
    AuditResourceType,
    DocumentVersionType,
    RefinementCreate,
    RefinementOut,
    RefinementStatus,
    RequestStatus,
    UsageEventType,
    User,
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

router = APIRouter(prefix="/api/requests", tags=["refinements"])


def _ip(http_request: Request) -> Optional[str]:
    return http_request.client.host if http_request.client else None


def _run_refinement_pipeline(
    db: dbmod.Database,
    request_id: str,
    refinement_id: str,
    gestora_id: str,
    user: User,
    ip_address: Optional[str],
) -> None:
    """Refinement pipeline (extract current draft -> Claude -> docx -> redline
    vs the ORIGINAL precedent base). Runs inside a generation job
    (services/jobs.py); raising makes the job runner retry."""
    settings = get_settings()
    row = db.get("requests", request_id)
    refinement = db.get("refinements", refinement_id)
    if row is None or refinement is None:
        raise RuntimeError(f"Request {request_id} or refinement {refinement_id} disappeared")
    iteration = refinement["iteration"]
    instruction = refinement["instruction"]

    current_draft = latest_document(db, request_id, DocumentVersionType.draft)
    if current_draft is None:
        raise RuntimeError(f"No draft to refine for request {request_id}")
    current_text = docx_renderer.extract_text(storage.read(current_draft["file_path"]))

    text = generator.refine_document(current_text=current_text, instruction=instruction)
    unclear_reason = generator.refinement_unclear_reason(text)
    if unclear_reason is not None:
        # Handled (non-retryable) outcome: the previous iteration stays the
        # valid draft, no documents are created, the reason reaches the client.
        db.update(
            "refinements",
            refinement_id,
            {"status": RefinementStatus.failed.value, "error": unclear_reason},
        )
        transition(db, db.get("requests", request_id), RequestStatus.review_pending)
        audit.log_action(
            db,
            user=user,
            action=AuditAction.document_generated,
            resource_type=AuditResourceType.request,
            resource_id=request_id,
            gestora_id=gestora_id,
            metadata={
                "refinement": True,
                "iteration": iteration,
                "instruction": instruction,
                "refinement_failed": unclear_reason,
            },
            ip_address=ip_address,
        )
        return

    # The precedent base id was propagated draft -> draft from iteration 0,
    # so every redline diffs against the SAME original precedent.
    base_version_id = current_draft.get("precedent_version_id")

    base_path = f"gestoras/{gestora_id}/funds/{row['fund_id']}/documents/{request_id}"
    draft_key = storage.save(
        f"{base_path}/draft_v{iteration}.docx", docx_renderer.render_docx(text)
    )
    draft_doc = db.insert(
        "documents",
        {
            "request_id": request_id,
            "version_type": DocumentVersionType.draft.value,
            "file_path": draft_key,
            "precedent_version_id": base_version_id,
            "uploaded_by": None,
            "iteration": iteration,
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
            "refinement": True,
            "iteration": iteration,
            "instruction": instruction,
            "model": settings.claude_model,
        },
        ip_address=ip_address,
    )
    # Each applied refinement consumes an LLM generation — billable.
    usage.record_usage(
        db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.document_generated
    )

    base_version = db.get("precedent_versions", base_version_id) if base_version_id else None
    base_text = rag.load_version_text(base_version) if base_version else None
    if base_text is not None:
        redline_key = storage.save(
            f"{base_path}/redline_v{iteration}.docx",
            redline_service.build_redline(base_text, text),
        )
        redline_doc = db.insert(
            "documents",
            {
                "request_id": request_id,
                "version_type": DocumentVersionType.redline.value,
                "file_path": redline_key,
                "precedent_version_id": base_version_id,
                "uploaded_by": None,
                "iteration": iteration,
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
                "refinement": True,
                "iteration": iteration,
                "instruction": instruction,
                "base_precedent_version_id": base_version_id,
                "author": redline_service.REDLINE_AUTHOR,
            },
            ip_address=ip_address,
        )

    db.update(
        "refinements",
        refinement_id,
        {"status": RefinementStatus.applied.value, "applied_at": now_iso()},
    )
    transition(db, db.get("requests", request_id), RequestStatus.review_pending)


@router.post("/{request_id}/refinements", status_code=202)
async def request_refinement(
    request_id: str,
    body: RefinementCreate,
    http_request: Request,
    user: User = Depends(require_client),
) -> Any:
    """Enqueue one iterative refinement of the generated document (202).

    Only allowed in 'review_pending' (after generation, before Exit A/B) and
    while under the max_refinements limit. The pipeline runs as an async
    generation job; poll GET .../generation-job, then re-read the refinement
    history for the applied/failed outcome.
    """
    db = dbmod.get_db()
    settings = get_settings()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.review_pending)

    existing = db.select("refinements", request_id=request_id)
    # Failed refinements (unclear instruction / job error) produced no new
    # iteration and are not billed, so they do not consume the quota.
    consumed = [r for r in existing if r["status"] != RefinementStatus.failed.value]
    if len(consumed) >= settings.max_refinements:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Límite de ajustes alcanzado ({settings.max_refinements}). "
                "Para más cambios, usa 'Solicitar Validación' (Exit B)."
            ),
        )

    if latest_document(db, request_id, DocumentVersionType.draft) is None:
        raise HTTPException(status_code=409, detail="No draft document available to refine")

    # Fail fast BEFORE mutating status so a 503 leaves the request untouched.
    if not settings.anthropic_configured:
        raise ServiceNotConfiguredError("anthropic", "Set ANTHROPIC_API_KEY.")

    # Iterations are never reused (unique(request_id, iteration)), so a failed
    # refinement leaves a numbering gap by design.
    iteration = max((r["iteration"] for r in existing), default=0) + 1
    refinement = db.insert(
        "refinements",
        {
            "request_id": request_id,
            "iteration": iteration,
            "instruction": body.instruction,
            "status": RefinementStatus.pending.value,
            "error": None,
            "created_by": user.id,
            "applied_at": None,
        },
    )
    transition(db, row, RequestStatus.generating)
    ip_address = _ip(http_request)

    def on_final_failure(exc: Exception) -> None:
        # The previous draft is still valid: back to 'review_pending', NOT
        # 'confirmed', and the refinement carries the failure reason.
        current = db.get("requests", request_id)
        if current is not None and current["status"] == RequestStatus.generating.value:
            transition(db, current, RequestStatus.review_pending)
        pending = db.get("refinements", refinement["id"])
        if pending is not None and pending["status"] == RefinementStatus.pending.value:
            db.update(
                "refinements",
                refinement["id"],
                {"status": RefinementStatus.failed.value, "error": str(exc)},
            )
        audit.log_action(
            db,
            user=user,
            action=AuditAction.document_generated,
            resource_type=AuditResourceType.request,
            resource_id=request_id,
            gestora_id=gestora_id,
            metadata={
                "failed": True,
                "refinement": True,
                "iteration": iteration,
                "instruction": body.instruction,
                "refinement_failed": str(exc),
            },
            ip_address=ip_address,
        )

    job = jobs.get_runner().enqueue(
        db,
        request_id=request_id,
        factory=lambda: asyncio.to_thread(
            _run_refinement_pipeline, db, request_id, refinement["id"], gestora_id, user, ip_address
        ),
        on_final_failure=on_final_failure,
    )
    return {"refinement_id": refinement["id"], "job_id": job["id"], "iteration": iteration}


@router.get("/{request_id}/refinements", response_model=list[RefinementOut])
async def list_refinements(
    request_id: str,
    user: User = Depends(get_current_user),
) -> Any:
    """Refinement history for a request (oldest first)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    return db.select("refinements", request_id=request_id)
