"""API request/response DTOs.

Split out of models/schema.py (which remains the backwards-compatible facade).

Note: RequestOut, DocumentOut, PrecedentOut and PrecedentVersionOut double as
table-mirror models AND API responses; they live here (DTO side) by convention.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from models.enums import (
    DocumentVersionType,
    GenerationJobStatus,
    PrecedentSource,
    PrecedentVersionStatus,
    RefinementStatus,
    RequestStatus,
    SubscriptionTier,
    TabularColType,
    TabularSourceKind,
    UserRole,
)


# ---------------------------------------------------------------------------
# Row-mirroring response models (also serve as the API "Out" shapes)
# ---------------------------------------------------------------------------

class RequestOut(BaseModel):  # doubles as requests-row mirror and API DTO
    id: str
    fund_id: str
    # Display enrichment (list/detail endpoints): the fund's name, so the UI
    # never has to show a bare fund UUID. Not stored on the row.
    fund_name: Optional[str] = None
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


class DocumentOut(BaseModel):  # doubles as documents-row mirror and API DTO
    id: str
    request_id: str
    version_type: DocumentVersionType
    file_path: str
    precedent_version_id: Optional[str] = None
    uploaded_by: Optional[str] = None
    # Refinement iteration this version belongs to (0 = original generation).
    iteration: int = 0
    created_at: Optional[datetime] = None


class PrecedentOut(BaseModel):  # doubles as precedents-row mirror and API DTO
    id: str
    gestora_id: Optional[str] = None
    fund_id: Optional[str] = None
    doc_type: str
    language: str
    source: PrecedentSource = PrecedentSource.manual_upload
    created_at: Optional[datetime] = None
    # Embedded versions (GET /api/precedents): the admin library UI and the
    # tabular-review document picker need the versions with the precedent.
    versions: list[PrecedentVersionOut] = Field(default_factory=list)


class PrecedentVersionOut(BaseModel):  # doubles as row mirror and API DTO
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
    mistral_api_key: Optional[str] = None
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
    mistral_key_set: bool = False
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


# ---------------------------------------------------------------------------
# Directory + counsel review thread (013_directory_and_comments.sql)
# ---------------------------------------------------------------------------

class GestoraCreate(BaseModel):
    """POST /api/gestoras (admin) — onboard a new gestora."""

    name: str = Field(min_length=1, max_length=200)
    subscription_tier: SubscriptionTier = SubscriptionTier.starter
    billing_email: Optional[str] = None


class FundCreate(BaseModel):
    """POST /api/funds — a client registers a fund/vehicle in their own
    gestora (admin must name the target gestora)."""

    name: str = Field(min_length=1, max_length=200)
    jurisdiction: str = Field(default="España", min_length=1, max_length=100)
    # Ignored for clients (always their own gestora); required for admin.
    gestora_id: Optional[str] = None


class UserInviteBody(BaseModel):
    """POST /api/users (admin) — provision a platform user.

    Mirrors the users-table constraint: a client MUST belong to a gestora;
    admin/counsel are cross-gestora (gestora_id NULL). In Supabase mode the
    user is also invited through Supabase Auth so the row id matches the
    auth id (signup alone does not provision ``public.users``)."""

    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: UserRole = UserRole.client
    gestora_id: Optional[str] = None


class CounselCommentCreate(BaseModel):
    """POST /api/requests/{id}/comments — mirrors the DB CHECK (1..4000)."""

    text: str = Field(min_length=1, max_length=4000)


class CounselCommentOut(BaseModel):
    id: str
    request_id: str
    # Display name denormalized at write time (survives author erasure).
    author: str
    text: str
    created_at: Optional[datetime] = None


class RedlineSegmentOut(BaseModel):
    """One diff segment of the draft→redline comparison (eq/ins/del)."""

    type: Literal["eq", "ins", "del"]
    text: str


class ReviewBundleOut(BaseModel):
    """GET /api/requests/{id}/review — everything the counsel review screen
    needs in one payload (request + extracted draft text + comment thread).
    The rendered redline HTML is served separately by
    GET /api/requests/{id}/documents/redline/html."""

    request: RequestOut
    draft_text: str = ""
    redline: list[RedlineSegmentOut] = Field(default_factory=list)
    comments: list[CounselCommentOut] = Field(default_factory=list)
