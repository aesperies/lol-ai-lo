"""Dashboard de gestora (Roadmap D): agregados scoped a la gestora del caller."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import auth


class TestDashboardStats:
    def test_empty_gestora(self, client, seed):
        res = client.get("/api/dashboard/stats", headers=auth(seed["client_a"]))
        assert res.status_code == 200
        body = res.json()
        assert body["counts"]["in_progress"] == 0
        assert body["upcoming_deadlines"] == []
        assert body["funds_count"] == 1

    def test_counts_deadlines_and_isolation(self, client, seed, wf, db):
        # Una solicitud esperando decisión del cliente…
        rid1, _ = wf.to_review_pending(user=seed["client_a"], fund=seed["fund_a"])
        # …y otra en validación con el SLA medio consumido.
        rid2, _ = wf.to_review_pending(user=seed["client_a"], fund=seed["fund_a"])
        client.post(f"/api/requests/{rid2}/exit-b", headers=auth(seed["client_a"]))
        old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        db.update("requests", rid2, {"counsel_requested_at": old})

        body = client.get("/api/dashboard/stats", headers=auth(seed["client_a"])).json()
        assert body["counts"]["awaiting_you"] == 1
        assert body["counts"]["in_counsel_review"] == 1
        deadline = body["upcoming_deadlines"][0]
        assert deadline["request_id"] == rid2
        assert 17 < deadline["hours_remaining"] < 19  # 48 - 30
        assert deadline["overdue"] is False
        assert body["recent_activity"], "la actividad de la gestora no puede estar vacía"

        # Aislamiento: la gestora B no ve nada de esto.
        body_b = client.get("/api/dashboard/stats", headers=auth(seed["client_b"])).json()
        assert body_b["counts"]["in_counsel_review"] == 0
        assert body_b["upcoming_deadlines"] == []

    def test_turnaround_after_validation(self, client, seed, wf, db):
        rid, _ = wf.to_review_pending(user=seed["client_a"], fund=seed["fund_a"])
        client.post(f"/api/requests/{rid}/exit-b", headers=auth(seed["client_a"]))
        start = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
        db.update("requests", rid, {"counsel_requested_at": start})
        assert client.post(f"/api/requests/{rid}/validate", headers=auth(seed["counsel"])).status_code == 200

        body = client.get("/api/dashboard/stats", headers=auth(seed["client_a"])).json()
        assert 9.5 < body["avg_validation_hours"] < 10.5
        assert body["counts"]["ready"] == 1

    def test_counsel_cannot_call(self, client, seed):
        assert client.get("/api/dashboard/stats", headers=auth(seed["counsel"])).status_code == 403
