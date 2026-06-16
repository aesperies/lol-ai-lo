"""Review playbooks: retrieval hard-filter, critic injection, admin-only CRUD.

Cross-gestora playbook isolation lives in test_gestora_isolation.py.
"""
from __future__ import annotations

from typing import Any

from models.doc_branches import Branch, branch_for
from services import critic, llm, playbooks
from tests.conftest import DOC_TYPE, auth


def _insert_playbook(db, gestora_id, *, content, branch=None, doc_type=None, is_active=True, title="PB"):
    return db.insert(
        "review_playbooks",
        {
            "gestora_id": gestora_id,
            "branch": branch,
            "doc_type": doc_type,
            "title": title,
            "content": content,
            "file_path": None,
            "is_active": is_active,
        },
    )


# ---------------------------------------------------------------------------
# playbooks_for retrieval
# ---------------------------------------------------------------------------

def test_playbooks_for_hard_filters_by_gestora(db, seed):
    branch = branch_for(DOC_TYPE)
    _insert_playbook(db, seed["gestora_a"]["id"], content="REGLA DE ALFA", branch=branch.value)

    for_a = playbooks.playbooks_for(
        db, gestora_id=seed["gestora_a"]["id"], branch=branch, doc_type=DOC_TYPE
    )
    assert "REGLA DE ALFA" in for_a
    for_b = playbooks.playbooks_for(
        db, gestora_id=seed["gestora_b"]["id"], branch=branch, doc_type=DOC_TYPE
    )
    assert for_b == []


def test_playbooks_for_active_only(db, seed):
    _insert_playbook(db, seed["gestora_a"]["id"], content="INACTIVA", is_active=False)
    assert playbooks.playbooks_for(db, gestora_id=seed["gestora_a"]["id"]) == []


def test_playbooks_for_prefers_doc_type_then_branch_then_wide(db, seed):
    gid = seed["gestora_a"]["id"]
    branch = branch_for(DOC_TYPE)
    _insert_playbook(db, gid, content="WIDE", title="wide")
    _insert_playbook(db, gid, content="BRANCH", branch=branch.value, title="branch")
    _insert_playbook(db, gid, content="DOCTYPE", branch=branch.value, doc_type=DOC_TYPE, title="dt")

    result = playbooks.playbooks_for(db, gestora_id=gid, branch=branch, doc_type=DOC_TYPE)
    # doc_type match ranks first, then branch, then gestora-wide.
    assert result[0] == "DOCTYPE"
    assert result[1] == "BRANCH"
    assert "WIDE" in result


def test_playbooks_for_excludes_mismatched_scope(db, seed):
    gid = seed["gestora_a"]["id"]
    _insert_playbook(db, gid, content="OTRA RAMA", branch="some_other_branch")
    # A playbook scoped to a different branch must not load for this branch.
    result = playbooks.playbooks_for(
        db, gestora_id=gid, branch=branch_for(DOC_TYPE), doc_type=DOC_TYPE
    )
    assert "OTRA RAMA" not in result


# ---------------------------------------------------------------------------
# Critic injection
# ---------------------------------------------------------------------------

def test_critic_injects_playbook_into_prompt(db, seed, monkeypatch):
    gid = seed["gestora_a"]["id"]
    _insert_playbook(
        db, gid, content="SIEMPRE INCLUIR CLAUSULA DE CONFIDENCIALIDAD",
        branch=branch_for(DOC_TYPE).value,
    )

    captured: dict[str, Any] = {}

    def fake_complete_json(prompt, schema, *, max_tokens=8192, system=None, gestora_id=None):
        captured["prompt"] = prompt
        return {"approved": True, "issues": []}

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)

    verdict = critic.review(
        draft_text="DOC",
        doc_type=DOC_TYPE,
        branch=branch_for(DOC_TYPE),
        parsed_params={},
        precedent_text="P",
        gestora_id=gid,
        db=db,
    )
    assert verdict.approved is True
    assert "GESTORA REVIEW PLAYBOOK" in captured["prompt"]
    assert "SIEMPRE INCLUIR CLAUSULA DE CONFIDENCIALIDAD" in captured["prompt"]


def test_critic_no_playbook_when_none(db, seed, monkeypatch):
    captured: dict[str, Any] = {}

    def fake_complete_json(prompt, schema, *, max_tokens=8192, system=None, gestora_id=None):
        captured["prompt"] = prompt
        return {"approved": True, "issues": []}

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    critic.review(
        draft_text="DOC",
        doc_type=DOC_TYPE,
        branch=branch_for(DOC_TYPE),
        parsed_params={},
        precedent_text="P",
        gestora_id=seed["gestora_a"]["id"],
        db=db,
    )
    # No active playbooks -> header absent (critic behaves exactly as before).
    assert "GESTORA REVIEW PLAYBOOK" not in captured["prompt"]


# ---------------------------------------------------------------------------
# CRUD (admin-only) + gestora-siloed listing
# ---------------------------------------------------------------------------

def test_admin_creates_and_lists_playbook(client, seed):
    response = client.post(
        "/api/playbooks",
        data={
            "gestora_id": seed["gestora_a"]["id"],
            "title": "Reglas Alfa",
            "content": "Enforce the confidentiality clause.",
            "branch": branch_for(DOC_TYPE).value,
        },
        headers=auth(seed["admin"]),
    )
    assert response.status_code == 201, response.text
    pb_id = response.json()["id"]

    listed = client.get(
        f"/api/playbooks?gestora_id={seed['gestora_a']['id']}", headers=auth(seed["admin"])
    ).json()
    assert any(p["id"] == pb_id for p in listed)


def test_client_cannot_create_playbook(client, seed):
    response = client.post(
        "/api/playbooks",
        data={
            "gestora_id": seed["gestora_a"]["id"],
            "title": "x",
            "content": "y",
        },
        headers=auth(seed["client_a"]),
    )
    assert response.status_code == 403


def test_admin_can_attach_file(client, seed):
    docx = b"PK\x03\x04" + b"0" * 64
    response = client.post(
        "/api/playbooks",
        data={
            "gestora_id": seed["gestora_a"]["id"],
            "title": "Con archivo",
            "content": "rules",
        },
        files={"file": ("rules.docx", docx, "application/octet-stream")},
        headers=auth(seed["admin"]),
    )
    assert response.status_code == 201, response.text
    assert "/playbooks/" in response.json()["file_path"]


def test_update_and_deactivate_playbook(client, seed):
    pb = client.post(
        "/api/playbooks",
        data={"gestora_id": seed["gestora_a"]["id"], "title": "t", "content": "c"},
        headers=auth(seed["admin"]),
    ).json()
    pb_id = pb["id"]

    updated = client.patch(
        f"/api/playbooks/{pb_id}",
        json={"content": "nuevo contenido"},
        headers=auth(seed["admin"]),
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "nuevo contenido"

    deactivated = client.post(f"/api/playbooks/{pb_id}/deactivate", headers=auth(seed["admin"]))
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    client_resp = client.patch(
        f"/api/playbooks/{pb_id}", json={"content": "x"}, headers=auth(seed["client_a"])
    )
    assert client_resp.status_code == 403


def test_delete_playbook_admin_only(client, seed):
    pb = client.post(
        "/api/playbooks",
        data={"gestora_id": seed["gestora_a"]["id"], "title": "t", "content": "c"},
        headers=auth(seed["admin"]),
    ).json()
    pb_id = pb["id"]

    assert client.delete(f"/api/playbooks/{pb_id}", headers=auth(seed["client_a"])).status_code == 403
    assert client.delete(f"/api/playbooks/{pb_id}", headers=auth(seed["admin"])).status_code == 204
    assert client.get(f"/api/playbooks/{pb_id}", headers=auth(seed["admin"])).status_code == 404
