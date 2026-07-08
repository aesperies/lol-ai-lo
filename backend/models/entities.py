"""Pydantic models mirroring DB rows (table-mirror entities).

Split out of models/schema.py (which remains the backwards-compatible facade).
Authoritative source: supabase/migrations/001_initial_schema.sql.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models.enums import (
    GenerationJobStatus,
    SubscriptionTier,
    UserRole,
)


class Gestora(BaseModel):
    id: str
    name: str
    drive_folder_id: Optional[str] = None
    subscription_tier: SubscriptionTier = SubscriptionTier.starter
    billing_email: Optional[str] = None
    created_at: Optional[datetime] = None


class Fund(BaseModel):
    id: str
    gestora_id: str
    name: str
    jurisdiction: str
    created_at: Optional[datetime] = None


class Vehicle(BaseModel):
    """SPV / vehículo de inversión colgando de un fondo (015_vehicles.sql)."""

    id: str
    fund_id: str
    name: str
    vehicle_type: str = "spv"
    jurisdiction: Optional[str] = None
    created_at: Optional[datetime] = None


class User(BaseModel):
    id: str
    email: str
    role: UserRole = UserRole.client
    gestora_id: Optional[str] = None  # NULL for admin/counsel
    # Status mirror only (011_account_security.sql): Supabase Auth enforces the
    # actual TOTP factor; this reflects it for display + an admin overview.
    mfa_enabled: bool = False
    created_at: Optional[datetime] = None


class Party(BaseModel):
    role: str
    name: str


class KeyDate(BaseModel):
    label: str
    date: str


class KeyTerm(BaseModel):
    field: str
    value: str


class ParsedParams(BaseModel):
    """Output of the Claude intake parser (SPEC.md verbatim JSON contract)."""

    language: str = "es"
    doc_type_confirmed: str = ""
    parties: list[Party] = Field(default_factory=list)
    key_dates: list[KeyDate] = Field(default_factory=list)
    jurisdiction: str = ""
    governing_law: str = ""
    key_terms: list[KeyTerm] = Field(default_factory=list)
    summary: str = ""
    confidence: float = 0.0
    unclear_fields: list[str] = Field(default_factory=list)
    generation_ready: bool = False
    message: Optional[str] = None  # set when the request is unclassifiable


class CounselAssignment(BaseModel):
    id: str
    gestora_id: str
    counsel_user_id: str
    is_primary: bool = False
    created_at: Optional[datetime] = None


class GenerationJob(BaseModel):
    id: str
    request_id: str
    status: GenerationJobStatus = GenerationJobStatus.queued
    attempts: int = 0
    max_attempts: int = 3
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Review playbooks (009_models_and_playbooks.sql) — human-authored review rules
# ---------------------------------------------------------------------------

class ReviewPlaybook(BaseModel):
    """A human-authored set of review rules the critic enforces, STRICTLY
    gestora-siloed (gestora_id NOT NULL is the hard pre-filter on every read,
    services/playbooks.py). Optionally scoped to a branch and/or doc_type."""

    id: str
    gestora_id: str
    branch: Optional[str] = None
    doc_type: Optional[str] = None
    title: str
    content: str
    file_path: Optional[str] = None
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
