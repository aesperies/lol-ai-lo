"""Claude intake parsing (SPEC.md verbatim prompt).

Extracts structured parameters from the client's free-text request. If
Anthropic is not configured, raises ServiceNotConfiguredError (API -> 503).
"""
from __future__ import annotations

import json
import re
from typing import Any

from config import ServiceNotConfiguredError, get_settings
from models.schema import UNCLASSIFIABLE_MESSAGE

# Verbatim from docs/SPEC.md — do not edit. Placeholders substituted via
# .replace() because the JSON braces would break str.format().
INTAKE_PROMPT = """You are a legal document intake parser for a European VC fund servicer.
Your job is to extract structured parameters from a client's document request.
INPUT:
- doc_type: {doc_type}
- freetext: {freetext}
OUTPUT (JSON only, no preamble):
{
  "language": "es|en|fr|de|other",
  "doc_type_confirmed": "string",
  "parties": [{"role": "string", "name": "string"}],
  "key_dates": [{"label": "string", "date": "string"}],
  "jurisdiction": "string",
  "governing_law": "string",
  "key_terms": [{"field": "string", "value": "string"}],
  "summary": "2-sentence human-readable summary in detected language",
  "confidence": 0.0-1.0,
  "unclear_fields": ["list of fields with confidence < 0.7"],
  "generation_ready": true|false
}
Rules:
- Respond ONLY in JSON. No markdown, no preamble.
- If confidence < 0.7 on any field, set generation_ready: false
- Always respond in the same language as the freetext
- For European VC context: assume AIFMD applies, default jurisdiction
  to Spain (CNMV) unless stated otherwise"""


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
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", "") == "text")


def _extract_json(raw: str) -> dict[str, Any]:
    """Parse the model output; tolerate stray code fences despite the prompt."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def parse_intake(doc_type: str, freetext: str) -> dict[str, Any]:
    """Run the intake parser and apply the SPEC post-rules.

    Post-rules (enforced server-side regardless of model output):
    - confidence < 0.7 or any unclear field -> generation_ready = False
    - doc_type 'other' and unclassifiable -> reformulation message, not ready
    """
    prompt = INTAKE_PROMPT.replace("{doc_type}", doc_type).replace("{freetext}", freetext)
    parsed = _extract_json(_call_claude(prompt))

    confidence = float(parsed.get("confidence") or 0.0)
    if confidence < 0.7 or parsed.get("unclear_fields"):
        parsed["generation_ready"] = False

    doc_type_confirmed = (parsed.get("doc_type_confirmed") or "").strip().lower()
    if doc_type.strip().lower().startswith("other") and doc_type_confirmed in ("", "other", "unknown", "unclassifiable"):
        parsed["generation_ready"] = False
        parsed["message"] = UNCLASSIFIABLE_MESSAGE

    return parsed
