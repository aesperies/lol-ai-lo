"""Quality metric: draft→validated edit distance (improvement #6).

The platform's core quality KPI: how much did counsel change the AI draft?
One quality_metrics row per request (UNIQUE on request_id):

- Exit B — at validation time, similarity between the latest draft iteration
  and the final (counsel_edit) version, computed with difflib on normalized
  text (whitespace collapsed, casefolded). similarity 1.0 = counsel validated
  the AI draft untouched.
- Exit A — at download time, similarity 1.0 by definition: the client
  accepted the draft as-is (the strongest quality signal).

Recording a metric must NEVER block the workflow: callers wrap these helpers
in try/except and log failures (see api/requests.py). No new dependencies —
difflib only.
"""
from __future__ import annotations

import difflib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from models.schema import RefinementStatus
from services import db as dbmod
from services import docx_renderer, storage

logger = logging.getLogger("lolailo.quality")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    """Collapse whitespace and casefold so formatting noise is not 'change'."""
    return " ".join(text.split()).casefold()


def compute_quality_metric(draft_text: str, final_text: str) -> dict[str, Any]:
    """Similarity + word-level change count between draft and final text.

    similarity is difflib.SequenceMatcher.ratio() on the normalized texts
    (0.0–1.0; 1.0 = identical). words_changed counts words on either side of
    every non-equal opcode (the larger side per opcode, so a 1:1 replacement
    counts once).
    """
    norm_draft = _normalize(draft_text)
    norm_final = _normalize(final_text)
    similarity = difflib.SequenceMatcher(a=norm_draft, b=norm_final).ratio()

    draft_words = norm_draft.split()
    final_words = norm_final.split()
    words_changed = sum(
        max(i2 - i1, j2 - j1)
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            a=draft_words, b=final_words
        ).get_opcodes()
        if tag != "equal"
    )
    return {
        "similarity": similarity,
        "chars_draft": len(norm_draft),
        "chars_final": len(norm_final),
        "words_changed": words_changed,
    }


# ---------------------------------------------------------------------------
# Persistence (one metric row per request; UNIQUE(request_id) in the DB)
# ---------------------------------------------------------------------------

def _refinements_used(db: dbmod.Database, request_id: str) -> int:
    """Applied refinements only (failed ones produced no new iteration)."""
    rows = db.select("refinements", request_id=request_id)
    return len([r for r in rows if r["status"] == RefinementStatus.applied.value])


def _fallback_level(db: dbmod.Database, request_id: str) -> Optional[int]:
    """Precedent fallback level used at generation time, read from the
    document_generated audit metadata (rag_level; refinement re-generations
    do not carry it, so the original generation entry wins)."""
    levels = [
        entry["metadata"]["rag_level"]
        for entry in db.select("audit_log", action="document_generated")
        if (entry.get("metadata") or {}).get("request_id") == request_id
        and "rag_level" in (entry.get("metadata") or {})
    ]
    return levels[-1] if levels else None


def _document_text(doc: dict[str, Any]) -> str:
    return docx_renderer.extract_text(storage.read(doc["file_path"]))


def _insert_metric(
    db: dbmod.Database,
    *,
    request_row: dict[str, Any],
    gestora_id: str,
    draft_doc: dict[str, Any],
    computed: dict[str, Any],
) -> Optional[dict[str, Any]]:
    # Mirrors the UNIQUE(request_id) constraint in the dev store: at most one
    # metric per request (e.g. exit-a/download is re-callable).
    if db.select("quality_metrics", request_id=request_row["id"]):
        return None
    return db.insert(
        "quality_metrics",
        {
            "request_id": request_row["id"],
            "gestora_id": gestora_id,
            "doc_type": request_row["doc_type"],
            "language": request_row.get("language"),
            "draft_iteration": draft_doc.get("iteration", 0),
            "similarity": computed["similarity"],
            "chars_draft": computed["chars_draft"],
            "chars_final": computed["chars_final"],
            "words_changed": computed["words_changed"],
            "refinements_used": _refinements_used(db, request_row["id"]),
            "fallback_level": _fallback_level(db, request_row["id"]),
            "computed_at": _now_iso(),
        },
    )


def record_exit_b_metric(
    db: dbmod.Database,
    *,
    request_row: dict[str, Any],
    gestora_id: str,
    draft_doc: Optional[dict[str, Any]],
    final_doc_path: str,
) -> Optional[dict[str, Any]]:
    """Exit B: compare the latest AI draft iteration with the validated final.

    Caller wraps in try/except — a metric failure never blocks validation.
    """
    if draft_doc is None:
        return None
    draft_text = _document_text(draft_doc)
    final_text = docx_renderer.extract_text(storage.read(final_doc_path))
    computed = compute_quality_metric(draft_text, final_text)
    return _insert_metric(
        db, request_row=request_row, gestora_id=gestora_id, draft_doc=draft_doc, computed=computed
    )


def record_exit_a_metric(
    db: dbmod.Database,
    *,
    request_row: dict[str, Any],
    gestora_id: str,
    draft_doc: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Exit A: the client accepted the draft as-is → similarity 1.0.

    Caller wraps in try/except — a metric failure never blocks delivery.
    """
    text = _normalize(_document_text(draft_doc))
    computed = {
        "similarity": 1.0,
        "chars_draft": len(text),
        "chars_final": len(text),
        "words_changed": 0,
    }
    return _insert_metric(
        db, request_row=request_row, gestora_id=gestora_id, draft_doc=draft_doc, computed=computed
    )
