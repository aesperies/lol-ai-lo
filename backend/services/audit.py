"""Append-only audit log writer.

Every workflow action listed in the ``audit_action`` DB enum is recorded here.
The storage layer refuses UPDATE/DELETE on audit_log (DB trigger + RLS in
production, PermissionError in the dev store), so this module only inserts.
"""
from __future__ import annotations

from typing import Any, Optional

from models.schema import AuditAction, AuditResourceType, User
from services import db as dbmod


def log_action(
    db: dbmod.Database,
    *,
    user: Optional[User],
    action: AuditAction,
    resource_type: AuditResourceType,
    resource_id: Optional[str],
    gestora_id: Optional[str],
    metadata: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> dict[str, Any]:
    """Insert one audit row. Never raises on metadata content; raises if the
    action is not part of the enum (programming error, not user error)."""
    row = {
        "user_id": user.id if user else None,
        "user_role": user.role.value if user else None,
        "gestora_id": gestora_id,
        "action": AuditAction(action).value,
        "resource_type": AuditResourceType(resource_type).value,
        "resource_id": resource_id,
        "metadata": metadata or {},
        "ip_address": ip_address,
    }
    return db.insert("audit_log", row)
