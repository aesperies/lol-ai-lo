"""Billing dashboard tests (improvement #7): per-gestora aggregation over
usage_events, tier limits, overage pricing, CSV export, the client /api/my/usage
silo, and the 80%/100% usage alert emails (idempotent, never-blocking)."""
from __future__ import annotations

from typing import Any

import pytest

import config
from models.schema import UsageEventType
from services import email_service, usage
from tests.conftest import auth

PERIOD_MAY = "2026-05"
PERIOD_JUNE = "2026-06"


def seed_events(db, gestora: dict, event_type: str, period: str, count: int) -> None:
    for _ in range(count):
        db.insert(
            "usage_events",
            {
                "gestora_id": gestora["id"],
                "request_id": None,
                "event_type": event_type,
                "billing_period": period,
            },
        )


@pytest.fixture()
def seeded_events(db, seed) -> None:
    """Two gestoras x two periods.

    May:  A (growth, limit 75): 10 docs, 4 exit A, 3 exit B req, 2 exit B val.
          B (starter, limit 20): 25 docs (5 over), 5 exit A, 5 exit B req.
    June: A: 2 docs. B: nothing.
    """
    seed_events(db, seed["gestora_a"], "document_generated", PERIOD_MAY, 10)
    seed_events(db, seed["gestora_a"], "exit_a", PERIOD_MAY, 4)
    seed_events(db, seed["gestora_a"], "exit_b_requested", PERIOD_MAY, 3)
    seed_events(db, seed["gestora_a"], "exit_b_validated", PERIOD_MAY, 2)
    seed_events(db, seed["gestora_b"], "document_generated", PERIOD_MAY, 25)
    seed_events(db, seed["gestora_b"], "exit_a", PERIOD_MAY, 5)
    seed_events(db, seed["gestora_b"], "exit_b_requested", PERIOD_MAY, 5)
    seed_events(db, seed["gestora_a"], "document_generated", PERIOD_JUNE, 2)


def billing_rows(client, admin: dict, period: str | None = None) -> dict[str, dict]:
    query = f"?period={period}" if period else ""
    response = client.get(f"/api/admin/billing{query}", headers=auth(admin))
    assert response.status_code == 200, response.text
    return {row["gestora_id"]: row for row in response.json()["rows"]}


class TestBillingReport:
    def test_admin_only(self, client, seed):
        for user in (seed["client_a"], seed["counsel"]):
            assert client.get("/api/admin/billing", headers=auth(user)).status_code == 403
            assert client.get("/api/admin/billing/periods", headers=auth(user)).status_code == 403
            assert client.get("/api/admin/billing/export", headers=auth(user)).status_code == 403

    def test_invalid_period_rejected(self, client, seed):
        response = client.get("/api/admin/billing?period=2026-13", headers=auth(seed["admin"]))
        assert response.status_code == 422

    def test_per_gestora_aggregation_math(self, client, seed, seeded_events):
        rows = billing_rows(client, seed["admin"], PERIOD_MAY)

        a = rows[seed["gestora_a"]["id"]]
        assert a["gestora_name"] == seed["gestora_a"]["name"]
        assert a["subscription_tier"] == "growth"
        assert a["docs_generated"] == 10
        assert a["overage_docs"] == 0
        assert a["exit_a_count"] == 4
        assert a["exit_b_requested"] == 3
        assert a["exit_b_validated"] == 2
        assert a["fund_count"] == 1
        assert a["over_funds_limit"] is False
        assert a["estimated_overage_eur"] == 0.0

        b = rows[seed["gestora_b"]["id"]]
        assert b["subscription_tier"] == "starter"
        assert b["docs_generated"] == 25
        assert b["overage_docs"] == 5  # 25 - starter limit 20
        assert b["exit_a_count"] == 5
        assert b["exit_b_requested"] == 5
        assert b["exit_b_validated"] == 0
        # Prices unset (default 0 = TBD): the estimate stays 0.
        assert b["estimated_overage_eur"] == 0.0

    def test_period_filter(self, client, seed, seeded_events):
        rows = billing_rows(client, seed["admin"], PERIOD_JUNE)
        assert rows[seed["gestora_a"]["id"]]["docs_generated"] == 2
        # Every gestora appears even with zero events in the period.
        assert rows[seed["gestora_b"]["id"]]["docs_generated"] == 0
        assert rows[seed["gestora_b"]["id"]]["overage_docs"] == 0

    def test_default_period_is_current(self, client, seed, seeded_events):
        response = client.get("/api/admin/billing", headers=auth(seed["admin"]))
        assert response.json()["period"] == usage.current_billing_period()

    def test_limits_by_tier(self, client, db, seed):
        custom = db.insert(
            "gestoras", {"name": "Gestora Custom", "subscription_tier": "custom"}
        )
        rows = billing_rows(client, seed["admin"], PERIOD_MAY)
        starter = rows[seed["gestora_b"]["id"]]
        growth = rows[seed["gestora_a"]["id"]]
        unlimited = rows[custom["id"]]
        assert (starter["docs_limit"], starter["funds_limit"]) == (20, 2)
        assert (growth["docs_limit"], growth["funds_limit"]) == (75, 5)
        assert (unlimited["docs_limit"], unlimited["funds_limit"]) == (None, None)
        assert unlimited["over_funds_limit"] is False

    def test_over_funds_limit_flag(self, client, db, seed):
        # Starter allows 2 funds; give gestora B a third.
        for name in ("Beta Fund II", "Beta Fund III"):
            db.insert(
                "funds",
                {"gestora_id": seed["gestora_b"]["id"], "name": name, "jurisdiction": "España"},
            )
        rows = billing_rows(client, seed["admin"], PERIOD_MAY)
        b = rows[seed["gestora_b"]["id"]]
        assert b["fund_count"] == 3
        assert b["over_funds_limit"] is True

    def test_overage_pricing(self, client, seed, seeded_events, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "price_exit_a_eur", 10.0)
        monkeypatch.setattr(config.get_settings(), "price_exit_b_eur", 40.0)
        rows = billing_rows(client, seed["admin"], PERIOD_MAY)
        # B: 5 overage docs split 5:5 between exit A and exit B counts ->
        # 2.5 x 10 + 2.5 x 40 = 125.
        assert rows[seed["gestora_b"]["id"]]["estimated_overage_eur"] == 125.0
        # A is within its limit: no overage regardless of prices.
        assert rows[seed["gestora_a"]["id"]]["estimated_overage_eur"] == 0.0

    def test_overage_without_exits_priced_at_exit_a(self, client, db, seed, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "price_exit_a_eur", 10.0)
        monkeypatch.setattr(config.get_settings(), "price_exit_b_eur", 40.0)
        # 22 docs, no exit events at all -> 2 overage docs at the Exit A price.
        seed_events(db, seed["gestora_b"], "document_generated", PERIOD_MAY, 22)
        rows = billing_rows(client, seed["admin"], PERIOD_MAY)
        assert rows[seed["gestora_b"]["id"]]["estimated_overage_eur"] == 20.0


class TestBillingPeriods:
    def test_distinct_periods_newest_first(self, client, seed, seeded_events):
        response = client.get("/api/admin/billing/periods", headers=auth(seed["admin"]))
        assert response.status_code == 200
        periods = response.json()["periods"]
        # Distinct event periods plus the current one, newest first.
        expected = sorted({PERIOD_MAY, PERIOD_JUNE, usage.current_billing_period()}, reverse=True)
        assert periods == expected


class TestBillingExport:
    def test_csv_content_and_content_type(self, client, seed, seeded_events):
        response = client.get(
            f"/api/admin/billing/export?period={PERIOD_MAY}", headers=auth(seed["admin"])
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert f'billing-{PERIOD_MAY}.csv' in response.headers["content-disposition"]

        lines = response.text.strip().splitlines()
        header = lines[0].split(",")
        assert header[:6] == [
            "gestora_id",
            "gestora_name",
            "subscription_tier",
            "docs_generated",
            "docs_limit",
            "overage_docs",
        ]
        assert len(lines) == 3  # header + one row per gestora
        b_line = next(l for l in lines if seed["gestora_b"]["id"] in l)
        cells = b_line.split(",")
        assert cells[header.index("docs_generated")] == "25"
        assert cells[header.index("overage_docs")] == "5"
        assert cells[header.index("subscription_tier")] == "starter"


class TestMyUsage:
    def test_client_sees_only_own_gestora(self, client, db, seed):
        period = usage.current_billing_period()
        seed_events(db, seed["gestora_a"], "document_generated", period, 3)
        seed_events(db, seed["gestora_b"], "document_generated", period, 7)

        res_a = client.get("/api/my/usage", headers=auth(seed["client_a"]))
        assert res_a.status_code == 200
        body_a = res_a.json()
        assert body_a == {
            "billing_period": period,
            "subscription_tier": "growth",
            "docs_generated": 3,  # gestora B's 7 events never leak in
            "docs_limit": 75,
        }

        res_b = client.get("/api/my/usage", headers=auth(seed["client_b"]))
        assert res_b.json()["docs_generated"] == 7
        assert res_b.json()["docs_limit"] == 20

    def test_counsel_and_admin_get_403(self, client, seed):
        for user in (seed["counsel"], seed["admin"]):
            assert client.get("/api/my/usage", headers=auth(user)).status_code == 403


class TestUsageAlerts:
    @pytest.fixture()
    def alert_calls(self, monkeypatch) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []

        def fake_send_usage_alert(**kwargs: Any) -> dict:
            calls.append(kwargs)
            return {"delivery": "console", "to": kwargs["billing_email"]}

        monkeypatch.setattr(email_service, "send_usage_alert", fake_send_usage_alert)
        return calls

    @pytest.fixture()
    def gestora_b_billable(self, db, seed) -> dict[str, Any]:
        """Gestora B (starter, limit 20 -> thresholds at 16 and 20 docs)."""
        return db.update(
            "gestoras", seed["gestora_b"]["id"], {"billing_email": "billing@beta.es"}
        )

    def record_generated(self, db, gestora: dict, times: int) -> None:
        for _ in range(times):
            usage.record_usage(
                db,
                gestora_id=gestora["id"],
                request_id=None,
                event_type=UsageEventType.document_generated,
            )

    def test_80_and_100_alerts_fire_exactly_once(self, db, seed, gestora_b_billable, alert_calls):
        gestora = gestora_b_billable

        self.record_generated(db, gestora, 15)
        assert alert_calls == []  # 15/20 = 75%: below the first threshold

        self.record_generated(db, gestora, 1)  # 16/20 = 80%
        assert len(alert_calls) == 1
        assert alert_calls[0]["threshold"] == 80
        assert alert_calls[0]["billing_email"] == "billing@beta.es"
        assert alert_calls[0]["docs_generated"] == 16
        assert alert_calls[0]["docs_limit"] == 20

        self.record_generated(db, gestora, 3)  # 17..19: no re-fire
        assert len(alert_calls) == 1

        self.record_generated(db, gestora, 1)  # 20/20 = 100%
        assert len(alert_calls) == 2
        assert alert_calls[1]["threshold"] == 100
        assert alert_calls[1]["docs_generated"] == 20

        self.record_generated(db, gestora, 2)  # past the limit: no re-fire
        assert len(alert_calls) == 2

        sent = db.select("usage_alerts", gestora_id=gestora["id"])
        assert sorted(a["threshold"] for a in sent) == [80, 100]

    def test_custom_tier_never_alerts(self, db, seed, alert_calls):
        custom = db.insert(
            "gestoras",
            {
                "name": "Gestora Custom",
                "subscription_tier": "custom",
                "billing_email": "billing@custom.es",
            },
        )
        self.record_generated(db, custom, 30)
        assert alert_calls == []
        assert db.select("usage_alerts", gestora_id=custom["id"]) == []

    def test_other_event_types_do_not_alert(self, db, seed, gestora_b_billable, alert_calls):
        for event_type in (
            UsageEventType.exit_a,
            UsageEventType.exit_b_requested,
            UsageEventType.exit_b_validated,
        ):
            for _ in range(25):
                usage.record_usage(
                    db,
                    gestora_id=gestora_b_billable["id"],
                    request_id=None,
                    event_type=event_type,
                )
        assert alert_calls == []

    def test_alert_failure_never_blocks_event_recording(
        self, db, seed, gestora_b_billable, monkeypatch
    ):
        def boom(**kwargs: Any) -> dict:
            raise RuntimeError("email provider exploded")

        monkeypatch.setattr(email_service, "send_usage_alert", boom)
        self.record_generated(db, gestora_b_billable, 16)  # crosses 80%

        events = db.select(
            "usage_events",
            gestora_id=gestora_b_billable["id"],
            event_type="document_generated",
        )
        assert len(events) == 16  # every event recorded despite the failure
        # Nothing persisted as sent: the alert can retry on the next event.
        assert db.select("usage_alerts", gestora_id=gestora_b_billable["id"]) == []
