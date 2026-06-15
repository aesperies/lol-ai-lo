"""Critic / reviewer loop (drafting-agents Feature 2).

Covers:
- approved draft → no revision, ships as-is
- blocking issues → one revision incorporating the feedback, then re-review
- still failing after the budget → forced_counsel + generation_reviews rows
- critic SKIPPED when the LLM is unreachable (draft proceeds unchanged).
"""
from __future__ import annotations

from typing import Any

import pytest

import config
from models.doc_branches import Branch
from services import critic, llm
from tests.conftest import seed_precedent


def _params() -> dict[str, Any]:
    return {"jurisdiction": "España", "parties": [{"role": "fondo", "name": "Alfa"}]}


def _verdict_sequence(monkeypatch: pytest.MonkeyPatch, verdicts: list[dict[str, Any]]):
    """Make llm.complete_json return the queued critic verdicts in order."""
    calls = {"n": 0}

    def fake_complete_json(prompt, schema, *, max_tokens=8192, system=None):
        idx = min(calls["n"], len(verdicts) - 1)
        calls["n"] += 1
        return verdicts[idx]

    monkeypatch.setattr(llm, "complete_json", fake_complete_json)
    return calls


# ---------------------------------------------------------------------------
# review()
# ---------------------------------------------------------------------------

def test_review_approved_no_issues(monkeypatch):
    _verdict_sequence(monkeypatch, [{"approved": True, "issues": []}])
    verdict = critic.review(
        draft_text="DOC", doc_type="Llamada de Capital (Capital Call Notice)",
        branch=Branch.OPERACIONES_DE_FONDO, parsed_params=_params(), precedent_text="P",
    )
    assert verdict.approved is True
    assert verdict.skipped is False
    assert verdict.issues == []


def test_review_skips_when_llm_unreachable(monkeypatch):
    # conftest already simulates an unreachable Ollama at the httpx layer, so a
    # real complete_json raises ServiceNotConfiguredError -> skipped verdict.
    verdict = critic.review(
        draft_text="DOC", doc_type="Llamada de Capital (Capital Call Notice)",
        branch=Branch.OPERACIONES_DE_FONDO, parsed_params=_params(), precedent_text="P",
    )
    assert verdict.skipped is True
    assert verdict.approved is True  # approved-by-default so workflow proceeds


# ---------------------------------------------------------------------------
# draft_with_review() loop controller
# ---------------------------------------------------------------------------

def test_approved_first_draft_ships_as_is(monkeypatch):
    _verdict_sequence(monkeypatch, [{"approved": True, "issues": []}])

    def revise(_text, _instruction):
        raise AssertionError("revise must not be called when the draft is approved")

    result = critic.draft_with_review(
        first_draft="ORIGINAL DRAFT",
        doc_type="Llamada de Capital (Capital Call Notice)",
        branch=Branch.OPERACIONES_DE_FONDO,
        parsed_params=_params(),
        precedent_text="P",
        revise=revise,
    )
    assert result.text == "ORIGINAL DRAFT"
    assert result.approved is True
    assert result.forced_counsel is False
    assert len(result.rounds) == 1
    assert result.rounds[0].round == 0
    assert result.rounds[0].approved is True


def test_blocking_issue_triggers_one_revision_then_reapproves(monkeypatch):
    blocking = {
        "approved": False,
        "issues": [{
            "severity": "blocking", "category": "factual",
            "problem": "Amount contradicts the parameters",
            "suggested_fix": "Set the amount to 500.000 EUR",
            "location": "clause 2",
        }],
    }
    _verdict_sequence(monkeypatch, [blocking, {"approved": True, "issues": []}])

    received: dict[str, Any] = {}

    def revise(text, instruction):
        received["text"] = text
        received["instruction"] = instruction
        return "REVISED DRAFT"

    result = critic.draft_with_review(
        first_draft="ORIGINAL DRAFT",
        doc_type="Llamada de Capital (Capital Call Notice)",
        branch=Branch.OPERACIONES_DE_FONDO,
        parsed_params=_params(),
        precedent_text="P",
        revise=revise,
    )
    # Revision incorporated the critic's feedback (problem + suggested fix).
    assert "Amount contradicts the parameters" in received["instruction"]
    assert "Set the amount to 500.000 EUR" in received["instruction"]
    assert received["text"] == "ORIGINAL DRAFT"
    # Re-reviewed and approved -> ships the revised draft.
    assert result.text == "REVISED DRAFT"
    assert result.approved is True
    assert result.forced_counsel is False
    assert len(result.rounds) == 2  # round 0 (blocking) + round 1 (approved)


def test_still_failing_after_budget_forces_counsel(monkeypatch):
    blocking = {
        "approved": False,
        "issues": [{
            "severity": "blocking", "category": "legal",
            "problem": "Missing governing-law clause", "suggested_fix": "Add it",
            "location": "end",
        }],
    }
    # Always blocking -> never approves.
    _verdict_sequence(monkeypatch, [blocking])

    result = critic.draft_with_review(
        first_draft="ORIGINAL DRAFT",
        doc_type="Llamada de Capital (Capital Call Notice)",
        branch=Branch.OPERACIONES_DE_FONDO,
        parsed_params=_params(),
        precedent_text="P",
        revise=lambda _t, _i: "ANOTHER STILL-BAD DRAFT",
    )
    assert result.approved is False
    assert result.forced_counsel is True
    # critic_max_rounds default 2 -> rounds 0,1,2 reviewed = 3 trail rows.
    assert len(result.rounds) == config.get_settings().critic_max_rounds + 1
    assert all(r.approved is False for r in result.rounds)


def test_minor_issues_do_not_trigger_revision(monkeypatch):
    minor = {
        "approved": False,
        "issues": [{
            "severity": "minor", "category": "consistency",
            "problem": "tiny nit", "suggested_fix": "", "location": "",
        }],
    }
    _verdict_sequence(monkeypatch, [minor])

    def revise(_t, _i):
        raise AssertionError("minor issues must not trigger a revision")

    result = critic.draft_with_review(
        first_draft="ORIGINAL DRAFT",
        doc_type="Llamada de Capital (Capital Call Notice)",
        branch=Branch.OPERACIONES_DE_FONDO,
        parsed_params=_params(),
        precedent_text="P",
        revise=revise,
    )
    # Only minor (sub-threshold) issues -> done, ships as-is.
    assert result.text == "ORIGINAL DRAFT"
    assert result.approved is True
    assert result.forced_counsel is False


def test_critic_disabled_is_a_noop(monkeypatch):
    monkeypatch.setattr(config.get_settings(), "critic_enabled", False)

    def boom(*_a, **_k):
        raise AssertionError("critic must not run when disabled")

    monkeypatch.setattr(llm, "complete_json", boom)
    result = critic.draft_with_review(
        first_draft="ORIGINAL DRAFT",
        doc_type="Llamada de Capital (Capital Call Notice)",
        branch=Branch.OPERACIONES_DE_FONDO,
        parsed_params=_params(),
        precedent_text="P",
    )
    assert result.text == "ORIGINAL DRAFT"
    assert result.rounds == []
    assert result.approved is True
    assert result.forced_counsel is False


def test_skipped_when_llm_unreachable_ships_first_draft(monkeypatch):
    # No monkeypatch of complete_json: conftest's unreachable Ollama makes the
    # real critic raise -> skipped -> ships the first draft.
    def revise(_t, _i):
        raise AssertionError("revise must not run when critic is skipped")

    result = critic.draft_with_review(
        first_draft="ORIGINAL DRAFT",
        doc_type="Llamada de Capital (Capital Call Notice)",
        branch=Branch.OPERACIONES_DE_FONDO,
        parsed_params=_params(),
        precedent_text="P",
        revise=revise,
    )
    assert result.text == "ORIGINAL DRAFT"
    assert result.approved is True
    assert result.forced_counsel is False
    assert result.rounds == []  # skipped before any round is recorded


# ---------------------------------------------------------------------------
# Integration: critic inside the async generation pipeline
# ---------------------------------------------------------------------------

def test_pipeline_critic_skipped_under_unreachable_llm(wf, db, seed):
    """Default test mode = unreachable Ollama: the critic no-ops and generation
    succeeds normally (no generation_reviews rows, requires_counsel unchanged)."""
    seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
    request_id, summary = wf.to_review_pending()
    assert summary["request"]["status"] == "review_pending"
    assert db.select("generation_reviews", request_id=request_id) == []


def test_pipeline_forces_counsel_when_critic_cannot_approve(wf, db, seed, monkeypatch):
    """A critic that always returns blocking issues forces Exit B and writes a
    generation_reviews row per round (persisted review trail)."""
    seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")

    blocking = {
        "approved": False,
        "issues": [{
            "severity": "blocking", "category": "factual",
            "problem": "Invented amount not in parameters",
            "suggested_fix": "Remove the invented amount", "location": "clause 3",
        }],
    }
    monkeypatch.setattr(
        llm, "complete_json",
        lambda prompt, schema, *, max_tokens=8192, system=None: blocking,
    )
    # Revisions must produce a valid (non-unclear) draft each round so the loop
    # exhausts its budget; refine_document would otherwise hit the unreachable
    # LLM. (generator is the module the loop calls into.)
    from services import generator
    monkeypatch.setattr(
        generator, "refine_document",
        lambda *, current_text, instruction: current_text + " [revised]",
    )

    request_id, summary = wf.to_review_pending()
    row = db.get("requests", request_id)
    assert row["requires_counsel"] is True  # forced Exit B

    reviews = db.select("generation_reviews", request_id=request_id)
    assert len(reviews) == config.get_settings().critic_max_rounds + 1
    assert all(r["approved"] is False for r in reviews)
    assert reviews[0]["round"] == 0

    # Critic outcome reflected in document_generated audit metadata.
    generated = [
        e for e in db.select("audit_log", action="document_generated")
        if (e.get("metadata") or {}).get("request_id") == request_id
    ]
    assert generated
    critic_meta = generated[-1]["metadata"]["critic"]
    assert critic_meta["forced_counsel"] is True
    assert critic_meta["approved"] is False
    assert generated[-1]["metadata"]["branch"]  # branch recorded


def test_pipeline_critic_approves_no_forced_counsel(wf, db, seed, monkeypatch):
    """An approving critic leaves requires_counsel false and writes one
    approved review round."""
    seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
    monkeypatch.setattr(
        llm, "complete_json",
        lambda prompt, schema, *, max_tokens=8192, system=None: {"approved": True, "issues": []},
    )

    request_id, _ = wf.to_review_pending()
    row = db.get("requests", request_id)
    assert row["requires_counsel"] is False

    reviews = db.select("generation_reviews", request_id=request_id)
    assert len(reviews) == 1
    assert reviews[0]["approved"] is True
