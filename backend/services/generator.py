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
