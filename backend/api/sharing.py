"""Collaboration / sharing endpoints (012_collaboration.sql).

An OWNER may share two resources with same-gestora colleagues:
  * a REQUEST (the whole document thread: params, draft/redline/final,
    reviews, downloads), and
  * a TABULAR REVIEW (view + CSV export).

ACCESS SEMANTICS (the deliberate design choice — documented here once):
  A collaborator gets READ access only. For a shared request they can view the
  request, its documents and reviews, and download. For a shared tabular review
  they can view it and CSV-export it. The OWNER keeps EVERY mutating /
  irreversible action: Exit A acknowledgment, requesting counsel / Exit B,
  refinements, the counsel flow, deleting, and managing the share list itself.
  Owner-only gating lives next to each action (auth.assert_request_owner /
  api.tabular._assert_review_owner); read access lives in
  auth.assert_request_access / api.tabular._assert_review_access.

THE INVIOLABLE RULE (SPEC guardrail 1 extended to sharing): sharing is
STRICTLY within a single gestora. Enforced at TWO points:
  * CREATE — the sharee must be a client of the SAME gestora as the resource
    (and not the owner); anything else is rejected (404 for a cross-gestora /
    unknown user — never leak existence — and 400 for self-share).
  * ACCESS — a share only grants access when the share row, the sharee AND the
    resource are all the same gestora (re-checked in the *_is_shared_with
    helpers). A share row also records gestora_id once (= the resource's
    gestora), so it can never become gestora-less.
There is NO cross-gestora share, ever.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from api import client_ip, get_request_or_404
from api.tabular import _get_review_or_404
from auth import (
    assert_request_access,
    assert_request_owner,
    assert_review_access,
    assert_review_owner,
    get_current_user,
    require_client,
)
from models.schema import (
    AuditAction,
    AuditResourceType,
    ColleagueOut,
    ShareCreate,
    ShareOut,
    User,
    UserRole,
)
from services import audit, db as dbmod

logger = logging.getLogger("lolailo.sharing")

# /api/my/colleagues lives on its own prefix; the share endpoints hang off the
# existing resource routers' paths.
colleagues_router = APIRouter(prefix="/api/my", tags=["collaboration"])
request_shares_router = APIRouter(prefix="/api/requests", tags=["collaboration"])
review_shares_router = APIRouter(prefix="/api/tabular-reviews", tags=["collaboration"])



def _name_from_email(email: str) -> str:
    return (email or "").split("@")[0]


def _share_out(db: dbmod.Database, row: dict[str, Any]) -> ShareOut:
    """Resolve the display fields for one share row."""
    sharee = db.get("users", row["shared_with_user_id"]) or {}
    sharer = db.get("users", row["shared_by"]) or {}
    sharee_email = sharee.get("email")
    return ShareOut(
        id=row["id"],
        gestora_id=row["gestora_id"],
        shared_with_user_id=row["shared_with_user_id"],
        shared_with_email=sharee_email,
        shared_with_name=_name_from_email(sharee_email) if sharee_email else None,
        shared_by=row["shared_by"],
        shared_by_email=sharer.get("email"),
        created_at=row.get("created_at"),
    )


# ---------------------------------------------------------------------------
# Colleague picker (same-gestora client users, excluding the caller)
# ---------------------------------------------------------------------------

@colleagues_router.get("/colleagues", response_model=list[ColleagueOut])
async def list_colleagues(user: User = Depends(require_client)) -> Any:
    """Same-gestora CLIENT colleagues for the share picker, excluding the caller.

    Gestora-siloed: only users of the caller's own gestora are ever returned,
    so the picker can never offer a cross-gestora sharee (the inviolable rule).
    """
    db = dbmod.get_db()
    if user.gestora_id is None:
        return []
    rows = db.select("users", gestora_id=user.gestora_id, role=UserRole.client.value)
    return [
        ColleagueOut(id=u["id"], email=u["email"], name=_name_from_email(u["email"]))
        for u in rows
        if u["id"] != user.id
    ]


# ---------------------------------------------------------------------------
# Shared validation: the sharee must be a same-gestora client, not the owner
# ---------------------------------------------------------------------------

def _validate_sharee(
    db: dbmod.Database, *, owner: User, gestora_id: str, sharee_user_id: str
) -> dict[str, Any]:
    """Resolve and validate a candidate sharee (the inviolable single-gestora rule).

    Rejects with 400 on self-share and 404 when the user is unknown or belongs
    to another gestora (404 — never leak which other-gestora user exists). A
    counsel/admin target (gestora_id None) is also rejected: sharing is a
    client-to-client, single-gestora feature. Returns the sharee row.
    """
    if sharee_user_id == owner.id:
        raise HTTPException(status_code=400, detail="No puedes compartir contigo mismo.")
    sharee = db.get("users", sharee_user_id)
    # 404 (not 403/400) for unknown OR cross-gestora users so the existence of
    # other gestoras' users is never discoverable.
    if (
        sharee is None
        or sharee.get("role") != UserRole.client.value
        or sharee.get("gestora_id") != gestora_id
    ):
        raise HTTPException(status_code=404, detail="Colega no encontrado en tu gestora.")
    return sharee


# ---------------------------------------------------------------------------
# Request shares
# ---------------------------------------------------------------------------

@request_shares_router.get("/{request_id}/shares", response_model=list[ShareOut])
async def list_request_shares(
    request_id: str, user: User = Depends(get_current_user)
) -> Any:
    """Collaborators on a request (owner and collaborators may view the list).

    Same 404-no-leak read access as the request itself: a stranger to the
    gestora never learns the request exists."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    shares = db.select("request_shares", request_id=request_id)
    shares.sort(key=lambda s: str(s.get("created_at") or ""))
    return [_share_out(db, s) for s in shares]


@request_shares_router.post("/{request_id}/shares", response_model=ShareOut, status_code=201)
async def create_request_share(
    request_id: str,
    body: ShareCreate,
    http_request: Request,
    user: User = Depends(require_client),
) -> Any:
    """Share a request with a same-gestora colleague (OWNER only; idempotent).

    The colleague gains READ access (view the request, its documents & reviews,
    download). Enforces the inviolable single-gestora rule: the sharee must be a
    client of the SAME gestora as the request (cross-gestora / unknown → 404;
    self-share → 400)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_owner(db, user, row)

    _validate_sharee(db, owner=user, gestora_id=gestora_id, sharee_user_id=body.user_id)

    # Idempotent: re-sharing with the same colleague returns the existing row.
    existing = db.select(
        "request_shares", request_id=request_id, shared_with_user_id=body.user_id
    )
    if existing:
        return _share_out(db, existing[0])

    share = db.insert(
        "request_shares",
        {
            "request_id": request_id,
            "gestora_id": gestora_id,
            "shared_with_user_id": body.user_id,
            "shared_by": user.id,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.resource_shared,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id,
        metadata={
            "resource_type": "request",
            "resource_id": request_id,
            "shared_with": body.user_id,
        },
        ip_address=client_ip(http_request),
    )
    return _share_out(db, share)


@request_shares_router.delete("/{request_id}/shares/{user_id}", status_code=204)
async def delete_request_share(
    request_id: str,
    user_id: str,
    http_request: Request,
    user: User = Depends(require_client),
) -> None:
    """Revoke a colleague's access to a request (OWNER only; idempotent)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_owner(db, user, row)

    existing = db.select(
        "request_shares", request_id=request_id, shared_with_user_id=user_id
    )
    for share in existing:
        db.delete("request_shares", share["id"])
    if existing:
        audit.log_action(
            db,
            user=user,
            action=AuditAction.resource_unshared,
            resource_type=AuditResourceType.request,
            resource_id=request_id,
            gestora_id=gestora_id,
            metadata={
                "resource_type": "request",
                "resource_id": request_id,
                "shared_with": user_id,
            },
            ip_address=client_ip(http_request),
        )


# ---------------------------------------------------------------------------
# Tabular-review shares
# ---------------------------------------------------------------------------

@review_shares_router.get("/{review_id}/shares", response_model=list[ShareOut])
async def list_review_shares(
    review_id: str, user: User = Depends(get_current_user)
) -> Any:
    """Collaborators on a tabular review (owner and collaborators may view)."""
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    assert_review_access(db, user, review)
    shares = db.select("tabular_review_shares", review_id=review_id)
    shares.sort(key=lambda s: str(s.get("created_at") or ""))
    return [_share_out(db, s) for s in shares]


@review_shares_router.post("/{review_id}/shares", response_model=ShareOut, status_code=201)
async def create_review_share(
    review_id: str,
    body: ShareCreate,
    http_request: Request,
    user: User = Depends(require_client),
) -> Any:
    """Share a tabular review with a same-gestora colleague (OWNER only).

    The colleague gains READ access (view + CSV export). Same inviolable
    single-gestora rule as request sharing."""
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    gestora_id = assert_review_owner(db, user, review)

    _validate_sharee(db, owner=user, gestora_id=gestora_id, sharee_user_id=body.user_id)

    existing = db.select(
        "tabular_review_shares", review_id=review_id, shared_with_user_id=body.user_id
    )
    if existing:
        return _share_out(db, existing[0])

    share = db.insert(
        "tabular_review_shares",
        {
            "review_id": review_id,
            "gestora_id": gestora_id,
            "shared_with_user_id": body.user_id,
            "shared_by": user.id,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.resource_shared,
        resource_type=AuditResourceType.tabular_review,
        resource_id=review_id,
        gestora_id=gestora_id,
        metadata={
            "resource_type": "tabular_review",
            "resource_id": review_id,
            "shared_with": body.user_id,
        },
        ip_address=client_ip(http_request),
    )
    return _share_out(db, share)


@review_shares_router.delete("/{review_id}/shares/{user_id}", status_code=204)
async def delete_review_share(
    review_id: str,
    user_id: str,
    http_request: Request,
    user: User = Depends(require_client),
) -> None:
    """Revoke a colleague's access to a tabular review (OWNER only; idempotent)."""
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    gestora_id = assert_review_owner(db, user, review)

    existing = db.select(
        "tabular_review_shares", review_id=review_id, shared_with_user_id=user_id
    )
    for share in existing:
        db.delete("tabular_review_shares", share["id"])
    if existing:
        audit.log_action(
            db,
            user=user,
            action=AuditAction.resource_unshared,
            resource_type=AuditResourceType.tabular_review,
            resource_id=review_id,
            gestora_id=gestora_id,
            metadata={
                "resource_type": "tabular_review",
                "resource_id": review_id,
                "shared_with": user_id,
            },
            ip_address=client_ip(http_request),
        )
