"""Critic / reviewer loop (drafting-agents Feature 2).

After the specialized drafter produces a draft (services/drafting_agents.py),
:func:`review` runs an LLM "critic" pass that flags ONLY substantive problems
(factual errors vs the supplied parameters, missing mandatory clauses /
``[MISSING]`` gaps, legal / consistency errors). It NEVER flags stylistic
preferences or rephrasings — a sound draft returns ``approved: true`` with no
issues.

:func:`draft_with_review` is the loop controller:
  1. produce the first draft (passed in by the caller);
  2. review it; approved (or only sub-threshold issues) → done;
  3. otherwise build a revision instruction from the issues + suggested fixes
     and ask the drafter to revise (``generator.refine_document``);
  4. re-review; repeat up to ``critic_max_rounds`` revision rounds;
  5. if still not approved after the budget → force Exit B
     (``requires_counsel=True``) and record why.

Graceful degradation: the critic is an EXTRA LLM pass. If the LLM is
unreachable (or ``critic_enabled`` is false) the whole loop is SKIPPED and the
original draft proceeds unchanged — exactly what the conftest unreachable-Ollama
simulation exercises.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from config import ServiceNotConfiguredError, get_settings
from models.doc_branches import Branch
from services import db as dbmod, generator, llm, playbooks

logger = logging.getLogger("lolailo.critic")

# Severity ordering (higher = more severe). Used to decide which issues force a
# revision (>= critic_min_severity_to_revise).
_SEVERITY_RANK = {"minor": 1, "major": 2, "blocking": 3}

CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"enum": ["blocking", "major", "minor"]},
                    "category": {
                        "enum": ["factual", "completeness", "legal", "consistency"]
                    },
                    "problem": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                    "location": {"type": "string"},
                    # Verifiable grounding (grounding Feature 2): the exact draft
                    # text this issue is about, so "something is wrong" is
                    # checkable. Same SHAPE as the tabular-review citation
                    # ({where/quote} mirrors {page/quote}).
                    "citation": {
                        "type": "object",
                        "properties": {
                            "where": {"type": "string"},
                            "quote": {"type": "string"},
                        },
                    },
                },
                "required": ["severity", "category", "problem"],
            },
        },
    },
    "required": ["approved", "issues"],
}

_CRITIC_SYSTEM = (
    "You are a meticulous senior legal reviewer for a European VC fund "
    "servicer. You review a generated draft for SUBSTANTIVE defects only. "
    "Flag ONLY: factual errors versus the provided parameters; missing "
    "mandatory clauses or unresolved [MISSING] gaps; legal errors; internal "
    "inconsistencies. NEVER flag stylistic preferences, tone, or alternative "
    "phrasings, and NEVER rewrite the document. Every issue you raise MUST be "
    'grounded with a "citation" object pointing to the exact draft text it is '
    'about: {"where": "<clause/section ref or short locator in the DRAFT>", '
    '"quote": "<verbatim excerpt from the draft, ≤25 words, copied exactly, '
    'that is problematic>"}. For a MISSING-clause issue, quote the surrounding '
    "draft text where the clause should appear (or the empty [MISSING] marker). "
    "If the draft is substantively sound, return approved=true with an empty "
    "issues list. Output strictly the requested JSON."
)

_CRITIC_PROMPT = """Review this {branch} draft (document type: {doc_type}).

CONFIRMED PARAMETERS (the source of truth — the draft must not contradict these\
 and must not invent parties, amounts or dates beyond them):
{parsed_params}

PRECEDENT THE DRAFT WAS BASED ON (structural/stylistic reference; absence of a\
 clause here is not itself a defect):
{precedent}

DRAFT UNDER REVIEW:
{draft}
{playbook}
Return JSON matching the schema. Set approved=false only if at least one\
 substantive (factual / completeness / legal / consistency) issue exists.\
 Each issue MUST include a "citation" {where, quote} pointing to the exact\
 DRAFT text it is about (quote verbatim, ≤25 words).\
 Otherwise approved=true with issues: []."""

# Header for the gestora-authored review rules, injected only when the gestora
# has active playbooks for this request (otherwise the placeholder is empty and
# the critic behaves exactly as before).
_PLAYBOOK_HEADER = (
    "GESTORA REVIEW PLAYBOOK — enforce these rules (treat a violation as a "
    "substantive issue of the most appropriate category):"
)


def _playbook_block(
    db: Optional[dbmod.Database],
    *,
    gestora_id: Optional[str],
    branch_value: str,
    doc_type: str,
) -> str:
    """The gestora-siloed playbook block to inject, or "" when there is nothing
    to enforce. HARD gestora_id filter lives in playbooks.playbooks_for."""
    if db is None or not gestora_id:
        return ""
    rules = playbooks.playbooks_for(
        db, gestora_id=gestora_id, branch=branch_value, doc_type=doc_type
    )
    if not rules:
        return ""
    body = "\n\n".join(rules)
    return f"\n{_PLAYBOOK_HEADER}\n{body}\n"

_REVISION_HEADER = (
    "A legal reviewer flagged the following SUBSTANTIVE issues in the current "
    "document. Revise the FULL document to resolve every issue below, changing "
    "ONLY what each fix requires and leaving all other clauses intact. Keep "
    "language, governing law, jurisdiction, defined terms and numbering "
    "unchanged. Issues to fix:"
)


# Verbatim draft-quote citations are kept short and checkable (mirrors the
# tabular-review quote cap so the {where, quote} citation shape is consistent).
_MAX_CITATION_QUOTE_WORDS = 25


def _normalise_citation(raw: Any) -> Optional[dict[str, str]]:
    """Coerce the critic's citation into {"where", "quote"} (quote word-capped),
    or None when no usable citation was supplied. Same SHAPE as the tabular
    {page, quote} citation, with ``where`` as the DRAFT locator."""
    if not isinstance(raw, dict):
        return None
    where = str(raw.get("where", "")).strip()
    quote = str(raw.get("quote", "")).strip()
    if not where and not quote:
        return None
    words = quote.split()
    if len(words) > _MAX_CITATION_QUOTE_WORDS:
        quote = " ".join(words[:_MAX_CITATION_QUOTE_WORDS])
    return {"where": where, "quote": quote}


@dataclass
class Issue:
    """One substantive defect raised by the critic."""

    severity: str
    category: str
    problem: str
    suggested_fix: str = ""
    location: str = ""
    # Verifiable grounding (grounding Feature 2): {where, quote} pointing to the
    # exact problematic DRAFT text. None when the critic supplied no citation.
    citation: Optional[dict[str, str]] = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Issue":
        return cls(
            severity=str(raw.get("severity", "minor")).lower(),
            category=str(raw.get("category", "consistency")).lower(),
            problem=str(raw.get("problem", "")),
            suggested_fix=str(raw.get("suggested_fix", "")),
            location=str(raw.get("location", "")),
            citation=_normalise_citation(raw.get("citation")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "problem": self.problem,
            "suggested_fix": self.suggested_fix,
            "location": self.location,
            "citation": self.citation,
        }


@dataclass
class Verdict:
    """The outcome of one critic review pass."""

    approved: bool
    issues: list[Issue] = field(default_factory=list)
    # True when the critic was skipped (LLM unreachable / disabled): the draft
    # is treated as approved-by-default so the workflow proceeds unchanged.
    skipped: bool = False

    def issues_at_or_above(self, min_severity: str) -> list[Issue]:
        threshold = _SEVERITY_RANK.get(min_severity, 2)
        return [i for i in self.issues if _SEVERITY_RANK.get(i.severity, 1) >= threshold]


@dataclass
class ReviewRound:
    """One persisted critic round in the review trail."""

    round: int
    approved: bool
    issues: list[dict[str, Any]]
    model_note: Optional[str] = None


@dataclass
class DraftWithReviewResult:
    """Best draft plus the structured review trail from the loop."""

    text: str
    rounds: list[ReviewRound]
    approved: bool
    forced_counsel: bool

    @property
    def critic_ran(self) -> bool:
        return bool(self.rounds)


def review(
    *,
    draft_text: str,
    doc_type: str,
    branch: Branch,
    parsed_params: dict[str, Any],
    precedent_text: Optional[str],
    gestora_id: Optional[str] = None,
    db: Optional[dbmod.Database] = None,
) -> Verdict:
    """Run one critic pass over ``draft_text``.

    When ``gestora_id`` (+ ``db``) is supplied, the gestora's ACTIVE review
    playbooks (services/playbooks.py, hard gestora_id filter) are injected into
    the prompt so the reviewer enforces them on top of its built-in checks. With
    no playbooks the prompt is byte-for-byte what it was before, so the critic
    behaves exactly as today.

    Returns a :class:`Verdict`. When the LLM is unreachable / misconfigured the
    verdict is ``approved=True, skipped=True`` (graceful degradation: the draft
    proceeds). Robust to JSON issues — ``complete_json`` already repair-retries;
    any residual parse failure also degrades to a skipped, approved verdict
    rather than blocking the pipeline.
    """
    branch_value = branch.value if isinstance(branch, Branch) else str(branch)
    playbook = _playbook_block(
        db, gestora_id=gestora_id, branch_value=branch_value, doc_type=doc_type
    )
    prompt = (
        _CRITIC_PROMPT
        .replace("{branch}", branch_value)
        .replace("{doc_type}", doc_type)
        .replace("{parsed_params}", json.dumps(parsed_params, ensure_ascii=False))
        .replace("{precedent}", precedent_text or "(none — generated from scratch)")
        .replace("{draft}", draft_text)
        .replace("{playbook}", playbook)
    )
    try:
        result = llm.complete_json(prompt, CRITIC_SCHEMA, system=_CRITIC_SYSTEM)
    except ServiceNotConfiguredError:
        logger.info("Critic skipped: LLM unreachable; draft proceeds unreviewed.")
        return Verdict(approved=True, skipped=True)
    except Exception as exc:  # noqa: BLE001 — never block the pipeline on the critic
        logger.warning("Critic review failed (%s); draft proceeds unreviewed.", exc)
        return Verdict(approved=True, skipped=True)

    issues = [
        Issue.from_dict(item)
        for item in (result.get("issues") or [])
        if isinstance(item, dict)
    ]
    approved = bool(result.get("approved", not issues))
    return Verdict(approved=approved, issues=issues)


def build_revision_instruction(issues: list[Issue]) -> str:
    """Build a refine_document instruction enumerating the issues + fixes."""
    lines = [_REVISION_HEADER]
    for idx, issue in enumerate(issues, start=1):
        parts = [f"{idx}. [{issue.severity}/{issue.category}] {issue.problem}"]
        if issue.location:
            parts.append(f"(location: {issue.location})")
        # Cite the exact problematic passage so the drafter can locate + fix it.
        if issue.citation:
            where = issue.citation.get("where")
            quote = issue.citation.get("quote")
            if where:
                parts.append(f"(in: {where})")
            if quote:
                parts.append(f'Offending text: "{quote}"')
        if issue.suggested_fix:
            parts.append(f"Suggested fix: {issue.suggested_fix}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


# A revise callable takes (current_text, instruction) and returns the full
# revised document. Defaults to generator.refine_document; injectable for tests.
ReviseFn = Callable[[str, str], str]


def _default_revise(current_text: str, instruction: str) -> str:
    return generator.refine_document(current_text=current_text, instruction=instruction)


def draft_with_review(
    *,
    first_draft: str,
    doc_type: str,
    branch: Branch,
    parsed_params: dict[str, Any],
    precedent_text: Optional[str],
    revise: Optional[ReviseFn] = None,
    gestora_id: Optional[str] = None,
    db: Optional[dbmod.Database] = None,
) -> DraftWithReviewResult:
    """Critic-driven revise loop over a first draft.

    ``revise(current_text, instruction) -> full_revised_text`` defaults to
    :func:`generator.refine_document`. Returns the best draft plus the review
    trail; ``forced_counsel`` is set when the draft is still not approved after
    the revision budget (the caller forces Exit B). ``gestora_id`` (+ ``db``)
    is threaded into every review pass so the gestora's siloed playbooks are
    enforced (no-op when absent or empty).

    Graceful degradation: if ``critic_enabled`` is false the loop is a no-op
    (no rounds, draft unchanged). If the LLM is unreachable the first review is
    ``skipped`` and the loop exits immediately with the original draft.
    """
    settings = get_settings()
    revise = revise or _default_revise

    if not settings.critic_enabled:
        return DraftWithReviewResult(
            text=first_draft, rounds=[], approved=True, forced_counsel=False
        )

    min_severity = settings.critic_min_severity_to_revise
    current_text = first_draft
    rounds: list[ReviewRound] = []

    # Round 0 reviews the first draft; rounds 1..max_rounds are revise→review.
    for round_idx in range(0, settings.critic_max_rounds + 1):
        verdict = review(
            draft_text=current_text,
            doc_type=doc_type,
            branch=branch,
            parsed_params=parsed_params,
            precedent_text=precedent_text,
            gestora_id=gestora_id,
            db=db,
        )
        if verdict.skipped:
            # LLM unreachable: degrade gracefully, ship the current draft.
            return DraftWithReviewResult(
                text=current_text, rounds=rounds, approved=True, forced_counsel=False
            )

        actionable = verdict.issues_at_or_above(min_severity)
        rounds.append(
            ReviewRound(
                round=round_idx,
                approved=verdict.approved,
                issues=[i.to_dict() for i in verdict.issues],
                model_note=None,
            )
        )

        if verdict.approved or not actionable:
            # Approved, or only sub-threshold (e.g. minor) issues remain → done.
            return DraftWithReviewResult(
                text=current_text, rounds=rounds, approved=True, forced_counsel=False
            )

        if round_idx >= settings.critic_max_rounds:
            # Budget exhausted and still not clean → force Exit B.
            logger.info(
                "Critic budget exhausted with %d actionable issue(s); forcing counsel.",
                len(actionable),
            )
            return DraftWithReviewResult(
                text=current_text, rounds=rounds, approved=False, forced_counsel=True
            )

        # Revise incorporating the critic's feedback, then re-review next loop.
        instruction = build_revision_instruction(actionable)
        try:
            revised = revise(current_text, instruction)
        except ServiceNotConfiguredError:
            logger.info("Revision skipped: LLM unreachable; shipping current draft.")
            return DraftWithReviewResult(
                text=current_text, rounds=rounds, approved=True, forced_counsel=False
            )
        # An unclear-revision marker means the drafter could not safely apply
        # the fix; keep the prior draft and force counsel rather than ship a
        # broken revision.
        if generator.refinement_unclear_reason(revised) is not None:
            logger.info("Revision came back unclear; forcing counsel.")
            return DraftWithReviewResult(
                text=current_text, rounds=rounds, approved=False, forced_counsel=True
            )
        current_text = revised

    # Unreachable (loop always returns), but keep a safe default.
    return DraftWithReviewResult(
        text=current_text, rounds=rounds, approved=False, forced_counsel=True
    )
