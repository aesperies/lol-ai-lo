"""Claude document generation (SPEC.md verbatim prompt).

Generates the full document text from the confirmed parameters plus the
retrieved precedent, then appends the mandatory Lol-AI-lo Legal SLP
disclaimer. Raises ServiceNotConfiguredError when Anthropic is unset.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from config import ServiceNotConfiguredError, get_settings
from models.schema import SLP_DISCLAIMER

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
3. Keep all existing [DEVIATION: ...] and [MISSING: ...] flags that
   are still accurate; add new ones if your change introduces them;
   remove ones the change resolves.
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


def _call_claude(prompt: str) -> str:
    settings = get_settings()
    if not settings.anthropic_configured:
        raise ServiceNotConfiguredError("anthropic", "Set ANTHROPIC_API_KEY.")
    # Lazy import: heavy optional dep; app must start without it.
    import anthropic  # type: ignore[import-not-found]

    # TODO: real Anthropic API key required (ANTHROPIC_API_KEY).
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


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
) -> str:
    """Generate the document text and append the SLP disclaimer."""
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
    text = _call_claude(prompt).strip()
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
    text = _call_claude(prompt).strip()
    if refinement_unclear_reason(text) is not None:
        return text
    # The disclaimer travels inside current_text; re-append if the model
    # dropped it (mandatory on every generated document).
    if SLP_DISCLAIMER not in text:
        text = f"{text}\n\n{SLP_DISCLAIMER}"
    return text
