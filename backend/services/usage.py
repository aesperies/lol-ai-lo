"""Usage events writer for billing (SPEC guardrail 12).

Events: document_generated / exit_a / exit_b_requested / exit_b_validated.
billing_period is 'YYYY-MM' of the moment the event occurred.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from models.schema import UsageEventType
from services import db as dbmod


def current_billing_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def record_usage(
    db: dbmod.Database,
    *,
    gestora_id: str,
    request_id: Optional[str],
    event_type: UsageEventType,
) -> dict[str, Any]:
    """Insert one usage event for the gestora's current billing period."""
    return db.insert(
        "usage_events",
        {
            "gestora_id": gestora_id,
            "request_id": request_id,
            "event_type": UsageEventType(event_type).value,
            "billing_period": current_billing_period(),
        },
    )
