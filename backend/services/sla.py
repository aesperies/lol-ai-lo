"""Counsel SLA sweep: reminders + escalations for stuck reviews (improvement #8).

Exit B promises a review turnaround (config sla_review_hours, default 48h).
run_sla_sweep() finds requests stuck in 'counsel_review' and, idempotently
(one event of each kind per request, guarded by the sla_events table):

- past sla_reminder_hours (default 24h — half the SLA): emails the request's
  routed counsel (primary -> backup -> broadcast) a reminder;
- past sla_escalation_hours (default 56h — SLA + 8h grace): emails the
  gestora's BACKUP counsel (broadcast to all counsel when no backup exists).

Every email is audited as counsel_notified with metadata
{"sla": "reminder"|"escalation", "hours_pending": n}.

The sweep is exposed two ways (main.py / api/admin_metrics.py):
- POST /api/admin/sla/sweep (admin-only, manual trigger);
- an in-process asyncio loop started on app startup, every
  sla_sweep_interval_minutes (default 30), disabled under pytest and when
  sla_sweep_enabled=false.

TODO: the in-process loop is single-worker by design — move it to an external
scheduler (cron / Celery beat) in production multi-worker setups; the sweep
itself is idempotent so overlapping schedulers are safe.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from config import get_settings
from models.schema import (
    AuditAction,
    AuditResourceType,
    RequestStatus,
    SlaEventKind,
)
from services import audit, db as dbmod, email_service

logger = logging.getLogger("lolailo.sla")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hours_pending(request_row: dict[str, Any], now: Optional[datetime] = None) -> Optional[float]:
    """Hours since the request entered counsel review (counsel_requested_at;
    falls back to updated_at for rows predating migration 005)."""
    stamp = request_row.get("counsel_requested_at") or request_row.get("updated_at")
    if not stamp:
        return None
    try:
        since = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    return ((now or _now()) - since).total_seconds() / 3600


def _already_sent(db: dbmod.Database, request_id: str, kind: SlaEventKind) -> bool:
    return bool(db.select("sla_events", request_id=request_id, kind=kind.value))


def _notify(
    db: dbmod.Database,
    *,
    kind: SlaEventKind,
    request_row: dict[str, Any],
    gestora_id: Optional[str],
    recipients: list[dict[str, Any]],
    routing: str,
    pending: float,
) -> int:
    """Send one SLA email per recipient, record the sla_events rows and audit
    each delivery. Returns the number of emails sent."""
    settings = get_settings()
    fund = db.get("funds", request_row["fund_id"]) or {}
    send = (
        email_service.send_sla_reminder
        if kind is SlaEventKind.reminder
        else email_service.send_sla_escalation
    )
    sent = 0
    for counsel_user in recipients:
        delivery = send(
            counsel_name=counsel_user["email"].split("@")[0],
            counsel_email=counsel_user["email"],
            fund_name=fund.get("name", ""),
            doc_type=request_row["doc_type"],
            hours_pending=int(pending),
            sla_hours=int(settings.sla_review_hours),
            review_url=f"{settings.frontend_url}/review/{request_row['id']}",
        )
        db.insert(
            "sla_events",
            {
                "request_id": request_row["id"],
                "kind": kind.value,
                "recipient_email": counsel_user["email"],
                "sent_at": _now().isoformat(),
            },
        )
        audit.log_action(
            db,
            user=None,  # system action (the sweep has no acting user)
            action=AuditAction.counsel_notified,
            resource_type=AuditResourceType.request,
            resource_id=request_row["id"],
            gestora_id=gestora_id,
            metadata={
                "sla": kind.value,
                "hours_pending": round(pending, 1),
                "to": counsel_user["email"],
                "delivery": delivery.get("delivery"),
                "routing": routing,
            },
        )
        sent += 1
    return sent


def run_sla_sweep(db: Optional[dbmod.Database] = None) -> dict[str, int]:
    """One idempotent pass over all requests stuck in 'counsel_review'."""
    from auth import gestora_of_request
    from services.counsel_routing import (
        resolve_backup_counsel_recipients,
        resolve_counsel_recipients,
    )

    db = db if db is not None else dbmod.get_db()
    settings = get_settings()
    now = _now()
    reminders_sent = 0
    escalations_sent = 0

    for row in db.unscoped_select("requests", status=RequestStatus.counsel_review.value):
        pending = hours_pending(row, now)
        if pending is None:
            continue
        gestora_id = gestora_of_request(db, row)

        if pending >= settings.sla_reminder_hours and not _already_sent(
            db, row["id"], SlaEventKind.reminder
        ):
            routing, recipients = resolve_counsel_recipients(db, gestora_id)
            reminders_sent += _notify(
                db,
                kind=SlaEventKind.reminder,
                request_row=row,
                gestora_id=gestora_id,
                recipients=recipients,
                routing=routing,
                pending=pending,
            )

        if pending >= settings.sla_escalation_hours and not _already_sent(
            db, row["id"], SlaEventKind.escalation
        ):
            routing, recipients = resolve_backup_counsel_recipients(db, gestora_id)
            escalations_sent += _notify(
                db,
                kind=SlaEventKind.escalation,
                request_row=row,
                gestora_id=gestora_id,
                recipients=recipients,
                routing=routing,
                pending=pending,
            )

    return {"reminders_sent": reminders_sent, "escalations_sent": escalations_sent}


# ---------------------------------------------------------------------------
# In-process periodic sweep (started from main.py on app startup)
# ---------------------------------------------------------------------------

_sweep_task: Optional[asyncio.Task] = None


async def _sweep_loop() -> None:
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.sla_sweep_interval_minutes * 60)
        try:
            result = run_sla_sweep()
            if result["reminders_sent"] or result["escalations_sent"]:
                logger.info("SLA sweep: %s", result)
        except Exception:  # noqa: BLE001 — the loop must survive any sweep error
            logger.exception("SLA sweep failed; retrying next interval")


def start_sweep_loop() -> Optional[asyncio.Task]:
    """Start the periodic sweep task (no-op under pytest or when disabled)."""
    global _sweep_task
    settings = get_settings()
    if not settings.sla_sweep_enabled or "pytest" in sys.modules:
        return None
    if _sweep_task is None or _sweep_task.done():
        _sweep_task = asyncio.create_task(_sweep_loop())
    return _sweep_task


def stop_sweep_loop() -> None:
    global _sweep_task
    if _sweep_task is not None:
        _sweep_task.cancel()
        _sweep_task = None
