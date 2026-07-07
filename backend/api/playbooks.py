"""Review playbook management (admin) + gestora-siloed listing.

Playbooks are human-authored review rules the critic enforces (services/
critic.py via services/playbooks.py). They are STRICTLY gestora-siloed: every
read hard-filters on gestora_id and cross-gestora access 404s (no-leak pattern),
exactly like precedents and lessons.

CRUD is admin-only. The text ``content`` is what the critic injects; an optional
file attachment (validated with the shared upload hardening) is stored under the
gestora's playbooks/ folder for the admin's own reference.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile

from api import client_ip, now_iso, validate_upload
from auth import get_current_user, require_admin
from models.schema import (
    AuditAction,
    AuditResourceType,
    ReviewPlaybookOut,
    ReviewPlaybookUpdate,
    User,
    UserRole,
)
from services import audit, db as dbmod, storage

router = APIRouter(prefix="/api/playbooks", tags=["playbooks"])

# Optional attachment kinds (same hardening as precedent/counsel uploads).
_PLAYBOOK_EXTENSIONS = (".docx", ".pdf")



def _get_playbook_for_user(db: dbmod.Database, playbook_id: str, user: User) -> dict[str, Any]:
    """Fetch a playbook the user may access, else 404 (gestora-siloed no-leak).

    Clients only ever see their own gestora's playbooks; admin/counsel are
    cross-gestora by design (SPEC actor matrix). A 404 (not 403) avoids leaking
    the existence of other gestoras' playbooks.
    """
    playbook = db.get("review_playbooks", playbook_id)
    if playbook is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    if user.role not in (UserRole.admin, UserRole.counsel):
        if playbook.get("gestora_id") != user.gestora_id:
            raise HTTPException(status_code=404, detail="Playbook not found")
    return playbook


@router.post("", status_code=201, response_model=ReviewPlaybookOut)
async def create_playbook(
    http_request: Request,
    gestora_id: str = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    branch: Optional[str] = Form(None),
    doc_type: Optional[str] = Form(None),
    file: Optional[UploadFile] = None,
    user: User = Depends(require_admin),
) -> Any:
    """Admin creates a review playbook (gestora-scoped; gestora_id required).

    ``content`` is the rule text injected into the critic. An optional file is
    validated (extension + size + magic bytes) and stored under playbooks/.
    """
    db = dbmod.get_db()
    if db.get("gestoras", gestora_id) is None:
        raise HTTPException(status_code=404, detail="Gestora not found")
    if not title.strip() or not content.strip():
        raise HTTPException(status_code=422, detail="title and content are required")

    playbook = db.insert(
        "review_playbooks",
        {
            "gestora_id": gestora_id,  # isolation anchor — hard filter on read
            "branch": branch,
            "doc_type": doc_type,
            "title": title,
            "content": content,
            "file_path": None,
            "is_active": True,
            "created_by": user.id,
            "updated_at": now_iso(),
        },
    )

    if file is not None and file.filename:
        data = await file.read()
        extension = validate_upload(file.filename, data, _PLAYBOOK_EXTENSIONS)
        key = storage.save(
            storage.playbooks_path(gestora_id, f"{playbook['id']}{extension}"), data
        )
        playbook = db.update("review_playbooks", playbook["id"], {"file_path": key})

    audit.log_action(
        db,
        user=user,
        action=AuditAction.playbook_created,
        resource_type=AuditResourceType.playbook,
        resource_id=playbook["id"],
        gestora_id=gestora_id,
        metadata={"title": title, "branch": branch, "doc_type": doc_type,
                  "has_file": playbook.get("file_path") is not None},
        ip_address=client_ip(http_request),
    )
    return playbook


@router.get("", response_model=list[ReviewPlaybookOut])
async def list_playbooks(
    gestora_id: Optional[str] = None,
    user: User = Depends(get_current_user),
) -> Any:
    """List playbooks. Clients only ever see their own gestora's playbooks; the
    gestora_id query param is honoured for admin/counsel only."""
    db = dbmod.get_db()
    if user.role in (UserRole.admin, UserRole.counsel):
        if gestora_id:
            return db.select("review_playbooks", gestora_id=gestora_id)
        return db.unscoped_select("review_playbooks")
    # Hard gestora_id filter — a client never sees another gestora's playbooks.
    return db.select("review_playbooks", gestora_id=user.gestora_id)


@router.get("/{playbook_id}", response_model=ReviewPlaybookOut)
async def get_playbook(playbook_id: str, user: User = Depends(get_current_user)) -> Any:
    db = dbmod.get_db()
    return _get_playbook_for_user(db, playbook_id, user)


@router.patch("/{playbook_id}", response_model=ReviewPlaybookOut)
async def update_playbook(
    playbook_id: str,
    body: ReviewPlaybookUpdate,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Admin updates a playbook (partial). activate/deactivate via is_active."""
    db = dbmod.get_db()
    playbook = db.get("review_playbooks", playbook_id)
    if playbook is None:
        raise HTTPException(status_code=404, detail="Playbook not found")

    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=422, detail="No fields to update")
    fields["updated_at"] = now_iso()
    playbook = db.update("review_playbooks", playbook_id, fields)

    audit.log_action(
        db,
        user=user,
        action=AuditAction.playbook_updated,
        resource_type=AuditResourceType.playbook,
        resource_id=playbook_id,
        gestora_id=playbook.get("gestora_id"),
        metadata={"updated": sorted(k for k in fields if k != "updated_at")},
        ip_address=client_ip(http_request),
    )
    return playbook


@router.post("/{playbook_id}/activate", response_model=ReviewPlaybookOut)
async def activate_playbook(
    playbook_id: str,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    return await _set_active(playbook_id, True, http_request, user)


@router.post("/{playbook_id}/deactivate", response_model=ReviewPlaybookOut)
async def deactivate_playbook(
    playbook_id: str,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    return await _set_active(playbook_id, False, http_request, user)


async def _set_active(
    playbook_id: str, is_active: bool, http_request: Request, user: User
) -> Any:
    db = dbmod.get_db()
    playbook = db.get("review_playbooks", playbook_id)
    if playbook is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    playbook = db.update(
        "review_playbooks", playbook_id, {"is_active": is_active, "updated_at": now_iso()}
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.playbook_updated,
        resource_type=AuditResourceType.playbook,
        resource_id=playbook_id,
        gestora_id=playbook.get("gestora_id"),
        metadata={"is_active": is_active},
        ip_address=client_ip(http_request),
    )
    return playbook


@router.delete("/{playbook_id}", status_code=204)
async def delete_playbook(
    playbook_id: str,
    http_request: Request,
    user: User = Depends(require_admin),
) -> None:
    db = dbmod.get_db()
    playbook = db.get("review_playbooks", playbook_id)
    if playbook is None:
        raise HTTPException(status_code=404, detail="Playbook not found")
    if playbook.get("file_path"):
        storage.delete(playbook["file_path"])
    db.delete("review_playbooks", playbook_id)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.playbook_deleted,
        resource_type=AuditResourceType.playbook,
        resource_id=playbook_id,
        gestora_id=playbook.get("gestora_id"),
        metadata={"title": playbook.get("title")},
        ip_address=client_ip(http_request),
    )
