"""Platform directory endpoints: gestoras, funds and users.

Backs the admin consoles (gestoras/users/model-config/precedents pickers) and
the client intake (fund selector). Listing is role-scoped: a client only ever
sees their own gestora and its funds; counsel/admin are cross-gestora by role
(SPEC actor matrix). Creation endpoints are admin-only and audited.

User provisioning (POST /api/users) follows the platform rule that signup does
NOT provision ``public.users``: in Supabase mode the user is invited through
Supabase Auth (so the row id equals the auth id) and the row is inserted here;
in dev-stub mode the row is simply inserted with a generated id.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from api import client_ip
from auth import get_current_user, require_admin
from config import get_settings
from models.schema import (
    AuditAction,
    AuditResourceType,
    Fund,
    Gestora,
    GestoraCreate,
    User,
    UserInviteBody,
    UserProfileOut,
    UserRole,
)
from services import audit, db as dbmod

logger = logging.getLogger("lolailo.directory")

router = APIRouter(prefix="/api", tags=["directory"])


@router.get("/gestoras", response_model=list[Gestora])
async def list_gestoras(user: User = Depends(get_current_user)) -> Any:
    """List gestoras. Admin/counsel see all; a client only their own."""
    db = dbmod.get_db()
    if user.role in (UserRole.admin, UserRole.counsel):
        return db.unscoped_select("gestoras")
    if user.gestora_id is None:
        return []
    row = db.get("gestoras", user.gestora_id)
    return [row] if row else []


@router.post("/gestoras", response_model=Gestora, status_code=201)
async def create_gestora(
    body: GestoraCreate,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Admin onboards a new gestora (its silo starts empty)."""
    db = dbmod.get_db()
    row = db.insert(
        "gestoras",
        {
            "name": body.name,
            "subscription_tier": body.subscription_tier.value,
            "billing_email": body.billing_email,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.gestora_created,
        resource_type=AuditResourceType.gestora,
        resource_id=row["id"],
        gestora_id=row["id"],
        metadata={"name": body.name, "subscription_tier": body.subscription_tier.value},
        ip_address=client_ip(http_request),
    )
    return row


@router.get("/funds", response_model=list[Fund])
async def list_funds(
    gestora_id: Optional[str] = None,
    user: User = Depends(get_current_user),
) -> Any:
    """List funds. Clients only their own gestora's; the gestora_id query
    param is honoured for admin/counsel only."""
    db = dbmod.get_db()
    if user.role in (UserRole.admin, UserRole.counsel):
        if gestora_id:
            return db.select("funds", gestora_id=gestora_id)
        return db.unscoped_select("funds")
    if user.gestora_id is None:
        return []
    return db.select("funds", gestora_id=user.gestora_id)


@router.get("/users", response_model=list[UserProfileOut])
async def list_users(user: User = Depends(require_admin)) -> Any:
    """Admin: the platform user roster (id/email/role/gestora/MFA mirror)."""
    db = dbmod.get_db()
    return db.unscoped_select("users")


def _invite_supabase_auth_user(email: str, role: str, gestora_id: Optional[str]) -> str:
    """Invite ``email`` through Supabase Auth and return the new auth user id.

    The role (and gestora for clients) is stamped on ``app_metadata`` because
    the frontend middleware and session provider read the role from there.
    Raises HTTPException 502 when the invite cannot be delivered — the users
    row must never exist with an id that does not match an auth identity."""
    settings = get_settings()
    try:
        from supabase import create_client  # type: ignore[import-not-found]
    except ImportError:
        raise HTTPException(status_code=503, detail="supabase package not installed")
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        res = client.auth.admin.invite_user_by_email(email)
        if not res or not res.user:
            raise ValueError("Supabase invite returned no user")
        app_metadata: dict[str, Any] = {"role": role}
        if gestora_id:
            app_metadata["gestora_id"] = gestora_id
        client.auth.admin.update_user_by_id(res.user.id, {"app_metadata": app_metadata})
    except HTTPException:
        raise
    except Exception as exc:  # supabase-py raises provider-specific errors
        logger.warning("Supabase invite failed for %s: %s", email, exc)
        raise HTTPException(status_code=502, detail=f"Supabase invite failed: {exc}")
    return res.user.id


@router.post("/users", response_model=UserProfileOut, status_code=201)
async def invite_user(
    body: UserInviteBody,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Admin provisions a platform user (and, in Supabase mode, sends the
    Supabase Auth invite email so the auth identity exists with the same id).
    Mirrors the DB constraint: a client MUST belong to an existing gestora."""
    db = dbmod.get_db()
    if body.role == UserRole.client and not body.gestora_id:
        raise HTTPException(status_code=422, detail="A client user requires gestora_id")
    if body.gestora_id and db.get("gestoras", body.gestora_id) is None:
        raise HTTPException(status_code=404, detail="Gestora not found")
    email = body.email.strip().lower()
    if any(u.get("email") == email for u in db.unscoped_select("users")):
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    settings = get_settings()
    fields: dict[str, Any] = {
        "email": email,
        "role": body.role.value,
        # Admin/counsel are cross-gestora (NULL) even if a gestora was sent.
        "gestora_id": body.gestora_id if body.role == UserRole.client else None,
    }
    if not settings.dev_auth_stub:
        # Supabase mode: the users row id MUST equal the Supabase Auth id.
        fields["id"] = _invite_supabase_auth_user(
            email, body.role.value, fields["gestora_id"]
        )
    row = db.insert("users", fields)

    audit.log_action(
        db,
        user=user,
        action=AuditAction.user_invited,
        resource_type=AuditResourceType.user,
        resource_id=row["id"],
        gestora_id=row.get("gestora_id"),
        metadata={"email": email, "role": body.role.value},
        ip_address=client_ip(http_request),
    )
    return row
