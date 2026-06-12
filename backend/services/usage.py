"""Usage events writer for billing (SPEC guardrail 12).

Events: document_generated / exit_a / exit_b_requested / exit_b_validated.
billing_period is 'YYYY-MM' of the moment the event occurred.

After every document_generated event the gestora's monthly count is checked
against its tier limit (models/billing.py) and a usage alert email is sent to
the gestora's billing_email at the 80% and 100% thresholds — idempotent per
(gestora, period, threshold) via the usage_alerts table (006_usage_alerts.sql).
Alert failures NEVER block the request flow.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from models.billing import USAGE_ALERT_THRESHOLDS, tier_limits
from models.schema import UsageEventType
from services import db as dbmod
from services import email_service

logger = logging.getLogger("lolailo.usage")


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
    billing_period = current_billing_period()
    row = db.insert(
        "usage_events",
        {
            "gestora_id": gestora_id,
            "request_id": request_id,
            "event_type": UsageEventType(event_type).value,
            "billing_period": billing_period,
        },
    )
    if UsageEventType(event_type) is UsageEventType.document_generated:
        try:
            check_usage_alerts(db, gestora_id=gestora_id, billing_period=billing_period)
        except Exception:  # noqa: BLE001 — alerts are best-effort by design
            logger.exception(
                "Usage alert check failed for gestora %s (event recording continues)",
                gestora_id,
            )
    return row


def _alert_already_sent(
    db: dbmod.Database, gestora_id: str, billing_period: str, threshold: int
) -> bool:
    return bool(
        db.select(
            "usage_alerts",
            gestora_id=gestora_id,
            billing_period=billing_period,
            threshold=threshold,
        )
    )


def check_usage_alerts(
    db: dbmod.Database, *, gestora_id: str, billing_period: str
) -> int:
    """Send any due usage alerts for one gestora+period. Returns emails sent.

    A threshold T is due when docs_generated >= ceil(limit * T / 100) and no
    usage_alerts row exists yet for (gestora, period, T) — that row is the
    idempotency guard (UNIQUE in Postgres, select-then-insert in DevStore).
    Unlimited tiers (custom) and gestoras without billing_email never alert.
    """
    gestora = db.get("gestoras", gestora_id)
    if gestora is None:
        return 0
    limit = tier_limits(gestora.get("subscription_tier")).docs_per_month
    if limit is None:
        return 0  # custom tier: unlimited, nothing to alert on
    billing_email = gestora.get("billing_email")
    if not billing_email:
        logger.warning(
            "Gestora %s has no billing_email; skipping usage alert", gestora_id
        )
        return 0

    docs_generated = len(
        db.select(
            "usage_events",
            gestora_id=gestora_id,
            billing_period=billing_period,
            event_type=UsageEventType.document_generated.value,
        )
    )

    sent = 0
    for threshold in USAGE_ALERT_THRESHOLDS:
        if docs_generated < math.ceil(limit * threshold / 100):
            continue
        if _alert_already_sent(db, gestora_id, billing_period, threshold):
            continue
        email_service.send_usage_alert(
            gestora_name=gestora.get("name", ""),
            billing_email=billing_email,
            billing_period=billing_period,
            threshold=threshold,
            docs_generated=docs_generated,
            docs_limit=limit,
        )
        db.insert(
            "usage_alerts",
            {
                "gestora_id": gestora_id,
                "billing_period": billing_period,
                "threshold": threshold,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        sent += 1
    return sent
