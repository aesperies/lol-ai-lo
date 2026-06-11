"""Authentication and authorization dependencies.

Two modes:
- Production: Supabase JWT in the Authorization header, verified against
  Supabase Auth; the matching row in ``users`` provides role + gestora.
- Dev stub (DEV_AUTH_STUB=true): the ``X-Dev-User`` header carries a user id
  that must exist in the dev store. Used by local dev and the test suite.

Gestora isolation helpers live here too so every API module shares one
audited implementation.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, Header, HTTPException, status

from config import ServiceNotConfiguredError, get_settings
from models.schema import User, UserRole
from services import db as dbmod


def _load_user_row(db: dbmod.Database, user_id: str) -> Optional[dict[str, Any]]:
    return db.get("users", user_id)


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    x_dev_user: Optional[str] = Header(default=None),
) -> User:
    """Resolve the calling user, either from the dev stub header or a Supabase JWT."""
    settings = get_settings()
    try:
        db = dbmod.get_db()
    except ServiceNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    if settings.dev_auth_stub:
        if not x_dev_user:
            raise HTTPException(status_code=401, detail="X-Dev-User header required (DEV_AUTH_STUB mode)")
        row = _load_user_row(db, x_dev_user)
        if row is None:
            raise HTTPException(status_code=401, detail="Unknown dev user")
        return User(**row)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]

    if not settings.supabase_configured:
        raise HTTPException(status_code=503, detail="Service not configured: supabase auth")

    # Lazy import: the supabase package is optional in dev.
    try:
        from supabase import create_client  # type: ignore[import-not-found]
    except ImportError:
        raise HTTPException(status_code=503, detail="supabase package not installed")

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        auth_user = client.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if not auth_user or not auth_user.user:
        raise HTTPException(status_code=401, detail="Invalid token")

    row = _load_user_row(db, auth_user.user.id)
    if row is None:
        raise HTTPException(status_code=403, detail="User not provisioned in platform")
    return User(**row)


def _require_role(*roles: UserRole):
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(r.value for r in roles)}")
        return user

    return dependency


require_client = _require_role(UserRole.client)
require_counsel = _require_role(UserRole.counsel)
require_admin = _require_role(UserRole.admin)
require_counsel_or_admin = _require_role(UserRole.counsel, UserRole.admin)
require_any = get_current_user


# ---------------------------------------------------------------------------
# Gestora isolation helpers (SPEC guardrail 1)
# ---------------------------------------------------------------------------

def gestora_of_request(db: dbmod.Database, request_row: dict[str, Any]) -> Optional[str]:
    fund = db.get("funds", request_row["fund_id"])
    return fund["gestora_id"] if fund else None


def assert_request_access(db: dbmod.Database, user: User, request_row: dict[str, Any]) -> str:
    """404 unless the user may access this request. Returns the gestora_id.

    Clients only ever see requests whose fund belongs to their own gestora;
    counsel/admin are cross-gestora by design (SPEC actor matrix).
    A 404 (not 403) avoids leaking the existence of other gestoras' data.
    """
    gestora_id = gestora_of_request(db, request_row)
    if user.role in (UserRole.counsel, UserRole.admin):
        return gestora_id or ""
    if gestora_id is None or user.gestora_id != gestora_id:
        raise HTTPException(status_code=404, detail="Request not found")
    return gestora_id


def assert_precedent_access(db: dbmod.Database, user: User, precedent_row: dict[str, Any]) -> None:
    """404 unless the user may access this precedent (own silo or global templates)."""
    if user.role in (UserRole.counsel, UserRole.admin):
        return
    gestora_id = precedent_row.get("gestora_id")
    if gestora_id is None and precedent_row.get("source") in ("slp_curated", "platform_base"):
        return
    if gestora_id != user.gestora_id:
        raise HTTPException(status_code=404, detail="Precedent not found")
