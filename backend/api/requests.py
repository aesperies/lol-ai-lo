"""Request lifecycle endpoints: intake, parse, confirm, Exit A/B, counsel flow."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api import (
    client_ip,
    DOCX_MEDIA_TYPE,
    exit_a_blockers,
    get_request_or_404,
    latest_document,
    now_iso,
    require_status,
    transition,
)
from services.counsel_routing import resolve_counsel_recipients
from auth import (
    assert_request_access,
    assert_request_owner,
    get_current_user,
    is_request_owner,
    request_is_shared_with,
    require_client,
    require_counsel,
)
from config import get_settings
from models import doc_fields
from models.doc_branches import branch_for
from models.schema import (
    EXIT_A_CHECKBOX_TEXT,
    AuditAction,
    AuditResourceType,
    ConfirmParamsBody,
    DocumentVersionType,
    ExitAAcknowledgeBody,
    GenerationReviewOut,
    VerificationOut,
    RequestBranchOut,
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
    delivery,
    email_service,
    intake_parser,
    notifications,
    quality,
    signed_urls,
    storage,
    usage,
)
from services.rate_limit import rate_limit

router = APIRouter(prefix="/api/requests", tags=["requests"])

logger = logging.getLogger("lolailo.requests")



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

    # SPV/vehículo opcional: debe existir Y pertenecer al fondo indicado
    # (015_vehicles.sql). Mismo patrón 404-no-leak que el fondo.
    if body.vehicle_id:
        vehicle = db.get("vehicles", body.vehicle_id)
        if vehicle is None or vehicle["fund_id"] != body.fund_id:
            raise HTTPException(status_code=404, detail="Vehicle not found")

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
            "vehicle_id": body.vehicle_id,
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
        ip_address=client_ip(http_request),
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
    assert_request_owner(db, user, row)
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
    gestora_id = assert_request_owner(db, user, row)
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
            ip_address=client_ip(http_request),
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
        ip_address=client_ip(http_request),
    )
    return row


# ---------------------------------------------------------------------------
# Listing / detail (gestora-siloed for clients)
# ---------------------------------------------------------------------------

def _vehicle_name(db: dbmod.Database, row: dict[str, Any]) -> dict[str, Any]:
    """Display enrichment (015): the vehicle's name, mirroring _fund_name."""
    vehicle = db.get("vehicles", row["vehicle_id"]) if row.get("vehicle_id") else None
    return {"vehicle_name": (vehicle or {}).get("name")}


def _fund_name(db: dbmod.Database, row: dict[str, Any]) -> dict[str, Any]:
    """Display enrichment: the request's fund name (never a bare UUID in the UI)."""
    fund = db.get("funds", row["fund_id"]) if row.get("fund_id") else None
    return {"fund_name": (fund or {}).get("name")}


def _request_flags(db: dbmod.Database, user: User, row: dict[str, Any]) -> dict[str, Any]:
    """Per-caller is_owner / shared_with_me / shared_by_email flags for a request.

    Collaboration (012_collaboration.sql): lets the UI distinguish "mine" from
    "shared with me" and hide owner-only actions. None for counsel/admin
    (cross-gestora by role; not part of the sharing model)."""
    if user.role in (UserRole.counsel, UserRole.admin):
        return {"is_owner": None, "shared_with_me": None, "shared_by_email": None}
    owner = is_request_owner(user, row)
    shared = (not owner) and request_is_shared_with(db, row["id"], user)
    shared_by_email = None
    if shared:
        owner_row = db.get("users", row.get("user_id")) if row.get("user_id") else None
        shared_by_email = (owner_row or {}).get("email")
    return {"is_owner": owner, "shared_with_me": shared, "shared_by_email": shared_by_email}


@router.get("", response_model=list[RequestOut])
async def list_requests(user: User = Depends(get_current_user)) -> Any:
    """List requests. Counsel/admin see all (cross-gestora). A client sees their
    own gestora's requests PLUS any request shared WITH them (collaboration);
    each row is flagged is_owner / shared_with_me so the UI can show a
    "Compartido contigo" badge and hide owner-only actions."""
    db = dbmod.get_db()
    rows = db.unscoped_select("requests")
    if user.role in (UserRole.counsel, UserRole.admin):
        return [{**r, **_fund_name(db, r), **_vehicle_name(db, r)} for r in rows]
    # Client: requests they OWN, plus requests a same-gestora colleague SHARED
    # with them (collaboration). A request is private to its owner otherwise.
    fund_ids = {f["id"] for f in db.select("funds", gestora_id=user.gestora_id)}
    shared_ids = {
        s["request_id"]
        for s in db.select("request_shares", shared_with_user_id=user.id)
        if s.get("gestora_id") == user.gestora_id
    }
    visible = [
        r
        for r in rows
        if r["fund_id"] in fund_ids
        and (is_request_owner(user, r) or r["id"] in shared_ids)
    ]
    return [{**r, **_request_flags(db, user, r), **_fund_name(db, r), **_vehicle_name(db, r)} for r in visible]


@router.get("/{request_id}", response_model=RequestOut)
async def get_request(request_id: str, user: User = Depends(get_current_user)) -> Any:
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    return {**row, **_request_flags(db, user, row), **_fund_name(db, row), **_vehicle_name(db, row)}


@router.get("/{request_id}/branch", response_model=RequestBranchOut)
async def get_request_branch(
    request_id: str, user: User = Depends(get_current_user)
) -> Any:
    """The specialized drafting branch used for this request (Feature 1).

    Derived from the request's effective doc_type via doc_branches.branch_for,
    so the UI can show which agent drafted it. Same gestora-isolation 404 as
    the other request endpoints."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    doc_type = _effective_doc_type(row)
    return RequestBranchOut(doc_type=doc_type, branch=branch_for(doc_type).value)


@router.get("/{request_id}/reviews", response_model=list[GenerationReviewOut])
async def get_request_reviews(
    request_id: str, user: User = Depends(get_current_user)
) -> Any:
    """The critic review trail for a request (Feature 2), one entry per round.

    Read-only; same gestora-isolation 404 + access rules as the other request
    endpoints (client only on own gestora; counsel/admin cross-gestora). When
    the critic was skipped (LLM unreachable / disabled) the list is empty."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    rounds = db.select("generation_reviews", request_id=request_id)
    rounds.sort(key=lambda r: r.get("round") or 0)
    return [
        GenerationReviewOut(
            round=r.get("round", 0),
            approved=bool(r.get("approved")),
            issues=r.get("issues") or [],
            created_at=r.get("created_at"),
        )
        for r in rounds
    ]


@router.get("/{request_id}/verifications", response_model=list[VerificationOut])
async def get_request_verifications(
    request_id: str, user: User = Depends(get_current_user)
) -> Any:
    """El rastro del verificador cruzado (020), una entrada por iteración.

    Solo lectura; mismas reglas de acceso 404-no-leak que el resto de
    endpoints de la solicitud. Lista vacía si el verificador está desactivado
    o la solicitud es anterior a la feature."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    rows = db.select("verifications", request_id=request_id)
    return [
        VerificationOut(
            iteration=r.get("iteration", 0),
            provider=r.get("provider"),
            model=r.get("model"),
            findings=r.get("findings") or [],
            critical_count=r.get("critical_count", 0),
            forced_counsel=bool(r.get("forced_counsel")),
            created_at=r.get("created_at"),
        )
        for r in rows
    ]


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
    gestora_id = assert_request_owner(db, user, row)
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
        ip_address=client_ip(http_request),
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
    gestora_id = assert_request_owner(db, user, row)
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
    delivery.create_final_document(db, request_id=request_id, source_doc=draft, uploaded_by=None)
    transition(db, row, RequestStatus.delivered)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.exit_a_downloaded,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id,
        metadata={"document_id": draft["id"], "acknowledged_at": row["exit_a_acknowledged_at"]},
        ip_address=client_ip(http_request),
    )
    usage.record_usage(db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.exit_a)

    # Quality KPI (improvement #6): accepted as-is → similarity 1.0, once per
    # request. Learning (Feature 3): accepted-as-is is a strong positive
    # signal (final ≈ draft, usually a no-op). Both best-effort — a failure
    # NEVER blocks delivery (services/delivery.py).
    delivery.best_effort(
        "Quality metric",
        request_id,
        lambda: quality.record_exit_a_metric(
            db, request_row=row, gestora_id=gestora_id, draft_doc=draft
        ),
    )
    delivery.enqueue_lessons(
        db,
        gestora_id=gestora_id,
        doc_type=row["doc_type"],
        request_id=request_id,
        ai_draft_path=draft["file_path"],
        final_path=draft["file_path"],
    )

    # Precedent CANDIDATE: not active until an admin approves (guardrail 8).
    delivery.register_precedent(
        db,
        user=user,
        gestora_id=gestora_id,
        request_row=row,
        file_path=draft["file_path"],
        origin="exit_a",
        activate=False,
        ip_address=client_ip(http_request),
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
    gestora_id = assert_request_owner(db, user, row)
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
        ip_address=client_ip(http_request),
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
        notifications.notify(
            db,
            user_id=counsel_user["id"],
            kind=notifications.KIND_COUNSEL_REQUESTED,
            title=f"Nueva validación pendiente: {_effective_doc_type(row)}",
            body=f"{fund.get('name', '')} — solicitada por {user.email}",
            request_id=request_id,
            gestora_id=gestora_id,
        )
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
            ip_address=client_ip(http_request),
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
        ip_address=client_ip(http_request),
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

    final_doc = delivery.create_final_document(
        db, request_id=request_id, source_doc=source_doc, uploaded_by=user.id
    )
    transition(db, row, RequestStatus.validated)
    # SLA clock stops now (counsel response metrics, services/sla.py).
    row = db.update("requests", request_id, {"counsel_validated_at": now_iso()})

    # Quality KPI (improvement #6): how much did counsel change the AI draft?
    # Learning (Feature 3): distill gestora-siloed lessons from the AI draft
    # vs. the counsel-validated final. Both best-effort — a failure NEVER
    # blocks validation (services/delivery.py).
    draft_doc = latest_document(db, request_id, DocumentVersionType.draft)
    delivery.best_effort(
        "Quality metric",
        request_id,
        lambda: quality.record_exit_b_metric(
            db,
            request_row=row,
            gestora_id=gestora_id,
            draft_doc=draft_doc,
            final_doc_path=source_doc["file_path"],
        ),
    )
    delivery.enqueue_lessons(
        db,
        gestora_id=gestora_id,
        doc_type=row["doc_type"],
        request_id=request_id,
        ai_draft_path=draft_doc["file_path"] if draft_doc else None,
        final_path=source_doc["file_path"],
    )

    audit.log_action(
        db,
        user=user,
        action=AuditAction.document_validated,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id,
        metadata={"final_document_id": final_doc["id"], "from_document_id": source_doc["id"]},
        ip_address=client_ip(http_request),
    )
    usage.record_usage(
        db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.exit_b_validated
    )

    # Counsel-validated output enters the precedent library automatically
    # (ACTIVE, guardrail 8 exception) and the gestora's RAG index refreshes.
    delivery.register_precedent(
        db,
        user=user,
        gestora_id=gestora_id,
        request_row=row,
        file_path=source_doc["file_path"],
        origin="counsel_validation",
        activate=True,
        ip_address=client_ip(http_request),
    )

    # Notify the client that the validated document is ready.
    notifications.notify(
        db,
        user_id=row["user_id"],
        kind=notifications.KIND_DOCUMENT_VALIDATED,
        title=f"Documento validado: {_effective_doc_type(row)}",
        body=f"Validado por {user.email}. Ya puedes descargar la versión final.",
        request_id=request_id,
        gestora_id=gestora_id,
    )
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
