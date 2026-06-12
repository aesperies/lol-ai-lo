"""Request lifecycle endpoints: intake, parse, confirm, Exit A/B, counsel flow."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api import (
    DOCX_MEDIA_TYPE,
    exit_a_blockers,
    get_request_or_404,
    latest_document,
    now_iso,
    require_status,
    transition,
)
from api.counsel_assignments import resolve_counsel_recipients
from auth import (
    assert_request_access,
    get_current_user,
    require_client,
    require_counsel,
)
from config import get_settings
from models import doc_fields
from models.schema import (
    EXIT_A_CHECKBOX_TEXT,
    AuditAction,
    AuditResourceType,
    ConfirmParamsBody,
    DocumentVersionType,
    ExitAAcknowledgeBody,
    PrecedentSource,
    PrecedentVersionStatus,
    RequestCreate,
    RequestOut,
    RequestStatus,
    UsageEventType,
    User,
    UserRole,
)
from services import (
    audit,
    db as dbmod,
    email_service,
    intake_parser,
    quality,
    rag,
    signed_urls,
    storage,
    usage,
)
from services.rate_limit import rate_limit

router = APIRouter(prefix="/api/requests", tags=["requests"])

logger = logging.getLogger("lolailo.requests")


def _ip(http_request: Request) -> Optional[str]:
    return http_request.client.host if http_request.client else None


def _effective_doc_type(request_row: dict[str, Any]) -> str:
    if request_row["doc_type"].lower().startswith("other") and request_row.get("doc_type_custom"):
        return f"Other: {request_row['doc_type_custom']}"
    return request_row["doc_type"]


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------

@router.post("", response_model=RequestOut, status_code=201)
async def submit_request(
    body: RequestCreate,
    http_request: Request,
    user: User = Depends(require_client),
) -> Any:
    """Client intake form submission. Fund must belong to the client's gestora."""
    db = dbmod.get_db()
    fund = db.get("funds", body.fund_id)
    if fund is None or fund["gestora_id"] != user.gestora_id:
        # 404 (not 403) so other gestoras' fund ids are not discoverable.
        raise HTTPException(status_code=404, detail="Fund not found")

    # Structured intake values: unknown keys are rejected; required keys may
    # be missing at submit time (the parser flags them as unclear).
    if body.structured_fields:
        try:
            doc_fields.validate_structured_fields(body.doc_type, body.structured_fields)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    row = db.insert(
        "requests",
        {
            "fund_id": body.fund_id,
            "user_id": user.id,
            "doc_type": body.doc_type,
            "doc_type_custom": body.doc_type_custom,
            "freetext": body.freetext,
            "language": None,
            "parsed_params": None,
            "structured_fields": body.structured_fields or None,
            "status": RequestStatus.parsing.value,
            # "validación por abogado" toggle: counsel review requested upfront
            "requires_counsel": body.validation_requested,
            "exit_a_acknowledged_at": None,
            # Counsel SLA timestamps (005_quality_and_sla.sql).
            "counsel_requested_at": None,
            "counsel_validated_at": None,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.document_requested,
        resource_type=AuditResourceType.request,
        resource_id=row["id"],
        gestora_id=user.gestora_id,
        metadata={
            "doc_type": body.doc_type,
            "fund_id": body.fund_id,
            "validation_requested": body.validation_requested,
            "freetext_length": len(body.freetext),
            "structured_field_keys": sorted(body.structured_fields or {}),
        },
        ip_address=_ip(http_request),
    )
    return row


@router.post(
    "/{request_id}/parse",
    # LLM-cost endpoint: 10/min per user (improvement #9 rate limiting).
    dependencies=[Depends(rate_limit("parse", 10))],
)
async def parse_request(
    request_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Run the Claude intake parser and store parsed_params (503 if Anthropic unset)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    require_status(row, RequestStatus.parsing)

    parsed = intake_parser.parse_intake(
        _effective_doc_type(row),
        row["freetext"],
        structured_fields=row.get("structured_fields") or None,
    )
    row = db.update(
        "requests",
        request_id,
        {"parsed_params": parsed, "language": parsed.get("language")},
    )
    return {"request": row, "parsed_params": parsed}


@router.post("/{request_id}/confirm", response_model=RequestOut)
async def confirm_params(
    request_id: str,
    body: ConfirmParamsBody,
    http_request: Request,
    user: User = Depends(require_client),
) -> Any:
    """Client confirms (or inline-edits) the parsed parameters.

    Guardrail 2: generation is impossible without this confirmation AND
    generation_ready=true on the final parameters.
    """
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.parsing)

    params = row.get("parsed_params")
    if not params:
        raise HTTPException(status_code=409, detail="Request has not been parsed yet")

    edited = False
    if body.parsed_params is not None and body.parsed_params != params:
        edited_fields = sorted(
            k for k in set(params) | set(body.parsed_params)
            if params.get(k) != body.parsed_params.get(k)
        )
        params = body.parsed_params
        edited = True
        audit.log_action(
            db,
            user=user,
            action=AuditAction.params_edited,
            resource_type=AuditResourceType.request,
            resource_id=request_id,
            gestora_id=gestora_id,
            metadata={"edited_fields": edited_fields},
            ip_address=_ip(http_request),
        )

    if not params.get("generation_ready"):
        raise HTTPException(
            status_code=422,
            detail=params.get("message")
            or "Parameters are not generation-ready; please clarify the unclear fields.",
        )

    db.update("requests", request_id, {"parsed_params": params})
    row = transition(db, row, RequestStatus.confirmed)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.params_confirmed,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id,
        metadata={"edited": edited, "language": params.get("language")},
        ip_address=_ip(http_request),
    )
    return row


# ---------------------------------------------------------------------------
# Listing / detail (gestora-siloed for clients)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[RequestOut])
async def list_requests(user: User = Depends(get_current_user)) -> Any:
    db = dbmod.get_db()
    rows = db.select("requests")
    if user.role in (UserRole.counsel, UserRole.admin):
        return rows
    # Client: only requests whose fund belongs to their gestora.
    fund_ids = {f["id"] for f in db.select("funds", gestora_id=user.gestora_id)}
    return [r for r in rows if r["fund_id"] in fund_ids]


@router.get("/{request_id}", response_model=RequestOut)
async def get_request(request_id: str, user: User = Depends(get_current_user)) -> Any:
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    return row


# ---------------------------------------------------------------------------
# Exit A — "Me vale" (no counsel review; explicit acknowledgment required)
# ---------------------------------------------------------------------------

@router.post("/{request_id}/exit-a/acknowledge", response_model=RequestOut)
async def exit_a_acknowledge(
    request_id: str,
    body: ExitAAcknowledgeBody,
    http_request: Request,
    user: User = Depends(require_client),
) -> Any:
    """Record the explicit Exit A responsibility acknowledgment (guardrail 9)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.review_pending)

    if not body.acknowledged:
        raise HTTPException(status_code=422, detail=f"Debes aceptar: '{EXIT_A_CHECKBOX_TEXT}'")

    blockers = exit_a_blockers(db, row)
    if blockers:
        raise HTTPException(status_code=409, detail={"exit_a_blocked": blockers})

    row = db.update("requests", request_id, {"exit_a_acknowledged_at": now_iso()})
    audit.log_action(
        db,
        user=user,
        action=AuditAction.exit_a_acknowledged,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id,
        metadata={"checkbox_text": EXIT_A_CHECKBOX_TEXT},
        ip_address=_ip(http_request),
    )
    return row


@router.post("/{request_id}/exit-a/download")
async def exit_a_download(
    request_id: str,
    http_request: Request,
    user: User = Depends(require_client),
) -> Response:
    """Confirm & download (Exit A): delivers the draft, registers usage and
    creates a precedent CANDIDATE (status 'draft', pending admin activation)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.review_pending)

    if not row.get("exit_a_acknowledged_at"):
        raise HTTPException(status_code=409, detail="Exit A requires explicit acknowledgment first")
    blockers = exit_a_blockers(db, row)
    if blockers:
        raise HTTPException(status_code=409, detail={"exit_a_blocked": blockers})

    draft = latest_document(db, request_id, DocumentVersionType.draft)
    if draft is None:
        raise HTTPException(status_code=409, detail="No draft document available")
    data = storage.read(draft["file_path"])

    # The delivered draft becomes the 'final' version record.
    db.insert(
        "documents",
        {
            "request_id": request_id,
            "version_type": DocumentVersionType.final.value,
            "file_path": draft["file_path"],
            "precedent_version_id": draft.get("precedent_version_id"),
            "uploaded_by": None,
            "iteration": draft.get("iteration", 0),
        },
    )
    transition(db, row, RequestStatus.delivered)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.exit_a_downloaded,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id,
        metadata={"document_id": draft["id"], "acknowledged_at": row["exit_a_acknowledged_at"]},
        ip_address=_ip(http_request),
    )
    usage.record_usage(db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.exit_a)

    # Quality KPI (improvement #6): accepted as-is → similarity 1.0 (the
    # strongest quality signal). Once per request (UNIQUE on request_id);
    # a metric failure must NEVER block delivery.
    try:
        quality.record_exit_a_metric(db, request_row=row, gestora_id=gestora_id, draft_doc=draft)
    except Exception:  # noqa: BLE001 — metrics are best-effort by design
        logger.exception("Quality metric failed for request %s (delivery continues)", request_id)

    # Precedent candidate: NOT active until an admin approves (guardrail 8).
    precedent = db.insert(
        "precedents",
        {
            "gestora_id": gestora_id,
            "fund_id": row["fund_id"],
            "doc_type": row["doc_type"],
            "language": row.get("language") or "es",
            "source": PrecedentSource.validated_output.value,
        },
    )
    version = db.insert(
        "precedent_versions",
        {
            "precedent_id": precedent["id"],
            "version_number": 1,
            "file_path": draft["file_path"],
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
        gestora_id=gestora_id,
        metadata={"origin": "exit_a", "request_id": request_id, "pending_admin_activation": True},
        ip_address=_ip(http_request),
    )

    return Response(
        content=data,
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{request_id}-final.docx"'},
    )


# ---------------------------------------------------------------------------
# Exit B — counsel validation
# ---------------------------------------------------------------------------

@router.post("/{request_id}/exit-b", response_model=RequestOut)
async def exit_b_request_validation(
    request_id: str,
    http_request: Request,
    user: User = Depends(require_client),
) -> Any:
    """Solicitar Validación: routes the request to counsel and notifies them."""
    db = dbmod.get_db()
    settings = get_settings()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.review_pending)

    transition(db, row, RequestStatus.counsel_review)
    # SLA clock starts now (counsel response metrics + sweep, services/sla.py).
    row = db.update("requests", request_id, {"counsel_requested_at": now_iso()})
    audit.log_action(
        db,
        user=user,
        action=AuditAction.counsel_requested,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id,
        metadata={"doc_type": row["doc_type"], "requires_counsel": row.get("requires_counsel", False)},
        ip_address=_ip(http_request),
    )
    usage.record_usage(
        db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.exit_b_requested
    )

    fund = db.get("funds", row["fund_id"]) or {}
    deadline = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")
    # Session-free, expiring draft download for the email (improvement #9);
    # the platform review link stays alongside it.
    draft_download_url = signed_urls.signed_download_url(
        request_id, DocumentVersionType.draft.value
    )
    # Routing: gestora's PRIMARY assigned counsel -> backup -> broadcast.
    routing, recipients = resolve_counsel_recipients(db, gestora_id)
    recipient_emails = [u["email"] for u in recipients]
    for counsel_user in recipients:
        delivery = email_service.send_counsel_notification(
            counsel_name=counsel_user["email"].split("@")[0],
            counsel_email=counsel_user["email"],
            fund_name=fund.get("name", ""),
            doc_type=_effective_doc_type(row),
            requested_by=user.email,
            review_url=f"{settings.frontend_url}/review/{request_id}",
            suggested_deadline=deadline,
            signed_download_url=draft_download_url,
        )
        audit.log_action(
            db,
            user=user,
            action=AuditAction.counsel_notified,
            resource_type=AuditResourceType.request,
            resource_id=request_id,
            gestora_id=gestora_id,
            metadata={
                "to": counsel_user["email"],
                "delivery": delivery.get("delivery"),
                "routing": routing,
                "recipients": recipient_emails,
            },
            ip_address=_ip(http_request),
        )
    return row


@router.post("/{request_id}/review/start", response_model=RequestOut)
async def counsel_review_start(
    request_id: str,
    http_request: Request,
    user: User = Depends(require_counsel),
) -> Any:
    """Counsel opens the review (audit marker; no status change)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.counsel_review)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.counsel_review_started,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id,
        metadata={"doc_type": row["doc_type"]},
        ip_address=_ip(http_request),
    )
    return row


@router.post("/{request_id}/validate", response_model=RequestOut)
async def counsel_validate(
    request_id: str,
    http_request: Request,
    user: User = Depends(require_counsel),
) -> Any:
    """Validar y Entregar: counsel approves; the validated document enters the
    precedent library AUTOMATICALLY as an active version (guardrail 8 exception)."""
    db = dbmod.get_db()
    settings = get_settings()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    require_status(row, RequestStatus.counsel_review)

    # Final = latest counsel edit if any, else the AI draft.
    source_doc = latest_document(db, request_id, DocumentVersionType.counsel_edit) or latest_document(
        db, request_id, DocumentVersionType.draft
    )
    if source_doc is None:
        raise HTTPException(status_code=409, detail="No document available to validate")

    final_doc = db.insert(
        "documents",
        {
            "request_id": request_id,
            "version_type": DocumentVersionType.final.value,
            "file_path": source_doc["file_path"],
            "precedent_version_id": source_doc.get("precedent_version_id"),
            "uploaded_by": user.id,
            "iteration": source_doc.get("iteration", 0),
        },
    )
    transition(db, row, RequestStatus.validated)
    # SLA clock stops now (counsel response metrics, services/sla.py).
    row = db.update("requests", request_id, {"counsel_validated_at": now_iso()})

    # Quality KPI (improvement #6): how much did counsel change the AI draft?
    # A metric failure must NEVER block validation.
    try:
        quality.record_exit_b_metric(
            db,
            request_row=row,
            gestora_id=gestora_id,
            draft_doc=latest_document(db, request_id, DocumentVersionType.draft),
            final_doc_path=source_doc["file_path"],
        )
    except Exception:  # noqa: BLE001 — metrics are best-effort by design
        logger.exception("Quality metric failed for request %s (validation continues)", request_id)

    audit.log_action(
        db,
        user=user,
        action=AuditAction.document_validated,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id,
        metadata={"final_document_id": final_doc["id"], "from_document_id": source_doc["id"]},
        ip_address=_ip(http_request),
    )
    usage.record_usage(
        db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.exit_b_validated
    )

    # Counsel-validated output enters the precedent library automatically (ACTIVE).
    precedent = db.insert(
        "precedents",
        {
            "gestora_id": gestora_id,
            "fund_id": row["fund_id"],
            "doc_type": row["doc_type"],
            "language": row.get("language") or "es",
            "source": PrecedentSource.validated_output.value,
        },
    )
    version = db.insert(
        "precedent_versions",
        {
            "precedent_id": precedent["id"],
            "version_number": 1,
            "file_path": source_doc["file_path"],
            "status": PrecedentVersionStatus.active.value,
            "rag_weight": 1.0,
            "activated_at": now_iso(),
            "created_by": user.id,
        },
    )
    for action, metadata in (
        (AuditAction.precedent_version_created, {"origin": "counsel_validation", "request_id": request_id}),
        (AuditAction.precedent_activated, {"automatic": True, "reason": "counsel_validated"}),
    ):
        audit.log_action(
            db,
            user=user,
            action=action,
            resource_type=AuditResourceType.precedent_version,
            resource_id=version["id"],
            gestora_id=gestora_id,
            metadata=metadata,
            ip_address=_ip(http_request),
        )
    rag.reindex_gestora(gestora_id)

    # Notify the client that the validated document is ready.
    client_user = db.get("users", row["user_id"]) or {}
    fund = db.get("funds", row["fund_id"]) or {}
    if client_user.get("email"):
        email_service.send_client_ready(
            client_name=client_user["email"].split("@")[0],
            client_email=client_user["email"],
            doc_type=_effective_doc_type(row),
            fund_name=fund.get("name", ""),
            download_url=f"{settings.frontend_url}/requests/{request_id}/download/final",
            validated_by_counsel=user.email,
            # Session-free, expiring direct download (improvement #9).
            signed_download_url=signed_urls.signed_download_url(
                request_id, DocumentVersionType.final.value
            ),
        )
    return row
