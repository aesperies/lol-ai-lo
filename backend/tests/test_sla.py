"""Counsel SLA tests (improvement #8): request timestamps, the idempotent
sweep (reminder -> assigned counsel, escalation -> backup), and the admin
response-metrics endpoint."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from services import sla
from tests.conftest import auth


def hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def to_counsel_review(wf, client, seed) -> str:
    request_id, _ = wf.to_review_pending()
    response = client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"]))
    assert response.status_code == 200, response.text
    return request_id


def sla_audit_entries(db, kind: str) -> list[dict[str, Any]]:
    return [
        row
        for row in db.select("audit_log", action="counsel_notified")
        if (row.get("metadata") or {}).get("sla") == kind
    ]


@pytest.fixture()
def counsel_b(db) -> dict[str, Any]:
    return db.insert(
        "users", {"email": "abogado2@lolailolegal.es", "role": "counsel", "gestora_id": None}
    )


def assign(client, seed, *, counsel: dict, is_primary: bool = False):
    response = client.post(
        "/api/counsel-assignments",
        json={
            "gestora_id": seed["gestora_a"]["id"],
            "counsel_user_id": counsel["id"],
            "is_primary": is_primary,
        },
        headers=auth(seed["admin"]),
    )
    assert response.status_code == 201, response.text


class TestSlaTimestamps:
    def test_exit_b_stamps_counsel_requested_at(self, wf, client, db, seed):
        request_id = to_counsel_review(wf, client, seed)
        row = db.get("requests", request_id)
        assert row["counsel_requested_at"] is not None
        assert row["counsel_validated_at"] is None

    def test_validation_stamps_counsel_validated_at(self, wf, client, db, seed):
        request_id = to_counsel_review(wf, client, seed)
        assert client.post(f"/api/requests/{request_id}/validate", headers=auth(seed["counsel"])).status_code == 200
        row = db.get("requests", request_id)
        assert row["counsel_validated_at"] is not None


class TestSlaSweep:
    def test_fresh_request_triggers_nothing(self, wf, client, db, seed):
        to_counsel_review(wf, client, seed)
        result = sla.run_sla_sweep(db)
        assert result == {"reminders_sent": 0, "escalations_sent": 0}
        assert db.select("sla_events") == []

    def test_reminder_past_threshold(self, wf, client, db, seed):
        request_id = to_counsel_review(wf, client, seed)
        # Pending for 30h: past the 24h reminder, below the 56h escalation.
        db.update("requests", request_id, {"counsel_requested_at": hours_ago(30)})

        result = sla.run_sla_sweep(db)
        assert result == {"reminders_sent": 1, "escalations_sent": 0}

        events = db.select("sla_events", request_id=request_id)
        assert len(events) == 1
        assert events[0]["kind"] == "reminder"
        # No assignment -> broadcast to the only counsel user.
        assert events[0]["recipient_email"] == seed["counsel"]["email"]

        entries = sla_audit_entries(db, "reminder")
        assert len(entries) == 1
        assert entries[0]["metadata"]["hours_pending"] == pytest.approx(30, abs=0.5)
        assert entries[0]["metadata"]["to"] == seed["counsel"]["email"]

    def test_escalation_goes_to_backup_counsel(self, wf, client, db, seed, counsel_b):
        assign(client, seed, counsel=seed["counsel"], is_primary=True)
        assign(client, seed, counsel=counsel_b)

        request_id = to_counsel_review(wf, client, seed)
        # Pending for 60h: past both thresholds (48h SLA + 8h grace = 56h).
        db.update("requests", request_id, {"counsel_requested_at": hours_ago(60)})

        result = sla.run_sla_sweep(db)
        assert result == {"reminders_sent": 1, "escalations_sent": 1}

        events = {e["kind"]: e for e in db.select("sla_events", request_id=request_id)}
        # Reminder -> assigned (primary) counsel; escalation -> the BACKUP.
        assert events["reminder"]["recipient_email"] == seed["counsel"]["email"]
        assert events["escalation"]["recipient_email"] == counsel_b["email"]

        escalations = sla_audit_entries(db, "escalation")
        assert len(escalations) == 1
        assert escalations[0]["metadata"]["routing"] == "backup"

    def test_escalation_broadcasts_without_backup(self, wf, client, db, seed):
        request_id = to_counsel_review(wf, client, seed)
        db.update("requests", request_id, {"counsel_requested_at": hours_ago(60)})

        sla.run_sla_sweep(db)
        escalations = db.select("sla_events", request_id=request_id, kind="escalation")
        assert [e["recipient_email"] for e in escalations] == [seed["counsel"]["email"]]
        assert sla_audit_entries(db, "escalation")[0]["metadata"]["routing"] == "broadcast"

    def test_sweep_is_idempotent(self, wf, client, db, seed):
        request_id = to_counsel_review(wf, client, seed)
        db.update("requests", request_id, {"counsel_requested_at": hours_ago(60)})

        first = sla.run_sla_sweep(db)
        assert first == {"reminders_sent": 1, "escalations_sent": 1}
        before = len(db.select("sla_events"))

        second = sla.run_sla_sweep(db)
        assert second == {"reminders_sent": 0, "escalations_sent": 0}
        assert len(db.select("sla_events")) == before

    def test_sweep_endpoint_admin_only(self, wf, client, db, seed):
        request_id = to_counsel_review(wf, client, seed)
        db.update("requests", request_id, {"counsel_requested_at": hours_ago(30)})

        for user in (seed["client_a"], seed["counsel"]):
            assert client.post("/api/admin/sla/sweep", headers=auth(user)).status_code == 403

        response = client.post("/api/admin/sla/sweep", headers=auth(seed["admin"]))
        assert response.status_code == 200
        assert response.json() == {"reminders_sent": 1, "escalations_sent": 0}


class TestSlaReport:
    def test_admin_only(self, client, seed):
        for user in (seed["client_a"], seed["counsel"]):
            assert client.get("/api/admin/sla", headers=auth(user)).status_code == 403
        assert client.get("/api/admin/sla", headers=auth(seed["admin"])).status_code == 200

    def test_response_metrics_math(self, wf, client, db, seed):
        # One completed validation that took ~10h.
        validated_id = to_counsel_review(wf, client, seed)
        db.update("requests", validated_id, {"counsel_requested_at": hours_ago(10)})
        assert client.post(f"/api/requests/{validated_id}/validate", headers=auth(seed["counsel"])).status_code == 200

        # One review pending for 50h (past the 48h SLA), with a reminder sent.
        pending_id = to_counsel_review(wf, client, seed)
        db.update("requests", pending_id, {"counsel_requested_at": hours_ago(50)})
        assert sla.run_sla_sweep(db) == {"reminders_sent": 1, "escalations_sent": 0}

        report = client.get("/api/admin/sla", headers=auth(seed["admin"])).json()
        assert report["sla_hours"] == 48

        overall = report["overall"]
        assert overall["pending"] == 1
        assert overall["past_sla"] == 1
        assert overall["avg_validation_hours"] == pytest.approx(10, abs=0.5)
        assert overall["reminders_sent"] == 1
        assert overall["escalations_sent"] == 0

        by_counsel = {r["counsel_email"]: r for r in report["by_counsel"]}
        row = by_counsel[seed["counsel"]["email"]]
        assert row["pending"] == 1  # broadcast pending attributed to the counsel
        assert row["past_sla"] == 1
        assert row["avg_validation_hours"] == pytest.approx(10, abs=0.5)
        assert row["reminders_sent"] == 1
