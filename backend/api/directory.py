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
    FundCreate,
    FundUpdate,
    Gestora,
    GestoraCreate,
    User,
    UserInviteBody,
    UserProfileOut,
    Vehicle,
    VehicleCreate,
    VehicleUpdate,
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


@router.post("/funds", response_model=Fund, status_code=201)
async def create_fund(
    body: FundCreate,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Register a fund/vehicle. A client creates it in their OWN gestora —
    naming a foreign gestora is rejected (isolation); admin must say which
    gestora. Counsel cannot create funds (read-only actor for the directory).
    """
    db = dbmod.get_db()
    if user.role == UserRole.counsel:
        raise HTTPException(status_code=403, detail="Counsel cannot create funds")
    if user.role == UserRole.client:
        if user.gestora_id is None:
            raise HTTPException(status_code=403, detail="Client user has no gestora")
        if body.gestora_id and body.gestora_id != user.gestora_id:
            raise HTTPException(
                status_code=403,
                detail="Solo puedes crear fondos en tu propia gestora.",
            )
        gestora_id = user.gestora_id
    else:  # admin
        if not body.gestora_id:
            raise HTTPException(status_code=422, detail="gestora_id is required")
        gestora_id = body.gestora_id
    if db.get("gestoras", gestora_id) is None:
        raise HTTPException(status_code=404, detail="Gestora not found")

    row = db.insert(
        "funds",
        {
            "gestora_id": gestora_id,
            "name": body.name.strip(),
            "jurisdiction": body.jurisdiction.strip(),
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.fund_created,
        resource_type=AuditResourceType.fund,
        resource_id=row["id"],
        gestora_id=gestora_id,
        metadata={"name": row["name"], "jurisdiction": row["jurisdiction"]},
        ip_address=client_ip(http_request),
    )
    return row


def _fund_for_user_or_404(db: dbmod.Database, user: User, fund_id: str) -> dict[str, Any]:
    """404-no-leak access to a fund: clients only within their own gestora;
    admin cross-gestora; counsel read-only (mutations rejected at each endpoint)."""
    fund = db.get("funds", fund_id)
    if fund is None:
        raise HTTPException(status_code=404, detail="Fund not found")
    if user.role == UserRole.client and fund["gestora_id"] != user.gestora_id:
        raise HTTPException(status_code=404, detail="Fund not found")
    return fund


def _require_fund_mutator(user: User) -> None:
    if user.role == UserRole.counsel:
        raise HTTPException(status_code=403, detail="Counsel cannot manage funds")


@router.patch("/funds/{fund_id}", response_model=Fund)
async def update_fund(
    fund_id: str,
    body: FundUpdate,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Rename / re-jurisdiction a fund (client within own gestora, or admin)."""
    db = dbmod.get_db()
    _require_fund_mutator(user)
    fund = _fund_for_user_or_404(db, user, fund_id)
    fields = {k: v.strip() for k, v in (("name", body.name), ("jurisdiction", body.jurisdiction)) if v}
    if not fields:
        return fund
    row = db.update("funds", fund_id, fields)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.fund_updated,
        resource_type=AuditResourceType.fund,
        resource_id=fund_id,
        gestora_id=fund["gestora_id"],
        metadata=fields,
        ip_address=client_ip(http_request),
    )
    return row


@router.delete("/funds/{fund_id}", status_code=204)
async def delete_fund(
    fund_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Delete a fund. Refused (409) while any request references it — the
    request/document history is immutable evidence and must never be orphaned.
    Its vehicles are deleted with it (they only exist within the fund)."""
    db = dbmod.get_db()
    _require_fund_mutator(user)
    fund = _fund_for_user_or_404(db, user, fund_id)
    if db.select("requests", fund_id=fund_id):
        raise HTTPException(
            status_code=409,
            detail="El fondo tiene solicitudes asociadas y no puede eliminarse.",
        )
    for vehicle in db.select("vehicles", fund_id=fund_id):
        db.delete("vehicles", vehicle["id"])
    db.delete("funds", fund_id)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.fund_deleted,
        resource_type=AuditResourceType.fund,
        resource_id=fund_id,
        gestora_id=fund["gestora_id"],
        metadata={"name": fund.get("name")},
        ip_address=client_ip(http_request),
    )


@router.get("/funds/{fund_id}/vehicles", response_model=list[Vehicle])
async def list_vehicles(
    fund_id: str,
    user: User = Depends(get_current_user),
) -> Any:
    """The fund's SPVs/vehicles (isolation inherited from the fund)."""
    db = dbmod.get_db()
    _fund_for_user_or_404(db, user, fund_id)
    return db.select("vehicles", fund_id=fund_id)


@router.post("/funds/{fund_id}/vehicles", response_model=Vehicle, status_code=201)
async def create_vehicle(
    fund_id: str,
    body: VehicleCreate,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Register an SPV/vehicle under a fund (client in own gestora, or admin)."""
    db = dbmod.get_db()
    _require_fund_mutator(user)
    fund = _fund_for_user_or_404(db, user, fund_id)
    row = db.insert(
        "vehicles",
        {
            "fund_id": fund_id,
            "name": body.name.strip(),
            "vehicle_type": body.vehicle_type,
            "jurisdiction": body.jurisdiction.strip() if body.jurisdiction else None,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.vehicle_created,
        resource_type=AuditResourceType.vehicle,
        resource_id=row["id"],
        gestora_id=fund["gestora_id"],
        metadata={"fund_id": fund_id, "name": row["name"], "vehicle_type": row["vehicle_type"]},
        ip_address=client_ip(http_request),
    )
    return row


def _vehicle_for_user_or_404(
    db: dbmod.Database, user: User, vehicle_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    vehicle = db.get("vehicles", vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    fund = _fund_for_user_or_404(db, user, vehicle["fund_id"])
    return vehicle, fund


@router.patch("/vehicles/{vehicle_id}", response_model=Vehicle)
async def update_vehicle(
    vehicle_id: str,
    body: VehicleUpdate,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    db = dbmod.get_db()
    _require_fund_mutator(user)
    vehicle, fund = _vehicle_for_user_or_404(db, user, vehicle_id)
    fields: dict[str, Any] = {}
    if body.name:
        fields["name"] = body.name.strip()
    if body.vehicle_type:
        fields["vehicle_type"] = body.vehicle_type
    if body.jurisdiction is not None:
        fields["jurisdiction"] = body.jurisdiction.strip() or None
    if not fields:
        return vehicle
    row = db.update("vehicles", vehicle_id, fields)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.vehicle_updated,
        resource_type=AuditResourceType.vehicle,
        resource_id=vehicle_id,
        gestora_id=fund["gestora_id"],
        metadata=fields,
        ip_address=client_ip(http_request),
    )
    return row


@router.delete("/vehicles/{vehicle_id}", status_code=204)
async def delete_vehicle(
    vehicle_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> None:
    """Delete a vehicle. Refused (409) while any request references it."""
    db = dbmod.get_db()
    _require_fund_mutator(user)
    vehicle, fund = _vehicle_for_user_or_404(db, user, vehicle_id)
    if db.select("requests", vehicle_id=vehicle_id):
        raise HTTPException(
            status_code=409,
            detail="El vehículo tiene solicitudes asociadas y no puede eliminarse.",
        )
    db.delete("vehicles", vehicle_id)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.vehicle_deleted,
        resource_type=AuditResourceType.vehicle,
        resource_id=vehicle_id,
        gestora_id=fund["gestora_id"],
        metadata={"fund_id": vehicle["fund_id"], "name": vehicle.get("name")},
        ip_address=client_ip(http_request),
    )


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
