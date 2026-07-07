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
from models.schema import (
    AuditAction,
    AuditResourceType,
    CounselCommentCreate,
    CounselCommentOut,
    RequestOut,
    RequestStatus,
    ReviewBundleOut,
    User,
)
from services import audit, db as dbmod

router = APIRouter(prefix="/api", tags=["counsel-review"])


def _comment_out(row: dict[str, Any]) -> CounselCommentOut:
    return CounselCommentOut(
        id=row["id"],
        request_id=row["request_id"],
        author=row.get("author_name") or "",
        text=row["text"],
        created_at=row.get("created_at"),
    )


@router.get("/counsel/queue", response_model=list[RequestOut])
async def counsel_queue(user: User = Depends(require_counsel_or_admin)) -> Any:
    """Requests awaiting counsel review, oldest first (FIFO queue)."""
    db = dbmod.get_db()
    rows = db.unscoped_select("requests", status=RequestStatus.counsel_review.value)
    def fund_name(row: dict[str, Any]) -> Any:
        fund = db.get("funds", row["fund_id"]) if row.get("fund_id") else None
        return (fund or {}).get("name")
    return [{**r, "fund_name": fund_name(r)} for r in rows]


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
    return _comment_out(comment)
