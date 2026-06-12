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
  | "platform_base";

export type PrecedentVersionStatus = "draft" | "active" | "superseded";

/** Precedent fallback chain level (SPEC.md). Level 3 forces Exit B. */
export type FallbackLevel = 0 | 1 | 2 | 3;

export type AppLanguage = "es" | "en" | "fr" | "de" | "other";

export interface Gestora {
  id: string;
  name: string;
  driveFolderId?: string | null;
  subscriptionTier: SubscriptionTier;
  billingEmail: string;
  createdAt: string;
}

export interface Fund {
  id: string;
  gestoraId: string;
  name: string;
  jurisdiction: string;
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
  /** Precedent fallback chain level used at generation time. Level 3 forces Exit B. */
  fallbackLevel?: FallbackLevel;
  /** True when the generated document contains [MISSING: …] fields → blocks Exit A. */
  hasMissingFields?: boolean;
  createdAt: string;
  updatedAt: string;
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
