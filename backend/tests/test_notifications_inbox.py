"""In-app notifications (016): emisión en eventos clave + endpoints de bandeja."""
from __future__ import annotations

from tests.conftest import auth


def _to_counsel_review(client, seed, wf) -> str:
    rid, _ = wf.to_review_pending(user=seed["client_a"], fund=seed["fund_a"])
    assert client.post(f"/api/requests/{rid}/exit-b", headers=auth(seed["client_a"])).status_code == 200
    return rid


class TestEmission:
    def test_exit_b_notifies_counsel(self, client, seed, wf):
        _to_counsel_review(client, seed, wf)
        res = client.get("/api/notifications/inbox", headers=auth(seed["counsel"]))
        assert res.status_code == 200
        kinds = [n["kind"] for n in res.json()]
        assert "counsel_requested" in kinds

    def test_validation_notifies_owner(self, client, seed, wf):
        rid = _to_counsel_review(client, seed, wf)
        assert client.post(f"/api/requests/{rid}/validate", headers=auth(seed["counsel"])).status_code == 200
        res = client.get("/api/notifications/inbox", headers=auth(seed["client_a"]))
        assert "document_validated" in [n["kind"] for n in res.json()]

    def test_comment_notifies_owner(self, client, seed, wf):
        rid = _to_counsel_review(client, seed, wf)
        client.post(
            f"/api/requests/{rid}/comments", headers=auth(seed["counsel"]),
            json={"text": "Revisa la cláusula 4, por favor."},
        )
        inbox = client.get("/api/notifications/inbox", headers=auth(seed["client_a"])).json()
        comment = next(n for n in inbox if n["kind"] == "comment_added")
        assert "cláusula 4" in comment["body"]


class TestInbox:
    def test_isolation_between_users(self, client, seed, wf):
        _to_counsel_review(client, seed, wf)
        res = client.get("/api/notifications/inbox", headers=auth(seed["client_b"]))
        assert res.json() == []

    def test_unread_count_and_mark_read(self, client, seed, wf):
        rid = _to_counsel_review(client, seed, wf)
        client.post(f"/api/requests/{rid}/validate", headers=auth(seed["counsel"]))
        res = client.get("/api/notifications/inbox/unread-count", headers=auth(seed["client_a"]))
        assert res.json()["unread"] >= 1

        res = client.post("/api/notifications/read", headers=auth(seed["client_a"]), json={"ids": None})
        assert res.json()["marked"] >= 1
        res = client.get("/api/notifications/inbox/unread-count", headers=auth(seed["client_a"]))
        assert res.json()["unread"] == 0

    def test_mark_read_cannot_touch_other_users(self, client, seed, wf):
        _to_counsel_review(client, seed, wf)  # notifica al counsel
        ids = [n["id"] for n in client.get("/api/notifications/inbox", headers=auth(seed["counsel"])).json()]
        res = client.post("/api/notifications/read", headers=auth(seed["client_b"]), json={"ids": ids})
        assert res.json()["marked"] == 0
