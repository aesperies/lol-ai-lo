"""Human-authored review playbooks for the critic — STRICTLY gestora-siloed.

The inviolable isolation rule (SPEC guardrails 1 & 3) applies here exactly as
it does to precedents and lessons: a playbook authored for gestora A is NEVER
loaded into gestora B's review. There is no global / cross-gestora playbook
pool — every read hard-filters on ``gestora_id``.

A playbook is a block of free-text review rules (optionally scoped to a branch
and/or doc_type). :func:`playbooks_for` retrieves the most relevant ACTIVE
playbook contents for a given request; services/critic.py injects them into the
review prompt so the reviewer enforces the gestora's own rules on top of its
built-in substantive checks.
"""
from __future__ import annotations

from typing import Any, Optional

from models.doc_branches import Branch
from services import db as dbmod

DEFAULT_TOP_K = 5


def _coerce_branch(branch: Any) -> Optional[str]:
    """Accept a Branch enum, its string value, or None."""
    if branch is None:
        return None
    return branch.value if isinstance(branch, Branch) else str(branch)


def _recency_key(row: dict[str, Any]) -> str:
    return str(row.get("updated_at") or row.get("created_at") or "")


def playbooks_for(
    db: dbmod.Database,
    *,
    gestora_id: str,
    branch: Any = None,
    doc_type: Optional[str] = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[str]:
    """Retrieve up to ``top_k`` ACTIVE playbook contents for the critic.

    HARD ``gestora_id`` filter (isolation: another gestora's playbooks can never
    surface). Active only. Ranking prefers, in order: a doc_type match, then a
    branch match, then gestora-wide (unscoped) playbooks — most recent first
    within each tier. Returns the playbook ``content`` strings to inject into
    the review prompt.
    """
    branch_value = _coerce_branch(branch)

    # gestora_id is the hard pre-filter (db.select equality match); is_active
    # narrows to live rules only.
    rows = db.select("review_playbooks", gestora_id=gestora_id, is_active=True)

    def in_scope(row: dict[str, Any]) -> bool:
        # A playbook scoped to a branch/doc_type only applies when that scope
        # matches the request; an unscoped (NULL) field is gestora-wide.
        row_branch = row.get("branch")
        if row_branch and branch_value and row_branch != branch_value:
            return False
        row_doc_type = row.get("doc_type")
        if row_doc_type and doc_type and row_doc_type != doc_type:
            return False
        return True

    def rank_key(row: dict[str, Any]) -> tuple[Any, ...]:
        doc_match = 1 if doc_type is not None and row.get("doc_type") == doc_type else 0
        branch_match = 1 if branch_value is not None and row.get("branch") == branch_value else 0
        return (doc_match, branch_match, _recency_key(row))

    scoped = [row for row in rows if in_scope(row)]
    scoped.sort(key=rank_key, reverse=True)
    return [row["content"] for row in scoped[:top_k]]
