"""Admin GDPR data-retention endpoints (improvement #10, docs/GDPR.md).

Per-gestora retention policy (months, 6-120, 007_data_retention.sql) plus the
manual retention sweep trigger. All admin-only: retention is a compliance
setting agreed between the SLP and each gestora, never client-editable.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from api import client_ip, get_gestora_or_404, now_iso
from auth import require_admin
from models.schema import (
    AuditAction,
    AuditResourceType,
    RetentionPolicyBody,
    RetentionPolicyOut,
    User,
)
from services import audit, db as dbmod, retention

router = APIRouter(prefix="/api/admin", tags=["admin-retention"])



@router.get("/gestoras/{gestora_id}/retention", response_model=RetentionPolicyOut)
async def get_retention_policy(
    gestora_id: str,
    user: User = Depends(require_admin),
) -> Any:
    """The gestora's retention policy; the platform default (is_default=true)
    when no explicit policy row exists."""
    db = dbmod.get_db()
    get_gestora_or_404(db, gestora_id)
    rows = db.select("data_retention_policies", gestora_id=gestora_id)
    if not rows:
        return RetentionPolicyOut(
            gestora_id=gestora_id,
            months=retention.DEFAULT_RETENTION_MONTHS,
            is_default=True,
        )
    row = rows[-1]
    return RetentionPolicyOut(
        gestora_id=gestora_id,
        months=row["months"],
        is_default=False,
        updated_by=row.get("updated_by"),
        updated_at=row.get("updated_at"),
    )


@router.put("/gestoras/{gestora_id}/retention", response_model=RetentionPolicyOut)
async def put_retention_policy(
    gestora_id: str,
    body: RetentionPolicyBody,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Upsert the gestora's retention policy (months, 6-120)."""
    db = dbmod.get_db()
    get_gestora_or_404(db, gestora_id)
    existing = db.select("data_retention_policies", gestora_id=gestora_id)
    fields = {"months": body.months, "updated_by": user.id, "updated_at": now_iso()}
    previous_months = existing[-1]["months"] if existing else None
    if existing:
        row = db.update("data_retention_policies", existing[-1]["id"], fields)
    else:
        row = db.insert("data_retention_policies", {"gestora_id": gestora_id, **fields})
    audit.log_action(
        db,
        user=user,
        action=AuditAction.retention_policy_updated,
        resource_type=AuditResourceType.gestora,
        resource_id=gestora_id,
        gestora_id=gestora_id,
        metadata={"months": body.months, "previous_months": previous_months},
        ip_address=client_ip(http_request),
    )
    return RetentionPolicyOut(
        gestora_id=gestora_id,
        months=row["months"],
        is_default=False,
        updated_by=row.get("updated_by"),
        updated_at=row.get("updated_at"),
    )


@router.post("/retention/sweep")
async def trigger_retention_sweep(
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Manual retention sweep (services/retention.py). Returns the counts.

    TODO: schedule via external cron in production — the sweep is idempotent
    so overlapping runs are safe.
    """
    db = dbmod.get_db()
    counts = retention.run_retention_sweep(db)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.retention_sweep,
        resource_type=AuditResourceType.gestora,
        resource_id=None,
        gestora_id=None,
        metadata=counts,
        ip_address=client_ip(http_request),
    )
    return counts
