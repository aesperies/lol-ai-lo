"""Enums mirroring the Postgres enums exactly.

Split out of models/schema.py (which remains the backwards-compatible facade).
Authoritative source: supabase/migrations/001_initial_schema.sql.
"""
from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    client = "client"
    counsel = "counsel"
    admin = "admin"


class SubscriptionTier(str, Enum):
    starter = "starter"
    growth = "growth"
    custom = "custom"


class RequestStatus(str, Enum):
    parsing = "parsing"
    confirmed = "confirmed"
    generating = "generating"
    review_pending = "review_pending"
    counsel_review = "counsel_review"
    validated = "validated"
    delivered = "delivered"


class DocumentVersionType(str, Enum):
    draft = "draft"
    redline = "redline"
    counsel_edit = "counsel_edit"
    final = "final"


class PrecedentSource(str, Enum):
    manual_upload = "manual_upload"
    validated_output = "validated_output"
    slp_curated = "slp_curated"
    platform_base = "platform_base"
    # Gestora master template (009_models_and_playbooks.sql): gestora-scoped,
    # versioned/activated exactly like a precedent, but stored under modelos/
    # and outranks regular precedents as the generation base (RAG Level 0a).
    gestora_model = "gestora_model"


class PrecedentVersionStatus(str, Enum):
    draft = "draft"
    active = "active"
    superseded = "superseded"


class AuditAction(str, Enum):
    document_requested = "document_requested"
    params_confirmed = "params_confirmed"
    params_edited = "params_edited"
    document_generated = "document_generated"
    redline_generated = "redline_generated"
    draft_downloaded = "draft_downloaded"
    redline_downloaded = "redline_downloaded"
    exit_a_acknowledged = "exit_a_acknowledged"
    exit_a_downloaded = "exit_a_downloaded"
    counsel_requested = "counsel_requested"
    counsel_notified = "counsel_notified"
    counsel_review_started = "counsel_review_started"
    counsel_edit_inline = "counsel_edit_inline"
    counsel_edit_uploaded = "counsel_edit_uploaded"
    document_validated = "document_validated"
    final_downloaded = "final_downloaded"
    precedent_uploaded = "precedent_uploaded"
    precedent_activated = "precedent_activated"
    precedent_superseded = "precedent_superseded"
    precedent_version_created = "precedent_version_created"
    # GDPR data retention (improvement #10, 007_data_retention.sql).
    retention_policy_updated = "retention_policy_updated"
    retention_sweep = "retention_sweep"
    # Review playbooks (009_models_and_playbooks.sql): human-authored review
    # rules injected into the critic. Admin-only CRUD, gestora-siloed.
    playbook_created = "playbook_created"
    playbook_updated = "playbook_updated"
    playbook_deleted = "playbook_deleted"
    # Tabular Review (010_tabular_reviews.sql): multi-document extraction grid,
    # gestora-siloed. Created/run/exported + column/document mutations.
    tabular_review_created = "tabular_review_created"
    tabular_review_run = "tabular_review_run"
    tabular_review_column_added = "tabular_review_column_added"
    tabular_review_column_deleted = "tabular_review_column_deleted"
    tabular_review_document_deleted = "tabular_review_document_deleted"
    tabular_review_exported = "tabular_review_exported"
    # Account & security (011_account_security.sql).
    # MFA status mirror (Supabase enforces the actual TOTP factor).
    mfa_status_changed = "mfa_status_changed"
    # GDPR data-subject rights (RGPD arts. 15/17).
    data_exported = "data_exported"
    data_subject_deleted = "data_subject_deleted"
    # Per-gestora BYO model configuration.
    model_config_updated = "model_config_updated"
    # Collaboration / sharing (012_collaboration.sql): an owner grants a
    # same-gestora colleague READ access to a request or a tabular review.
    resource_shared = "resource_shared"
    resource_unshared = "resource_unshared"
    # Directory + counsel review thread (013_directory_and_comments.sql).
    gestora_created = "gestora_created"
    user_invited = "user_invited"
    counsel_comment_added = "counsel_comment_added"
    # Alta de fondos/vehículos (014_fund_creation.sql, 015_vehicles.sql).
    fund_created = "fund_created"
    fund_updated = "fund_updated"
    fund_deleted = "fund_deleted"
    vehicle_created = "vehicle_created"
    vehicle_updated = "vehicle_updated"
    vehicle_deleted = "vehicle_deleted"
    # Chat Q&A sobre el RAG de la gestora (021_chat.sql).
    chat_message_sent = "chat_message_sent"


class AuditResourceType(str, Enum):
    request = "request"
    document = "document"
    precedent = "precedent"
    precedent_version = "precedent_version"
    # GDPR data retention (improvement #10, 007_data_retention.sql).
    gestora = "gestora"
    # Review playbooks (009_models_and_playbooks.sql).
    playbook = "playbook"
    # Tabular Review (010_tabular_reviews.sql).
    tabular_review = "tabular_review"
    # Account & security (011_account_security.sql).
    user = "user"
    model_config = "model_config"
    # Alta de fondos/vehículos (014_fund_creation.sql, 015_vehicles.sql).
    fund = "fund"
    vehicle = "vehicle"
    # Chat Q&A sobre el RAG de la gestora (021_chat.sql).
    conversation = "conversation"


class UsageEventType(str, Enum):
    document_generated = "document_generated"
    exit_a = "exit_a"
    exit_b_requested = "exit_b_requested"
    exit_b_validated = "exit_b_validated"


class GenerationJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class RefinementStatus(str, Enum):
    pending = "pending"
    applied = "applied"
    failed = "failed"


class SlaEventKind(str, Enum):
    """Mirrors the sla_events.kind CHECK constraint (005_quality_and_sla.sql)."""

    reminder = "reminder"
    escalation = "escalation"


# ---------------------------------------------------------------------------
# Tabular Review (010_tabular_reviews.sql) — multi-document extraction grid.
# ---------------------------------------------------------------------------

class TabularReviewStatus(str, Enum):
    """Mirrors tabular_reviews.status."""

    draft = "draft"
    running = "running"
    complete = "complete"
    failed = "failed"


class TabularColType(str, Enum):
    """Answer type of a tabular column (mirrors tabular_review_columns.col_type)."""

    text = "text"
    number = "number"
    percent = "percent"
    monetary = "monetary"
    date = "date"
    yes_no = "yes_no"
    tag = "tag"


class TabularSourceKind(str, Enum):
    """What a review document references (mirrors tabular_review_documents.source_kind).

    Both kinds already live in the gestora silo: a precedent VERSION
    (precedent_versions.id) or a generated request DOCUMENT (documents.id).
    """

    precedent_version = "precedent_version"
    request_document = "request_document"


class TabularCellStatus(str, Enum):
    """Mirrors tabular_review_cells.status."""

    pending = "pending"
    done = "done"
    error = "error"
