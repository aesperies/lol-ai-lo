"""Account & security endpoints (011_account_security.sql).

Feature A — MFA status mirror: ``POST /api/me/mfa`` reflects the user's Supabase
TOTP status onto ``users.mfa_enabled`` (Supabase Auth enforces the real factor);
``GET /api/me`` exposes the profile incl. ``mfa_enabled``.

Feature B — GDPR data-subject rights (RGPD arts. 15/17):
``GET /api/me/export`` (the requesting user's own data, as a downloadable JSON
file), ``POST /api/me/delete`` (self-service erasure/anonymisation, confirmation
required), and the admin-triggered ``POST /api/admin/users/{id}/delete``.

Every action is audited. The append-only ``audit_log`` is NEVER scrubbed/erased
(guardrail 11 / immutable legal evidence) — see services/data_subject.py.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from api import client_ip
from auth import get_current_user, require_admin
from models.schema import (
    DATA_DELETE_CONFIRMATION,
    AuditAction,
    AuditResourceType,
    DataDeleteBody,
    MfaStatusBody,
    User,
    UserProfileOut,
)
from services import audit, data_subject, db as dbmod

logger = logging.getLogger("lolailo.account")

router = APIRouter(prefix="/api", tags=["account"])



# ---------------------------------------------------------------------------
# Profile + MFA status mirror (Feature A)
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserProfileOut)
async def get_me(user: User = Depends(get_current_user)) -> Any:
    """The calling user's own profile (incl. mfa_enabled)."""
    db = dbmod.get_db()
    row = db.get("users", user.id) or {}
    return UserProfileOut(
        id=user.id,
        email=user.email,
        role=user.role,
        gestora_id=user.gestora_id,
        mfa_enabled=bool(row.get("mfa_enabled", False)),
        created_at=row.get("created_at"),
    )


@router.post("/me/mfa", response_model=UserProfileOut)
async def set_my_mfa(
    body: MfaStatusBody,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Mirror the user's Supabase TOTP status onto users.mfa_enabled.

    Called by the client after a successful Supabase enroll-verify (enabled=true)
    or unenroll (enabled=false). The platform does not store the TOTP secret;
    Supabase remains the authority that enforces the factor.
    """
    db = dbmod.get_db()
    previous = bool((db.get("users", user.id) or {}).get("mfa_enabled", False))
    db.update("users", user.id, {"mfa_enabled": body.enabled})
    audit.log_action(
        db,
        user=user,
        action=AuditAction.mfa_status_changed,
        resource_type=AuditResourceType.user,
        resource_id=user.id,
        gestora_id=user.gestora_id,
        metadata={"enabled": body.enabled, "previous": previous},
        ip_address=client_ip(http_request),
    )
    row = db.get("users", user.id) or {}
    return UserProfileOut(
        id=user.id,
        email=user.email,
        role=user.role,
        gestora_id=user.gestora_id,
        mfa_enabled=bool(row.get("mfa_enabled", False)),
        created_at=row.get("created_at"),
    )


# ---------------------------------------------------------------------------
# GDPR data-subject rights (Feature B)
# ---------------------------------------------------------------------------

@router.get("/me/export")
async def export_my_data(
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """Download the requesting user's own data as a JSON file (Art. 15/20).

    Strictly the caller's own data — never another gestora's (isolation).
    """
    db = dbmod.get_db()
    bundle = data_subject.export_user_data(db, user.id)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.data_exported,
        resource_type=AuditResourceType.user,
        resource_id=user.id,
        gestora_id=user.gestora_id,
        metadata={
            "requests": len(bundle.get("requests", [])),
            "documents": len(bundle.get("documents", [])),
            "tabular_reviews": len(bundle.get("tabular_reviews", [])),
        },
        ip_address=client_ip(http_request),
    )
    payload = json.dumps(bundle, ensure_ascii=False, indent=2, default=str)
    return Response(
        content=payload,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="lolailo-export-{user.id}.json"'
        },
    )


@router.post("/me/delete")
async def delete_my_data(
    body: DataDeleteBody,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Self-service erasure/anonymisation (Art. 17). Confirmation required.

    ``mode`` = 'anonymize' (default, scrub PII keep tombstones) or 'erase'
    (delete the user's own requests/documents/reviews + files). audit_log is
    never touched.
    """
    if body.confirm != DATA_DELETE_CONFIRMATION:
        raise HTTPException(
            status_code=422,
            detail=f"Confirmation required: send confirm='{DATA_DELETE_CONFIRMATION}'.",
        )
    db = dbmod.get_db()
    counts = data_subject.delete_user_data(db, user.id, mode=body.mode)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.data_subject_deleted,
        resource_type=AuditResourceType.user,
        resource_id=user.id,
        gestora_id=user.gestora_id,
        metadata={"mode": body.mode, "self_service": True, **counts},
        ip_address=client_ip(http_request),
    )
    return counts


@router.post("/admin/users/{user_id}/delete")
async def admin_delete_user_data(
    user_id: str,
    body: DataDeleteBody,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Admin-triggered erasure/anonymisation for a user (Art. 17). Confirmation
    required; audit_log is never touched."""
    if body.confirm != DATA_DELETE_CONFIRMATION:
        raise HTTPException(
            status_code=422,
            detail=f"Confirmation required: send confirm='{DATA_DELETE_CONFIRMATION}'.",
        )
    db = dbmod.get_db()
    subject = db.get("users", user_id)
    if subject is None:
        raise HTTPException(status_code=404, detail="User not found")
    counts = data_subject.delete_user_data(db, user_id, mode=body.mode)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.data_subject_deleted,
        resource_type=AuditResourceType.user,
        resource_id=user_id,
        gestora_id=subject.get("gestora_id"),
        metadata={"mode": body.mode, "self_service": False, "subject_id": user_id, **counts},
        ip_address=client_ip(http_request),
    )
    return counts
