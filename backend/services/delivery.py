"""Delivery building blocks shared by Exit A and Exit B (api/requests.py).

Both exits perform the same closing moves with small policy differences:
promote a source document to the 'final' version record, record a quality
metric and enqueue lesson extraction (both best-effort — a failure must NEVER
block a delivery), and register the delivered document in the precedent
library:

- Exit A  -> precedent CANDIDATE: status 'draft', rag_weight 0.0, pending
             admin activation (SPEC guardrail 8).
- Exit B  -> ACTIVE precedent: status 'active', rag_weight 1.0, activated
             immediately (guardrail 8 exception: counsel already validated it),
             followed by a gestora re-index.

Keeping the two policies side by side here (instead of duplicated across two
130-line endpoints) is what guarantees they never drift apart.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from models.schema import (
    AuditAction,
    AuditResourceType,
    DocumentVersionType,
    PrecedentSource,
    PrecedentVersionStatus,
    User,
)
from services import audit, db as dbmod, lessons, rag
from services.workflow import now_iso as _now_iso

logger = logging.getLogger("lolailo.delivery")


def create_final_document(
    db: dbmod.Database,
    *,
    request_id: str,
    source_doc: dict[str, Any],
    uploaded_by: Optional[str],
) -> dict[str, Any]:
    """Promote ``source_doc`` (draft or counsel edit) to the 'final' version row."""
    return db.insert(
        "documents",
        {
            "request_id": request_id,
            "version_type": DocumentVersionType.final.value,
            "file_path": source_doc["file_path"],
            "precedent_version_id": source_doc.get("precedent_version_id"),
            "uploaded_by": uploaded_by,
            "iteration": source_doc.get("iteration", 0),
        },
    )


def best_effort(label: str, request_id: str, fn: Callable[[], Any]) -> None:
    """Run a non-essential side effect (quality metric, lesson extraction).

    Failures are logged and swallowed: metrics and learning must NEVER block a
    delivery or validation (SPEC graceful degradation).
    """
    try:
        fn()
    except Exception:  # noqa: BLE001 — best-effort by design
        logger.exception("%s failed for request %s (delivery continues)", label, request_id)


def enqueue_lessons(
    db: dbmod.Database,
    *,
    gestora_id: str,
    doc_type: str,
    request_id: str,
    ai_draft_path: Optional[str],
    final_path: str,
) -> None:
    """Best-effort lesson extraction (Feature 3, gestora-siloed)."""
    best_effort(
        "Lessons enqueue",
        request_id,
        lambda: lessons.enqueue_extraction(
            db,
            gestora_id=gestora_id,
            doc_type=doc_type,
            request_id=request_id,
            ai_draft_path=ai_draft_path,
            final_path=final_path,
        ),
    )


def register_precedent(
    db: dbmod.Database,
    *,
    user: User,
    gestora_id: str,
    request_row: dict[str, Any],
    file_path: str,
    origin: str,
    activate: bool,
    ip_address: Optional[str],
) -> dict[str, Any]:
    """Register a delivered document in the gestora's precedent library.

    ``activate=False`` (Exit A): candidate pending admin approval (guardrail 8).
    ``activate=True`` (Exit B): active immediately — counsel validated it —
    and the gestora's RAG index is refreshed.

    Returns the created precedent_versions row.
    """
    request_id = request_row["id"]
    precedent = db.insert(
        "precedents",
        {
            "gestora_id": gestora_id,
            "fund_id": request_row["fund_id"],
            "doc_type": request_row["doc_type"],
            "language": request_row.get("language") or "es",
            "source": PrecedentSource.validated_output.value,
        },
    )
    version_fields: dict[str, Any] = {
        "precedent_id": precedent["id"],
        "version_number": 1,
        "file_path": file_path,
        "status": (
            PrecedentVersionStatus.active.value
            if activate
            else PrecedentVersionStatus.draft.value
        ),
        "rag_weight": 1.0 if activate else 0.0,
        "created_by": user.id,
    }
    if activate:
        version_fields["activated_at"] = _now_iso()
    version = db.insert("precedent_versions", version_fields)

    if activate:
        audit_entries = (
            (
                AuditAction.precedent_version_created,
                {"origin": origin, "request_id": request_id},
            ),
            (
                AuditAction.precedent_activated,
                {"automatic": True, "reason": "counsel_validated"},
            ),
        )
    else:
        audit_entries = (
            (
                AuditAction.precedent_version_created,
                {"origin": origin, "request_id": request_id, "pending_admin_activation": True},
            ),
        )
    for action, metadata in audit_entries:
        audit.log_action(
            db,
            user=user,
            action=action,
            resource_type=AuditResourceType.precedent_version,
            resource_id=version["id"],
            gestora_id=gestora_id,
            metadata=metadata,
            ip_address=ip_address,
        )
    if activate:
        rag.reindex_gestora(gestora_id, precedent["id"])
    return version
