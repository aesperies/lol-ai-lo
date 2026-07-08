"""Learning from validated versions (drafting-agents Feature 3, siloed).

Covers:
- extract_lessons stores gestora-siloed rows
- high-similarity short-circuit (nothing to learn → no-op)
- lessons_for hard-filters by gestora_id
- extraction failure / LLM unreachable doesn't break validation.
"""
from __future__ import annotations

from typing import Any

import pytest

import config
from models.doc_branches import Branch
from services import lessons, llm


def _stub_complete_json(monkeypatch, payload):
    monkeypatch.setattr(
        llm, "complete_json",
        lambda prompt, schema, *, max_tokens=8192, system=None, gestora_id=None, **kwargs: payload,
    )


# ---------------------------------------------------------------------------
# extract_lessons
# ---------------------------------------------------------------------------

def test_extract_lessons_stores_siloed_rows(db, seed, monkeypatch):
    _stub_complete_json(monkeypatch, {"lessons": [
        "Cite the LPA drawdown clause.",
        "State the per-investor allocation basis.",
    ]})
    result = lessons.extract_lessons(
        gestora_id=seed["gestora_a"]["id"],
        branch=Branch.OPERACIONES_DE_FONDO,
        doc_type="Llamada de Capital (Capital Call Notice)",
        ai_draft_text="short draft about a capital call",
        final_text="a substantially different validated final document text body",
        source_request_id="req-1",
        db=db,
    )
    assert len(result) == 2
    rows = db.select("drafting_lessons", gestora_id=seed["gestora_a"]["id"])
    assert len(rows) == 2
    assert all(r["gestora_id"] == seed["gestora_a"]["id"] for r in rows)
    assert all(r["branch"] == Branch.OPERACIONES_DE_FONDO.value for r in rows)
    assert {r["lesson"] for r in rows} == set(result)


def test_extract_lessons_caps_at_three(db, seed, monkeypatch):
    _stub_complete_json(monkeypatch, {"lessons": ["a", "b", "c", "d", "e"]})
    result = lessons.extract_lessons(
        gestora_id=seed["gestora_a"]["id"], branch=Branch.GENERIC, doc_type=None,
        ai_draft_text="draft one", final_text="a very different validated text body here",
        source_request_id=None, db=db,
    )
    assert len(result) == 3


def test_high_similarity_short_circuits(db, seed, monkeypatch):
    # Identical text -> similarity 1.0 >= threshold -> no LLM call, no rows.
    def boom(*_a, **_k):
        raise AssertionError("LLM must not be called on the high-similarity path")

    monkeypatch.setattr(llm, "complete_json", boom)
    same = "exactly the same document text on both sides"
    result = lessons.extract_lessons(
        gestora_id=seed["gestora_a"]["id"], branch=Branch.GENERIC, doc_type=None,
        ai_draft_text=same, final_text=same, source_request_id=None, db=db,
    )
    assert result == []
    assert db.select("drafting_lessons", gestora_id=seed["gestora_a"]["id"]) == []


def test_extract_lessons_swallows_llm_unreachable(db, seed):
    # conftest simulates an unreachable Ollama: real complete_json raises ->
    # extract_lessons returns [] rather than propagating (best-effort).
    result = lessons.extract_lessons(
        gestora_id=seed["gestora_a"]["id"], branch=Branch.GENERIC, doc_type=None,
        ai_draft_text="draft text alpha", final_text="a wholly different final text body",
        source_request_id=None, db=db,
    )
    assert result == []
    assert db.select("drafting_lessons", gestora_id=seed["gestora_a"]["id"]) == []


def test_extract_lessons_swallows_bad_json(db, seed, monkeypatch):
    def raise_value_error(*_a, **_k):
        raise ValueError("unparseable model output")

    monkeypatch.setattr(llm, "complete_json", raise_value_error)
    result = lessons.extract_lessons(
        gestora_id=seed["gestora_a"]["id"], branch=Branch.GENERIC, doc_type=None,
        ai_draft_text="draft text alpha", final_text="a wholly different final text body",
        source_request_id=None, db=db,
    )
    assert result == []


# ---------------------------------------------------------------------------
# lessons_for: hard gestora_id filter (isolation)
# ---------------------------------------------------------------------------

def test_lessons_for_hard_filters_by_gestora_id(db, seed):
    db.insert("drafting_lessons", {
        "gestora_id": seed["gestora_a"]["id"], "branch": Branch.GENERIC.value,
        "doc_type": None, "lesson": "ALFA ONLY", "source_request_id": None, "weight": 1.0,
    })
    assert lessons.lessons_for(db, gestora_id=seed["gestora_a"]["id"], branch=Branch.GENERIC) == ["ALFA ONLY"]
    assert lessons.lessons_for(db, gestora_id=seed["gestora_b"]["id"], branch=Branch.GENERIC) == []


def test_lessons_for_respects_top_k(db, seed):
    gid = seed["gestora_a"]["id"]
    for i in range(10):
        db.insert("drafting_lessons", {
            "gestora_id": gid, "branch": Branch.GENERIC.value, "doc_type": None,
            "lesson": f"lesson {i}", "source_request_id": None, "weight": 1.0,
        })
    assert len(lessons.lessons_for(db, gestora_id=gid, branch=Branch.GENERIC, top_k=3)) == 3


def test_lessons_for_branch_filter(db, seed):
    gid = seed["gestora_a"]["id"]
    db.insert("drafting_lessons", {
        "gestora_id": gid, "branch": Branch.OPERACIONES_DE_FONDO.value, "doc_type": None,
        "lesson": "ops lesson", "source_request_id": None, "weight": 1.0,
    })
    assert lessons.lessons_for(db, gestora_id=gid, branch=Branch.OPERACIONES_DE_FONDO) == ["ops lesson"]
    assert lessons.lessons_for(db, gestora_id=gid, branch=Branch.GOBIERNO_CORPORATIVO) == []


# ---------------------------------------------------------------------------
# Extraction failure must never break the validation flow (Exit B)
# ---------------------------------------------------------------------------

def test_extraction_failure_does_not_break_validation(wf, client, seed, db, monkeypatch):
    from tests.conftest import auth, seed_precedent

    seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")

    # Make the extraction blow up; validation must still succeed.
    def boom(**_kwargs):
        raise RuntimeError("extraction exploded")

    monkeypatch.setattr(lessons, "extract_lessons", boom)

    request_id, _ = wf.to_review_pending()
    assert client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"])).status_code == 200
    resp = client.post(f"/api/requests/{request_id}/validate", headers=auth(seed["counsel"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "validated"
