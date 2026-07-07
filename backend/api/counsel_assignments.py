"""Counsel↔gestora assignments: admin CRUD and client "my counsel" lookup.

The Exit B notification routing lives in services/counsel_routing.py."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user, require_admin, require_client
from config import get_settings
from models.schema import (
    AssignedCounselOut,
    CounselAssignmentCreate,
    CounselAssignmentOut,
    User,
    UserRole,
)
from services import db as dbmod

router = APIRouter(prefix="/api", tags=["counsel-assignments"])


def _to_out(db: dbmod.Database, row: dict[str, Any]) -> CounselAssignmentOut:
    counsel = db.get("users", row["counsel_user_id"]) or {}
    return CounselAssignmentOut(**row, counsel_email=counsel.get("email"))


# ---------------------------------------------------------------------------
# Admin CRUD
# ---------------------------------------------------------------------------

@router.post("/counsel-assignments", response_model=CounselAssignmentOut, status_code=201)
async def assign_counsel(
    body: CounselAssignmentCreate,
    user: User = Depends(require_admin),
) -> Any:
    """Assign a counsel user to a gestora (upserts the pair). Assigning a new
    primary demotes the previous primary (one primary per gestora)."""
    db = dbmod.get_db()
    if db.get("gestoras", body.gestora_id) is None:
        raise HTTPException(status_code=404, detail="Gestora not found")
    counsel = db.get("users", body.counsel_user_id)
    if counsel is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Mirrors the trg_counsel_assignments_role DB trigger.
    if counsel.get("role") != UserRole.counsel.value:
        raise HTTPException(status_code=422, detail="Assigned user must have role 'counsel'")

    existing = db.select("counsel_assignments", gestora_id=body.gestora_id)
    if body.is_primary:
        # One primary per gestora: demote the current primary, if any.
        for assignment in existing:
            if assignment["is_primary"] and assignment["counsel_user_id"] != body.counsel_user_id:
                db.update("counsel_assignments", assignment["id"], {"is_primary": False})

    pair = next((a for a in existing if a["counsel_user_id"] == body.counsel_user_id), None)
    if pair is not None:
        row = db.update("counsel_assignments", pair["id"], {"is_primary": body.is_primary})
    else:
        row = db.insert(
            "counsel_assignments",
            {
                "gestora_id": body.gestora_id,
                "counsel_user_id": body.counsel_user_id,
                "is_primary": body.is_primary,
            },
        )
    return _to_out(db, row)


@router.delete("/counsel-assignments/{assignment_id}", status_code=204)
async def remove_counsel_assignment(
    assignment_id: str,
    user: User = Depends(require_admin),
) -> None:
    db = dbmod.get_db()
    if db.get("counsel_assignments", assignment_id) is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete("counsel_assignments", assignment_id)


@router.get("/counsel-assignments", response_model=list[CounselAssignmentOut])
async def list_counsel_assignments(
    gestora_id: str,
    user: User = Depends(get_current_user),
) -> Any:
    """Assignments of one gestora. Admin sees any gestora; clients only their
    own (404 pattern, guardrail 1); counsel only their own assignments."""
    db = dbmod.get_db()
    if user.role == UserRole.client and user.gestora_id != gestora_id:
        raise HTTPException(status_code=404, detail="Gestora not found")
    if db.get("gestoras", gestora_id) is None:
        raise HTTPException(status_code=404, detail="Gestora not found")
    rows = db.select("counsel_assignments", gestora_id=gestora_id)
    if user.role == UserRole.counsel:
        rows = [r for r in rows if r["counsel_user_id"] == user.id]
    return [_to_out(db, r) for r in rows]


# ---------------------------------------------------------------------------
# Client: my gestora's assigned counsel (intake form display)
# ---------------------------------------------------------------------------

@router.get("/my/counsel", response_model=Optional[AssignedCounselOut])
async def my_counsel(user: User = Depends(require_client)) -> Any:
    """The requesting client's gestora's assigned counsel (primary preferred,
    else any backup), or null when the gestora has no assignment."""
    db = dbmod.get_db()
    assignments = db.select("counsel_assignments", gestora_id=user.gestora_id)
    chosen = next((a for a in assignments if a["is_primary"]), None) or (
        assignments[0] if assignments else None
    )
    if chosen is None:
        return None
    counsel = db.get("users", chosen["counsel_user_id"])
    if counsel is None:
        return None
    return AssignedCounselOut(
        name=counsel["email"].split("@")[0],
        email=counsel["email"],
        is_primary=chosen["is_primary"],
        # Review SLA (config sla_review_hours, default 48h).
        # TODO: make it configurable per gestora/assignment (subscription tier).
        turnaround_hours=int(get_settings().sla_review_hours),
    )
