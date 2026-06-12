"""Shared helpers for the API routers (workflow guardrails live here)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from models.schema import (
    LEVEL3_WARNING,
    STATUS_TRANSITIONS,
    DocumentVersionType,
    RequestStatus,
)
from services import db as dbmod
from services import docx_renderer, storage

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

MISSING_MARKER = "[MISSING:"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_request_or_404(db: dbmod.Database, request_id: str) -> dict[str, Any]:
    row = db.get("requests", request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return row


def transition(db: dbmod.Database, request_row: dict[str, Any], new_status: RequestStatus) -> dict[str, Any]:
    """Apply a status transition, enforcing the workflow state machine."""
    current = RequestStatus(request_row["status"])
    if new_status not in STATUS_TRANSITIONS[current]:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid status transition: {current.value} -> {new_status.value}",
        )
    return db.update("requests", request_row["id"], {"status": new_status.value})


def require_status(request_row: dict[str, Any], *allowed: RequestStatus) -> None:
    if RequestStatus(request_row["status"]) not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Request status must be {[s.value for s in allowed]}, got '{request_row['status']}'",
        )


def latest_document(
    db: dbmod.Database,
    request_id: str,
    version_type: DocumentVersionType,
    iteration: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    """The document to serve: highest refinement iteration by default, or the
    exact ``iteration`` when given (version-history viewing)."""
    filters: dict[str, Any] = {"request_id": request_id, "version_type": version_type.value}
    if iteration is not None:
        filters["iteration"] = iteration
    docs = db.select("documents", **filters)
    if not docs:
        return None
    # select() sorts by created_at; a stable sort on iteration keeps the most
    # recent row last within the winning iteration.
    docs.sort(key=lambda d: d.get("iteration") or 0)
    return docs[-1]


def load_draft_text(db: dbmod.Database, request_id: str) -> Optional[str]:
    draft = latest_document(db, request_id, DocumentVersionType.draft)
    if draft is None:
        return None
    try:
        return docx_renderer.extract_text(storage.read(draft["file_path"]))
    except Exception:
        return None


def exit_a_blockers(db: dbmod.Database, request_row: dict[str, Any]) -> list[str]:
    """Why Exit A is not available for this request (SPEC guardrails 5 & 10).

    The check re-reads the stored draft so it cannot be bypassed by stale or
    tampered request state.
    """
    blockers: list[str] = []
    if request_row.get("requires_counsel"):
        blockers.append(LEVEL3_WARNING)
    draft_text = load_draft_text(db, request_row["id"])
    if draft_text is None:
        blockers.append("No hay borrador generado para esta solicitud.")
    elif MISSING_MARKER in draft_text:
        blockers.append(
            "El borrador contiene campos sin completar [MISSING]. "
            "Se requiere revisión por abogado antes de la entrega."
        )
    return blockers
