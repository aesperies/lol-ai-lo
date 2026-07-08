"""Specialized drafting agents + gestora-siloed lessons (drafting-agents F1/F3).

Covers:
- branch_for maps every catalog doc_type to the right branch (+ unknown→generic)
- draft() passes the branch persona as the LLM system message and injects the
  gestora's learned lessons as a clearly-labelled extra-guidance block
- lessons are STRICTLY gestora-siloed — a lesson stored for gestora A is NEVER
  retrieved for gestora B (the critical isolation test).
"""
from __future__ import annotations

from typing import Any

import pytest

from models.doc_branches import Branch, branch_for
from models.schema import DOC_TYPE_CATALOG
from services import drafting_agents, generator, lessons, llm


# ---------------------------------------------------------------------------
# branch_for: every catalog doc_type maps to the right branch
# ---------------------------------------------------------------------------

_EXPECTED_BRANCH_BY_GROUP = {
    "🏛 Gobierno Corporativo": Branch.GOBIERNO_CORPORATIVO,
    "💼 Operaciones de Fondo": Branch.OPERACIONES_DE_FONDO,
    "📋 Gestión de Portfolio": Branch.GESTION_DE_PORTFOLIO,
    "⚖️ Cumplimiento y Regulatorio": Branch.CUMPLIMIENTO_REGULATORIO,
    "📝 Contratos con Terceros": Branch.CONTRATOS_TERCEROS,
    "🔧 Otros": Branch.GENERIC,
}


def test_branch_for_maps_every_catalog_doc_type():
    for group_label, doc_types in DOC_TYPE_CATALOG.items():
        expected = _EXPECTED_BRANCH_BY_GROUP[group_label]
        for doc_type in doc_types:
            assert branch_for(doc_type) is expected, (doc_type, expected)


def test_branch_for_unknown_doc_type_is_generic():
    assert branch_for("Other: bespoke widget licence") is Branch.GENERIC
    assert branch_for("totally uncatalogued thing") is Branch.GENERIC


def test_every_branch_has_guidance():
    from models.doc_branches import BRANCH_GUIDANCE

    for branch in Branch:
        assert branch in BRANCH_GUIDANCE
        assert BRANCH_GUIDANCE[branch].strip()


# ---------------------------------------------------------------------------
# draft(): branch persona as system + gestora lessons as extra guidance
# ---------------------------------------------------------------------------

def _capture_complete(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Monkeypatch llm.complete and capture the prompt + system it received."""
    captured: dict[str, Any] = {}

    def fake_complete(prompt: str, *, max_tokens: int = 8192, json_schema=None, system=None, gestora_id=None, **kwargs):
        captured["prompt"] = prompt
        captured["system"] = system
        return "DOCUMENTO GENERADO"

    monkeypatch.setattr(llm, "complete", fake_complete)
    return captured


def test_draft_passes_branch_persona_as_system(db, seed, monkeypatch):
    captured = _capture_complete(monkeypatch)

    drafting_agents.draft(
        doc_type="Llamada de Capital (Capital Call Notice)",
        language="es",
        fund_name="Alfa Fund I",
        gestora_name="Gestora Alfa",
        jurisdiction="España",
        governing_law="Derecho español",
        parties=[],
        key_terms=[],
        freetext="x" * 60,
        precedent_text="PRECEDENTE",
        gestora_id=seed["gestora_a"]["id"],
        db=db,
    )

    # Operaciones de Fondo persona: mentions capital-call / LPA mechanics.
    assert captured["system"] is not None
    assert "capital-call" in captured["system"] or "LPA" in captured["system"]


def test_draft_injects_gestora_lessons_as_labelled_guidance(db, seed, monkeypatch):
    branch = branch_for("Llamada de Capital (Capital Call Notice)")
    db.insert(
        "drafting_lessons",
        {
            "gestora_id": seed["gestora_a"]["id"],
            "branch": branch.value,
            "doc_type": "Llamada de Capital (Capital Call Notice)",
            "lesson": "Always cite the governing LPA drawdown clause.",
            "source_request_id": None,
            "weight": 1.0,
        },
    )
    captured = _capture_complete(monkeypatch)

    drafting_agents.draft(
        doc_type="Llamada de Capital (Capital Call Notice)",
        language="es",
        fund_name="Alfa Fund I",
        gestora_name="Gestora Alfa",
        jurisdiction="España",
        governing_law="Derecho español",
        parties=[],
        key_terms=[],
        freetext="x" * 60,
        precedent_text="PRECEDENTE",
        gestora_id=seed["gestora_a"]["id"],
        db=db,
    )

    prompt = captured["prompt"]
    assert generator.EXTRA_GUIDANCE_HEADER in prompt
    assert "Always cite the governing LPA drawdown clause." in prompt
    # The verbatim template body must remain intact (header appended AFTER it).
    assert "senior European VC fund legal document drafter" in prompt


def test_draft_without_lessons_omits_guidance_block(db, seed, monkeypatch):
    captured = _capture_complete(monkeypatch)

    drafting_agents.draft(
        doc_type="Llamada de Capital (Capital Call Notice)",
        language="es",
        fund_name="Alfa Fund I",
        gestora_name="Gestora Alfa",
        jurisdiction="España",
        governing_law="Derecho español",
        parties=[],
        key_terms=[],
        freetext="x" * 60,
        precedent_text="PRECEDENTE",
        gestora_id=seed["gestora_a"]["id"],
        db=db,
    )
    assert generator.EXTRA_GUIDANCE_HEADER not in captured["prompt"]


# ---------------------------------------------------------------------------
# CRITICAL: lessons are strictly gestora-siloed
# ---------------------------------------------------------------------------

def test_lessons_for_hard_filters_by_gestora(db, seed):
    branch = Branch.OPERACIONES_DE_FONDO
    db.insert(
        "drafting_lessons",
        {
            "gestora_id": seed["gestora_a"]["id"],
            "branch": branch.value,
            "doc_type": "Llamada de Capital (Capital Call Notice)",
            "lesson": "LESSON FOR ALFA ONLY",
            "source_request_id": None,
            "weight": 1.0,
        },
    )

    # Gestora A sees its lesson.
    for_a = lessons.lessons_for(db, gestora_id=seed["gestora_a"]["id"], branch=branch)
    assert "LESSON FOR ALFA ONLY" in for_a

    # Gestora B must NEVER see gestora A's lesson (isolation).
    for_b = lessons.lessons_for(db, gestora_id=seed["gestora_b"]["id"], branch=branch)
    assert for_b == []
    assert "LESSON FOR ALFA ONLY" not in for_b


def test_draft_for_gestora_b_never_injects_gestora_a_lesson(db, seed, monkeypatch):
    branch = branch_for("Llamada de Capital (Capital Call Notice)")
    db.insert(
        "drafting_lessons",
        {
            "gestora_id": seed["gestora_a"]["id"],
            "branch": branch.value,
            "doc_type": "Llamada de Capital (Capital Call Notice)",
            "lesson": "SECRET ALFA LESSON",
            "source_request_id": None,
            "weight": 1.0,
        },
    )
    captured = _capture_complete(monkeypatch)

    # Draft for gestora B — must not leak A's lesson into the prompt.
    drafting_agents.draft(
        doc_type="Llamada de Capital (Capital Call Notice)",
        language="es",
        fund_name="Beta Fund I",
        gestora_name="Gestora Beta",
        jurisdiction="España",
        governing_law="Derecho español",
        parties=[],
        key_terms=[],
        freetext="x" * 60,
        precedent_text="PRECEDENTE",
        gestora_id=seed["gestora_b"]["id"],
        db=db,
    )
    assert "SECRET ALFA LESSON" not in captured["prompt"]
    assert generator.EXTRA_GUIDANCE_HEADER not in captured["prompt"]


def test_lessons_for_prefers_matching_doc_type(db, seed):
    branch = Branch.GOBIERNO_CORPORATIVO
    gid = seed["gestora_a"]["id"]
    # A branch-only lesson and a doc_type-specific lesson.
    db.insert("drafting_lessons", {
        "gestora_id": gid, "branch": branch.value, "doc_type": None,
        "lesson": "branch-wide rule", "source_request_id": None, "weight": 1.0,
    })
    db.insert("drafting_lessons", {
        "gestora_id": gid, "branch": branch.value, "doc_type": "Poder Especial",
        "lesson": "poder-especial rule", "source_request_id": None, "weight": 1.0,
    })
    ranked = lessons.lessons_for(db, gestora_id=gid, branch=branch, doc_type="Poder Especial")
    # doc_type match ranked first.
    assert ranked[0] == "poder-especial rule"
    assert "branch-wide rule" in ranked
