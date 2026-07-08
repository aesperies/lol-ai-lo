"""Verifiable citations / grounding (grounding Feature 1).

Covers the generation-side ``[SOURCE: precedent §<ref> | "<quote>"]`` marker:
- :func:`generator.parse_source_markers` extracts ref + quote;
- a draft containing SOURCE markers round-trips render_docx -> extract_text
  VERBATIM (the Exit-A [MISSING] gate + redline bases read it back) and renders
  distinctly (small/grey/superscript run in the docx; <sup class="doc-source">
  in the in-browser HTML);
- the drafting guidance injected into the LLM prompt mentions the SOURCE
  convention (monkeypatch llm.complete, assert the prompt carries it).
"""
from __future__ import annotations

import io
from typing import Any

import pytest

from docx import Document

from services import docx_renderer, drafting_agents, generator, llm
from services.docx_html import SOURCE_CLASS, docx_to_html

SOURCE_LINE = (
    "El presente acuerdo aprueba la llamada de capital. "
    '[SOURCE: precedent §4.2 | "se aprueba la llamada de capital"]'
)


# ---------------------------------------------------------------------------
# parse_source_markers
# ---------------------------------------------------------------------------

def test_parse_source_markers_extracts_ref_and_quote():
    markers = generator.parse_source_markers(SOURCE_LINE)
    assert markers == [
        {"ref": "precedent §4.2", "quote": "se aprueba la llamada de capital"}
    ]


def test_parse_source_markers_multiple_in_document_order():
    text = (
        'Cláusula primera. [SOURCE: precedent §1 | "primera cosa"]\n'
        'Cláusula segunda. [SOURCE: precedent "Cláusula Tercera" | "segunda cosa"]'
    )
    markers = generator.parse_source_markers(text)
    assert [m["quote"] for m in markers] == ["primera cosa", "segunda cosa"]
    assert markers[1]["ref"] == 'precedent "Cláusula Tercera"'


def test_parse_source_markers_none_when_absent():
    assert generator.parse_source_markers("Un documento sin citas.") == []


# ---------------------------------------------------------------------------
# render -> extract round-trip stays VERBATIM
# ---------------------------------------------------------------------------

def test_source_marker_survives_render_extract_roundtrip_verbatim():
    docx_bytes = docx_renderer.render_docx(SOURCE_LINE)
    extracted = docx_renderer.extract_text(docx_bytes)
    # The marker survives byte-for-byte (the parser re-extracts it unchanged).
    assert '[SOURCE: precedent §4.2 | "se aprueba la llamada de capital"]' in extracted
    assert generator.parse_source_markers(extracted) == [
        {"ref": "precedent §4.2", "quote": "se aprueba la llamada de capital"}
    ]


def test_source_and_defect_markers_coexist_and_survive():
    line = (
        "Cláusula sin importe. [MISSING: importe] "
        '[SOURCE: precedent §2 | "importe de la llamada"]'
    )
    extracted = docx_renderer.extract_text(docx_renderer.render_docx(line))
    assert "[MISSING: importe]" in extracted
    assert '[SOURCE: precedent §2 | "importe de la llamada"]' in extracted


# ---------------------------------------------------------------------------
# rendered distinctly (docx run styling + HTML <sup>)
# ---------------------------------------------------------------------------

def test_source_marker_rendered_as_distinct_docx_run():
    docx_bytes = docx_renderer.render_docx(SOURCE_LINE)
    document = Document(io.BytesIO(docx_bytes))
    source_runs = [
        run
        for para in document.paragraphs
        for run in para.runs
        if run.text.startswith("[SOURCE:")
    ]
    assert source_runs, "expected a dedicated run for the SOURCE marker"
    run = source_runs[0]
    # Footnote-style: small, muted grey, superscript — NOT the defect highlight.
    assert run.font.superscript is True
    assert run.font.color.rgb == docx_renderer._SOURCE_FOOTNOTE
    assert run.bold is not True


def test_source_marker_wrapped_in_styled_sup_in_html():
    html = docx_to_html(docx_renderer.render_docx(SOURCE_LINE))["html"]
    assert f'<sup class="{SOURCE_CLASS}">' in html
    # Verbatim marker text preserved (escaped quotes) inside the wrapper.
    assert "[SOURCE: precedent §4.2" in html
    # The frontend's only-whitelisted-tags contract still holds (sup added).
    import re

    allowed = {
        "p", "h1", "h2", "h3", "strong", "em", "u", "ins", "del", "sup",
        "table", "tr", "td", "ul", "ol", "li", "br",
    }
    assert set(re.findall(r"</?([a-z0-9]+)", html)) <= allowed


# ---------------------------------------------------------------------------
# drafting guidance includes the SOURCE convention
# ---------------------------------------------------------------------------

def _capture_complete(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_complete(prompt: str, *, max_tokens: int = 8192, json_schema=None, system=None, gestora_id=None, **kwargs):
        captured["prompt"] = prompt
        captured["system"] = system
        return "DOCUMENTO GENERADO"

    monkeypatch.setattr(llm, "complete", fake_complete)
    return captured


def test_drafting_guidance_mentions_source_convention(db, seed, monkeypatch):
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
    assert "[SOURCE:" in prompt
    assert "VERIFIABLE CITATIONS" in prompt
    # The verbatim template body must remain intact (guidance appended AFTER it).
    assert "senior European VC fund legal document drafter" in prompt


def test_generate_document_appends_source_guidance(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_complete(prompt, *, max_tokens=8192, system=None, gestora_id=None, **kwargs):
        captured["prompt"] = prompt
        return "DOC"

    monkeypatch.setattr(llm, "complete", fake_complete)
    generator.generate_document(
        doc_type="NDA",
        language="es",
        fund_name="F",
        gestora_name="G",
        jurisdiction="España",
        governing_law="Derecho español",
        parties=[],
        key_terms=[],
        freetext="x" * 60,
        precedent_text="PRECEDENTE",
    )
    assert generator.SOURCE_GUIDANCE in captured["prompt"]
