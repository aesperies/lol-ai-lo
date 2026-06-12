"""Admin KPI endpoints: quality (draft→validated edit distance) and counsel
SLA response metrics, plus the manual SLA sweep trigger (improvements #6 & #8).

All endpoints are admin-only: quality_metrics is an internal KPI (clients
never see it) and the SLA report exposes per-counsel performance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends

from api.counsel_assignments import resolve_counsel_recipients
from auth import gestora_of_request, require_admin
from config import get_settings
from models.schema import (
    DocumentVersionType,
    RequestStatus,
    SlaEventKind,
    User,
    UserRole,
)
from services import db as dbmod
from services import sla as sla_service

router = APIRouter(prefix="/api/admin", tags=["admin-metrics"])


# ---------------------------------------------------------------------------
# Quality (improvement #6)
# ---------------------------------------------------------------------------

def _quality_stats(db: dbmod.Database, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """count / avg similarity / avg refinements / % Exit A / % Exit B for one
    group of quality_metrics rows. Exit A rows are identified through the
    request's exit_a_acknowledged_at (the metric schema is exit-agnostic)."""
    count = len(rows)
    if count == 0:
        return {
            "count": 0,
            "avg_similarity": None,
            "avg_refinements": None,
            "pct_accepted_as_is": None,
            "pct_validated": None,
        }
    exit_a = sum(
        1
        for r in rows
        if (db.get("requests", r["request_id"]) or {}).get("exit_a_acknowledged_at")
    )
    return {
        "count": count,
        "avg_similarity": round(sum(r["similarity"] for r in rows) / count, 4),
        "avg_refinements": round(sum(r.get("refinements_used") or 0 for r in rows) / count, 2),
        "pct_accepted_as_is": round(exit_a / count, 4),
        "pct_validated": round((count - exit_a) / count, 4),
    }


@router.get("/quality")
async def quality_report(
    gestora_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    user: User = Depends(require_admin),
) -> Any:
    """Aggregated quality stats: overall + grouped by doc_type and by gestora."""
    db = dbmod.get_db()
    rows = db.select("quality_metrics")
    if gestora_id:
        rows = [r for r in rows if r["gestora_id"] == gestora_id]
    if doc_type:
        rows = [r for r in rows if r["doc_type"] == doc_type]

    by_doc_type = []
    for value in sorted({r["doc_type"] for r in rows}):
        group = [r for r in rows if r["doc_type"] == value]
        by_doc_type.append({"doc_type": value, **_quality_stats(db, group)})

    by_gestora = []
    for value in sorted({r["gestora_id"] for r in rows}):
        group = [r for r in rows if r["gestora_id"] == value]
        gestora = db.get("gestoras", value) or {}
        by_gestora.append(
            {
                "gestora_id": value,
                "gestora_name": gestora.get("name"),
                **_quality_stats(db, group),
            }
        )

    return {
        "overall": _quality_stats(db, rows),
        "by_doc_type": by_doc_type,
        "by_gestora": by_gestora,
    }


# ---------------------------------------------------------------------------
# Counsel SLA (improvement #8)
# ---------------------------------------------------------------------------

def _validation_hours(row: dict[str, Any]) -> Optional[float]:
    requested, validated = row.get("counsel_requested_at"), row.get("counsel_validated_at")
    if not requested or not validated:
        return None
    try:
        start = datetime.fromisoformat(str(requested))
        end = datetime.fromisoformat(str(validated))
    except ValueError:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return (end - start).total_seconds() / 3600


def _validator_email(db: dbmod.Database, request_id: str) -> Optional[str]:
    """The counsel who validated: uploaded_by of the final document version."""
    finals = db.select(
        "documents", request_id=request_id, version_type=DocumentVersionType.final.value
    )
    if not finals or not finals[-1].get("uploaded_by"):
        return None
    counsel = db.get("users", finals[-1]["uploaded_by"])
    return counsel["email"] if counsel else None


@router.get("/sla")
async def sla_report(user: User = Depends(require_admin)) -> Any:
    """Counsel response metrics: per counsel email and overall — pending
    reviews, average validation hours, reviews currently past SLA, and SLA
    reminders/escalations sent."""
    db = dbmod.get_db()
    settings = get_settings()
    now = datetime.now(timezone.utc)

    def empty_bucket() -> dict[str, Any]:
        return {
            "pending": 0,
            "past_sla": 0,
            "validation_hours": [],
            "reminders_sent": 0,
            "escalations_sent": 0,
        }

    # Every counsel user appears in the report even with no activity.
    buckets: dict[str, dict[str, Any]] = {
        u["email"]: empty_bucket() for u in db.select("users", role=UserRole.counsel.value)
    }

    def bucket(email: Optional[str]) -> Optional[dict[str, Any]]:
        if email is None:
            return None
        return buckets.setdefault(email, empty_bucket())

    overall = empty_bucket()

    # Pending reviews, attributed to the routed counsel (primary -> backup ->
    # broadcast — a broadcast pending shows under every counsel user).
    for row in db.select("requests", status=RequestStatus.counsel_review.value):
        pending = sla_service.hours_pending(row, now)
        past = pending is not None and pending > settings.sla_review_hours
        overall["pending"] += 1
        overall["past_sla"] += 1 if past else 0
        _, recipients = resolve_counsel_recipients(db, gestora_of_request(db, row))
        for counsel_user in recipients:
            b = bucket(counsel_user.get("email"))
            if b is not None:
                b["pending"] += 1
                b["past_sla"] += 1 if past else 0

    # Completed validations, attributed to the validating counsel.
    for row in db.select("requests"):
        hours = _validation_hours(row)
        if hours is None:
            continue
        overall["validation_hours"].append(hours)
        b = bucket(_validator_email(db, row["id"]))
        if b is not None:
            b["validation_hours"].append(hours)

    # SLA notifications sent (sla_events), by recipient.
    for event in db.select("sla_events"):
        key = "reminders_sent" if event["kind"] == SlaEventKind.reminder.value else "escalations_sent"
        overall[key] += 1
        b = bucket(event.get("recipient_email"))
        if b is not None:
            b[key] += 1

    def finalize(data: dict[str, Any]) -> dict[str, Any]:
        hours = data.pop("validation_hours")
        data["avg_validation_hours"] = round(sum(hours) / len(hours), 2) if hours else None
        return data

    return {
        "sla_hours": settings.sla_review_hours,
        "overall": finalize(overall),
        "by_counsel": [
            {"counsel_email": email, **finalize(data)}
            for email, data in sorted(buckets.items())
        ],
    }


@router.post("/sla/sweep")
async def trigger_sla_sweep(user: User = Depends(require_admin)) -> Any:
    """Manual SLA sweep (same logic as the periodic in-process task)."""
    return sla_service.run_sla_sweep(dbmod.get_db())
