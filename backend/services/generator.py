"""Document generation (SPEC.md verbatim prompt).

Generates the full document text from the confirmed parameters plus the
retrieved precedent, then appends the mandatory Lol-AI-lo Legal SLP
disclaimer. Text generation routes through the provider-agnostic seam
(services/llm.py): local Ollama by default, Anthropic Claude as an optional
cloud fallback. Raises ServiceNotConfiguredError when the selected provider is
misconfigured or unreachable.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from config import get_settings
from models.schema import SLP_DISCLAIMER
from services import llm

# Verbatim from docs/SPEC.md — do not edit. Placeholders substituted via
# .replace() to avoid clashing with literal braces in client content.
GENERATION_PROMPT = """You are a senior European VC fund legal document drafter.
Your task is to generate a complete, professional {doc_type} in {language}.
CONTEXT:
- Fund: {fund_name}
- Gestora: {gestora_name}
- Jurisdiction: {jurisdiction}
- Governing Law: {governing_law}
- Parties: {parties}
- Key Terms: {key_terms}
- Client Instructions: {freetext}
PRECEDENT (retrieved from fund's document library):
{precedent_text}
INSTRUCTIONS:
1. Use the precedent as your structural and stylistic template
2. Adapt all variable fields (parties, dates, amounts) to the current request
3. Maintain the same governing law and jurisdiction as the precedent unless
   the client explicitly requests otherwise
4. Flag any clause where you deviate from the precedent with:
   [DEVIATION: reason]
5. Flag any field you could not fill from the available information with:
   [MISSING: field name]
6. Output the full document text, ready for conversion to .docx
7. Use formal legal register appropriate for {jurisdiction}
8. Apply 2026 European VC market standards
CRITICAL: Do not invent parties, amounts, or dates not provided in the input."""

NO_PRECEDENT_PLACEHOLDER = (
    "(no precedent available — generate from scratch following standard "
    "structure for this document type in this jurisdiction)"
)

# Header for the optional, gestora-siloed lessons block (drafting-agents
# Feature 1/3). Appended AFTER the verbatim GENERATION_PROMPT body so the
# template itself is never altered.
EXTRA_GUIDANCE_HEADER = (
    "DRAFTING GUIDANCE — learned from THIS gestora's validated documents:"
)

# Verifiable-citation guidance (grounding Feature 1). Steered through the
# additive ``extra_guidance`` channel — the verbatim GENERATION_PROMPT body is
# never edited. When the drafter grounds a clause in the supplied precedent it
# MAY annotate that clause with an inline ``[SOURCE: precedent §<ref> |
# "<verbatim quote>"]`` marker (a sibling of the existing [DEVIATION:] /
# [MISSING:] markers). The marker is OPTIONAL and additive: the document must
# still read cleanly without it, and it survives extract_text verbatim exactly
# like the other flag markers.
SOURCE_GUIDANCE = (
    "VERIFIABLE CITATIONS — when (and only when) you adapt a clause directly "
    "from the PRECEDENT above, you MAY ground it with an inline source marker, "
    "a sibling of the [DEVIATION: ...] / [MISSING: ...] markers, placed at the "
    "end of that clause:\n"
    '  [SOURCE: precedent §<ref> | "<verbatim quote, ≤20 words, copied '
    'exactly from the precedent>"]\n'
    "where <ref> is the precedent clause/section locator (e.g. §4.2, "
    '"Cláusula Tercera", or a short heading). Rules: keep it OPTIONAL and '
    "additive (never required for a clause to be valid); the document must read "
    "cleanly with the markers removed; quote the precedent VERBATIM and never "
    "invent a quote; do not cite anything not present in the precedent."
)

# Inline source-citation marker (grounding Feature 1). Parsed by
# :func:`parse_source_markers`; rendered distinctly (footnote-style) by
# services/docx_renderer.py + services/docx_html.py but kept verbatim by
# docx_renderer.extract_text so the Exit-A [MISSING] gate and round-trip tests
# are unaffected.
#   [SOURCE: precedent §4.2 | "exact quote from the precedent"]
_SOURCE_MARKER_RE = re.compile(
    r'\[SOURCE:\s*(?P<ref>.*?)\s*\|\s*"(?P<quote>[^"]*)"\s*\]'
)


def parse_source_markers(text: str) -> list[dict[str, str]]:
    """Extract every ``[SOURCE: <ref> | "<quote>"]`` citation from ``text``.

    Returns a list of ``{"ref": ..., "quote": ...}`` dicts in document order
    (empty when the drafter emitted no source markers). ``ref`` keeps the
    locator as written (e.g. ``precedent §4.2``); ``quote`` is the verbatim
    precedent excerpt. Reused by the renderers (to style markers distinctly) and
    the tests (to assert the convention round-trips).
    """
    return [
        {"ref": m.group("ref").strip(), "quote": m.group("quote").strip()}
        for m in _SOURCE_MARKER_RE.finditer(text)
    ]

# Iterative refinement prompt (improvement #4). Same conventions as
# GENERATION_PROMPT: placeholders substituted via .replace() to avoid
# clashing with literal braces in document text.
REFINEMENT_PROMPT = """You are a senior European VC fund legal document drafter.
A document you previously drafted needs a targeted revision.
CURRENT DOCUMENT:
{current_text}
CLIENT REVISION REQUEST (apply ONLY this change and anything strictly required for consistency):
{instruction}
RULES:
1. Apply the requested change precisely. Do NOT rewrite, reorder or
   restyle unaffected clauses.
2. Keep language, governing law, jurisdiction, defined terms and
   numbering conventions unchanged unless the request requires it.
3. Keep all existing [DEVIATION: ...], [MISSING: ...] and [SOURCE: ...]
   markers that are still accurate; add new ones if your change introduces
   them; remove ones the change resolves.
4. If the request is ambiguous, contradictory, or would require
   information you do not have, output exactly: [REFINEMENT-UNCLEAR: reason]
   and nothing else.
5. Output the full revised document text, ready for .docx conversion."""

REFINEMENT_UNCLEAR_MARKER = "[REFINEMENT-UNCLEAR:"


def refinement_unclear_reason(text: str) -> Optional[str]:
    """The reason inside a [REFINEMENT-UNCLEAR: ...] output, or None when the
    output is a real revised document."""
    stripped = text.strip()
    if not stripped.startswith(REFINEMENT_UNCLEAR_MARKER):
        return None
    reason = stripped[len(REFINEMENT_UNCLEAR_MARKER):].rsplit("]", 1)[0].strip()
    return reason or "unclear"


def generate_document(
    *,
    doc_type: str,
    language: str,
    fund_name: str,
    gestora_name: str,
    jurisdiction: str,
    governing_law: str,
    parties: list[dict[str, Any]],
    key_terms: list[dict[str, Any]],
    freetext: str,
    precedent_text: Optional[str],
    system: Optional[str] = None,
    extra_guidance: Optional[str] = None,
) -> str:
    """Generate the document text and append the SLP disclaimer.

    The verbatim ``GENERATION_PROMPT`` body is NEVER edited. Specialized
    drafting agents (services/drafting_agents.py) steer generation through two
    additive seams:

    - ``system``: an optional system persona (e.g. a branch persona +
      checklist) passed straight through to ``llm.complete(system=...)``.
    - ``extra_guidance``: an optional, clearly-labelled block (e.g. the
      gestora-siloed learned lessons) appended AFTER the template body so the
      template itself is untouched.

    Both default to ``None``, keeping the existing call signature working for
    legacy callers and tests.
    """
    prompt = (
        GENERATION_PROMPT
        .replace("{doc_type}", doc_type)
        .replace("{language}", language)
        .replace("{fund_name}", fund_name)
        .replace("{gestora_name}", gestora_name)
        .replace("{jurisdiction}", jurisdiction)
        .replace("{governing_law}", governing_law)
        .replace("{parties}", json.dumps(parties, ensure_ascii=False))
        .replace("{key_terms}", json.dumps(key_terms, ensure_ascii=False))
        .replace("{freetext}", freetext)
        .replace("{precedent_text}", precedent_text or NO_PRECEDENT_PLACEHOLDER)
    )
    if extra_guidance:
        prompt = f"{prompt}\n\n{EXTRA_GUIDANCE_HEADER}\n{extra_guidance}"
    # Verifiable-citation guidance: always appended (optional + additive for the
    # model) AFTER the verbatim template body, so the drafter may ground adapted
    # clauses with [SOURCE: ...] markers without ever editing GENERATION_PROMPT.
    prompt = f"{prompt}\n\n{SOURCE_GUIDANCE}"
    text = llm.complete(
        prompt, max_tokens=get_settings().max_generation_tokens, system=system
    ).strip()
    # Mandatory on every generated document (SPEC corporate structure).
    return f"{text}\n\n{SLP_DISCLAIMER}"


def refine_document(*, current_text: str, instruction: str) -> str:
    """Apply one targeted client revision to a previously generated document.

    Returns either the full revised document text or a verbatim
    ``[REFINEMENT-UNCLEAR: reason]`` marker (check with
    :func:`refinement_unclear_reason` — the caller must NOT create documents
    from an unclear output)."""
    prompt = (
        REFINEMENT_PROMPT
        .replace("{current_text}", current_text)
        .replace("{instruction}", instruction)
    )
    text = llm.complete(prompt, max_tokens=get_settings().max_generation_tokens).strip()
    if refinement_unclear_reason(text) is not None:
        return text
    # The disclaimer travels inside current_text; re-append if the model
    # dropped it (mandatory on every generated document).
    if SLP_DISCLAIMER not in text:
        text = f"{text}\n\n{SLP_DISCLAIMER}"
    return text
