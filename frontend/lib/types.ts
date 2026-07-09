/**
 * Shared types mirroring the backend schema (see docs/SPEC.md and
 * supabase/migrations/001_initial_schema.sql).
 */

export type Role = "client" | "counsel" | "admin";

export type RequestStatus =
  | "parsing"
  | "confirmed"
  | "generating"
  | "review_pending"
  | "counsel_review"
  | "validated"
  | "delivered";

export const REQUEST_STATUSES: RequestStatus[] = [
  "parsing",
  "confirmed",
  "generating",
  "review_pending",
  "counsel_review",
  "validated",
  "delivered",
];

export type SubscriptionTier = "starter" | "growth" | "custom";

export type DocumentVersionType = "draft" | "redline" | "counsel_edit" | "final";

export type PrecedentSource =
  | "manual_upload"
  | "validated_output"
  | "slp_curated"
  | "platform_base"
  // Gestora master template (modelos/): gestora-scoped, versioned/activated
  // exactly like a precedent, outranks regular precedents as generation base.
  | "gestora_model";

export type PrecedentVersionStatus = "draft" | "active" | "superseded";

/** Precedent fallback chain level (SPEC.md). Level 3 forces Exit B. */
export type FallbackLevel = 0 | 1 | 2 | 3;

export type AppLanguage = "es" | "en" | "fr" | "de" | "other";

/** Specialized drafting branch a doc_type resolves to (backend
 * models/doc_branches.Branch). Each maps to a focused drafter persona. */
export type Branch =
  | "gobierno_corporativo"
  | "operaciones_de_fondo"
  | "gestion_de_portfolio"
  | "cumplimiento_regulatorio"
  | "contratos_terceros"
  | "generic";

export const BRANCHES: Branch[] = [
  "gobierno_corporativo",
  "operaciones_de_fondo",
  "gestion_de_portfolio",
  "cumplimiento_regulatorio",
  "contratos_terceros",
  "generic",
];

export interface Gestora {
  id: string;
  name: string;
  driveFolderId?: string | null;
  subscriptionTier: SubscriptionTier;
  billingEmail: string;
  createdAt: string;
}

/** Per-gestora GDPR data-retention policy
 * (GET/PUT /api/admin/gestoras/{id}/retention, improvement #10). */
export interface RetentionPolicy {
  gestoraId: string;
  /** Months delivered-request documents are kept (6-120). */
  months: number;
  /** True when the gestora has no explicit policy (platform default). */
  isDefault: boolean;
  updatedAt?: string | null;
}

/** Mirror of the backend bounds/default (config + 007_data_retention.sql). */
export const RETENTION_MONTHS_MIN = 6;
export const RETENTION_MONTHS_MAX = 120;
export const RETENTION_MONTHS_DEFAULT = 60;

/* ---------- Account & security (011_account_security.sql) ------------- */

/** The calling user's own profile, incl. the MFA status mirror (GET /api/me). */
export interface AccountProfile {
  id: string;
  email: string;
  role: Role;
  gestoraId: string | null;
  mfaEnabled: boolean;
}

/** A Supabase MFA factor (subset of @supabase/supabase-js Factor). */
export interface MfaFactor {
  id: string;
  friendlyName: string | null;
  status: string;
}

/** GDPR deletion mode (services/data_subject.py). */
export type DeleteMode = "anonymize" | "erase";

/** Exact confirmation phrase required to delete one's own data (backend
 * DATA_DELETE_CONFIRMATION). */
export const DATA_DELETE_CONFIRMATION = "ELIMINAR MIS DATOS";

/** LLM provider options for the per-gestora model config. */
export type LlmProvider = "ollama" | "anthropic";
export type EmbeddingProvider = "ollama" | "openai";

/** Per-gestora model configuration (no plaintext keys ever; *_key_set only). */
export interface ModelConfig {
  gestoraId: string;
  llmProvider: string | null;
  llmModel: string | null;
  embeddingProvider: string | null;
  embeddingModel: string | null;
  ollamaBaseUrl: string | null;
  anthropicKeySet: boolean;
  mistralKeySet: boolean;
  openaiKeySet: boolean;
  isDefault: boolean;
  updatedAt: string | null;
}

export interface Fund {
  id: string;
  gestoraId: string;
  name: string;
  jurisdiction: string;
  createdAt: string;
}

/** SPV / vehicle kind (backend VehicleCreate pattern, 015_vehicles.sql). */
export type VehicleType = "spv" | "feeder" | "coinvest" | "holdco" | "other";

export const VEHICLE_TYPES: VehicleType[] = [
  "spv",
  "feeder",
  "coinvest",
  "holdco",
  "other",
];

/** SPV / investment vehicle hanging from a fund (015_vehicles.sql). */
export interface Vehicle {
  id: string;
  fundId: string;
  name: string;
  vehicleType: VehicleType;
  jurisdiction?: string | null;
  createdAt: string;
}

export interface UserProfile {
  id: string;
  email: string;
  role: Role;
  /** NULL for admin/counsel users. */
  gestoraId: string | null;
  name?: string;
}

/** Marker set by the backend post-merge on entries that originate from
 * client-provided structured fields (authoritative, shown as "confirmado"). */
export type ParsedSource = "client_confirmed";

export interface ParsedParty {
  role: string;
  name: string;
  source?: ParsedSource;
}

export interface ParsedDate {
  label: string;
  date: string;
  source?: ParsedSource;
}

export interface ParsedTerm {
  field: string;
  value: string;
  source?: ParsedSource;
}

/** Output of the Claude intake parser (SPEC.md, verbatim JSON contract). */
export interface ParsedParams {
  language: AppLanguage;
  docTypeConfirmed: string;
  parties: ParsedParty[];
  keyDates: ParsedDate[];
  jurisdiction: string;
  governingLaw: string;
  keyTerms: ParsedTerm[];
  summary: string;
  confidence: number;
  unclearFields: string[];
  generationReady: boolean;
  /** Frontend flag: doc_type='other' and the parser could not classify the request. */
  unclassifiable?: boolean;
}

/** Structured intake field types (backend models/doc_fields.py registry). */
export type DocFieldType =
  | "text"
  | "date"
  | "amount"
  | "percent"
  | "party"
  | "select";

/** One structured intake field spec for a doc_type
 * (GET /api/doc-types/{doc_type}/fields). */
export interface FieldSpec {
  key: string;
  /** i18n dictionary key for the field label (docfields.*). */
  labelI18nKey: string;
  type: DocFieldType;
  required: boolean;
  /** Allowed values when type === "select". */
  options?: string[];
  help?: string;
}

export interface RequestItem {
  id: string;
  fundId: string;
  fundName?: string;
  /** Optional SPV/vehicle the document belongs to (null = the fund itself). */
  vehicleId?: string | null;
  vehicleName?: string | null;
  gestoraId?: string;
  userId: string;
  requestedByName?: string;
  docType: string;
  docTypeLabel?: string;
  docTypeCustom?: string | null;
  freetext: string;
  /** Client-provided structured intake values (key → value); null/absent for
   * freetext-only requests. */
  structuredFields?: Record<string, string> | null;
  language: AppLanguage;
  parsedParams?: ParsedParams | null;
  status: RequestStatus;
  requiresCounsel: boolean;
  exitAAcknowledgedAt?: string | null;
  /** Counsel SLA clock: stamped when the request enters counsel_review. */
  counselRequestedAt?: string | null;
  /** Counsel SLA clock: stamped when counsel validates. */
  counselValidatedAt?: string | null;
  /** Specialized drafting branch used at generation time (GET .../branch). */
  branch?: Branch;
  /** Precedent fallback chain level used at generation time. Level 3 forces Exit B. */
  fallbackLevel?: FallbackLevel;
  /** True when the generated document contains [MISSING: …] fields → blocks Exit A. */
  hasMissingFields?: boolean;
  /** Collaboration (012_collaboration.sql): per-caller ownership/sharing flags
   * the list/detail endpoints set so the UI can distinguish "mine" from
   * "shared with me" and hide owner-only actions. Undefined for counsel/admin. */
  isOwner?: boolean | null;
  sharedWithMe?: boolean | null;
  sharedByEmail?: string | null;
  createdAt: string;
  updatedAt: string;
}

/** Server-computed SLA urgency of a pending counsel review
 * (GET /api/counsel/queue). Thresholds live in backend config (sla_*_hours). */
export type SlaUrgency = "green" | "amber" | "red";

/** Most-urgent-first, matching the backend queue ordering. */
export const SLA_URGENCIES: SlaUrgency[] = ["red", "amber", "green"];

/** Assignment policy scope of a queue item for the calling counsel
 * (GET /api/counsel/queue): "mine" = gestora assigned to this lawyer;
 * "pool" = gestora with NO lawyer assigned yet (visible to every counsel
 * until an admin assigns one). Items of gestoras assigned to OTHER lawyers
 * never reach the caller. */
export type CounselAssignmentScope = "mine" | "pool";

/** One row of the counsel review queue: the request plus SLA/gestora context
 * so the inbox can badge and filter without extra calls. */
export interface CounselQueueItem extends RequestItem {
  gestoraName?: string | null;
  /** Hours the review has been pending; null when the clock never started. */
  hoursPending: number | null;
  /** Promised review turnaround (backend sla_review_hours). */
  slaHours: number;
  urgency: SlaUrgency;
  /** Sectioning: own gestora vs. unassigned-gestora pool. */
  assignment: CounselAssignmentScope;
}

/** One in-app notification (bell inbox, GET /api/notifications/inbox). */
export interface AppNotification {
  id: string;
  /** Free-text event kind (counsel_requested, document_validated, …). */
  kind: string;
  title: string;
  body: string | null;
  /** When set, the notification links to the request's detail/review page. */
  requestId: string | null;
  /** null = unread. */
  readAt: string | null;
  createdAt: string | null;
}

export interface DocumentItem {
  id: string;
  requestId: string;
  versionType: DocumentVersionType;
  filePath: string;
  precedentVersionId?: string | null;
  uploadedBy?: string | null;
  /** Refinement iteration this version belongs to (0 = original generation). */
  iteration: number;
  createdAt: string;
}

export interface PrecedentVersion {
  id: string;
  precedentId: string;
  versionNumber: number;
  filePath: string;
  status: PrecedentVersionStatus;
  ragWeight: number;
  activatedAt?: string | null;
  supersededAt?: string | null;
  createdBy?: string | null;
}

export interface Precedent {
  id: string;
  gestoraId: string;
  fundId?: string | null;
  docType: string;
  docTypeLabel?: string;
  language: AppLanguage;
  source: PrecedentSource;
  createdAt: string;
  versions: PrecedentVersion[];
}

/** Redline rendered as a sequence of segments (insert / delete / equal). */
export interface RedlineSegment {
  type: "eq" | "ins" | "del";
  text: string;
}

/** Safe HTML rendering of a stored .docx (GET .../documents/{type}/html). */
export interface DocumentHtml {
  html: string;
  stats: {
    insertions: number;
    deletions: number;
  };
}

export interface CounselComment {
  id: string;
  requestId: string;
  author: string;
  text: string;
  createdAt: string;
}

/** Everything the counsel review screen needs in one payload. */
export interface ReviewBundle {
  request: RequestItem;
  draftText: string;
  redline: RedlineSegment[];
  comments: CounselComment[];
}

/* ------------------------------------------------------------------ */
/* Internal critic review trail (Feature 2)                            */
/* ------------------------------------------------------------------ */

export type ReviewIssueSeverity = "blocking" | "major" | "minor";
export type ReviewIssueCategory =
  | "factual"
  | "completeness"
  | "legal"
  | "consistency";

/** A verifiable {where, quote} pointer to the offending DRAFT text
 * (grounding Feature 2; same shape as the tabular-review {page, quote}). */
export interface ReviewIssueCitation {
  where: string;
  quote: string;
}

/** One substantive defect raised by the automated critic
 * (backend services/critic.py Issue). */
export interface ReviewIssue {
  severity: ReviewIssueSeverity;
  category: ReviewIssueCategory;
  problem: string;
  suggestedFix?: string;
  location?: string;
  /** Verifiable citation to the exact problematic draft text. */
  citation?: ReviewIssueCitation;
  /** Reviewer-reported confidence in [0, 1]; absent when the model omitted it. */
  confidence?: number;
}

/** One persisted critic round (GET /api/requests/{id}/reviews). */
export interface VerificationFinding {
  layer: "deterministic" | "llm";
  category: string;
  severity: "critical" | "warning";
  problem: string;
  quote?: string;
  where?: string;
}

/** Una pasada del verificador cruzado (020) por iteración de borrador. */
export interface Verification {
  iteration: number;
  provider?: string;
  model?: string;
  findings: VerificationFinding[];
  criticalCount: number;
  forcedCounsel: boolean;
  createdAt?: string;
}

export interface GenerationReview {
  round: number;
  approved: boolean;
  issues: ReviewIssue[];
  createdAt?: string | null;
}

/* ------------------------------------------------------------------ */
/* Drafting lessons (Feature 3) — admin-only, gestora-siloed           */
/* ------------------------------------------------------------------ */

/** One accumulated drafting lesson learned for a gestora
 * (GET /api/admin/gestoras/{id}/lessons). */
export interface DraftingLesson {
  id: string;
  gestoraId: string;
  branch: Branch;
  docType?: string | null;
  lesson: string;
  weight: number;
  createdAt?: string | null;
}

/* ------------------------------------------------------------------ */
/* Review playbooks — human-authored critic rules (admin CRUD)         */
/* ------------------------------------------------------------------ */

/** review_playbooks row: human-authored review rules injected into the
 * critic, STRICTLY gestora-siloed (GET/POST/PATCH /api/playbooks). */
export interface ReviewPlaybook {
  id: string;
  gestoraId: string;
  branch?: Branch | null;
  docType?: string | null;
  title: string;
  content: string;
  filePath?: string | null;
  isActive: boolean;
  createdBy?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

/** Counsel assigned to the requesting client's gestora (GET /api/my/counsel). */
export interface AssignedCounsel {
  name: string;
  email: string;
  isPrimary: boolean;
  turnaroundHours: number;
}

/** counsel_assignments row (admin management + Exit B routing). */
export interface CounselAssignment {
  id: string;
  gestoraId: string;
  counselUserId: string;
  isPrimary: boolean;
  counselEmail?: string | null;
  createdAt: string;
}

export type RefinementStatus = "pending" | "applied" | "failed";

/**
 * Iterative refinement of a generated document (refinements row): the client
 * requests a targeted adjustment in natural language and the document is
 * regenerated as a new iteration, keeping version history.
 */
export interface Refinement {
  id: string;
  requestId: string;
  iteration: number;
  instruction: string;
  status: RefinementStatus;
  /** Failure reason ([REFINEMENT-UNCLEAR] or job error); null unless failed. */
  error?: string | null;
  createdAt: string;
  appliedAt?: string | null;
}

export type GenerationJobStatus = "queued" | "running" | "succeeded" | "failed";

/** generation_jobs row exposed by the async generate flow (202 + poll). */
export interface GenerationJob {
  id: string;
  status: GenerationJobStatus;
  attempts: number;
  lastError?: string | null;
}

/* ------------------------------------------------------------------ */
/* Admin KPIs: quality (improvement #6) + counsel SLA (improvement #8)  */
/* ------------------------------------------------------------------ */

/** One aggregated quality group (GET /api/admin/quality). Ratios are 0–1. */
export interface QualityStats {
  count: number;
  /** Mean draft→final similarity (1.0 = validated/accepted untouched). */
  avgSimilarity: number | null;
  avgRefinements: number | null;
  /** Share delivered via Exit A (accepted as-is, the strongest signal). */
  pctAcceptedAsIs: number | null;
  /** Share validated by counsel (Exit B). */
  pctValidated: number | null;
}

export interface QualityReport {
  overall: QualityStats;
  byDocType: Array<QualityStats & { docType: string }>;
  byGestora: Array<QualityStats & { gestoraId: string; gestoraName?: string | null }>;
}

/** One counsel-SLA aggregate (GET /api/admin/sla). */
export interface SlaStats {
  /** Reviews currently in counsel_review. */
  pending: number;
  /** Pending reviews already past the SLA. */
  pastSla: number;
  /** Mean counsel response time over completed validations (hours). */
  avgValidationHours: number | null;
  remindersSent: number;
  escalationsSent: number;
}

export interface SlaReport {
  /** Promised review turnaround (backend sla_review_hours). */
  slaHours: number;
  overall: SlaStats;
  byCounsel: Array<SlaStats & { counselEmail: string }>;
}

/* ------------------------------------------------------------------ */
/* Billing over usage_events (improvement #7)                          */
/* ------------------------------------------------------------------ */

/** One gestora's consumption in a billing period (GET /api/admin/billing). */
export interface BillingRow {
  gestoraId: string;
  gestoraName: string | null;
  subscriptionTier: SubscriptionTier;
  /** Billable generations (document_generated events, refinements included). */
  docsGenerated: number;
  /** Monthly doc allowance of the tier; null = unlimited (custom). */
  docsLimit: number | null;
  overageDocs: number;
  exitACount: number;
  exitBRequested: number;
  exitBValidated: number;
  fundCount: number;
  /** Funds allowance of the tier; null = unlimited (custom). */
  fundsLimit: number | null;
  overFundsLimit: boolean;
  /** Dashboard estimate (0 while overage prices are unset / TBD). */
  estimatedOverageEur: number;
}

export interface BillingReport {
  /** YYYY-MM. */
  period: string;
  rows: BillingRow[];
}

/** The client's own gestora consumption this month (GET /api/my/usage). */
export interface MyUsage {
  /** YYYY-MM (current period). */
  billingPeriod: string;
  subscriptionTier: SubscriptionTier;
  docsGenerated: number;
  /** null = unlimited (custom tier). */
  docsLimit: number | null;
}

/* ------------------------------------------------------------------ */
/* Gestora dashboard aggregates (GET /api/dashboard/stats, Roadmap D)  */
/* ------------------------------------------------------------------ */

/** Status counts for the gestora dashboard metric cards. */
export interface DashboardCounts {
  /** parsing + confirmed + generating. */
  inProgress: number;
  /** review_pending: drafts waiting for the client's own review. */
  awaitingYou: number;
  /** counsel_review: out with the lawyer (Exit B). */
  inCounselReview: number;
  /** validated: ready to download. */
  ready: number;
  /** delivered during the current calendar month. */
  deliveredThisMonth: number;
}

/** One upcoming counsel-SLA validation deadline (soonest first). */
export interface DashboardDeadline {
  requestId: string;
  docType: string;
  fundName: string | null;
  /** ISO deadline (counsel_requested_at + sla_hours); null when unknown. */
  deadline: string | null;
  /** Hours until the SLA elapses; negative once overdue. */
  hoursRemaining: number;
  overdue: boolean;
}

/** One recent audit-log entry (already gestora-scoped server-side). */
export interface DashboardActivityItem {
  /** Raw audit action literal (AuditAction enum); UI humanizes common ones. */
  action: string;
  timestamp: string | null;
  resourceType: string | null;
  resourceId: string | null;
}

/** Everything the enriched client dashboard needs in one call
 * (GET /api/dashboard/stats, client role only). */
export interface DashboardStats {
  counts: DashboardCounts;
  upcomingDeadlines: DashboardDeadline[];
  /** Mean counsel validation turnaround (last 20 completed); null = none yet. */
  avgValidationHours: number | null;
  /** Promised review turnaround (backend sla_review_hours). */
  slaHours: number;
  /** Newest first. */
  recentActivity: DashboardActivityItem[];
  fundsCount: number;
}

/* ------------------------------------------------------------------ */
/* Tabular Review (010_tabular_reviews.sql) — extraction grid           */
/* ------------------------------------------------------------------ */

/** Answer type of a tabular column (mirrors backend TabularColType). */
export type ColType =
  | "text"
  | "number"
  | "percent"
  | "monetary"
  | "date"
  | "yes_no"
  | "tag";

export const COL_TYPES: ColType[] = [
  "text",
  "number",
  "percent",
  "monetary",
  "date",
  "yes_no",
  "tag",
];

export type TabularReviewStatus = "draft" | "running" | "complete" | "failed";

export type TabularCellStatus = "pending" | "done" | "error";

/** What a review document references; both live in the gestora silo. */
export type TabularSourceKind = "precedent_version" | "request_document";

/** A column = a question + an answer type (+ options for the 'tag' type). */
export interface TabularColumn {
  id: string;
  reviewId: string;
  position: number;
  name: string;
  question: string;
  colType: ColType;
  options: string[] | null;
}

/** A document row in the grid (a precedent version or a generated document). */
export interface TabularDocumentRef {
  id: string;
  reviewId: string;
  position: number;
  sourceKind: TabularSourceKind;
  sourceId: string;
  label: string | null;
}

/** A verifiable citation: page (null for plain text) + verbatim quote. */
export interface TabularCitation {
  page: number | string | null;
  quote: string | null;
}

/** One extracted cell: a typed value + reasoning + citation, or an error. */
export interface TabularCell {
  id: string;
  documentId: string;
  columnId: string;
  value: string | null;
  reasoning: string | null;
  citation: TabularCitation | null;
  status: TabularCellStatus;
  error: string | null;
}

/** A tabular review header (list view). */
export interface TabularReview {
  id: string;
  gestoraId: string;
  fundId: string | null;
  createdBy: string | null;
  title: string;
  status: TabularReviewStatus;
  /** Collaboration (012_collaboration.sql): per-caller ownership/sharing flags,
   * mirroring RequestItem. Undefined for counsel/admin. */
  isOwner?: boolean | null;
  sharedWithMe?: boolean | null;
  sharedByEmail?: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

/* ------------------------------------------------------------------ */
/* Collaboration / sharing (012_collaboration.sql)                     */
/* ------------------------------------------------------------------ */

/** A same-gestora colleague offered in the share picker (GET /api/my/colleagues). */
export interface Colleague {
  id: string;
  email: string;
  name: string;
}

/** A collaborator on a shared resource (one share row). Always single-gestora:
 * gestoraId equals both the sharer's and the sharee's gestora. */
export interface Share {
  id: string;
  gestoraId: string;
  sharedWithUserId: string;
  sharedWithEmail: string | null;
  sharedWithName: string | null;
  sharedBy: string;
  sharedByEmail: string | null;
  createdAt: string | null;
}

/** A tabular review with its full grid (columns + documents + cells). */
export interface TabularReviewDetail extends TabularReview {
  columns: TabularColumn[];
  documents: TabularDocumentRef[];
  cells: TabularCell[];
}

/** Lightweight progress payload for the polling loop while a review runs. */
export interface TabularReviewStatusInfo {
  id: string;
  status: TabularReviewStatus;
  cellTotal: number;
  cellDone: number;
  cellError: number;
}

/** A document the user can pick into a new review (precedents / generated). */
export interface TabularDocumentOption {
  sourceKind: TabularSourceKind;
  sourceId: string;
  label: string;
}

/** Input column for the new-review flow (no ids yet). */
export interface TabularColumnInput {
  name: string;
  question: string;
  colType: ColType;
  options?: string[] | null;
}

/* ------------------------------------------------------------------ */
/* Chat Q&A sobre el RAG de la gestora (021_chat.sql)                  */
/* ------------------------------------------------------------------ */

/** Procedencia de un fragmento usado para responder (cita [n]). */
export interface ChatCitation {
  index: number;
  precedentId: string;
  precedentVersionId: string;
  docType: string;
  source: string;
  snippet: string;
}

/** Grounding posterior de la respuesta (verificador cruzado, 020). */
export interface ChatVerification {
  findings: Array<{ category: string; problem: string; quote: string }>;
  provider: string | null;
  model: string | null;
}

export interface ChatConversation {
  id: string;
  title: string | null;
  createdAt: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: ChatCitation[];
  verification: ChatVerification | null;
  createdAt: string | null;
}

/** Un evento del stream SSE de /api/chat/.../messages. */
export type ChatStreamEvent =
  | { type: "sources"; citations: ChatCitation[] }
  | { type: "delta"; text: string }
  | { type: "verification"; verification: ChatVerification }
  | { type: "done"; messageId: string }
  | { type: "error"; detail: string };
