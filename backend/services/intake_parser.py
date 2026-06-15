"""Intake parsing (SPEC.md verbatim prompt).

Extracts structured parameters from the client's free-text request. Parsing
routes through the provider-agnostic seam (services/llm.py) using JSON mode:
local Ollama by default (native ``format=json``), Anthropic Claude as an
optional cloud fallback (prompt-driven JSON). Raises ServiceNotConfiguredError
when the selected provider is misconfigured or unreachable (API -> 503).
"""
from __future__ import annotations

import json
from typing import Any, Optional

from models import doc_fields
from models.schema import UNCLASSIFIABLE_MESSAGE
from services import llm

# JSON schema for the parser output (SPEC OUTPUT object). Passed to the LLM
# seam so Ollama runs in JSON mode and the model knows the target shape.
INTAKE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "enum": ["es", "en", "fr", "de", "other"]},
        "doc_type_confirmed": {"type": "string"},
        "parties": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"role": {"type": "string"}, "name": {"type": "string"}},
            },
        },
        "key_dates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "date": {"type": "string"}},
            },
        },
        "jurisdiction": {"type": "string"},
        "governing_law": {"type": "string"},
        "key_terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"field": {"type": "string"}, "value": {"type": "string"}},
            },
        },
        "summary": {"type": "string"},
        "confidence": {"type": "number"},
        "unclear_fields": {"type": "array", "items": {"type": "string"}},
        "generation_ready": {"type": "boolean"},
    },
    "required": [
        "language",
        "doc_type_confirmed",
        "parties",
        "key_dates",
        "jurisdiction",
        "governing_law",
        "key_terms",
        "summary",
        "confidence",
        "unclear_fields",
        "generation_ready",
    ],
}

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
    # JSON mode (native on Ollama, prompt-driven on Anthropic) with one repair
    # retry on invalid output.
    parsed = llm.complete_json(prompt, INTAKE_SCHEMA, max_tokens=2048)

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
