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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from api import (
    client_ip,
    get_request_or_404,
    latest_document,
    require_status,
    transition,
)
from auth import assert_request_access, assert_request_owner, get_current_user, require_client
from config import ServiceNotConfiguredError, get_settings
from models.schema import (
    AuditAction,
    AuditResourceType,
    DocumentVersionType,
    RefinementCreate,
    RefinementOut,
    RefinementStatus,
    RequestStatus,
    User,
)
from services import (
    audit,
    db as dbmod,
    generation_pipeline,
    jobs,
)
from services.rate_limit import rate_limit

router = APIRouter(prefix="/api/requests", tags=["refinements"])



@router.post(
    "/{request_id}/refinements",
    status_code=202,
    # LLM-cost endpoint: 6/min per user (improvement #9 rate limiting).
    dependencies=[Depends(rate_limit("refinement", 6))],
)
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
    # Owner-only (collaboration): refinements are mutating; collaborators get 403.
    gestora_id = assert_request_owner(db, user, row)
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
    # Under the default local-first Ollama provider this is always true; a 503
    # then only surfaces at call time if the daemon is unreachable.
    if not settings.llm_configured:
        raise ServiceNotConfiguredError(
            settings.llm_provider, "Configure the selected LLM provider."
        )

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
    ip_address = client_ip(http_request)

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
            generation_pipeline.run_refinement, db, request_id, refinement["id"], gestora_id, user, ip_address
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
