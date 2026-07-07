"""Billing dashboard over usage_events (improvement #7).

Admin-only views of per-gestora monthly consumption (document_generated /
exit_a / exit_b_requested / exit_b_validated events, SPEC PRICING STRUCTURE)
plus the client-facing /api/my/usage consumption widget.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response

from auth import require_admin, require_client
from config import get_settings
from models.billing import BillingRowOut, MyUsageOut, tier_limits
from models.schema import SubscriptionTier, UsageEventType, User
from services import db as dbmod
from services import usage

router = APIRouter(prefix="/api", tags=["billing"])

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# Column order of both the JSON rows and the CSV export (kept in sync).
_BILLING_COLUMNS = list(BillingRowOut.model_fields.keys())


def _validate_period(period: Optional[str]) -> str:
    """Default = current period derived from the request date; 422 otherwise."""
    if period is None:
        return usage.current_billing_period()
    if not _PERIOD_RE.match(period):
        raise HTTPException(status_code=422, detail="period must be YYYY-MM")
    return period


def estimated_overage_eur(
    *, overage_docs: int, exit_a_count: int, exit_b_count: int
) -> float:
    """Estimated overage cost in EUR for one gestora+period.

    Formula (kept deliberately simple): the overage docs are split between
    the Exit A and Exit B prices proportionally to the period's exit counts —

        overage_a = overage_docs * exit_a_count / (exit_a_count + exit_b_count)
        overage_b = overage_docs - overage_a
        estimate  = overage_a * PRICE_EXIT_A_EUR + overage_b * PRICE_EXIT_B_EUR

    With no exit events in the period the whole overage is priced at the
    Exit A (lower) price. Returns 0 while the prices are unset (default 0 =
    TBD per SPEC). This is an ESTIMATE for the dashboard, not an invoice.
    """
    settings = get_settings()
    if overage_docs <= 0:
        return 0.0
    exits_total = exit_a_count + exit_b_count
    if exits_total > 0:
        overage_a = overage_docs * exit_a_count / exits_total
        overage_b = overage_docs - overage_a
    else:
        overage_a, overage_b = float(overage_docs), 0.0
    return round(
        overage_a * settings.price_exit_a_eur + overage_b * settings.price_exit_b_eur, 2
    )


def _billing_rows(db: dbmod.Database, period: str) -> list[BillingRowOut]:
    """One row per gestora (every gestora appears, even with zero events)."""
    events = db.unscoped_select("usage_events", billing_period=period)
    by_gestora: dict[str, dict[str, int]] = {}
    for event in events:
        counts = by_gestora.setdefault(event["gestora_id"], {})
        counts[event["event_type"]] = counts.get(event["event_type"], 0) + 1

    rows: list[BillingRowOut] = []
    for gestora in db.select("gestoras"):
        counts = by_gestora.get(gestora["id"], {})
        limits = tier_limits(gestora.get("subscription_tier"))
        docs_generated = counts.get(UsageEventType.document_generated.value, 0)
        exit_a_count = counts.get(UsageEventType.exit_a.value, 0)
        exit_b_requested = counts.get(UsageEventType.exit_b_requested.value, 0)
        overage_docs = (
            max(0, docs_generated - limits.docs_per_month)
            if limits.docs_per_month is not None
            else 0
        )
        fund_count = len(db.select("funds", gestora_id=gestora["id"]))
        rows.append(
            BillingRowOut(
                gestora_id=gestora["id"],
                gestora_name=gestora.get("name"),
                subscription_tier=gestora.get("subscription_tier")
                or SubscriptionTier.starter.value,
                docs_generated=docs_generated,
                docs_limit=limits.docs_per_month,
                overage_docs=overage_docs,
                exit_a_count=exit_a_count,
                exit_b_requested=exit_b_requested,
                exit_b_validated=counts.get(UsageEventType.exit_b_validated.value, 0),
                fund_count=fund_count,
                funds_limit=limits.funds,
                over_funds_limit=limits.funds is not None and fund_count > limits.funds,
                estimated_overage_eur=estimated_overage_eur(
                    overage_docs=overage_docs,
                    exit_a_count=exit_a_count,
                    exit_b_count=exit_b_requested,
                ),
            )
        )
    rows.sort(key=lambda r: (r.gestora_name or "", r.gestora_id))
    return rows


# ---------------------------------------------------------------------------
# Admin: per-gestora billing report + period selector + CSV export
# ---------------------------------------------------------------------------

@router.get("/admin/billing")
async def billing_report(
    period: Optional[str] = None,
    user: User = Depends(require_admin),
) -> Any:
    """Per-gestora consumption for one billing period (default: current)."""
    db = dbmod.get_db()
    effective_period = _validate_period(period)
    return {
        "period": effective_period,
        "rows": [row.model_dump() for row in _billing_rows(db, effective_period)],
    }


@router.get("/admin/billing/periods")
async def billing_periods(user: User = Depends(require_admin)) -> Any:
    """Distinct billing periods present in usage_events (newest first), for
    the period selector. Always includes the current period."""
    db = dbmod.get_db()
    periods = {e["billing_period"] for e in db.unscoped_select("usage_events")}
    periods.add(usage.current_billing_period())
    return {"periods": sorted(periods, reverse=True)}


@router.get("/admin/billing/export")
async def billing_export(
    period: Optional[str] = None,
    user: User = Depends(require_admin),
) -> Response:
    """CSV download of the billing report: one row per gestora, columns
    matching the JSON report.

    TODO: replace with Stripe invoice items integration (push overage_docs ×
    price as invoice items per gestora instead of a manual CSV handoff).
    """
    db = dbmod.get_db()
    effective_period = _validate_period(period)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_BILLING_COLUMNS)
    writer.writeheader()
    for row in _billing_rows(db, effective_period):
        writer.writerow(row.model_dump())
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="billing-{effective_period}.csv"'
            )
        },
    )


# ---------------------------------------------------------------------------
# Client: my gestora's current-period consumption
# ---------------------------------------------------------------------------

@router.get("/my/usage", response_model=MyUsageOut)
async def my_usage(user: User = Depends(require_client)) -> Any:
    """The requesting client's gestora consumption for the CURRENT period.

    Silo-checked like the other /api/my endpoints: scoped to user.gestora_id
    (clients can never address another gestora); counsel/admin get 403 via
    require_client."""
    db = dbmod.get_db()
    gestora = db.get("gestoras", user.gestora_id) if user.gestora_id else None
    if gestora is None:
        raise HTTPException(status_code=404, detail="Gestora not found")
    period = usage.current_billing_period()
    limits = tier_limits(gestora.get("subscription_tier"))
    docs_generated = len(
        db.select(
            "usage_events",
            gestora_id=gestora["id"],
            billing_period=period,
            event_type=UsageEventType.document_generated.value,
        )
    )
    return MyUsageOut(
        billing_period=period,
        subscription_tier=gestora.get("subscription_tier") or SubscriptionTier.starter.value,
        docs_generated=docs_generated,
        docs_limit=limits.docs_per_month,
    )
