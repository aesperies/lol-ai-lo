"""Counsel↔gestora assignment tests: Exit B routing (primary -> backup ->
broadcast), gestora isolation of assignments, and admin-only management."""
from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import auth


@pytest.fixture()
def counsel_b(db) -> dict[str, Any]:
    """Second counsel user (the seed fixture provides one)."""
    return db.insert(
        "users", {"email": "abogado2@lolailolegal.es", "role": "counsel", "gestora_id": None}
    )


def assign(client, seed, *, gestora: dict, counsel: dict, is_primary: bool = False):
    return client.post(
        "/api/counsel-assignments",
        json={
            "gestora_id": gestora["id"],
            "counsel_user_id": counsel["id"],
            "is_primary": is_primary,
        },
        headers=auth(seed["admin"]),
    )


def counsel_notified_entries(db) -> list[dict[str, Any]]:
    return [row for row in db.select("audit_log") if row["action"] == "counsel_notified"]


class TestExitBRouting:
    def test_routing_picks_primary(self, wf, client, db, seed, counsel_b):
        assert assign(client, seed, gestora=seed["gestora_a"], counsel=seed["counsel"], is_primary=True).status_code == 201
        assert assign(client, seed, gestora=seed["gestora_a"], counsel=counsel_b).status_code == 201

        request_id, _ = wf.to_review_pending()
        assert client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"])).status_code == 200

        entries = counsel_notified_entries(db)
        assert len(entries) == 1
        assert entries[0]["metadata"]["routing"] == "primary"
        assert entries[0]["metadata"]["recipients"] == [seed["counsel"]["email"]]
        assert entries[0]["metadata"]["to"] == seed["counsel"]["email"]

    def test_routing_falls_back_to_backup(self, wf, client, db, seed, counsel_b):
        # Backup-only assignment (no primary) for gestora A.
        assert assign(client, seed, gestora=seed["gestora_a"], counsel=counsel_b).status_code == 201

        request_id, _ = wf.to_review_pending()
        assert client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"])).status_code == 200

        entries = counsel_notified_entries(db)
        assert len(entries) == 1
        assert entries[0]["metadata"]["routing"] == "backup"
        assert entries[0]["metadata"]["recipients"] == [counsel_b["email"]]

    def test_routing_broadcasts_without_assignment(self, wf, client, db, seed, counsel_b):
        # Assignments on ANOTHER gestora must not affect gestora A's routing.
        assert assign(client, seed, gestora=seed["gestora_b"], counsel=counsel_b, is_primary=True).status_code == 201

        request_id, _ = wf.to_review_pending()
        assert client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"])).status_code == 200

        entries = counsel_notified_entries(db)
        assert {e["metadata"]["routing"] for e in entries} == {"broadcast"}
        notified = {e["metadata"]["to"] for e in entries}
        assert notified == {seed["counsel"]["email"], counsel_b["email"]}

    def test_new_primary_demotes_old_primary(self, client, db, seed, counsel_b):
        assert assign(client, seed, gestora=seed["gestora_a"], counsel=seed["counsel"], is_primary=True).status_code == 201
        assert assign(client, seed, gestora=seed["gestora_a"], counsel=counsel_b, is_primary=True).status_code == 201

        rows = db.select("counsel_assignments", gestora_id=seed["gestora_a"]["id"])
        primaries = [r for r in rows if r["is_primary"]]
        assert len(primaries) == 1
        assert primaries[0]["counsel_user_id"] == counsel_b["id"]


class TestAssignmentAccess:
    def test_client_cannot_read_other_gestora_assignments(self, client, seed, counsel_b):
        assert assign(client, seed, gestora=seed["gestora_b"], counsel=counsel_b, is_primary=True).status_code == 201

        # 404 (not 403): other gestoras' data is never discoverable.
        response = client.get(
            f"/api/counsel-assignments?gestora_id={seed['gestora_b']['id']}",
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 404

        # Own gestora is readable (intake form shows the assigned counsel).
        own = client.get(
            f"/api/counsel-assignments?gestora_id={seed['gestora_a']['id']}",
            headers=auth(seed["client_a"]),
        )
        assert own.status_code == 200

    def test_non_admin_cannot_create_assignments(self, client, seed):
        for user in (seed["client_a"], seed["counsel"]):
            response = client.post(
                "/api/counsel-assignments",
                json={
                    "gestora_id": seed["gestora_a"]["id"],
                    "counsel_user_id": seed["counsel"]["id"],
                    "is_primary": True,
                },
                headers=auth(user),
            )
            assert response.status_code == 403

    def test_assigning_client_role_user_is_rejected(self, client, db, seed):
        response = assign(client, seed, gestora=seed["gestora_a"], counsel=seed["client_b"], is_primary=True)
        assert response.status_code == 422
        assert db.select("counsel_assignments") == []


class TestMyCounsel:
    def test_my_counsel_prefers_primary(self, client, seed, counsel_b):
        assert assign(client, seed, gestora=seed["gestora_a"], counsel=counsel_b).status_code == 201
        assert assign(client, seed, gestora=seed["gestora_a"], counsel=seed["counsel"], is_primary=True).status_code == 201

        response = client.get("/api/my/counsel", headers=auth(seed["client_a"]))
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == seed["counsel"]["email"]
        assert body["is_primary"] is True
        assert body["turnaround_hours"] == 48

    def test_my_counsel_null_without_assignment(self, client, seed):
        response = client.get("/api/my/counsel", headers=auth(seed["client_a"]))
        assert response.status_code == 200
        assert response.json() is None
