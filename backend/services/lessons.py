"""Learning from counsel-validated documents — STRICTLY gestora-siloed.

The inviolable isolation rule (SPEC guardrails 1 & 3) applies here exactly as
it does to precedents: a lesson distilled from gestora A's validated documents
is NEVER retrievable for gestora B. There is no global / cross-gestora lesson
pool — every read and write hard-filters on ``gestora_id``.

Two halves:

- :func:`extract_lessons` — an LLM pass (``complete_json``) that compares the
  AI draft to the counsel-validated final and distills up to 3 SHORT,
  generalizable drafting rules. Short-circuits (no-op) when the draft and final
  are already near-identical (little to learn) or the LLM is unreachable, so it
  is safe to enqueue after every validation. Stores each rule as a
  ``drafting_lessons`` row, gestora-siloed.
- :func:`lessons_for` — retrieves the most relevant/recent lessons for the
  specialized drafter (services/drafting_agents.py). Hard ``gestora_id`` filter,
  then branch (+ preferred doc_type), ranked by weight × recency, capped at
  ``top_k``.

Failures here must NEVER block delivery: the validation flow swallows + logs
them (the extraction is enqueued on the async JobRunner).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import asyncio

from config import ServiceNotConfiguredError, get_settings
from models.doc_branches import Branch, branch_for
from services import db as dbmod
from services import docx_renderer, jobs, llm, quality, storage

logger = logging.getLogger("lolailo.lessons")

# JSON contract for the extraction pass.
LESSONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lessons": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 3,
        }
    },
    "required": ["lessons"],
}

_EXTRACTION_SYSTEM = (
    "You are a drafting-quality analyst for a European VC fund legal servicer. "
    "You compare an AI-generated draft with the version a human lawyer "
    "validated, and distill GENERALIZABLE drafting rules the drafter should "
    "apply next time. Output strictly the requested JSON."
)

_EXTRACTION_PROMPT = """Compare the AI DRAFT with the COUNSEL-VALIDATED FINAL of a {branch} document\
 (type: {doc_type}).

Distill up to 3 SHORT, generalizable drafting rules describing what the drafter\
 should have done differently next time. Each rule must:
- be a single concise imperative sentence (a reusable rule, not a description);
- generalize across future documents of this kind;
- DISCARD one-off, party-specific or date/amount-specific edits (names,
  numbers, this deal's particular terms) — those teach nothing reusable.

If the counsel changes were purely cosmetic or party-specific, return an empty
list.

AI DRAFT:
{ai_draft}

COUNSEL-VALIDATED FINAL:
{final}
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_branch(branch: Any) -> str:
    """Accept a Branch enum or its string value; store the string value."""
    return branch.value if isinstance(branch, Branch) else str(branch)


def extract_lessons(
    *,
    gestora_id: str,
    branch: Any,
    doc_type: Optional[str],
    ai_draft_text: str,
    final_text: str,
    source_request_id: Optional[str],
    db: Optional[dbmod.Database] = None,
) -> list[str]:
    """Distill up to 3 gestora-siloed drafting lessons from a validated doc.

    No-op (returns ``[]``) when:
    - the draft and final are already near-identical (similarity at or above
      ``lessons_similarity_skip_threshold`` — little/nothing to learn; covers
      the Exit A accepted-as-is case where final ≈ draft); or
    - the LLM is unreachable / misconfigured (graceful degradation); or
    - the model returns no generalizable rules.

    Each returned lesson is also persisted as a ``drafting_lessons`` row keyed
    on ``gestora_id`` (the isolation anchor). Never raises on LLM/parse errors
    — the caller is a best-effort async job.
    """
    settings = get_settings()
    branch_value = _coerce_branch(branch)
    store = db if db is not None else dbmod.get_db()

    # High-similarity short-circuit: nothing meaningful changed.
    similarity = quality.compute_quality_metric(ai_draft_text, final_text)["similarity"]
    if similarity >= settings.lessons_similarity_skip_threshold:
        logger.info(
            "Lessons extraction skipped (similarity %.4f >= %.4f) for request %s",
            similarity,
            settings.lessons_similarity_skip_threshold,
            source_request_id,
        )
        return []

    prompt = (
        _EXTRACTION_PROMPT
        .replace("{branch}", branch_value)
        .replace("{doc_type}", doc_type or "uncatalogued")
        .replace("{ai_draft}", ai_draft_text)
        .replace("{final}", final_text)
    )
    try:
        result = llm.complete_json(
            prompt, LESSONS_SCHEMA, system=_EXTRACTION_SYSTEM
        )
    except ServiceNotConfiguredError:
        logger.info("Lessons extraction skipped: LLM unreachable (request %s)", source_request_id)
        return []
    except Exception as exc:  # noqa: BLE001 — best-effort, never block delivery
        logger.warning("Lessons extraction failed for request %s: %s", source_request_id, exc)
        return []

    raw = result.get("lessons") or []
    lessons = [
        cleaned
        for item in raw
        if isinstance(item, str) and (cleaned := item.strip())
    ][:3]

    for lesson in lessons:
        store.insert(
            "drafting_lessons",
            {
                "gestora_id": gestora_id,  # isolation anchor — hard filter on read
                "branch": branch_value,
                "doc_type": doc_type,
                "lesson": lesson,
                "source_request_id": source_request_id,
                "weight": 1.0,
            },
        )
    logger.info(
        "Extracted %d lesson(s) for gestora %s / branch %s (request %s)",
        len(lessons),
        gestora_id,
        branch_value,
        source_request_id,
    )
    return lessons


def _recency_key(row: dict[str, Any]) -> str:
    return str(row.get("created_at") or "")


def lessons_for(
    db: dbmod.Database,
    *,
    gestora_id: str,
    branch: Any,
    doc_type: Optional[str] = None,
    top_k: Optional[int] = None,
) -> list[str]:
    """Retrieve up to ``top_k`` drafting lessons for the specialized drafter.

    HARD ``gestora_id`` filter (isolation: another gestora's lessons can never
    surface). Within the gestora silo, filters by ``branch``; lessons whose
    ``doc_type`` matches the request's are preferred (ranked first), then the
    rest of the branch. Ordered by weight × recency, capped at ``top_k``.
    """
    if top_k is None:
        top_k = get_settings().drafting_lessons_top_k
    branch_value = _coerce_branch(branch)

    # gestora_id + branch is the hard pre-filter (db.select equality match).
    rows = db.select("drafting_lessons", gestora_id=gestora_id, branch=branch_value)

    def rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
        doc_match = 1 if doc_type is not None and row.get("doc_type") == doc_type else 0
        weight = float(row.get("weight", 1.0))
        return (doc_match, weight, _recency_key(row))

    rows.sort(key=rank_key, reverse=True)
    return [row["lesson"] for row in rows[:top_k]]


def _document_text(file_path: str) -> str:
    return docx_renderer.extract_text(storage.read(file_path))


def enqueue_extraction(
    db: dbmod.Database,
    *,
    gestora_id: str,
    doc_type: str,
    request_id: str,
    ai_draft_path: Optional[str],
    final_path: str,
) -> None:
    """Enqueue gestora-siloed lessons extraction off the request thread.

    Hooked into the validation flow (Exit B counsel validate; Exit A
    accepted-as-is) so it NEVER blocks delivery. Reads the document texts and
    fires a best-effort background task (services/jobs.py). All failures —
    including no AI draft, an empty event loop, or LLM errors — are swallowed +
    logged; the workflow is unaffected.
    """
    if ai_draft_path is None:
        return
    try:
        ai_draft_text = _document_text(ai_draft_path)
        final_text = _document_text(final_path)
    except Exception:  # noqa: BLE001 — best-effort, never block delivery
        logger.exception("Lessons extraction setup failed for request %s", request_id)
        return

    branch = branch_for(doc_type)

    async def _job() -> None:
        # extract_lessons runs blocking I/O (LLM call); offload to a thread so
        # the event loop is never blocked, mirroring the generation pipeline.
        await asyncio.to_thread(
            extract_lessons,
            gestora_id=gestora_id,
            branch=branch,
            doc_type=doc_type,
            ai_draft_text=ai_draft_text,
            final_text=final_text,
            source_request_id=request_id,
            db=db,
        )

    jobs.get_runner().enqueue_background(_job, label=f"lessons:{request_id}")


# TODO: light de-dup / consolidation once many near-duplicate lessons
# accumulate per (gestora, branch) — e.g. merge by embedding similarity and
# decay weight. Kept simple for now.
