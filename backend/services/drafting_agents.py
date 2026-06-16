"""Specialized drafting agents per branch (drafting-agents Feature 1).

Each request is routed (by doc_type) to a :class:`Branch` whose persona +
checklist (:data:`models.doc_branches.BRANCH_GUIDANCE`) is passed to the LLM as
the ``system`` message, and the gestora's learned lessons (services/lessons.py,
strictly siloed) are injected as a clearly-labelled guidance block. Both seams
are ADDITIVE: the verbatim ``GENERATION_PROMPT`` body is never edited — the
actual call is delegated to :func:`generator.generate_document` via its new
``system`` / ``extra_guidance`` kwargs, preserving the SLP disclaimer logic.

:func:`draft` is a drop-in replacement for ``generator.generate_document`` in
the generation pipeline (same args + ``gestora_id``). :func:`draft_with_review`
additionally runs the critic loop (services/critic.py) on top of the first
draft.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from models.doc_branches import Branch, branch_for, guidance_for
from services import critic, db as dbmod, lessons

logger = logging.getLogger("lolailo.drafting_agents")


def _lessons_block(
    db: Optional[dbmod.Database],
    *,
    gestora_id: str,
    branch: Branch,
    doc_type: str,
) -> Optional[str]:
    """The gestora-siloed lessons block (numbered list) or None when there is
    nothing learned yet. HARD gestora_id filter lives in lessons.lessons_for."""
    if db is None:
        return None
    items = lessons.lessons_for(
        db, gestora_id=gestora_id, branch=branch, doc_type=doc_type
    )
    if not items:
        return None
    return "\n".join(f"{idx}. {text}" for idx, text in enumerate(items, start=1))


def draft(
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
    gestora_id: str,
    db: Optional[dbmod.Database] = None,
) -> str:
    """Produce one specialized draft via the branch agent.

    Routes ``doc_type`` to its :class:`Branch`, passes the branch persona +
    checklist as the ``system`` message and injects the gestora's learned
    lessons (top-K, siloed) as ``extra_guidance`` — then delegates to
    :func:`generator.generate_document` (verbatim template untouched, SLP
    disclaimer preserved).
    """
    # Local import: avoid any import-time coupling with the verbatim generator.
    from services import generator

    branch = branch_for(doc_type)
    system = guidance_for(branch)
    extra_guidance = _lessons_block(
        db, gestora_id=gestora_id, branch=branch, doc_type=doc_type
    )
    return generator.generate_document(
        doc_type=doc_type,
        language=language,
        fund_name=fund_name,
        gestora_name=gestora_name,
        jurisdiction=jurisdiction,
        governing_law=governing_law,
        parties=parties,
        key_terms=key_terms,
        freetext=freetext,
        precedent_text=precedent_text,
        system=system,
        extra_guidance=extra_guidance,
    )


def draft_with_review(
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
    parsed_params: dict[str, Any],
    gestora_id: str,
    db: Optional[dbmod.Database] = None,
) -> critic.DraftWithReviewResult:
    """Produce a specialized first draft (Feature 1) and run the critic loop
    (Feature 2) over it. Returns the best draft + structured review trail."""
    branch = branch_for(doc_type)
    first = draft(
        doc_type=doc_type,
        language=language,
        fund_name=fund_name,
        gestora_name=gestora_name,
        jurisdiction=jurisdiction,
        governing_law=governing_law,
        parties=parties,
        key_terms=key_terms,
        freetext=freetext,
        precedent_text=precedent_text,
        gestora_id=gestora_id,
        db=db,
    )
    return critic.draft_with_review(
        first_draft=first,
        doc_type=doc_type,
        branch=branch,
        parsed_params=parsed_params,
        precedent_text=precedent_text,
        # Thread the gestora through so the critic enforces the gestora's siloed
        # review playbooks (services/playbooks.py); no-op when none are active.
        gestora_id=gestora_id,
        db=db,
    )
