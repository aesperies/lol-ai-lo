"""Pydantic models mirroring the DB schema plus request/response DTOs.

Authoritative source: supabase/migrations/001_initial_schema.sql.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums (mirror the Postgres enums exactly)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Allowed workflow transitions (guardrail: enforced on every status change)
# ---------------------------------------------------------------------------

STATUS_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.parsing: {RequestStatus.confirmed},
    RequestStatus.confirmed: {RequestStatus.generating},
    # 'confirmed' = revert path after a generation job FINALLY fails, so the
    # client can re-trigger generation (services/jobs.py).
    RequestStatus.generating: {RequestStatus.review_pending, RequestStatus.confirmed},
    # 'generating' = iterative refinement loop (api/refinements.py): the
    # request re-enters generation and returns to 'review_pending' whether the
    # refinement is applied or fails (the previous draft stays valid).
    RequestStatus.review_pending: {
        RequestStatus.counsel_review,
        RequestStatus.delivered,
        RequestStatus.generating,
    },
    RequestStatus.counsel_review: {RequestStatus.validated},
    RequestStatus.validated: {RequestStatus.delivered},
    RequestStatus.delivered: set(),
}


# ---------------------------------------------------------------------------
# Document type catalog (grouped dropdown, SPEC.md)
# ---------------------------------------------------------------------------

DOC_TYPE_CATALOG: dict[str, list[str]] = {
    "🏛 Gobierno Corporativo": [
        "Acta de Reunión del Consejo",
        "Resolución del Consejo per rollam",
        "Acta de Junta General",
        "Resolución de Junta General sin Reunión",
        "Nombramiento / Cese de Administrador",
        "Poder General (Delegación de Facultades)",
        "Poder Especial",
    ],
    "💼 Operaciones de Fondo": [
        "Llamada de Capital (Capital Call Notice)",
        "Distribución a Inversores (Distribution Notice)",
        "Extensión del Período de Inversión",
        "Extensión del Plazo del Fondo",
        "Certificado de Participación del Inversor",
        "Waiver / Renuncia a Derecho Contractual",
    ],
    "📋 Gestión de Portfolio": [
        "Term Sheet (no vinculante)",
        "Carta de Intenciones (LOI)",
        "NDA / Acuerdo de Confidencialidad",
        "Acuerdo de Suscripción de Participaciones",
        "Resolución de Aprobación de Inversión",
        "Resolución de Seguimiento (Follow-on)",
        "Resolución de Desinversión",
    ],
    "⚖️ Cumplimiento y Regulatorio": [
        "Certificado de Titularidad Real (UBO)",
        "Declaración AML/KYC",
        "Certificado de Residencia Fiscal",
        "Comunicación a Regulador (CNMV / AMF / BaFin)",
        "Notificación AIFMD",
    ],
    "📝 Contratos con Terceros": [
        "Contrato de Prestación de Servicios",
        "Acuerdo de Asesoramiento (Advisory Agreement)",
        "Contrato de Gestor de Cartera Delegado",
        "Side Letter con Inversor",
    ],
    "🔧 Otros": [
        "Other (describir abajo)",
    ],
}

UNCLASSIFIABLE_MESSAGE = (
    "No hemos podido clasificar tu solicitud. Por favor reformúlala indicando "
    "el tipo de documento y las partes implicadas."
)

LEVEL3_WARNING = (
    "Este documento se ha generado sin precedente de referencia. La validación "
    "por abogado es obligatoria antes de su uso."
)

SLP_DISCLAIMER = (
    "Este documento ha sido generado por Lol-AI-lo Legal SLP. Su uso sin "
    "validación por abogado es responsabilidad exclusiva del cliente. "
    "Lol-AI-lo Legal SLP no asume responsabilidad por documentos descargados "
    "sin validación (Exit A)."
)

EXIT_A_CHECKBOX_TEXT = (
    "Entiendo que este documento no ha sido revisado por un abogado y asumo "
    "la responsabilidad de su uso."
)


# ---------------------------------------------------------------------------
# Entity models (DB rows)
# ---------------------------------------------------------------------------

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


class RequestOut(BaseModel):
    id: str
    fund_id: str
    user_id: str
    doc_type: str
    doc_type_custom: Optional[str] = None
    freetext: str
    language: Optional[str] = None
    parsed_params: Optional[dict[str, Any]] = None
    # Client-provided structured intake values (models/doc_fields.py registry);
    # NULL for freetext-only requests.
    structured_fields: Optional[dict[str, Any]] = None
    status: RequestStatus = RequestStatus.parsing
    requires_counsel: bool = False
    exit_a_acknowledged_at: Optional[datetime] = None
    # Counsel SLA timestamps (005_quality_and_sla.sql): stamped when the
    # request enters 'counsel_review' / 'validated' respectively.
    counsel_requested_at: Optional[datetime] = None
    counsel_validated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Collaboration (012_collaboration.sql): per-caller ownership/sharing flags
    # the list/detail endpoints set so the UI can distinguish "mine" from
    # "shared with me" and hide owner-only actions. Not stored on the request
    # row — derived for the calling user. None for counsel/admin (cross-gestora
    # by role; not part of the sharing model).
    is_owner: Optional[bool] = None
    shared_with_me: Optional[bool] = None
    shared_by_email: Optional[str] = None


class DocumentOut(BaseModel):
    id: str
    request_id: str
    version_type: DocumentVersionType
    file_path: str
    precedent_version_id: Optional[str] = None
    uploaded_by: Optional[str] = None
    # Refinement iteration this version belongs to (0 = original generation).
    iteration: int = 0
    created_at: Optional[datetime] = None


class PrecedentOut(BaseModel):
    id: str
    gestora_id: Optional[str] = None
    fund_id: Optional[str] = None
    doc_type: str
    language: str
    source: PrecedentSource = PrecedentSource.manual_upload
    created_at: Optional[datetime] = None


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


class PrecedentVersionOut(BaseModel):
    id: str
    precedent_id: str
    version_number: int
    file_path: str
    status: PrecedentVersionStatus = PrecedentVersionStatus.draft
    rag_weight: float = 0.0
    activated_at: Optional[datetime] = None
    superseded_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Request/response DTOs
# ---------------------------------------------------------------------------

class RequestCreate(BaseModel):
    fund_id: str
    doc_type: str
    doc_type_custom: Optional[str] = None
    freetext: str = Field(min_length=50, max_length=2000)
    # "validación por abogado" intake toggle (default OFF per SPEC)
    validation_requested: bool = False
    # Structured intake values keyed by the doc_type's registry field keys
    # (models/doc_fields.py). Unknown keys -> 422; required keys MAY be
    # missing at submit time (the parser flags them).
    structured_fields: Optional[dict[str, Any]] = None


class ConfirmParamsBody(BaseModel):
    """Client confirmation of parsed parameters; edited params optional."""

    parsed_params: Optional[dict[str, Any]] = None


class ExitAAcknowledgeBody(BaseModel):
    # Frontend must send the explicit checkbox value; server re-verifies it.
    acknowledged: bool = False


class CounselInlineEditBody(BaseModel):
    text: str = Field(min_length=1)
    comment: Optional[str] = None


class CounselAssignmentCreate(BaseModel):
    gestora_id: str
    counsel_user_id: str
    is_primary: bool = False


class CounselAssignmentOut(BaseModel):
    id: str
    gestora_id: str
    counsel_user_id: str
    is_primary: bool = False
    counsel_email: Optional[str] = None
    created_at: Optional[datetime] = None


class AssignedCounselOut(BaseModel):
    """The counsel a client's gestora is assigned to (intake form display)."""

    name: str
    email: str
    is_primary: bool = False
    turnaround_hours: int = 48


class GenerationJobOut(BaseModel):
    id: str
    status: GenerationJobStatus
    attempts: int = 0
    last_error: Optional[str] = None


class RefinementCreate(BaseModel):
    # Mirrors the DB CHECK: char_length(instruction) between 5 and 1000.
    instruction: str = Field(min_length=5, max_length=1000)


class RetentionPolicyBody(BaseModel):
    """PUT /api/admin/gestoras/{id}/retention — mirrors the DB CHECK
    (months between 6 and 120, 007_data_retention.sql)."""

    months: int = Field(ge=6, le=120)


class RetentionPolicyOut(BaseModel):
    gestora_id: str
    months: int
    # True when the gestora has no explicit policy row (platform default).
    is_default: bool = False
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class RefinementOut(BaseModel):
    id: str
    request_id: str
    iteration: int
    instruction: str
    status: RefinementStatus = RefinementStatus.pending
    # Failure reason surfaced to the client (unclear-instruction reason or
    # final job error). NULL unless status='failed'.
    error: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    applied_at: Optional[datetime] = None


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


class ReviewPlaybookOut(BaseModel):
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


class ReviewPlaybookUpdate(BaseModel):
    """Partial update of a playbook (admin-only). Any omitted field is left
    unchanged; ``branch``/``doc_type`` are settable to null to widen scope."""

    title: Optional[str] = Field(default=None, min_length=1)
    content: Optional[str] = Field(default=None, min_length=1)
    branch: Optional[str] = None
    doc_type: Optional[str] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Critic review trail (generation_reviews) + drafting lessons surfacing
# ---------------------------------------------------------------------------

class GenerationReviewOut(BaseModel):
    """One persisted critic round (services/critic.py ReviewRound), surfaced
    read-only to client/counsel/admin for the request they may access. The
    ``issues`` list mirrors the critic Issue shape (severity / category /
    problem / suggested_fix / location / citation), where ``citation`` is a
    verifiable {where, quote} pointer to the offending DRAFT text (grounding
    Feature 2)."""

    round: int
    approved: bool
    issues: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = None


class DraftingLessonOut(BaseModel):
    """One accumulated, gestora-siloed drafting lesson (services/lessons.py).
    Admin-only read; never exposed cross-gestora."""

    id: str
    gestora_id: str
    branch: str
    doc_type: Optional[str] = None
    lesson: str
    weight: float = 1.0
    created_at: Optional[datetime] = None


class RequestBranchOut(BaseModel):
    """The specialized drafting branch a doc_type resolves to
    (models/doc_branches.branch_for)."""

    doc_type: str
    branch: str


# ---------------------------------------------------------------------------
# Tabular Review DTOs (010_tabular_reviews.sql)
# ---------------------------------------------------------------------------

class TabularColumnCreate(BaseModel):
    """A column to extract: a question + the answer type (+ options for 'tag')."""

    name: str
    question: str
    col_type: TabularColType
    options: Optional[list[str]] = None


class TabularDocumentCreate(BaseModel):
    """A document to add as a grid row. ``source_id`` points to a
    precedent_versions.id or documents.id depending on ``source_kind``; both
    must belong to the caller's gestora silo (validated at create time)."""

    source_kind: TabularSourceKind
    source_id: str
    label: Optional[str] = None


class TabularReviewCreate(BaseModel):
    """Create a tabular review with its columns and documents (status 'draft')."""

    title: str
    fund_id: Optional[str] = None
    columns: list[TabularColumnCreate] = Field(default_factory=list)
    documents: list[TabularDocumentCreate] = Field(default_factory=list)


class TabularColumnOut(BaseModel):
    id: str
    review_id: str
    position: int
    name: str
    question: str
    col_type: str
    options: Optional[list[str]] = None
    created_at: Optional[datetime] = None


class TabularDocumentOut(BaseModel):
    id: str
    review_id: str
    position: int
    source_kind: str
    source_id: str
    label: Optional[str] = None
    created_at: Optional[datetime] = None


class TabularCellOut(BaseModel):
    """One extracted cell: a typed value + reasoning + verifiable citation
    ({"page": ..., "quote": ...}) from the document, or an error message."""

    id: str
    document_id: str
    column_id: str
    value: Optional[str] = None
    reasoning: Optional[str] = None
    citation: Optional[dict[str, Any]] = None
    status: str
    error: Optional[str] = None


class TabularReviewOut(BaseModel):
    """A tabular review header (list view)."""

    id: str
    gestora_id: str
    fund_id: Optional[str] = None
    created_by: Optional[str] = None
    title: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Collaboration (012_collaboration.sql): per-caller ownership/sharing flags,
    # mirroring RequestOut. Derived for the calling user, not stored on the row.
    is_owner: Optional[bool] = None
    shared_with_me: Optional[bool] = None
    shared_by_email: Optional[str] = None


class TabularReviewDetailOut(TabularReviewOut):
    """A tabular review with its columns, documents and cells (the full grid)."""

    columns: list[TabularColumnOut] = Field(default_factory=list)
    documents: list[TabularDocumentOut] = Field(default_factory=list)
    cells: list[TabularCellOut] = Field(default_factory=list)


class TabularReviewStatusOut(BaseModel):
    """Lightweight status payload for the polling loop while a review runs."""

    id: str
    status: str
    cell_total: int
    cell_done: int
    cell_error: int


# ---------------------------------------------------------------------------
# Account & security (011_account_security.sql)
# ---------------------------------------------------------------------------

class UserProfileOut(BaseModel):
    """The calling user's own profile (GET /api/me), incl. the MFA flag."""

    id: str
    email: str
    role: UserRole
    gestora_id: Optional[str] = None
    mfa_enabled: bool = False
    created_at: Optional[datetime] = None


class MfaStatusBody(BaseModel):
    """POST /api/me/mfa — the client mirrors its Supabase TOTP status here after
    a successful enroll-verify / unenroll. Supabase enforces the real factor."""

    enabled: bool


class DataDeleteBody(BaseModel):
    """POST /api/me/delete — self-service erasure/anonymisation.

    ``confirm`` MUST be the literal string below (a safety interlock so a stray
    request can never wipe data); ``mode`` defaults to the reversible-ish
    'anonymize'. 'erase' permanently removes the user's own rows + files.
    """

    confirm: str
    mode: Literal["anonymize", "erase"] = "anonymize"


# The exact confirmation phrase the client must type/send for a self-service
# deletion (also surfaced verbatim in the UI).
DATA_DELETE_CONFIRMATION = "ELIMINAR MIS DATOS"


class ModelConfigBody(BaseModel):
    """PUT /api/admin/gestoras/{id}/model-config — partial update.

    Provider/model/base-url fields: send a value to set, ``""`` to clear back to
    the global default. API-key fields are WRITE-ONLY: send a non-empty string
    to set (it is encrypted at rest), ``""`` to clear the stored key, or omit to
    leave it unchanged. The GET response NEVER returns decrypted keys.
    """

    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None


class ModelConfigOut(BaseModel):
    """GET/PUT /api/admin/gestoras/{id}/model-config — never exposes key plaintext.

    ``*_key_set`` booleans report whether an encrypted key is stored; the values
    themselves are write-only. ``is_default`` is true when the gestora has no
    override row (everything falls back to the global settings)."""

    gestora_id: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    anthropic_key_set: bool = False
    openai_key_set: bool = False
    is_default: bool = False
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Collaboration / sharing (012_collaboration.sql)
# ---------------------------------------------------------------------------

class ColleagueOut(BaseModel):
    """A same-gestora client colleague offered in the share picker
    (GET /api/my/colleagues). Excludes the caller; gestora-siloed."""

    id: str
    email: str
    name: str


class ShareCreate(BaseModel):
    """POST /api/{requests,tabular-reviews}/{id}/shares — share with one
    colleague. ``user_id`` MUST be a client of the SAME gestora as the
    resource (the inviolable single-gestora rule) and not the owner."""

    user_id: str


class ShareOut(BaseModel):
    """A collaborator on a shared resource (one share row).

    ``gestora_id`` is recorded once on the row (= the resource's gestora) and
    is always equal to both the sharer's and the sharee's gestora — the
    inviolable single-gestora rule. ``shared_with_email`` / ``shared_with_name``
    and ``shared_by_email`` are resolved for display."""

    id: str
    gestora_id: str
    shared_with_user_id: str
    shared_with_email: Optional[str] = None
    shared_with_name: Optional[str] = None
    shared_by: str
    shared_by_email: Optional[str] = None
    created_at: Optional[datetime] = None
