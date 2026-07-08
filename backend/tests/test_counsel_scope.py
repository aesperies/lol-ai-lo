"""Política de visibilidad por asignación (counsel).

Un abogado ve las solicitudes de SUS gestoras asignadas más el pool de
gestoras sin ningún abogado asignado; las gestoras asignadas a OTROS abogados
le son invisibles (404-no-leak). Admin ve todo.
"""
from __future__ import annotations

from tests.conftest import auth


def _second_counsel(db):
    return db.insert(
        "users",
        {"email": "abogado2@test.com", "role": "counsel", "gestora_id": None},
    )


def _to_counsel_review(client, seed, wf, fund_key="fund_a", user_key="client_a") -> str:
    rid, _ = wf.to_review_pending(user=seed[user_key], fund=seed[fund_key])
    res = client.post(f"/api/requests/{rid}/exit-b", headers=auth(seed[user_key]))
    assert res.status_code == 200
    return rid


class TestCounselScope:
    def test_assigned_gestora_is_invisible_to_other_counsel(self, client, seed, wf, db):
        other = _second_counsel(db)
        # gestora_a queda asignada al counsel del seed.
        db.insert("counsel_assignments", {
            "gestora_id": seed["gestora_a"]["id"],
            "counsel_user_id": seed["counsel"]["id"],
            "is_primary": True,
        })
        rid = _to_counsel_review(client, seed, wf)

        # El asignado la ve como 'mine'.
        items = client.get("/api/counsel/queue", headers=auth(seed["counsel"])).json()
        mine = next(i for i in items if i["id"] == rid)
        assert mine["assignment"] == "mine"

        # El otro abogado NI la ve en cola NI puede acceder al detalle (404).
        items = client.get("/api/counsel/queue", headers=auth(other)).json()
        assert rid not in [i["id"] for i in items]
        assert client.get(f"/api/requests/{rid}", headers=auth(other)).status_code == 404
        assert client.get(f"/api/requests/{rid}/review", headers=auth(other)).status_code == 404
        assert client.post(f"/api/requests/{rid}/validate", headers=auth(other)).status_code == 404

    def test_unassigned_gestora_is_pool_for_everyone(self, client, seed, wf, db):
        other = _second_counsel(db)
        db.insert("counsel_assignments", {
            "gestora_id": seed["gestora_a"]["id"],
            "counsel_user_id": seed["counsel"]["id"],
            "is_primary": True,
        })
        # gestora_b no tiene abogado: sus solicitudes son pool para todos.
        rid = _to_counsel_review(client, seed, wf, fund_key="fund_b", user_key="client_b")
        for counsel_user in (seed["counsel"], other):
            items = client.get("/api/counsel/queue", headers=auth(counsel_user)).json()
            item = next(i for i in items if i["id"] == rid)
            assert item["assignment"] == "pool"
        # Y puede validar (acceso completo al pool).
        assert client.get(f"/api/requests/{rid}", headers=auth(other)).status_code == 200

    def test_admin_sees_everything_as_mine(self, client, seed, wf, db):
        db.insert("counsel_assignments", {
            "gestora_id": seed["gestora_a"]["id"],
            "counsel_user_id": seed["counsel"]["id"],
            "is_primary": True,
        })
        rid = _to_counsel_review(client, seed, wf)
        items = client.get("/api/counsel/queue", headers=auth(seed["admin"])).json()
        assert next(i for i in items if i["id"] == rid)["assignment"] == "mine"
