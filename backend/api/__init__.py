"""Shared helpers for the API routers.

The workflow domain helpers (state machine, latest_document, Exit A gates)
live in services/workflow.py — they are re-exported here so routers keep one
import site; only the HTTP-specific helpers are defined in this module.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, Request

from config import get_settings
from services import db as dbmod
from services.workflow import (  # noqa: F401 — re-exported for the routers
    MISSING_MARKER,
    exit_a_blockers,
    latest_document,
    load_draft_text,
    now_iso,
    require_status,
    transition,
)

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def client_ip(http_request: Request) -> Optional[str]:
    """The caller's IP for audit logging (None when unavailable)."""
    return http_request.client.host if http_request.client else None

# Magic bytes per accepted upload extension (improvement #9 upload hardening):
# .docx is a ZIP container (PK header), .pdf starts with %PDF.
_UPLOAD_MAGIC = {".docx": b"PK\x03\x04", ".pdf": b"%PDF"}


def validate_upload(filename: str, data: bytes, allowed_extensions: tuple[str, ...]) -> str:
    """Upload hardening (improvement #9): extension allowlist + max size
    (config max_upload_mb) + magic-bytes check. 422 on any violation; returns
    the matched extension."""
    lowered = (filename or "").lower()
    extension = next((ext for ext in allowed_extensions if lowered.endswith(ext)), None)
    if extension is None:
        raise HTTPException(
            status_code=422,
            detail=f"Upload must be one of: {', '.join(allowed_extensions)}",
        )
    max_mb = get_settings().max_upload_mb
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=422, detail=f"Upload exceeds the {max_mb} MB limit")
    if not data.startswith(_UPLOAD_MAGIC[extension]):
        raise HTTPException(
            status_code=422,
            detail=f"File content does not match a valid {extension} file",
        )
    return extension


def get_request_or_404(db: dbmod.Database, request_id: str) -> dict[str, Any]:
    row = db.get("requests", request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return row


def get_gestora_or_404(db: dbmod.Database, gestora_id: str) -> dict[str, Any]:
    row = db.get("gestoras", gestora_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Gestora not found")
    return row
