"""In-app notifications (016_notifications.sql).

One row per recipient per event; the bell in the UI lists them and marks them
read. Emission is BEST-EFFORT by design: a notification failure must never
break the flow that triggered it (same rule as email — SPEC graceful
degradation), so callers use :func:`notify` and never handle errors.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services import db as dbmod

logger = logging.getLogger("lolailo.notifications")

# Known kinds (free text on purpose — new events should not need a migration).
KIND_COUNSEL_REQUESTED = "counsel_requested"
KIND_DOCUMENT_VALIDATED = "document_validated"
KIND_COMMENT_ADDED = "comment_added"
KIND_GENERATION_FAILED = "generation_failed"


def notify(
    db: dbmod.Database,
    *,
    user_id: str,
    kind: str,
    title: str,
    body: Optional[str] = None,
    request_id: Optional[str] = None,
    gestora_id: Optional[str] = None,
) -> None:
    """Insert one in-app notification for ``user_id``. Never raises."""
    try:
        db.insert(
            "notifications",
            {
                "user_id": user_id,
                "gestora_id": gestora_id,
                "request_id": request_id,
                "kind": kind,
                "title": title,
                "body": body,
                "read_at": None,
            },
        )
    except Exception:  # noqa: BLE001 — best-effort by design
        logger.exception("In-app notification failed (flow continues): %s", kind)


def for_user(db: dbmod.Database, user_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """The user's notifications, newest first."""
    rows = db.select("notifications", user_id=user_id)
    rows.reverse()  # select() is oldest-first
    return rows[:limit]


def unread_count(db: dbmod.Database, user_id: str) -> int:
    # read_at=None matches SQL NULL in both backends (db layer contract) — the
    # bell polls this every 60s per session, so never transfer read history.
    return len(db.select("notifications", user_id=user_id, read_at=None))


def mark_read(db: dbmod.Database, user_id: str, ids: Optional[list[str]] = None) -> int:
    """Mark the given notifications (or ALL unread when ids is None) as read.

    Scoped to ``user_id`` — a user can never mark another user's rows.
    """
    from services.workflow import now_iso

    marked = 0
    for row in db.select("notifications", user_id=user_id):
        if row.get("read_at"):
            continue
        if ids is not None and row["id"] not in ids:
            continue
        db.update("notifications", row["id"], {"read_at": now_iso()})
        marked += 1
    return marked
