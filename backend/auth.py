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


def request_is_shared_with(db: dbmod.Database, request_id: str, user: User) -> bool:
    """True iff a share row grants ``user`` access to this request AND it stays
    within a single gestora (the inviolable rule, defence in depth).

    Collaboration (012_collaboration.sql): a share only grants access when the
    share row, the sharee and the request all belong to the SAME gestora. We
    re-verify gestora equality here at ACCESS time even though it was enforced
    at CREATE time, so a later data inconsistency can never become a leak.
    """
    if user.gestora_id is None:
        return False
    request_gestora = gestora_of_request(db, db.get("requests", request_id) or {})
    if request_gestora is None or request_gestora != user.gestora_id:
        return False
    shares = db.select(
        "request_shares", request_id=request_id, shared_with_user_id=user.id
    )
    return any(s.get("gestora_id") == user.gestora_id for s in shares)


def assert_request_access(db: dbmod.Database, user: User, request_row: dict[str, Any]) -> str:
    """404 unless the user may READ this request. Returns the gestora_id.

    Read access is granted to:
      * the request's OWNER (the client who created it);
      * a same-gestora colleague the owner has SHARED it with (collaboration,
        012_collaboration.sql);
      * counsel/admin, who are cross-gestora by design (SPEC actor matrix).
    A request is otherwise PRIVATE to its owner: a different same-gestora client
    who was not shared with gets 404 (not 403) so the request's existence is
    never leaked — the same no-leak rule used across gestoras.

    Sharing NEVER crosses gestoras: a share only counts when the share row, the
    sharee and the request are all the same gestora (request_is_shared_with
    re-checks this), so this stays within the inviolable single-gestora rule.
    Owner-only / mutating actions are gated separately by assert_request_owner;
    this helper only governs READ access.
    """
    gestora_id = gestora_of_request(db, request_row)
    if user.role in (UserRole.counsel, UserRole.admin):
        return gestora_id or ""
    if gestora_id is None or user.gestora_id != gestora_id:
        # Cross-gestora (or fund-less) request: never visible to a client.
        raise HTTPException(status_code=404, detail="Request not found")
    if is_request_owner(user, request_row):
        return gestora_id
    if request_is_shared_with(db, request_row["id"], user):
        return gestora_id
    raise HTTPException(status_code=404, detail="Request not found")


def is_request_owner(user: User, request_row: dict[str, Any]) -> bool:
    """True iff ``user`` is the client who created the request."""
    return user.role == UserRole.client and request_row.get("user_id") == user.id


def assert_request_owner(db: dbmod.Database, user: User, request_row: dict[str, Any]) -> str:
    """404/403 unless ``user`` OWNS this request. Returns the gestora_id.

    Collaboration (012_collaboration.sql): every MUTATING / irreversible action
    on a request — Exit A acknowledgment & download, Exit B / counsel request,
    refinements, managing the share list — is reserved to the OWNER. A
    collaborator with read access is rejected here (403) without losing their
    read access elsewhere. We first run the standard 404-no-leak access check
    (so a stranger still gets 404, never 403), then require ownership.
    """
    gestora_id = assert_request_access(db, user, request_row)
    if not is_request_owner(user, request_row):
        raise HTTPException(
            status_code=403,
            detail="Solo el propietario de la solicitud puede realizar esta acción.",
        )
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
