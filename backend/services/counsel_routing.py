"""Exit B counsel notification routing (primary -> backup -> broadcast).

Business logic shared by the Exit B endpoint (api/requests.py), the manual
re-notify endpoint (api/notifications.py), the admin SLA report
(api/admin_metrics.py) and the SLA sweep (services/sla.py). It lives in the
service layer so no router ever imports from another router.
"""
from __future__ import annotations

from typing import Any, Optional

from models.schema import UserRole
from services import db as dbmod


def resolve_counsel_recipients(
    db: dbmod.Database, gestora_id: Optional[str]
) -> tuple[str, list[dict[str, Any]]]:
    """Who receives the Exit B notification for this gestora, and how.

    Routing modes (recorded in the counsel_notified audit metadata):
    - "primary"   — the gestora's PRIMARY assigned counsel
    - "backup"    — no primary: any backup assignment(s)
    - "broadcast" — no assignment at all: every counsel user (legacy behavior)
    """
    if gestora_id:
        assignments = db.select("counsel_assignments", gestora_id=gestora_id)
        primaries = [a for a in assignments if a.get("is_primary")]
        for mode, pool in (("primary", primaries), ("backup", assignments)):
            recipients = [
                u
                for u in (db.get("users", a["counsel_user_id"]) for a in pool)
                if u is not None and u.get("role") == UserRole.counsel.value
            ]
            if recipients:
                return mode, recipients
    return "broadcast", db.unscoped_select("users", role=UserRole.counsel.value)


def resolve_backup_counsel_recipients(
    db: dbmod.Database, gestora_id: Optional[str]
) -> tuple[str, list[dict[str, Any]]]:
    """Who receives an SLA ESCALATION for this gestora (services/sla.py).

    Escalations skip the primary (who already got the reminder) and go to the
    BACKUP assignment(s); with no backup, broadcast to every counsel user.
    """
    if gestora_id:
        backups = [
            a
            for a in db.select("counsel_assignments", gestora_id=gestora_id)
            if not a.get("is_primary")
        ]
        recipients = [
            u
            for u in (db.get("users", a["counsel_user_id"]) for a in backups)
            if u is not None and u.get("role") == UserRole.counsel.value
        ]
        if recipients:
            return "backup", recipients
    return "broadcast", db.unscoped_select("users", role=UserRole.counsel.value)


def counsel_gestora_scope(db: dbmod.Database, counsel_user_id: str) -> tuple[set[str], set[str]]:
    """El alcance de visibilidad de un abogado (política por asignación).

    Devuelve (asignadas, pool):
    - asignadas: gestoras donde este abogado tiene asignación (primaria o backup).
    - pool: gestoras SIN NINGÚN abogado asignado — visibles para todos los
      abogados para que las nuevas gestoras no queden huérfanas hasta que un
      admin asigne counsel.
    Un abogado puede acceder a solicitudes de (asignadas | pool); admin ve todo.
    """
    assignments = db.unscoped_select("counsel_assignments")
    assigned_by_gestora: dict[str, list[dict[str, Any]]] = {}
    for a in assignments:
        assigned_by_gestora.setdefault(a["gestora_id"], []).append(a)
    mine = {g for g, rows in assigned_by_gestora.items()
            if any(r["counsel_user_id"] == counsel_user_id for r in rows)}
    all_gestoras = {g["id"] for g in db.unscoped_select("gestoras")}
    pool = all_gestoras - set(assigned_by_gestora)
    return mine, pool


def counsel_can_access_gestora(db: dbmod.Database, counsel_user_id: str, gestora_id: Optional[str]) -> bool:
    """True si la política de asignación permite a este abogado esa gestora."""
    if gestora_id is None:
        return True  # recursos sin gestora (no debería darse en requests)
    mine, pool = counsel_gestora_scope(db, counsel_user_id)
    return gestora_id in mine or gestora_id in pool
