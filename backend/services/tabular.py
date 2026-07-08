"""Tabular Review — multi-document extraction grid.

A gestora user defines columns (each a question + an answer type) over a set of
their own documents. For each (document × column) the model extracts one cell:
a typed value, short reasoning, and a verifiable citation (page + verbatim
quote) pointing to where in THAT document the answer was found.

All text generation goes through the :mod:`services.llm` seam
(``complete_json`` with :data:`CELL_SCHEMA`). The runner degrades gracefully:
if the LLM is unreachable every affected cell is marked ``error`` with a clear
message and the review ``failed`` — it NEVER crashes or hangs.

Isolation: callers (api/tabular.py) resolve and gestora-scope the review and
validate every referenced document against the caller's gestora BEFORE running.
This module only ever touches rows under one already-scoped review.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from config import ServiceNotConfiguredError
from models.schema import (
    TabularCellStatus,
    TabularColType,
    TabularReviewStatus,
    TabularSourceKind,
)
from services import db as dbmod
from services import docx_renderer, llm, rag, storage

logger = logging.getLogger("lolailo.tabular")

# Cap the document text sent per cell so a huge file can't blow the context
# window (long-doc safety). Truncation is annotated so the model knows the doc
# was cut and a citation page may lie beyond the excerpt.
_MAX_DOC_CHARS = 24_000

# Verbatim citation quotes are kept short and checkable.
_MAX_QUOTE_WORDS = 25

# JSON shape every extraction must return (services.llm.complete_json schema).
CELL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "value": {"type": "string"},
        "reasoning": {"type": "string"},
        "citation": {
            "type": "object",
            "properties": {
                "page": {"type": ["integer", "string", "null"]},
                "quote": {"type": "string"},
            },
        },
    },
    "required": ["value", "reasoning", "citation"],
}

# Per-type answer-format instruction injected into the extraction prompt.
_TYPE_INSTRUCTIONS: dict[TabularColType, str] = {
    TabularColType.text: (
        "Answer with a concise free-text value (a short phrase, not a paragraph)."
    ),
    TabularColType.number: (
        "Answer with a single number only (digits, optional decimal point and "
        "minus sign). No units, no thousands separators, no words."
    ),
    TabularColType.percent: (
        "Answer with a percentage value only, including the '%' sign "
        "(e.g. '12.5%')."
    ),
    TabularColType.monetary: (
        "Answer with a single monetary amount, including its currency symbol or "
        "ISO code (e.g. '€500,000' or '500000 EUR'). No extra words."
    ),
    TabularColType.date: (
        "Answer with a single date in ISO 8601 format (YYYY-MM-DD). If only a "
        "month or year is determinable, give the most precise ISO prefix."
    ),
    TabularColType.yes_no: (
        "Answer with exactly 'yes' or 'no' (lowercase), nothing else."
    ),
    TabularColType.tag: (
        "Answer with EXACTLY ONE of the allowed options listed below, copied "
        "verbatim. Do not invent new options."
    ),
}

_NOT_FOUND = "N/D"


def _coerce_col_type(value: Any) -> TabularColType:
    return value if isinstance(value, TabularColType) else TabularColType(value)


def build_cell_prompt(
    *,
    question: str,
    col_type: TabularColType,
    document_text: str,
    options: Optional[list[str]] = None,
) -> str:
    """Build the per-cell extraction prompt for one (document × column).

    Instructs the model to answer ONLY in the required format for ``col_type``
    and to return a citation object pointing to where in the document the answer
    is found. For ``tag`` columns the allowed ``options`` are listed.

    Args:
        question: The column's question.
        col_type: The answer type driving the format instruction.
        document_text: The (already-capped) text of the document to read.
        options: Allowed tag values (required for ``col_type == tag``).

    Returns:
        The complete user prompt for :func:`services.llm.complete_json`.
    """
    col_type = _coerce_col_type(col_type)
    instruction = _TYPE_INSTRUCTIONS[col_type]
    options_block = ""
    if col_type is TabularColType.tag and options:
        joined = ", ".join(f'"{opt}"' for opt in options)
        options_block = f"\nAllowed options (choose exactly one): {joined}\n"

    return (
        "You extract a single answer from ONE document. Read the document below "
        "and answer the question using ONLY information found in this document.\n\n"
        f"QUESTION: {question}\n\n"
        f"ANSWER FORMAT: {instruction}\n"
        f"{options_block}\n"
        "Also return a citation object pointing to where in the document the "
        "answer is found: {\"page\": <page number as int, or the string label, "
        "or null if the document has no page info>, \"quote\": \"<a VERBATIM "
        f"excerpt of at most {_MAX_QUOTE_WORDS} words copied exactly from the "
        "document that supports the answer>\"}.\n"
        f"If the answer cannot be found in the document, set value to \"{_NOT_FOUND}\", "
        "explain why in reasoning, and use an empty quote with page null.\n\n"
        "DOCUMENT:\n"
        f"{document_text}\n"
    )


def _cap_text(text: str) -> str:
    """Cap document text to the per-cell budget, annotating any truncation."""
    if len(text) <= _MAX_DOC_CHARS:
        return text
    return (
        text[:_MAX_DOC_CHARS]
        + "\n\n[DOCUMENTO TRUNCADO: el texto supera el límite y se ha recortado.]"
    )


def _normalise_citation(citation: Any) -> Optional[dict[str, Any]]:
    """Coerce the model's citation into {"page", "quote"} (quote word-capped)."""
    if not isinstance(citation, dict):
        return None
    page = citation.get("page")
    quote = citation.get("quote")
    if quote is not None:
        words = str(quote).split()
        if len(words) > _MAX_QUOTE_WORDS:
            quote = " ".join(words[:_MAX_QUOTE_WORDS])
        else:
            quote = str(quote)
    return {"page": page, "quote": quote}


def resolve_document_text(db: dbmod.Database, doc_row: dict[str, Any]) -> Optional[str]:
    """Load the plain text of a review document via the existing extractors.

    ``precedent_version`` -> :func:`services.rag.load_version_text`.
    ``request_document``  -> read the stored file + ``docx_renderer.extract_text``
    (plain-text fallback for non-docx stored bytes).

    Returns None when the source row is missing or its text can't be read.
    """
    source_kind = doc_row["source_kind"]
    source_id = doc_row["source_id"]

    if source_kind == TabularSourceKind.precedent_version.value:
        version = db.get("precedent_versions", source_id)
        if version is None:
            return None
        return rag.load_version_text(version)

    if source_kind == TabularSourceKind.request_document.value:
        document = db.get("documents", source_id)
        if document is None:
            return None
        try:
            data = storage.read(document["file_path"])
        except Exception:  # noqa: BLE001 — missing/unreadable file degrades to None
            logger.exception("Could not read stored file for document %s", source_id)
            return None
        if document["file_path"].lower().endswith(".docx"):
            try:
                return docx_renderer.extract_text(data)
            except Exception:  # noqa: BLE001
                logger.exception("Could not extract docx text for document %s", source_id)
                return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    return None


def extract_cell(
    *,
    question: str,
    col_type: TabularColType,
    document_text: str,
    options: Optional[list[str]] = None,
    gestora_id: Optional[str] = None,
) -> dict[str, Any]:
    """Run one extraction. Returns {"value", "reasoning", "citation"}.

    Raises ServiceNotConfiguredError when the LLM provider is unreachable so
    the caller can mark the cell 'error' and the review 'failed'. ``gestora_id``
    routes to the gestora's BYO LLM config when present (feature C); None →
    global.
    """
    prompt = build_cell_prompt(
        question=question,
        col_type=col_type,
        document_text=_cap_text(document_text),
        options=options,
    )
    result = llm.complete_json(prompt, CELL_SCHEMA, max_tokens=512, gestora_id=gestora_id, task="tabular")
    return {
        "value": str(result.get("value", "")).strip(),
        "reasoning": str(result.get("reasoning", "")).strip(),
        "citation": _normalise_citation(result.get("citation")),
    }


def _upsert_cell(
    db: dbmod.Database,
    *,
    review_id: str,
    document_id: str,
    column_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Update the (document × column) cell if present, else insert it."""
    existing = db.select(
        "tabular_review_cells", document_id=document_id, column_id=column_id
    )
    if existing:
        return db.update("tabular_review_cells", existing[0]["id"], fields)
    return db.insert(
        "tabular_review_cells",
        {"review_id": review_id, "document_id": document_id, "column_id": column_id, **fields},
    )


async def run_review(db: dbmod.Database, review_id: str) -> None:
    """Extract every (document × column) cell for one review.

    The review is already gestora-scoped by the caller. Transitions the review
    running -> complete (or failed). On an unreachable LLM every remaining cell
    is marked 'error' and the review 'failed' — never crashes or hangs.

    Async so it composes with the JobRunner; the work itself is synchronous.
    """
    review = db.get("tabular_reviews", review_id)
    if review is None:
        logger.warning("run_review: review %s not found", review_id)
        return

    db.update("tabular_reviews", review_id, {"status": TabularReviewStatus.running.value})

    columns = sorted(
        db.select("tabular_review_columns", review_id=review_id),
        key=lambda c: c.get("position", 0),
    )
    documents = sorted(
        db.select("tabular_review_documents", review_id=review_id),
        key=lambda d: d.get("position", 0),
    )

    # Resolve each document's text once (reused across columns).
    doc_texts: dict[str, Optional[str]] = {
        doc["id"]: resolve_document_text(db, doc) for doc in documents
    }

    any_error = False
    llm_down = False

    for doc in documents:
        text = doc_texts.get(doc["id"])
        for col in columns:
            if llm_down:
                # Once the provider is known down, fail fast for the rest.
                _upsert_cell(
                    db,
                    review_id=review_id,
                    document_id=doc["id"],
                    column_id=col["id"],
                    fields={
                        "value": None,
                        "reasoning": None,
                        "citation": None,
                        "status": TabularCellStatus.error.value,
                        "error": "El servicio de IA no está disponible.",
                    },
                )
                any_error = True
                continue

            if not text:
                _upsert_cell(
                    db,
                    review_id=review_id,
                    document_id=doc["id"],
                    column_id=col["id"],
                    fields={
                        "value": None,
                        "reasoning": None,
                        "citation": None,
                        "status": TabularCellStatus.error.value,
                        "error": "No se pudo leer el texto del documento.",
                    },
                )
                any_error = True
                continue

            try:
                cell = extract_cell(
                    question=col["question"],
                    col_type=_coerce_col_type(col["col_type"]),
                    document_text=text,
                    options=col.get("options"),
                    gestora_id=review.get("gestora_id"),
                )
            except ServiceNotConfiguredError:
                logger.warning(
                    "run_review %s: LLM unreachable; marking remaining cells error.",
                    review_id,
                )
                llm_down = True
                any_error = True
                _upsert_cell(
                    db,
                    review_id=review_id,
                    document_id=doc["id"],
                    column_id=col["id"],
                    fields={
                        "value": None,
                        "reasoning": None,
                        "citation": None,
                        "status": TabularCellStatus.error.value,
                        "error": "El servicio de IA no está disponible.",
                    },
                )
                continue
            except Exception as exc:  # noqa: BLE001 — one bad cell must not abort the grid
                logger.exception("run_review %s: cell extraction failed", review_id)
                any_error = True
                _upsert_cell(
                    db,
                    review_id=review_id,
                    document_id=doc["id"],
                    column_id=col["id"],
                    fields={
                        "value": None,
                        "reasoning": None,
                        "citation": None,
                        "status": TabularCellStatus.error.value,
                        "error": str(exc)[:500],
                    },
                )
                continue

            _upsert_cell(
                db,
                review_id=review_id,
                document_id=doc["id"],
                column_id=col["id"],
                fields={
                    "value": cell["value"],
                    "reasoning": cell["reasoning"],
                    "citation": cell["citation"],
                    "status": TabularCellStatus.done.value,
                    "error": None,
                },
            )

    if llm_down:
        final_status = TabularReviewStatus.failed.value
    elif any_error and not columns:
        # No columns/documents to do anything meaningful with → still complete.
        final_status = TabularReviewStatus.complete.value
    else:
        final_status = TabularReviewStatus.complete.value
    db.update("tabular_reviews", review_id, {"status": final_status})
