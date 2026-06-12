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

export interface ParsedParty {
  role: string;
  name: string;
}

export interface ParsedDate {
  label: string;
  date: string;
}

export interface ParsedTerm {
  field: string;
  value: string;
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
  language: AppLanguage;
  parsedParams?: ParsedParams | null;
  status: RequestStatus;
  requiresCounsel: boolean;
  exitAAcknowledgedAt?: string | null;
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
