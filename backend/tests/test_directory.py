"""Directory endpoints (013): /api/gestoras, /api/funds, /api/users, plus the
counsel review surface (/api/counsel/queue, /review, /comments) and the manual
precedent-version supersede."""
from __future__ import annotations

from tests.conftest import DOC_TYPE, FREETEXT, auth, seed_precedent


class TestGestoras:
    def test_admin_sees_all(self, client, seed):
        res = client.get("/api/gestoras", headers=auth(seed["admin"]))
        assert res.status_code == 200
        names = {g["name"] for g in res.json()}
        assert {"Gestora Alfa", "Gestora Beta"} <= names

    def test_client_sees_only_own(self, client, seed):
        res = client.get("/api/gestoras", headers=auth(seed["client_a"]))
        assert res.status_code == 200
        assert [g["id"] for g in res.json()] == [seed["gestora_a"]["id"]]

    def test_admin_creates_gestora(self, client, seed, db):
        res = client.post(
            "/api/gestoras",
            headers=auth(seed["admin"]),
            json={"name": "Gestora Gamma", "subscription_tier": "growth",
                  "billing_email": "billing@gamma.es"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["name"] == "Gestora Gamma"
        assert db.get("gestoras", body["id"]) is not None
        actions = [r["action"] for r in db.unscoped_select("audit_log")]
        assert "gestora_created" in actions

    def test_client_cannot_create(self, client, seed):
        res = client.post(
            "/api/gestoras", headers=auth(seed["client_a"]), json={"name": "X"}
        )
        assert res.status_code == 403


class TestFunds:
    def test_client_sees_own_gestora_funds_only(self, client, seed):
        res = client.get("/api/funds", headers=auth(seed["client_a"]))
        assert res.status_code == 200
        assert [f["id"] for f in res.json()] == [seed["fund_a"]["id"]]

    def test_admin_sees_all_and_can_filter(self, client, seed):
        res = client.get("/api/funds", headers=auth(seed["admin"]))
        assert {f["id"] for f in res.json()} == {seed["fund_a"]["id"], seed["fund_b"]["id"]}
        res = client.get(
            f"/api/funds?gestora_id={seed['gestora_b']['id']}", headers=auth(seed["admin"])
        )
        assert [f["id"] for f in res.json()] == [seed["fund_b"]["id"]]

    def test_client_filter_param_ignored(self, client, seed):
        """A client may not use gestora_id to peek across silos."""
        res = client.get(
            f"/api/funds?gestora_id={seed['gestora_b']['id']}",
            headers=auth(seed["client_a"]),
        )
        assert [f["id"] for f in res.json()] == [seed["fund_a"]["id"]]


class TestFundCreation:
    def test_client_creates_fund_in_own_gestora(self, client, seed, db):
        res = client.post(
            "/api/funds",
            headers=auth(seed["client_a"]),
            json={"name": "Alfa Ventures II, FCR", "jurisdiction": "España"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["gestora_id"] == seed["gestora_a"]["id"]
        assert body["name"] == "Alfa Ventures II, FCR"
        actions = [r["action"] for r in db.unscoped_select("audit_log")]
        assert "fund_created" in actions

    def test_client_cannot_create_in_foreign_gestora(self, client, seed):
        res = client.post(
            "/api/funds",
            headers=auth(seed["client_a"]),
            json={"name": "Intruso FCR", "gestora_id": seed["gestora_b"]["id"]},
        )
        assert res.status_code == 403

    def test_new_fund_usable_for_requests(self, client, seed, wf):
        """El fondo recién creado sirve inmediatamente para el intake."""
        res = client.post(
            "/api/funds", headers=auth(seed["client_a"]), json={"name": "Alfa III, FCR"}
        )
        fund_id = res.json()["id"]
        res = client.post(
            "/api/requests",
            headers=auth(seed["client_a"]),
            json={"fund_id": fund_id, "doc_type": DOC_TYPE, "freetext": FREETEXT,
                  "validation_requested": False},
        )
        assert res.status_code == 201

    def test_admin_requires_gestora_id(self, client, seed):
        res = client.post(
            "/api/funds", headers=auth(seed["admin"]), json={"name": "Sin gestora"}
        )
        assert res.status_code == 422
        res = client.post(
            "/api/funds",
            headers=auth(seed["admin"]),
            json={"name": "Beta Growth I", "gestora_id": seed["gestora_b"]["id"]},
        )
        assert res.status_code == 201

    def test_counsel_cannot_create(self, client, seed):
        res = client.post(
            "/api/funds", headers=auth(seed["counsel"]), json={"name": "X"}
        )
        assert res.status_code == 403


class TestVehicles:
    def _create(self, client, seed, fund_key="fund_a", user_key="client_a", **kw):
        payload = {"name": "SPV Alfa I", "vehicle_type": "spv", **kw}
        return client.post(
            f"/api/funds/{seed[fund_key]['id']}/vehicles",
            headers=auth(seed[user_key]), json=payload,
        )

    def test_client_creates_and_lists_vehicle(self, client, seed, db):
        res = self._create(client, seed)
        assert res.status_code == 201
        res = client.get(
            f"/api/funds/{seed['fund_a']['id']}/vehicles", headers=auth(seed["client_a"])
        )
        assert [v["name"] for v in res.json()] == ["SPV Alfa I"]
        assert "vehicle_created" in [r["action"] for r in db.unscoped_select("audit_log")]

    def test_cross_gestora_fund_is_404(self, client, seed):
        res = self._create(client, seed, fund_key="fund_b")
        assert res.status_code == 404
        res = client.get(
            f"/api/funds/{seed['fund_b']['id']}/vehicles", headers=auth(seed["client_a"])
        )
        assert res.status_code == 404

    def test_update_and_delete_vehicle(self, client, seed):
        vid = self._create(client, seed).json()["id"]
        res = client.patch(
            f"/api/vehicles/{vid}", headers=auth(seed["client_a"]),
            json={"name": "SPV Alfa I bis", "vehicle_type": "feeder"},
        )
        assert res.status_code == 200 and res.json()["vehicle_type"] == "feeder"
        assert client.delete(f"/api/vehicles/{vid}", headers=auth(seed["client_a"])).status_code == 204

    def test_vehicle_with_requests_cannot_be_deleted(self, client, seed):
        vid = self._create(client, seed).json()["id"]
        res = client.post(
            "/api/requests", headers=auth(seed["client_a"]),
            json={"fund_id": seed["fund_a"]["id"], "vehicle_id": vid,
                  "doc_type": DOC_TYPE, "freetext": FREETEXT, "validation_requested": False},
        )
        assert res.status_code == 201
        assert res.json()["vehicle_id"] == vid
        assert client.delete(f"/api/vehicles/{vid}", headers=auth(seed["client_a"])).status_code == 409

    def test_request_rejects_foreign_or_mismatched_vehicle(self, client, seed):
        vid = self._create(client, seed).json()["id"]
        # Vehículo de otro fondo de la misma gestora: crear fondo 2 y usar el vid del fondo 1.
        fund2 = client.post(
            "/api/funds", headers=auth(seed["client_a"]), json={"name": "Alfa II"}
        ).json()
        res = client.post(
            "/api/requests", headers=auth(seed["client_a"]),
            json={"fund_id": fund2["id"], "vehicle_id": vid,
                  "doc_type": DOC_TYPE, "freetext": FREETEXT, "validation_requested": False},
        )
        assert res.status_code == 404

    def test_counsel_cannot_mutate(self, client, seed):
        res = self._create(client, seed, user_key="counsel")
        assert res.status_code == 403


class TestFundLifecycle:
    def test_update_fund(self, client, seed, db):
        res = client.patch(
            f"/api/funds/{seed['fund_a']['id']}", headers=auth(seed["client_a"]),
            json={"name": "Alfa Renombrado, FCR"},
        )
        assert res.status_code == 200 and res.json()["name"] == "Alfa Renombrado, FCR"
        assert "fund_updated" in [r["action"] for r in db.unscoped_select("audit_log")]

    def test_delete_fund_without_requests(self, client, seed):
        fund = client.post(
            "/api/funds", headers=auth(seed["client_a"]), json={"name": "Efímero FCR"}
        ).json()
        assert client.delete(f"/api/funds/{fund['id']}", headers=auth(seed["client_a"])).status_code == 204

    def test_delete_fund_with_requests_is_409(self, client, seed):
        res = client.post(
            "/api/requests", headers=auth(seed["client_a"]),
            json={"fund_id": seed["fund_a"]["id"], "doc_type": DOC_TYPE,
                  "freetext": FREETEXT, "validation_requested": False},
        )
        assert res.status_code == 201
        assert client.delete(
            f"/api/funds/{seed['fund_a']['id']}", headers=auth(seed["client_a"])
        ).status_code == 409

    def test_cross_gestora_fund_mutation_is_404(self, client, seed):
        res = client.patch(
            f"/api/funds/{seed['fund_b']['id']}", headers=auth(seed["client_a"]),
            json={"name": "Intruso"},
        )
        assert res.status_code == 404


class TestCounselQueueUrgency:
    def _to_review(self, client, seed, wf):
        rid, _ = wf.to_review_pending(user=seed["client_a"], fund=seed["fund_a"])
        res = client.post(f"/api/requests/{rid}/exit-b", headers=auth(seed["client_a"]))
        assert res.status_code == 200
        return rid

    def test_fresh_request_is_green_with_sla_context(self, client, seed, wf):
        rid = self._to_review(client, seed, wf)
        res = client.get("/api/counsel/queue", headers=auth(seed["counsel"]))
        item = next(i for i in res.json() if i["id"] == rid)
        assert item["urgency"] == "green"
        assert item["sla_hours"] == 48.0
        assert item["gestora_name"] == seed["gestora_a"]["name"]
        assert 0 <= item["hours_pending"] < 1

    def test_stale_request_goes_red_and_sorts_first(self, client, seed, wf, db):
        fresh = self._to_review(client, seed, wf)
        stale = self._to_review(client, seed, wf)
        # Simular 3 días pendiente (más allá de sla_review_hours=48).
        from datetime import datetime, timedelta, timezone
        old = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        db.update("requests", stale, {"counsel_requested_at": old})

        res = client.get("/api/counsel/queue", headers=auth(seed["counsel"]))
        items = {i["id"]: i for i in res.json()}
        assert items[stale]["urgency"] == "red"
        assert items[fresh]["urgency"] == "green"
        assert res.json()[0]["id"] == stale  # más urgente primero

        res = client.get("/api/counsel/queue?urgency=red", headers=auth(seed["counsel"]))
        assert [i["id"] for i in res.json()] == [stale]

    def test_gestora_filter(self, client, seed, wf):
        rid = self._to_review(client, seed, wf)
        res = client.get(
            f"/api/counsel/queue?gestora_id={seed['gestora_b']['id']}",
            headers=auth(seed["counsel"]),
        )
        assert rid not in [i["id"] for i in res.json()]


class TestUsers:
    def test_admin_lists_users(self, client, seed):
        res = client.get("/api/users", headers=auth(seed["admin"]))
        assert res.status_code == 200
        emails = {u["email"] for u in res.json()}
        assert {"clienta@alfa.es", "admin@lolailo.es"} <= emails

    def test_non_admin_forbidden(self, client, seed):
        for who in ("client_a", "counsel"):
            assert client.get("/api/users", headers=auth(seed[who])).status_code == 403

    def test_invite_client_requires_gestora(self, client, seed):
        res = client.post(
            "/api/users",
            headers=auth(seed["admin"]),
            json={"email": "nueva@alfa.es", "role": "client"},
        )
        assert res.status_code == 422

    def test_invite_creates_row_in_dev_mode(self, client, seed, db):
        res = client.post(
            "/api/users",
            headers=auth(seed["admin"]),
            json={"email": "Nueva@Alfa.es", "role": "client",
                  "gestora_id": seed["gestora_a"]["id"]},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["email"] == "nueva@alfa.es"  # normalized
        assert body["gestora_id"] == seed["gestora_a"]["id"]
        assert "user_invited" in [r["action"] for r in db.unscoped_select("audit_log")]

    def test_invite_duplicate_email_409(self, client, seed):
        res = client.post(
            "/api/users",
            headers=auth(seed["admin"]),
            json={"email": "clienta@alfa.es", "role": "client",
                  "gestora_id": seed["gestora_a"]["id"]},
        )
        assert res.status_code == 409

    def test_invite_counsel_strips_gestora(self, client, seed):
        res = client.post(
            "/api/users",
            headers=auth(seed["admin"]),
            json={"email": "counsel2@lolailolegal.es", "role": "counsel",
                  "gestora_id": seed["gestora_a"]["id"]},
        )
        assert res.status_code == 201
        assert res.json()["gestora_id"] is None


def _make_request(client, seed, db, fake_llm, *, requires_counsel=True) -> str:
    seed_precedent(db, gestora_id=seed["gestora_a"]["id"])
    res = client.post(
        "/api/requests",
        headers=auth(seed["client_a"]),
        json={
            "fund_id": seed["fund_a"]["id"],
            "doc_type": DOC_TYPE,
            "freetext": FREETEXT,
            "validation_requested": requires_counsel,
        },
    )
    assert res.status_code == 201
    return res.json()["id"]


class TestCounselReviewSurface:
    def test_queue_lists_counsel_review_requests(self, client, seed, db, fake_llm):
        request_id = _make_request(client, seed, db, fake_llm)
        db.update("requests", request_id, {"status": "counsel_review"})
        res = client.get("/api/counsel/queue", headers=auth(seed["counsel"]))
        assert res.status_code == 200
        assert [r["id"] for r in res.json()] == [request_id]

    def test_queue_forbidden_for_client(self, client, seed):
        assert client.get("/api/counsel/queue", headers=auth(seed["client_a"])).status_code == 403

    def test_review_bundle_shape_and_access(self, client, seed, db, fake_llm):
        request_id = _make_request(client, seed, db, fake_llm)
        res = client.get(f"/api/requests/{request_id}/review", headers=auth(seed["counsel"]))
        assert res.status_code == 200
        bundle = res.json()
        assert bundle["request"]["id"] == request_id
        assert isinstance(bundle["draft_text"], str)
        assert bundle["comments"] == []
        # Cross-gestora client: 404-no-leak.
        res = client.get(f"/api/requests/{request_id}/review", headers=auth(seed["client_b"]))
        assert res.status_code == 404

    def test_comment_thread_roundtrip(self, client, seed, db, fake_llm):
        request_id = _make_request(client, seed, db, fake_llm)
        res = client.post(
            f"/api/requests/{request_id}/comments",
            headers=auth(seed["counsel"]),
            json={"text": "Revisar la cláusula 3."},
        )
        assert res.status_code == 201
        comment = res.json()
        assert comment["author"] == "abogado@lolailolegal.es"
        res = client.get(
            f"/api/requests/{request_id}/comments", headers=auth(seed["client_a"])
        )
        assert [c["text"] for c in res.json()] == ["Revisar la cláusula 3."]
        # Clients cannot write to the thread.
        res = client.post(
            f"/api/requests/{request_id}/comments",
            headers=auth(seed["client_a"]),
            json={"text": "hola"},
        )
        assert res.status_code == 403
        assert "counsel_comment_added" in [r["action"] for r in db.unscoped_select("audit_log")]


class TestPrecedentVersionsEmbedAndSupersede:
    def test_list_embeds_versions(self, client, seed, db):
        precedent, version = seed_precedent(db, gestora_id=seed["gestora_a"]["id"])
        res = client.get("/api/precedents", headers=auth(seed["admin"]))
        assert res.status_code == 200
        row = next(p for p in res.json() if p["id"] == precedent["id"])
        assert [v["id"] for v in row["versions"]] == [version["id"]]

    def test_supersede_active_version(self, client, seed, db):
        precedent, version = seed_precedent(db, gestora_id=seed["gestora_a"]["id"])
        res = client.post(
            f"/api/precedents/versions/{version['id']}/supersede",
            headers=auth(seed["admin"]),
        )
        assert res.status_code == 200
        assert res.json()["status"] == "superseded"
        assert res.json()["rag_weight"] == 0.3

    def test_supersede_requires_active(self, client, seed, db):
        precedent, version = seed_precedent(
            db, gestora_id=seed["gestora_a"]["id"], status="draft"
        )
        res = client.post(
            f"/api/precedents/versions/{version['id']}/supersede",
            headers=auth(seed["admin"]),
        )
        assert res.status_code == 409

    def test_supersede_admin_only(self, client, seed, db):
        precedent, version = seed_precedent(db, gestora_id=seed["gestora_a"]["id"])
        res = client.post(
            f"/api/precedents/versions/{version['id']}/supersede",
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 403
