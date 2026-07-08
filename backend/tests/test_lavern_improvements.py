"""Lavern-inspired hardening: grounding verifier (P1), issue confidence (P7),
evaluator gate (P3) and lessons reinforcement/decay (P2)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

import config
from models.doc_branches import Branch
from services import critic, lessons, llm


def _params() -> dict[str, Any]:
    return {"jurisdiction": "España"}


def _review(draft: str, issues: list[dict[str, Any]], monkeypatch) -> critic.Verdict:
    monkeypatch.setattr(
        llm, "complete_json",
        lambda *a, **k: {"approved": False, "issues": issues},
    )
    return critic.review(
        draft_text=draft, doc_type="Acta de Reunión del Consejo",
        branch=Branch.GOBIERNO_CORPORATIVO, parsed_params=_params(), precedent_text="P",
    )


class TestGroundingVerifier:
    def test_fabricated_quote_drops_issue(self, monkeypatch):
        verdict = _review(
            "El consejo aprueba la llamada de capital de 500.000 euros.",
            [{
                "severity": "blocking", "category": "factual", "problem": "X",
                "citation": {"where": "c1", "quote": "importe de 999.999 EUR"},
            }],
            monkeypatch,
        )
        assert verdict.issues == []
        assert verdict.approved is True  # nothing verifiable left -> approved

    def test_verbatim_quote_keeps_issue_case_and_spacing_insensitive(self, monkeypatch):
        verdict = _review(
            "El consejo aprueba la llamada  de capital de 500.000 euros.",
            [{
                "severity": "major", "category": "factual", "problem": "X",
                "citation": {"where": "c1", "quote": "LLAMADA DE CAPITAL de 500.000 euros"},
            }],
            monkeypatch,
        )
        assert len(verdict.issues) == 1

    def test_issue_without_citation_is_kept(self, monkeypatch):
        verdict = _review(
            "Texto del acta.",
            [{"severity": "major", "category": "legal", "problem": "Falta ley aplicable"}],
            monkeypatch,
        )
        assert len(verdict.issues) == 1
        assert verdict.issues[0].severity == "major"

    def test_disabled_flag_keeps_fabricated_quote(self, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "critic_grounding_enabled", False)
        verdict = _review(
            "Texto.",
            [{
                "severity": "major", "category": "factual", "problem": "X",
                "citation": {"where": "c1", "quote": "no está en el borrador"},
            }],
            monkeypatch,
        )
        assert len(verdict.issues) == 1


class TestIssueConfidence:
    def test_confidence_parsed_clamped_and_persisted(self, monkeypatch):
        verdict = _review(
            "Texto problemático aquí.",
            [{
                "severity": "major", "category": "factual", "problem": "X",
                "confidence": 1.7,
                "citation": {"where": "c1", "quote": "Texto problemático"},
            }],
            monkeypatch,
        )
        assert verdict.issues[0].confidence == 1.0
        assert verdict.issues[0].to_dict()["confidence"] == 1.0

    def test_missing_confidence_is_none(self, monkeypatch):
        verdict = _review(
            "Texto problemático aquí.",
            [{
                "severity": "major", "category": "factual", "problem": "X",
                "citation": {"where": "c1", "quote": "Texto problemático"},
            }],
            monkeypatch,
        )
        assert verdict.issues[0].confidence is None


class TestEvaluatorGate:
    def _issues(self) -> list[critic.Issue]:
        return [
            critic.Issue(severity="blocking", category="factual", problem="real"),
            critic.Issue(severity="major", category="legal", problem="débil"),
        ]

    def test_gate_disabled_keeps_all(self, monkeypatch):
        def boom(*_a, **_k):
            raise AssertionError("gate must not call the LLM when disabled")
        monkeypatch.setattr(llm, "complete_json", boom)
        kept = critic._gate_issues(self._issues())
        assert len(kept) == 2

    def test_gate_filters_by_kept_indices(self, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "critic_gate_enabled", True)
        monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"keep": [1]})
        kept = critic._gate_issues(self._issues())
        assert [i.problem for i in kept] == ["real"]

    def test_gate_failure_degrades_to_keep_all(self, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "critic_gate_enabled", True)
        def boom(*_a, **_k):
            raise ValueError("bad json")
        monkeypatch.setattr(llm, "complete_json", boom)
        kept = critic._gate_issues(self._issues())
        assert len(kept) == 2


class TestLessonsReinforcement:
    def _extract(self, db, seed, monkeypatch, lesson: str) -> None:
        monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"lessons": [lesson]})
        lessons.extract_lessons(
            gestora_id=seed["gestora_a"]["id"], branch=Branch.GENERIC, doc_type="NDA",
            ai_draft_text="borrador alfa", final_text="un final totalmente distinto",
            source_request_id=None, db=db,
        )

    def test_near_duplicate_reinforces_instead_of_duplicating(self, db, seed, monkeypatch):
        self._extract(db, seed, monkeypatch, "Incluir siempre la cláusula de ley aplicable.")
        self._extract(db, seed, monkeypatch, "Incluir siempre la cláusula de ley aplicable")
        rows = db.select("drafting_lessons", gestora_id=seed["gestora_a"]["id"])
        assert len(rows) == 1
        assert rows[0]["occurrences"] == 2
        assert rows[0]["weight"] == 1.25
        # lessons_confirm_threshold default 2 -> promoted on the reinforcement.
        assert rows[0]["status"] == "confirmed"

    def test_distinct_lessons_insert_as_tentative(self, db, seed, monkeypatch):
        self._extract(db, seed, monkeypatch, "Incluir siempre la cláusula de ley aplicable.")
        self._extract(db, seed, monkeypatch, "Numerar los anexos con cifras romanas.")
        rows = db.select("drafting_lessons", gestora_id=seed["gestora_a"]["id"])
        assert len(rows) == 2
        assert {r["status"] for r in rows} == {"tentative"}

    def test_decay_floor_stops_injecting_stale_lessons(self, db, seed):
        old = (datetime.now(timezone.utc) - timedelta(days=3650)).isoformat()
        db.insert(
            "drafting_lessons",
            {
                "gestora_id": seed["gestora_a"]["id"], "branch": Branch.GENERIC.value,
                "doc_type": None, "lesson": "regla fósil", "weight": 1.0,
                "status": "confirmed", "occurrences": 3, "last_reinforced_at": old,
            },
        )
        db.insert(
            "drafting_lessons",
            {
                "gestora_id": seed["gestora_a"]["id"], "branch": Branch.GENERIC.value,
                "doc_type": None, "lesson": "regla fresca", "weight": 1.0,
                "status": "confirmed", "occurrences": 3,
                "last_reinforced_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        result = lessons.lessons_for(
            db, gestora_id=seed["gestora_a"]["id"], branch=Branch.GENERIC
        )
        assert result == ["regla fresca"]

    def test_confirmed_ranks_above_tentative(self, db, seed):
        now = datetime.now(timezone.utc).isoformat()
        for lesson, status in (("tentativa", "tentative"), ("confirmada", "confirmed")):
            db.insert(
                "drafting_lessons",
                {
                    "gestora_id": seed["gestora_a"]["id"], "branch": Branch.GENERIC.value,
                    "doc_type": None, "lesson": lesson, "weight": 1.0,
                    "status": status, "occurrences": 1, "last_reinforced_at": now,
                },
            )
        result = lessons.lessons_for(
            db, gestora_id=seed["gestora_a"]["id"], branch=Branch.GENERIC, top_k=1
        )
        assert result == ["confirmada"]
