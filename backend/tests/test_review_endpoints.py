"""Read-only UI endpoints added for the drafting-agents UI layer:

- GET /api/requests/{id}/reviews   (critic trail, gestora-siloed)
- GET /api/requests/{id}/branch    (derived drafting branch)
- GET /api/admin/gestoras/{id}/lessons (admin-only, gestora-siloed)

Cross-gestora isolation mirrors the existing request/precedent/playbook tests.
"""
from __future__ import annotations

from typing import Any

from models.doc_branches import branch_for
from tests.conftest import DOC_TYPE, auth


def _seed_request(db, seed, fund_key="fund_a") -> str:
    row = db.insert(
        "requests",
        {
            "fund_id": seed[fund_key]["id"],
            "user_id": seed["client_a"]["id"] if fund_key == "fund_a" else seed["client_b"]["id"],
            "doc_type": DOC_TYPE,
            "doc_type_custom": None,
            "freetext": "x" * 60,
            "language": "es",
            "parsed_params": {},
            "structured_fields": None,
            "status": "review_pending",
            "requires_counsel": False,
        },
    )
    return row["id"]


def _seed_review(db, request_id, *, round_, approved, issues):
    return db.insert(
        "generation_reviews",
        {
            "request_id": request_id,
            "iteration": 0,
            "round": round_,
            "approved": approved,
            "issues": issues,
            "model_note": None,
        },
    )


# ---------------------------------------------------------------------------
# /reviews
# ---------------------------------------------------------------------------

def test_reviews_returns_rounds_in_order(client, db, seed):
    request_id = _seed_request(db, seed)
    _seed_review(db, request_id, round_=1, approved=True, issues=[])
    _seed_review(
        db, request_id, round_=0, approved=False,
        issues=[{"severity": "major", "category": "factual", "problem": "wrong amount",
                 "suggested_fix": "use 500.000", "location": "clause 2"}],
    )

    resp = client.get(f"/api/requests/{request_id}/reviews", headers=auth(seed["client_a"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["round"] for r in body] == [0, 1]
    assert body[0]["approved"] is False
    assert body[0]["issues"][0]["severity"] == "major"
    assert body[1]["approved"] is True


def test_reviews_empty_when_no_critic(client, db, seed):
    request_id = _seed_request(db, seed)
    resp = client.get(f"/api/requests/{request_id}/reviews", headers=auth(seed["client_a"]))
    assert resp.status_code == 200
    assert resp.json() == []


def test_reviews_gestora_siloed_404_for_other_client(client, db, seed):
    request_id = _seed_request(db, seed)  # gestora A
    resp = client.get(f"/api/requests/{request_id}/reviews", headers=auth(seed["client_b"]))
    assert resp.status_code == 404


def test_reviews_visible_to_counsel_and_admin(client, db, seed):
    request_id = _seed_request(db, seed)
    _seed_review(db, request_id, round_=0, approved=True, issues=[])
    for actor in (seed["counsel"], seed["admin"]):
        resp = client.get(f"/api/requests/{request_id}/reviews", headers=auth(actor))
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# /branch
# ---------------------------------------------------------------------------

def test_branch_derived_from_doc_type(client, db, seed):
    request_id = _seed_request(db, seed)
    resp = client.get(f"/api/requests/{request_id}/branch", headers=auth(seed["client_a"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["branch"] == branch_for(DOC_TYPE).value


def test_branch_gestora_siloed_404(client, db, seed):
    request_id = _seed_request(db, seed)
    resp = client.get(f"/api/requests/{request_id}/branch", headers=auth(seed["client_b"]))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /admin/gestoras/{id}/lessons
# ---------------------------------------------------------------------------

def _seed_lesson(db, gestora_id, *, branch, doc_type=None, lesson="rule"):
    return db.insert(
        "drafting_lessons",
        {
            "gestora_id": gestora_id,
            "branch": branch,
            "doc_type": doc_type,
            "lesson": lesson,
            "source_request_id": None,
            "weight": 1.0,
        },
    )


def test_lessons_admin_only(client, db, seed):
    gid = seed["gestora_a"]["id"]
    _seed_lesson(db, gid, branch=branch_for(DOC_TYPE).value)
    assert client.get(f"/api/admin/gestoras/{gid}/lessons", headers=auth(seed["client_a"])).status_code == 403
    assert client.get(f"/api/admin/gestoras/{gid}/lessons", headers=auth(seed["counsel"])).status_code == 403
    ok = client.get(f"/api/admin/gestoras/{gid}/lessons", headers=auth(seed["admin"]))
    assert ok.status_code == 200
    assert len(ok.json()) == 1


def test_lessons_gestora_siloed(client, db, seed):
    branch = branch_for(DOC_TYPE).value
    _seed_lesson(db, seed["gestora_a"]["id"], branch=branch, lesson="ALFA RULE")
    _seed_lesson(db, seed["gestora_b"]["id"], branch=branch, lesson="BETA RULE")

    a = client.get(f"/api/admin/gestoras/{seed['gestora_a']['id']}/lessons", headers=auth(seed["admin"])).json()
    assert [l["lesson"] for l in a] == ["ALFA RULE"]
    b = client.get(f"/api/admin/gestoras/{seed['gestora_b']['id']}/lessons", headers=auth(seed["admin"])).json()
    assert [l["lesson"] for l in b] == ["BETA RULE"]


def test_lessons_branch_filter(client, db, seed):
    gid = seed["gestora_a"]["id"]
    _seed_lesson(db, gid, branch="gobierno_corporativo", lesson="GC")
    _seed_lesson(db, gid, branch="contratos_terceros", lesson="CT")

    filtered = client.get(
        f"/api/admin/gestoras/{gid}/lessons?branch=gobierno_corporativo",
        headers=auth(seed["admin"]),
    ).json()
    assert [l["lesson"] for l in filtered] == ["GC"]


def test_lessons_unknown_gestora_404(client, seed):
    resp = client.get("/api/admin/gestoras/nope/lessons", headers=auth(seed["admin"]))
    assert resp.status_code == 404
