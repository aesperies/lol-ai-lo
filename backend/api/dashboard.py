"""Gestora dashboard aggregates (Roadmap D).

One call feeds the client dashboard: status counts, upcoming counsel-SLA
deadlines, average validation turnaround and recent activity — all HARD-scoped
to the caller's gestora (fund_ids / gestora_id filters, never unscoped).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends

from auth import require_client
from config import get_settings
from models.schema import DashboardStatsOut, RequestStatus, User
from services import db as dbmod
from services.sla import hours_pending as sla_hours_pending

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_IN_PROGRESS = {
    RequestStatus.parsing.value,
    RequestStatus.confirmed.value,
    RequestStatus.generating.value,
}


def _parse_ts(stamp: Any) -> Optional[datetime]:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@router.get("/stats", response_model=DashboardStatsOut)
async def dashboard_stats(user: User = Depends(require_client)) -> Any:
    """Aggregates for the caller's gestora (clients only)."""
    db = dbmod.get_db()
    settings = get_settings()
    now = datetime.now(timezone.utc)

    funds = db.select("funds", gestora_id=user.gestora_id) if user.gestora_id else []
    fund_names = {f["id"]: f["name"] for f in funds}
    requests: list[dict[str, Any]] = []
    for fund_id in fund_names:
        requests.extend(db.select("requests", fund_id=fund_id))

    # -- recuentos por estado ------------------------------------------------
    counts = {"in_progress": 0, "awaiting_you": 0, "in_counsel_review": 0, "ready": 0, "delivered_this_month": 0}
    month = now.strftime("%Y-%m")
    for row in requests:
        status = row["status"]
        if status in _IN_PROGRESS:
            counts["in_progress"] += 1
        elif status == RequestStatus.review_pending.value:
            counts["awaiting_you"] += 1
        elif status == RequestStatus.counsel_review.value:
            counts["in_counsel_review"] += 1
        elif status == RequestStatus.validated.value:
            counts["ready"] += 1
        elif status == RequestStatus.delivered.value:
            delivered_at = _parse_ts(row.get("counsel_validated_at") or row.get("updated_at"))
            if delivered_at and delivered_at.strftime("%Y-%m") == month:
                counts["delivered_this_month"] += 1

    # -- vencimientos SLA próximos (validaciones en curso) --------------------
    deadlines: list[dict[str, Any]] = []
    for row in requests:
        if row["status"] != RequestStatus.counsel_review.value:
            continue
        pending = sla_hours_pending(row, now)
        if pending is None:
            continue
        remaining = settings.sla_review_hours - pending
        requested_at = _parse_ts(row.get("counsel_requested_at"))
        deadlines.append({
            "request_id": row["id"],
            "doc_type": row["doc_type"],
            "fund_name": fund_names.get(row["fund_id"]),
            "deadline": (requested_at + timedelta(hours=settings.sla_review_hours)).isoformat()
            if requested_at else None,
            "hours_remaining": round(remaining, 1),
            "overdue": remaining < 0,
        })
    deadlines.sort(key=lambda d: d["hours_remaining"])

    # -- tiempo medio de validación (últimas 20 completadas) ------------------
    turnarounds: list[float] = []
    for row in requests:
        start = _parse_ts(row.get("counsel_requested_at"))
        end = _parse_ts(row.get("counsel_validated_at"))
        if start and end and end > start:
            turnarounds.append((end - start).total_seconds() / 3600)
    turnarounds = turnarounds[-20:]
    avg_turnaround = round(sum(turnarounds) / len(turnarounds), 1) if turnarounds else None

    # -- actividad reciente (audit de la gestora, más nuevo primero) ----------
    audit_rows = db.select("audit_log", gestora_id=user.gestora_id) if user.gestora_id else []
    recent = [
        {
            "action": r["action"],
            "timestamp": r.get("timestamp"),
            "resource_type": r.get("resource_type"),
            "resource_id": r.get("resource_id"),
        }
        for r in audit_rows[-10:][::-1]
    ]

    return DashboardStatsOut(
        counts=counts,
        upcoming_deadlines=deadlines[:10],
        avg_validation_hours=avg_turnaround,
        sla_hours=settings.sla_review_hours,
        recent_activity=recent,
        funds_count=len(funds),
    )
