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
