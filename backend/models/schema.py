"""Backwards-compatible facade over the split model modules.

Historically this file held every enum, constant and Pydantic model. It is now
organized into themed modules:

- models.enums    — Enum classes mirroring the Postgres enums.
- models.content  — business constants: STATUS_TRANSITIONS, DOC_TYPE_CATALOG
                    and the Spanish legal/UI texts.
- models.entities — Pydantic models mirroring DB rows (Gestora, Fund, User, ...).
- models.dto      — API request/response DTOs (*Create, *Body, *Out, ...).

Every public name is re-exported here so existing imports
(``from models.schema import X``) keep working unchanged. New code may import
from the specific submodule instead.

Authoritative source: supabase/migrations/001_initial_schema.sql.
"""
from models.enums import (  # noqa: F401
    AuditAction,
    AuditResourceType,
    DocumentVersionType,
    GenerationJobStatus,
    PrecedentSource,
    PrecedentVersionStatus,
    RefinementStatus,
    RequestStatus,
    SlaEventKind,
    SubscriptionTier,
    TabularCellStatus,
    TabularColType,
    TabularReviewStatus,
    TabularSourceKind,
    UsageEventType,
    UserRole,
)
from models.content import (  # noqa: F401
    DATA_DELETE_CONFIRMATION,
    DOC_TYPE_CATALOG,
    EXIT_A_CHECKBOX_TEXT,
    LEVEL3_WARNING,
    SLP_DISCLAIMER,
    STATUS_TRANSITIONS,
    UNCLASSIFIABLE_MESSAGE,
)
from models.entities import (  # noqa: F401
    CounselAssignment,
    Fund,
    Vehicle,
    GenerationJob,
    Gestora,
    KeyDate,
    KeyTerm,
    ParsedParams,
    Party,
    ReviewPlaybook,
    User,
)
from models.dto import (  # noqa: F401
    AssignedCounselOut,
    ColleagueOut,
    ConfirmParamsBody,
    CounselAssignmentCreate,
    CounselAssignmentOut,
    CounselCommentCreate,
    CounselCommentOut,
    CounselInlineEditBody,
    DataDeleteBody,
    DocumentOut,
    DraftingLessonOut,
    ExitAAcknowledgeBody,
    GenerationJobOut,
    GenerationReviewOut,
    VerificationOut,
    CounselQueueItemOut,
    DashboardStatsOut,
    NotificationOut,
    NotificationsMarkReadBody,
    FundCreate,
    FundUpdate,
    GestoraCreate,
    MfaStatusBody,
    ModelConfigBody,
    ModelConfigOut,
    PrecedentOut,
    PrecedentVersionOut,
    RedlineSegmentOut,
    RefinementCreate,
    RefinementOut,
    RequestBranchOut,
    RequestCreate,
    RequestOut,
    RetentionPolicyBody,
    RetentionPolicyOut,
    ReviewBundleOut,
    ReviewPlaybookOut,
    ReviewPlaybookUpdate,
    ShareCreate,
    ShareOut,
    TabularCellOut,
    TabularColumnCreate,
    TabularColumnOut,
    TabularDocumentCreate,
    TabularDocumentOut,
    TabularReviewCreate,
    TabularReviewDetailOut,
    TabularReviewOut,
    TabularReviewStatusOut,
    UserInviteBody,
    VehicleCreate,
    VehicleUpdate,
    UserProfileOut,
)
