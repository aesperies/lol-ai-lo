"""Notification endpoints: (re)send counsel review and client-ready emails."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from api import get_request_or_404
from auth import assert_request_access, get_current_user, require_counsel_or_admin
from config import get_settings
from models.schema import (
    AuditAction,
    AuditResourceType,
    RequestStatus,
    User,
    UserRole,
)
from services import audit, db as dbmod, email_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _ip(http_request: Request) -> Optional[str]:
    return http_request.client.host if http_request.client else None


@router.post("/requests/{request_id}/counsel")
async def notify_counsel(
    request_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """(Re)send the review-pending email to all counsel users."""
    db = dbmod.get_db()
    settings = get_settings()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    if row["status"] != RequestStatus.counsel_review.value:
        raise HTTPException(status_code=409, detail="Request is not in counsel review")

    fund = db.get("funds", row["fund_id"]) or {}
    requester = db.get("users", row["user_id"]) or {}
    deadline = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d")

    deliveries: list[dict[str, Any]] = []
    for counsel_user in db.select("users", role=UserRole.counsel.value):
        delivery = email_service.send_counsel_notification(
            counsel_name=counsel_user["email"].split("@")[0],
            counsel_email=counsel_user["email"],
            fund_name=fund.get("name", ""),
            doc_type=row["doc_type"],
            requested_by=requester.get("email", ""),
            review_url=f"{settings.frontend_url}/review/{request_id}",
            suggested_deadline=deadline,
        )
        deliveries.append(delivery)
        audit.log_action(
            db,
            user=user,
            action=AuditAction.counsel_notified,
            resource_type=AuditResourceType.request,
            resource_id=request_id,
            gestora_id=gestora_id,
            metadata={"to": counsel_user["email"], "delivery": delivery.get("delivery")},
            ip_address=_ip(http_request),
        )
    return {"sent": len(deliveries), "deliveries": deliveries}


@router.post("/requests/{request_id}/client-ready")
async def notify_client_ready(
    request_id: str,
    http_request: Request,
    user: User = Depends(require_counsel_or_admin),
) -> Any:
    """(Re)send the document-ready email to the requesting client."""
    db = dbmod.get_db()
    settings = get_settings()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    if row["status"] not in (RequestStatus.validated.value, RequestStatus.delivered.value):
        raise HTTPException(status_code=409, detail="Document is not ready for delivery")

    client_user = db.get("users", row["user_id"])
    if client_user is None:
        raise HTTPException(status_code=404, detail="Requesting user not found")
    fund = db.get("funds", row["fund_id"]) or {}

    # Exit B requests (no Exit A acknowledgment) carry the validated-by line.
    validated_by = None
    if not row.get("exit_a_acknowledged_at"):
        validated_by = user.email if user.role == UserRole.counsel else "Lol-AI-lo Legal SLP"

    delivery = email_service.send_client_ready(
        client_name=client_user["email"].split("@")[0],
        client_email=client_user["email"],
        doc_type=row["doc_type"],
        fund_name=fund.get("name", ""),
        download_url=f"{settings.frontend_url}/requests/{request_id}/download/final",
        validated_by_counsel=validated_by,
    )
    return {"delivery": delivery}
