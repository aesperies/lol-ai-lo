"""Counsel review surface: queue, review bundle and the comment thread.

The queue lists every request sitting in ``counsel_review`` (counsel/admin are
cross-gestora by role, SPEC actor matrix). The bundle packs what the review
screen needs in one payload — the request row, the extracted draft text and
the comment thread; the rendered draft/redline HTML is served separately by
GET /api/requests/{id}/documents/{type}/html.

Comments (013_directory_and_comments.sql) are the counsel↔platform thread on
a request: readable by anyone with read access to the request, writable by
counsel/admin. ``author_name`` is denormalized at write time so the thread
survives author erasure (GDPR) without pointing at personal data.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from api import client_ip, get_request_or_404, load_draft_text
from auth import assert_request_access, get_current_user, require_counsel_or_admin
from typing import Optional

from config import get_settings
from models.schema import (
    AuditAction,
    AuditResourceType,
    CounselCommentCreate,
    CounselCommentOut,
    CounselQueueItemOut,
    RequestOut,
    RequestStatus,
    ReviewBundleOut,
    User,
)
from services import audit, db as dbmod
from services import notifications as notif
from services.counsel_routing import counsel_gestora_scope
from services.sla import hours_pending as sla_hours_pending

router = APIRouter(prefix="/api", tags=["counsel-review"])


def _comment_out(row: dict[str, Any]) -> CounselCommentOut:
    return CounselCommentOut(
        id=row["id"],
        request_id=row["request_id"],
        author=row.get("author_name") or "",
        text=row["text"],
        created_at=row.get("created_at"),
    )


@router.get("/counsel/queue", response_model=list[CounselQueueItemOut])
async def counsel_queue(
    gestora_id: Optional[str] = None,
    urgency: Optional[str] = None,
    user: User = Depends(require_counsel_or_admin),
) -> Any:
    """Requests awaiting counsel review, MOST URGENT first.

    Each item carries hours_pending / sla_hours / urgency (green|amber|red,
    thresholds from config sla_reminder_hours / sla_review_hours) plus the
    gestora id+name so the inbox can badge and filter without extra calls.
    Optional filters: ?gestora_id= and ?urgency=red|amber|green.
    """
    db = dbmod.get_db()
    settings = get_settings()
    rows = db.unscoped_select("requests", status=RequestStatus.counsel_review.value)

    # Política de asignación: un abogado ve SUS gestoras + el pool de gestoras
    # sin abogado asignado (etiquetadas para que la UI las separe). Admin: todo.
    if user.role.value == "counsel":
        mine, pool = counsel_gestora_scope(db, user.id)
    else:
        mine, pool = None, None

    items: list[dict[str, Any]] = []
    gestora_cache: dict[str, Any] = {}
    for row in rows:
        fund = db.get("funds", row["fund_id"]) if row.get("fund_id") else None
        # The fund row already carries gestora_id (gestora_of_request would
        # re-fetch this same fund); gestora rows are cached across the loop.
        row_gestora_id = (fund or {}).get("gestora_id")
        if row_gestora_id and row_gestora_id not in gestora_cache:
            gestora_cache[row_gestora_id] = db.get("gestoras", row_gestora_id)
        gestora = gestora_cache.get(row_gestora_id) if row_gestora_id else None
        pending = sla_hours_pending(row)
        if pending is None:
            level = "green"
        elif pending >= settings.sla_review_hours:
            level = "red"
        elif pending >= settings.sla_reminder_hours:
            level = "amber"
        else:
            level = "green"
        if mine is not None:
            if row_gestora_id in mine:
                assignment = "mine"
            elif row_gestora_id in pool:
                assignment = "pool"
            else:
                continue  # gestora asignada a OTRO abogado: fuera de su alcance
        else:
            assignment = "mine"
        items.append({
            **row,
            "fund_name": (fund or {}).get("name"),
            "gestora_id": row_gestora_id,
            "gestora_name": (gestora or {}).get("name"),
            "hours_pending": pending,
            "sla_hours": settings.sla_review_hours,
            "urgency": level,
            "assignment": assignment,
        })

    if gestora_id:
        items = [i for i in items if i["gestora_id"] == gestora_id]
    if urgency:
        items = [i for i in items if i["urgency"] == urgency]
    # Más urgente primero; los sin timestamp al final (estables por antigüedad).
    items.sort(key=lambda i: -(i["hours_pending"] or -1))
    return items


@router.get("/requests/{request_id}/review", response_model=ReviewBundleOut)
async def get_review_bundle(
    request_id: str, user: User = Depends(get_current_user)
) -> Any:
    """Everything the counsel review screen needs in one payload. Standard
    request access rules (owner / same-gestora sharee / counsel / admin)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    comments = db.select("counsel_comments", request_id=request_id)
    return ReviewBundleOut(
        request=RequestOut(**row),
        draft_text=load_draft_text(db, request_id) or "",
        comments=[_comment_out(c) for c in comments],
    )


@router.get("/requests/{request_id}/comments", response_model=list[CounselCommentOut])
async def list_comments(
    request_id: str, user: User = Depends(get_current_user)
) -> Any:
    """The request's comment thread, oldest first. Read follows request access."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    assert_request_access(db, user, row)
    return [_comment_out(c) for c in db.select("counsel_comments", request_id=request_id)]


@router.post("/requests/{request_id}/comments", response_model=CounselCommentOut, status_code=201)
async def add_comment(
    request_id: str,
    body: CounselCommentCreate,
    http_request: Request,
    user: User = Depends(require_counsel_or_admin),
) -> Any:
    """Counsel/admin appends to the review thread (audited)."""
    db = dbmod.get_db()
    row = get_request_or_404(db, request_id)
    gestora_id = assert_request_access(db, user, row)
    comment = db.insert(
        "counsel_comments",
        {
            "request_id": request_id,
            "author_id": user.id,
            "author_name": user.email,
            "text": body.text,
        },
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.counsel_comment_added,
        resource_type=AuditResourceType.request,
        resource_id=request_id,
        gestora_id=gestora_id or None,
        metadata={"comment_id": comment["id"]},
        ip_address=client_ip(http_request),
    )
    # Campana del cliente propietario: hay mensaje nuevo del abogado.
    if row.get("user_id") and row["user_id"] != user.id:
        notif.notify(
            db,
            user_id=row["user_id"],
            kind=notif.KIND_COMMENT_ADDED,
            title="Nuevo comentario del abogado",
            body=body.text[:200],
            request_id=request_id,
            gestora_id=gestora_id or None,
        )
    return _comment_out(comment)
