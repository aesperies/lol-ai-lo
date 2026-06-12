"""Claude intake parsing (SPEC.md verbatim prompt).

Extracts structured parameters from the client's free-text request. If
Anthropic is not configured, raises ServiceNotConfiguredError (API -> 503).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from config import ServiceNotConfiguredError, get_settings
from models import doc_fields
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

# Structured intake (improvement #5): when the client filled structured
# fields, they are appended to the prompt INPUT section plus one extra rule.
# The verbatim SPEC prompt above stays untouched; these blocks are spliced in
# at build time only when structured_fields are present.
STRUCTURED_FIELDS_INPUT = (
    "- structured_fields (client-provided, authoritative — do not second-guess "
    "these values):\n{structured_fields_json}\n"
)
STRUCTURED_FIELDS_RULE = (
    "- Values in structured_fields are authoritative: copy them into the "
    "corresponding output fields with confidence 1.0; only freetext-derived "
    "fields can be unclear."
)

_OUTPUT_MARKER = "OUTPUT (JSON only, no preamble):"


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


def parse_intake(
    doc_type: str,
    freetext: str,
    structured_fields: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run the intake parser and apply the SPEC post-rules.

    Post-rules (enforced server-side regardless of model output):
    - confidence < 0.7 or any unclear field -> generation_ready = False
    - doc_type 'other' and unclassifiable -> reformulation message, not ready
    - structured_fields (when present) are deterministically merged OVER the
      parser output (models/doc_fields.py): client values win conflicts, the
      covered fields leave unclear_fields and generation_ready is recomputed.
    """
    prompt = INTAKE_PROMPT.replace("{doc_type}", doc_type).replace("{freetext}", freetext)
    if structured_fields:
        section = STRUCTURED_FIELDS_INPUT.replace(
            "{structured_fields_json}",
            json.dumps(structured_fields, ensure_ascii=False),
        )
        prompt = prompt.replace(_OUTPUT_MARKER, section + _OUTPUT_MARKER, 1)
        prompt = f"{prompt}\n{STRUCTURED_FIELDS_RULE}"
    parsed = _extract_json(_call_claude(prompt))

    confidence = float(parsed.get("confidence") or 0.0)
    if confidence < 0.7 or parsed.get("unclear_fields"):
        parsed["generation_ready"] = False

    doc_type_confirmed = (parsed.get("doc_type_confirmed") or "").strip().lower()
    if doc_type.strip().lower().startswith("other") and doc_type_confirmed in ("", "other", "unknown", "unclassifiable"):
        parsed["generation_ready"] = False
        parsed["message"] = UNCLASSIFIABLE_MESSAGE

    if structured_fields:
        # Post-merge in code: the LLM is INSTRUCTED to honor structured
        # values, but the client input must win deterministically.
        parsed = doc_fields.merge_structured_into_parsed(parsed, doc_type, structured_fields)

    return parsed
