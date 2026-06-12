"""Billing tier limits + billing DTOs (improvement #7, SPEC PRICING STRUCTURE).

Subscription per gestora/month (SPEC): Starter (2 funds, 20 docs),
Growth (5 funds, 75 docs), Custom (unlimited). Per-doc overage prices are
env-configured (PRICE_EXIT_A_EUR / PRICE_EXIT_B_EUR, config.py) and default
to 0 = TBD.

"Docs consumed in a period" = count of `document_generated` usage events
(refinements log this event too — they are billable generations).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from models.schema import SubscriptionTier


class TierLimits(BaseModel):
    """Monthly limits of one subscription tier. ``None`` = unlimited."""

    funds: Optional[int] = None
    docs_per_month: Optional[int] = None


# TODO: tiers TBD per SPEC PRICING STRUCTURE — confirm final numbers/prices
# with the SLP before launch.
TIER_LIMITS: dict[SubscriptionTier, TierLimits] = {
    SubscriptionTier.starter: TierLimits(funds=2, docs_per_month=20),
    SubscriptionTier.growth: TierLimits(funds=5, docs_per_month=75),
    SubscriptionTier.custom: TierLimits(funds=None, docs_per_month=None),
}


def tier_limits(tier: str | SubscriptionTier | None) -> TierLimits:
    """Limits for a gestora's tier; unknown/missing tiers behave as starter
    (the most conservative limit, mirroring the DB column default)."""
    try:
        return TIER_LIMITS[SubscriptionTier(tier)]
    except (ValueError, KeyError):
        return TIER_LIMITS[SubscriptionTier.starter]


# Usage-alert thresholds, in percent of the tier's monthly doc limit.
# Persisted per (gestora, period, threshold) in usage_alerts for idempotency.
USAGE_ALERT_THRESHOLDS: tuple[int, ...] = (80, 100)


class BillingRowOut(BaseModel):
    """One gestora's consumption in one billing period (GET /api/admin/billing)."""

    gestora_id: str
    gestora_name: Optional[str] = None
    subscription_tier: str
    docs_generated: int
    docs_limit: Optional[int] = None  # None = unlimited (custom tier)
    overage_docs: int
    exit_a_count: int
    exit_b_requested: int
    exit_b_validated: int
    fund_count: int
    funds_limit: Optional[int] = None  # None = unlimited (custom tier)
    over_funds_limit: bool = False
    estimated_overage_eur: float = 0.0


class MyUsageOut(BaseModel):
    """The requesting client's gestora consumption (GET /api/my/usage)."""

    billing_period: str
    subscription_tier: str
    docs_generated: int
    docs_limit: Optional[int] = None  # None = unlimited (custom tier)
