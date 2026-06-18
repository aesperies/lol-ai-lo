"use client";

/**
 * Typed fetch wrapper to the FastAPI backend (NEXT_PUBLIC_API_URL).
 *
 * ALL backend REST paths live in `apiPaths` below so they are easy to adjust
 * when the backend lands.
 *
 * Graceful degradation: in dev stub mode (NEXT_PUBLIC_SUPABASE_URL unset)
 * every function resolves against the in-memory stub store (lib/stub-data.ts)
 * with a simulated latency, so the whole UI is fully navigable without a
 * backend or Supabase.
 */

import { docTypeLabel } from "@/lib/catalog";
import {
  STUB_ASSIGNED_COUNSEL,
  STUB_FUNDS,
  STUB_ALL_USERS,
  STUB_QUALITY_REPORT,
  STUB_SLA_REPORT,
  delay,
  findRequest,
  nextRequestId,
  nowIso,
  stubAddComment,
  stubBillingCsv,
  stubBillingPeriods,
  stubBillingReport,
  stubCounselAssignments,
  stubDocumentHtml,
  stubDraftText,
  stubGestoras,
  stubMyUsage,
  stubParse,
  stubPollGenerationJob,
  stubGetRetentionPolicy,
  stubPrecedents,
  stubPutRetentionPolicy,
  stubRedline,
  stubRefinements,
  stubRequests,
  stubDocFields,
  stubReviewBundle,
  stubStartGenerationJob,
  stubStartRefinement,
  stubRequestReviews,
  stubRequestBranch,
  stubGestoraLessons,
  stubPlaybooks,
  stubCreatePlaybook,
  stubUpdatePlaybook,
  stubSetPlaybookActive,
  stubDeletePlaybook,
  stubUploadModel,
  stubTabularReviews,
  stubTabularReview,
  stubCreateTabularReview,
  stubRunTabularReview,
  stubTabularReviewStatus,
  stubAddTabularColumn,
  stubDeleteTabularColumn,
  stubDeleteTabularDocument,
  stubTabularReviewCsv,
  stubTabularDocumentOptions,
  stubAccountProfile,
  stubSetMfaEnabled,
  stubExportMyData,
  stubDeleteMyData,
  stubGetModelConfig,
  stubPutModelConfig,
  stubColleagues,
  stubRequestShares,
  stubCreateRequestShare,
  stubDeleteRequestShare,
  stubReviewShares,
  stubCreateReviewShare,
  stubDeleteReviewShare,
} from "@/lib/stub-data";
import {
  getSupabaseBrowserClient,
  isStubMode,
  readDevRoleCookie,
} from "@/lib/supabase/client";
import type {
  AccountProfile,
  AssignedCounsel,
  BillingReport,
  BillingRow,
  Branch,
  Colleague,
  DeleteMode,
  ModelConfig,
  CounselAssignment,
  CounselComment,
  DocumentHtml,
  DocumentVersionType,
  DraftingLesson,
  FieldSpec,
  Fund,
  GenerationJob,
  GenerationJobStatus,
  GenerationReview,
  Gestora,
  MyUsage,
  ParsedParams,
  Precedent,
  QualityReport,
  QualityStats,
  RedlineSegment,
  Refinement,
  RefinementStatus,
  RequestItem,
  RetentionPolicy,
  ReviewBundle,
  ReviewIssue,
  ReviewPlaybook,
  Role,
  Share,
  SlaReport,
  SlaStats,
  SubscriptionTier,
  TabularColumnInput,
  TabularDocumentOption,
  TabularReview,
  TabularReviewDetail,
  TabularReviewStatusInfo,
  UserProfile,
} from "@/lib/types";

/* ------------------------------------------------------------------ */
/* REST paths — single source of truth, adjust here when backend lands */
/* ------------------------------------------------------------------ */

// TODO: confirm final REST paths with the FastAPI backend once implemented.
export const apiPaths = {
  requests: "/api/requests",
  request: (id: string) => `/api/requests/${id}`,
  parse: (id: string) => `/api/requests/${id}/parse`,
  confirm: (id: string) => `/api/requests/${id}/confirm`,
  generate: (id: string) => `/api/requests/${id}/generate`,
  generationJob: (id: string) => `/api/requests/${id}/generation-job`,
  exitAAcknowledge: (id: string) => `/api/requests/${id}/exit-a/acknowledge`,
  exitB: (id: string) => `/api/requests/${id}/exit-b`,
  refinements: (id: string) => `/api/requests/${id}/refinements`,
  // iteration: refinement version history (latest served when omitted).
  documentDownload: (id: string, type: DocumentVersionType, iteration?: number) =>
    `/api/requests/${id}/documents/${type}/download${
      iteration === undefined ? "" : `?iteration=${iteration}`
    }`,
  documentHtml: (id: string, type: DocumentVersionType, iteration?: number) =>
    `/api/requests/${id}/documents/${type}/html${
      iteration === undefined ? "" : `?iteration=${iteration}`
    }`,
  reviewBundle: (id: string) => `/api/requests/${id}/review`,
  // Critic review trail + derived drafting branch (drafting-agents UI).
  requestReviews: (id: string) => `/api/requests/${id}/reviews`,
  requestBranch: (id: string) => `/api/requests/${id}/branch`,
  counselEdit: (id: string) => `/api/requests/${id}/counsel-edit`,
  counselUpload: (id: string) => `/api/requests/${id}/counsel-upload`,
  validate: (id: string) => `/api/requests/${id}/validate`,
  comments: (id: string) => `/api/requests/${id}/comments`,
  counselQueue: "/api/counsel/queue",
  myCounsel: "/api/my/counsel",
  counselAssignments: (gestoraId: string) =>
    `/api/counsel-assignments?gestora_id=${gestoraId}`,
  counselAssignmentCreate: "/api/counsel-assignments",
  counselAssignment: (id: string) => `/api/counsel-assignments/${id}`,
  // Structured intake field specs per doc_type (improvement #5).
  docFields: (docType: string) =>
    `/api/doc-types/${encodeURIComponent(docType)}/fields`,
  funds: "/api/funds",
  gestoras: "/api/gestoras",
  precedents: "/api/precedents",
  precedentVersions: (precedentId: string) =>
    `/api/precedents/${precedentId}/versions`,
  precedentVersionActivate: (precedentId: string, versionId: string) =>
    `/api/precedents/${precedentId}/versions/${versionId}/activate`,
  precedentVersionSupersede: (precedentId: string, versionId: string) =>
    `/api/precedents/${precedentId}/versions/${versionId}/supersede`,
  users: "/api/users",
  // Review playbooks CRUD (admin) — gestora-siloed critic rules.
  playbooks: (gestoraId?: string) =>
    `/api/playbooks${gestoraId ? `?gestora_id=${gestoraId}` : ""}`,
  playbook: (id: string) => `/api/playbooks/${id}`,
  playbookActivate: (id: string) => `/api/playbooks/${id}/activate`,
  playbookDeactivate: (id: string) => `/api/playbooks/${id}/deactivate`,
  // Accumulated drafting lessons per gestora (admin-only, gestora-siloed).
  gestoraLessons: (gestoraId: string, branch?: string) =>
    `/api/admin/gestoras/${gestoraId}/lessons${branch ? `?branch=${branch}` : ""}`,
  // Admin KPIs: quality (improvement #6) + counsel SLA (improvement #8).
  adminQuality: "/api/admin/quality",
  adminSla: "/api/admin/sla",
  adminSlaSweep: "/api/admin/sla/sweep",
  // Billing over usage_events (improvement #7).
  adminBilling: (period?: string) =>
    `/api/admin/billing${period ? `?period=${period}` : ""}`,
  adminBillingPeriods: "/api/admin/billing/periods",
  adminBillingExport: (period?: string) =>
    `/api/admin/billing/export${period ? `?period=${period}` : ""}`,
  myUsage: "/api/my/usage",
  // GDPR data retention per gestora (improvement #10).
  adminRetention: (gestoraId: string) =>
    `/api/admin/gestoras/${gestoraId}/retention`,
  adminRetentionSweep: "/api/admin/retention/sweep",
  // Tabular Review (010_tabular_reviews.sql) — gestora-siloed extraction grid.
  tabularReviews: "/api/tabular-reviews",
  tabularReview: (id: string) => `/api/tabular-reviews/${id}`,
  tabularReviewRun: (id: string) => `/api/tabular-reviews/${id}/run`,
  tabularReviewStatus: (id: string) => `/api/tabular-reviews/${id}/status`,
  tabularReviewColumns: (id: string) => `/api/tabular-reviews/${id}/columns`,
  tabularReviewColumn: (id: string, colId: string) =>
    `/api/tabular-reviews/${id}/columns/${colId}`,
  tabularReviewDocument: (id: string, docId: string) =>
    `/api/tabular-reviews/${id}/documents/${docId}`,
  tabularReviewExport: (id: string) => `/api/tabular-reviews/${id}/export.csv`,
  // Account & security (011_account_security.sql).
  me: "/api/me",
  meMfa: "/api/me/mfa",
  meExport: "/api/me/export",
  meDelete: "/api/me/delete",
  adminUserDelete: (id: string) => `/api/admin/users/${id}/delete`,
  // Per-gestora model configuration (admin-only).
  adminModelConfig: (gestoraId: string) =>
    `/api/admin/gestoras/${gestoraId}/model-config`,
  // Collaboration / sharing (012_collaboration.sql) — single-gestora only.
  colleagues: "/api/my/colleagues",
  requestShares: (id: string) => `/api/requests/${id}/shares`,
  requestShare: (id: string, userId: string) =>
    `/api/requests/${id}/shares/${userId}`,
  reviewShares: (id: string) => `/api/tabular-reviews/${id}/shares`,
  reviewShare: (id: string, userId: string) =>
    `/api/tabular-reviews/${id}/shares/${userId}`,
} as const;

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Builds auth headers: Supabase access token, or X-Dev-User in stub mode. */
async function authHeaders(): Promise<Record<string, string>> {
  if (isStubMode()) {
    // Backend dev-stub auth (DEV_AUTH_STUB=true) reads the X-Dev-User header.
    const role = readDevRoleCookie() ?? "client";
    return { "X-Dev-User": `dev-${role}` };
  }
  const supabase = getSupabaseBrowserClient();
  const { data } = (await supabase?.auth.getSession()) ?? { data: null };
  const token = data?.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(await authHeaders()),
  };
  const res = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const STUB_LATENCY = 600;

/* ------------------------------------------------------------------ */
/* Requests — client flow                                               */
/* ------------------------------------------------------------------ */

export interface CreateRequestInput {
  fundId: string;
  docType: string;
  docTypeCustom?: string;
  freetext: string;
  requiresCounsel: boolean;
  /** Structured intake values (registry keys of the selected doc_type);
   * omit/undefined for freetext-only requests. */
  structuredFields?: Record<string, string>;
}

export async function createRequest(
  input: CreateRequestInput,
): Promise<RequestItem> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    const fund = STUB_FUNDS.find((f) => f.id === input.fundId);
    const req: RequestItem = {
      id: nextRequestId(),
      fundId: input.fundId,
      fundName: fund?.name,
      gestoraId: fund?.gestoraId,
      userId: "u-client-1",
      requestedByName: "Lucía Fernández",
      docType: input.docType,
      docTypeLabel: docTypeLabel(input.docType),
      docTypeCustom: input.docTypeCustom ?? null,
      freetext: input.freetext,
      structuredFields: input.structuredFields ?? null,
      language: "es",
      status: "parsing",
      requiresCounsel: input.requiresCounsel,
      createdAt: nowIso(),
      updatedAt: nowIso(),
    };
    stubRequests.unshift(req);
    return req;
  }
  return apiFetch<RequestItem>(apiPaths.requests, {
    method: "POST",
    // snake_case key expected by the backend (RequestCreate.structured_fields).
    body: { ...input, structured_fields: input.structuredFields },
  });
}

/** Structured intake field specs for a doc_type ([] = freetext-only). */
export async function getDocFields(docType: string): Promise<FieldSpec[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubDocFields(docType);
  }
  const res = await apiFetch<{
    doc_type: string;
    fields: Array<{
      key: string;
      label_i18n_key: string;
      type: FieldSpec["type"];
      required: boolean;
      options?: string[];
      help?: string;
    }>;
  }>(apiPaths.docFields(docType));
  return res.fields.map((f) => ({
    key: f.key,
    labelI18nKey: f.label_i18n_key,
    type: f.type,
    required: f.required,
    options: f.options,
    help: f.help,
  }));
}

export async function parseRequest(id: string): Promise<ParsedParams> {
  if (isStubMode()) {
    await delay(1200);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    const params = stubParse(req);
    req.parsedParams = params;
    req.updatedAt = nowIso();
    return params;
  }
  return apiFetch<ParsedParams>(apiPaths.parse(id), { method: "POST" });
}

export async function confirmRequest(
  id: string,
  params: ParsedParams,
  edited: boolean,
): Promise<RequestItem> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    // TODO backend: log `params_edited` audit action when edited === true.
    req.parsedParams = params;
    req.status = "confirmed";
    req.updatedAt = nowIso();
    return req;
  }
  return apiFetch<RequestItem>(apiPaths.confirm(id), {
    method: "POST",
    body: { parsedParams: params, edited },
  });
}

/** Enqueues generation (202): returns the job to poll via getGenerationJob. */
export async function generateRequest(id: string): Promise<GenerationJob> {
  if (isStubMode()) {
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    await delay(STUB_LATENCY / 2);
    req.status = "generating";
    req.updatedAt = nowIso();
    return stubStartGenerationJob(req);
  }
  const res = await apiFetch<{ job_id: string; status: GenerationJobStatus }>(
    apiPaths.generate(id),
    { method: "POST" },
  );
  return { id: res.job_id, status: res.status, attempts: 0 };
}

/** Latest generation job for a request (poll target of the 202 flow). */
export async function getGenerationJob(
  requestId: string,
): Promise<GenerationJob> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 4);
    const job = stubPollGenerationJob(requestId);
    if (!job) throw new ApiError(404, "No generation job for this request");
    return job;
  }
  const res = await apiFetch<{
    id: string;
    status: GenerationJobStatus;
    attempts: number;
    last_error?: string | null;
  }>(apiPaths.generationJob(requestId));
  return {
    id: res.id,
    status: res.status,
    attempts: res.attempts,
    lastError: res.last_error ?? null,
  };
}

export async function acknowledgeExitA(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    req.exitAAcknowledgedAt = nowIso();
    req.status = "delivered";
    req.updatedAt = nowIso();
    return req;
  }
  return apiFetch<RequestItem>(apiPaths.exitAAcknowledge(id), {
    method: "POST",
  });
}

/* ------------------------------------------------------------------ */
/* Iterative refinements (improvement #4)                              */
/* ------------------------------------------------------------------ */

/** Mirrors the backend `max_refinements` setting (config.py, default 3). */
export const MAX_REFINEMENTS = 3;

/** Mirrors the backend `sla_review_hours` setting (config.py, default 48):
 * promised counsel review turnaround for Exit B. */
export const SLA_REVIEW_HOURS = 48;

interface RefinementWire {
  id: string;
  request_id: string;
  iteration: number;
  instruction: string;
  status: RefinementStatus;
  error?: string | null;
  created_at?: string;
  applied_at?: string | null;
}

function mapRefinement(wire: RefinementWire): Refinement {
  return {
    id: wire.id,
    requestId: wire.request_id,
    iteration: wire.iteration,
    instruction: wire.instruction,
    status: wire.status,
    error: wire.error ?? null,
    createdAt: wire.created_at ?? "",
    appliedAt: wire.applied_at ?? null,
  };
}

/**
 * Requests one iterative refinement (202): the document is regenerated as a
 * new iteration. Poll getGenerationJob, then re-read getRefinements for the
 * applied/failed outcome.
 */
export async function createRefinement(
  id: string,
  instruction: string,
): Promise<{ refinementId: string; jobId: string; iteration: number }> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    return stubStartRefinement(req, instruction);
  }
  const res = await apiFetch<{
    refinement_id: string;
    job_id: string;
    iteration: number;
  }>(apiPaths.refinements(id), { method: "POST", body: { instruction } });
  return {
    refinementId: res.refinement_id,
    jobId: res.job_id,
    iteration: res.iteration,
  };
}

/** Refinement history for a request (oldest first). */
export async function getRefinements(id: string): Promise<Refinement[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 4);
    return stubRefinements
      .filter((r) => r.requestId === id)
      .map((r) => ({ ...r }));
  }
  const rows = await apiFetch<RefinementWire[]>(apiPaths.refinements(id));
  return rows.map(mapRefinement);
}

export async function requestExitB(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    req.status = "counsel_review";
    req.requiresCounsel = true;
    // SLA clock starts now (counsel dashboard chip / admin SLA report).
    req.counselRequestedAt = nowIso();
    req.updatedAt = nowIso();
    return req;
  }
  return apiFetch<RequestItem>(apiPaths.exitB(id), { method: "POST" });
}

/** Overlays the collaboration flags (snake_case on the wire) onto a request,
 * leaving the rest of the existing pass-through shape untouched. */
function withRequestShareFlags(req: RequestItem): RequestItem {
  const wire = req as RequestItem & {
    is_owner?: boolean | null;
    shared_with_me?: boolean | null;
    shared_by_email?: string | null;
  };
  return {
    ...req,
    isOwner: req.isOwner ?? wire.is_owner ?? null,
    sharedWithMe: req.sharedWithMe ?? wire.shared_with_me ?? null,
    sharedByEmail: req.sharedByEmail ?? wire.shared_by_email ?? null,
  };
}

export async function getRequests(): Promise<RequestItem[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return [...stubRequests];
  }
  const rows = await apiFetch<RequestItem[]>(apiPaths.requests);
  return rows.map(withRequestShareFlags);
}

export async function getRequest(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    return req;
  }
  return withRequestShareFlags(await apiFetch<RequestItem>(apiPaths.request(id)));
}

/** Downloads a document version as a Blob (stub: plain-text .docx placeholder).
 * `iteration` selects an older refinement version; latest when omitted. */
export async function downloadDocument(
  id: string,
  type: DocumentVersionType,
  iteration?: number,
): Promise<Blob> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    const text =
      type === "redline"
        ? stubRedline(req, iteration)
            .map((s) =>
              s.type === "ins"
                ? `[+${s.text}+]`
                : s.type === "del"
                  ? `[-${s.text}-]`
                  : s.text,
            )
            .join("")
        : stubDraftText(req, iteration);
    return new Blob([text], { type: "text/plain;charset=utf-8" });
  }
  const headers = await authHeaders();
  const res = await fetch(
    `${API_URL}${apiPaths.documentDownload(id, type, iteration)}`,
    { headers },
  );
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
}

/** Safe HTML rendering of a document version for the in-browser viewer.
 * `iteration` selects an older refinement version; latest when omitted. */
export async function getDocumentHtml(
  id: string,
  type: DocumentVersionType,
  iteration?: number,
): Promise<DocumentHtml> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    return stubDocumentHtml(req, type, iteration);
  }
  return apiFetch<DocumentHtml>(apiPaths.documentHtml(id, type, iteration));
}

/* ------------------------------------------------------------------ */
/* Internal critic review trail + drafting branch (drafting-agents)    */
/* ------------------------------------------------------------------ */

interface ReviewIssueWire {
  severity: ReviewIssue["severity"];
  category: ReviewIssue["category"];
  problem: string;
  suggested_fix?: string | null;
  location?: string | null;
  citation?: { where?: string | null; quote?: string | null } | null;
}

interface GenerationReviewWire {
  round: number;
  approved: boolean;
  issues: ReviewIssueWire[];
  created_at?: string | null;
}

function mapReviewIssue(wire: ReviewIssueWire): ReviewIssue {
  const citation =
    wire.citation && (wire.citation.where || wire.citation.quote)
      ? {
          where: wire.citation.where ?? "",
          quote: wire.citation.quote ?? "",
        }
      : undefined;
  return {
    severity: wire.severity,
    category: wire.category,
    problem: wire.problem,
    suggestedFix: wire.suggested_fix ?? undefined,
    location: wire.location ?? undefined,
    citation,
  };
}

/** The critic review trail for a request (one entry per round). Empty when
 * the critic was skipped (LLM unreachable / disabled). */
export async function getRequestReviews(
  id: string,
): Promise<GenerationReview[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubRequestReviews(id);
  }
  const rows = await apiFetch<GenerationReviewWire[]>(apiPaths.requestReviews(id));
  return rows.map((r) => ({
    round: r.round,
    approved: r.approved,
    issues: (r.issues ?? []).map(mapReviewIssue),
    createdAt: r.created_at ?? null,
  }));
}

/** The specialized drafting branch used for a request. */
export async function getRequestBranch(id: string): Promise<Branch> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 4);
    return stubRequestBranch(id);
  }
  const res = await apiFetch<{ doc_type: string; branch: Branch }>(
    apiPaths.requestBranch(id),
  );
  return res.branch;
}

/* ------------------------------------------------------------------ */
/* Counsel                                                             */
/* ------------------------------------------------------------------ */

export async function getCounselQueue(): Promise<RequestItem[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubRequests.filter((r) => r.status === "counsel_review");
  }
  return apiFetch<RequestItem[]>(apiPaths.counselQueue);
}

export async function getReviewBundle(id: string): Promise<ReviewBundle> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    return stubReviewBundle(req);
  }
  return apiFetch<ReviewBundle>(apiPaths.reviewBundle(id));
}

export async function saveCounselEdit(
  id: string,
  text: string,
): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    // Stub: counsel_edit version is kept server-side in the real backend.
    return;
  }
  await apiFetch(apiPaths.counselEdit(id), { method: "POST", body: { text } });
}

export async function uploadCounselDocx(
  id: string,
  file: File,
): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    return;
  }
  // TODO: multipart upload to the backend once the endpoint exists.
  const headers = await authHeaders();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}${apiPaths.counselUpload(id)}`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
}

export async function addComment(
  id: string,
  text: string,
): Promise<CounselComment> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubAddComment(id, "María Llopis", text);
  }
  return apiFetch<CounselComment>(apiPaths.comments(id), {
    method: "POST",
    body: { text },
  });
}

export async function validateRequest(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    // Counsel-validated docs enter the precedent library automatically.
    req.status = "delivered";
    // SLA clock stops now (counsel response metrics).
    req.counselValidatedAt = nowIso();
    req.updatedAt = nowIso();
    return req;
  }
  return apiFetch<RequestItem>(apiPaths.validate(id), { method: "POST" });
}

/** The requesting client's gestora's assigned counsel, or null when none. */
export async function getAssignedCounsel(): Promise<AssignedCounsel | null> {
  if (isStubMode()) {
    return STUB_ASSIGNED_COUNSEL;
  }
  const res = await apiFetch<{
    name: string;
    email: string;
    is_primary: boolean;
    turnaround_hours: number;
  } | null>(apiPaths.myCounsel);
  if (!res) return null;
  return {
    name: res.name,
    email: res.email,
    isPrimary: res.is_primary,
    turnaroundHours: res.turnaround_hours,
  };
}

/* ------------------------------------------------------------------ */
/* Reference data / admin                                              */
/* ------------------------------------------------------------------ */

export async function getFunds(): Promise<Fund[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return STUB_FUNDS;
  }
  return apiFetch<Fund[]>(apiPaths.funds);
}

export async function getGestoras(): Promise<Gestora[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return [...stubGestoras];
  }
  return apiFetch<Gestora[]>(apiPaths.gestoras);
}

export async function createGestora(input: {
  name: string;
  subscriptionTier: SubscriptionTier;
  billingEmail: string;
}): Promise<Gestora> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    const gestora: Gestora = {
      id: `g-${Date.now()}`,
      name: input.name,
      driveFolderId: null,
      subscriptionTier: input.subscriptionTier,
      billingEmail: input.billingEmail,
      createdAt: nowIso(),
    };
    stubGestoras.push(gestora);
    return gestora;
  }
  return apiFetch<Gestora>(apiPaths.gestoras, { method: "POST", body: input });
}

export async function getPrecedents(): Promise<Precedent[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return [...stubPrecedents];
  }
  return apiFetch<Precedent[]>(apiPaths.precedents);
}

export async function uploadPrecedent(input: {
  gestoraId: string;
  docType: string;
  language: string;
  file: File;
}): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    stubPrecedents.push({
      id: `p-${Date.now()}`,
      gestoraId: input.gestoraId,
      fundId: null,
      docType: input.docType,
      docTypeLabel: docTypeLabel(input.docType),
      language: input.language as Precedent["language"],
      source: "manual_upload",
      createdAt: nowIso(),
      versions: [
        {
          id: `pv-${Date.now()}`,
          precedentId: `p-${Date.now()}`,
          versionNumber: 1,
          filePath: `/gestoras/${input.gestoraId}/precedents/${input.file.name}`,
          status: "draft",
          ragWeight: 1.0,
          createdBy: "u-admin-1",
        },
      ],
    });
    return;
  }
  // TODO: multipart upload to the backend once the endpoint exists.
  const headers = await authHeaders();
  const form = new FormData();
  form.append("gestora_id", input.gestoraId);
  form.append("doc_type", input.docType);
  form.append("language", input.language);
  form.append("file", input.file);
  const res = await fetch(`${API_URL}${apiPaths.precedents}`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
}

export async function activatePrecedentVersion(
  precedentId: string,
  versionId: string,
): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const precedent = stubPrecedents.find((p) => p.id === precedentId);
    if (!precedent) return;
    for (const v of precedent.versions) {
      if (v.id === versionId) {
        v.status = "active";
        v.ragWeight = 1.0;
        v.activatedAt = nowIso();
      } else if (v.status === "active") {
        v.status = "superseded";
        v.ragWeight = 0.3;
        v.supersededAt = nowIso();
      }
    }
    return;
  }
  await apiFetch(apiPaths.precedentVersionActivate(precedentId, versionId), {
    method: "POST",
  });
}

export async function supersedePrecedentVersion(
  precedentId: string,
  versionId: string,
): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const precedent = stubPrecedents.find((p) => p.id === precedentId);
    const version = precedent?.versions.find((v) => v.id === versionId);
    if (version) {
      version.status = "superseded";
      version.ragWeight = 0.3;
      version.supersededAt = nowIso();
    }
    return;
  }
  await apiFetch(apiPaths.precedentVersionSupersede(precedentId, versionId), {
    method: "POST",
  });
}

/* ------------------------------------------------------------------ */
/* Gestora master templates (modelos/) — source=gestora_model           */
/* ------------------------------------------------------------------ */

/**
 * Uploads a gestora MASTER TEMPLATE (precedent with source=gestora_model,
 * stored under modelos/). Reuses the precedents upload flow with the model
 * source; versioned/activated exactly like a precedent.
 */
export async function uploadModel(input: {
  gestoraId: string;
  docType: string;
  language: string;
  file: File;
}): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    stubUploadModel(input);
    return;
  }
  const headers = await authHeaders();
  const form = new FormData();
  form.append("gestora_id", input.gestoraId);
  form.append("doc_type", input.docType);
  form.append("language", input.language);
  form.append("source", "gestora_model");
  form.append("file", input.file);
  const res = await fetch(`${API_URL}${apiPaths.precedents}`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
}

/* ------------------------------------------------------------------ */
/* Review playbooks CRUD (admin) — gestora-siloed critic rules          */
/* ------------------------------------------------------------------ */

interface ReviewPlaybookWire {
  id: string;
  gestora_id: string;
  branch?: string | null;
  doc_type?: string | null;
  title: string;
  content: string;
  file_path?: string | null;
  is_active: boolean;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

function mapPlaybook(wire: ReviewPlaybookWire): ReviewPlaybook {
  return {
    id: wire.id,
    gestoraId: wire.gestora_id,
    branch: (wire.branch ?? null) as ReviewPlaybook["branch"],
    docType: wire.doc_type ?? null,
    title: wire.title,
    content: wire.content,
    filePath: wire.file_path ?? null,
    isActive: wire.is_active,
    createdBy: wire.created_by ?? null,
    createdAt: wire.created_at ?? null,
    updatedAt: wire.updated_at ?? null,
  };
}

/** Lists review playbooks for a gestora (admin/counsel cross-gestora). */
export async function getPlaybooks(
  gestoraId: string,
): Promise<ReviewPlaybook[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubPlaybooks(gestoraId);
  }
  const rows = await apiFetch<ReviewPlaybookWire[]>(apiPaths.playbooks(gestoraId));
  return rows.map(mapPlaybook);
}

/** Creates a playbook (multipart: text fields + optional file attachment). */
export async function createPlaybook(input: {
  gestoraId: string;
  title: string;
  content: string;
  branch?: string | null;
  docType?: string | null;
  file?: File | null;
}): Promise<ReviewPlaybook> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubCreatePlaybook(input);
  }
  const headers = await authHeaders();
  const form = new FormData();
  form.append("gestora_id", input.gestoraId);
  form.append("title", input.title);
  form.append("content", input.content);
  if (input.branch) form.append("branch", input.branch);
  if (input.docType) form.append("doc_type", input.docType);
  if (input.file) form.append("file", input.file);
  const res = await fetch(`${API_URL}${apiPaths.playbooks()}`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return mapPlaybook((await res.json()) as ReviewPlaybookWire);
}

/** Partial update of a playbook (title / content / scope). */
export async function updatePlaybook(
  id: string,
  fields: {
    title?: string;
    content?: string;
    branch?: string | null;
    docType?: string | null;
  },
): Promise<ReviewPlaybook> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubUpdatePlaybook(id, fields);
  }
  const body: Record<string, unknown> = {};
  if (fields.title !== undefined) body.title = fields.title;
  if (fields.content !== undefined) body.content = fields.content;
  if (fields.branch !== undefined) body.branch = fields.branch;
  if (fields.docType !== undefined) body.doc_type = fields.docType;
  const wire = await apiFetch<ReviewPlaybookWire>(apiPaths.playbook(id), {
    method: "PATCH",
    body,
  });
  return mapPlaybook(wire);
}

/** Activates or deactivates a playbook. */
export async function setPlaybookActive(
  id: string,
  active: boolean,
): Promise<ReviewPlaybook> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubSetPlaybookActive(id, active);
  }
  const wire = await apiFetch<ReviewPlaybookWire>(
    active ? apiPaths.playbookActivate(id) : apiPaths.playbookDeactivate(id),
    { method: "POST" },
  );
  return mapPlaybook(wire);
}

export async function deletePlaybook(id: string): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    stubDeletePlaybook(id);
    return;
  }
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${apiPaths.playbook(id)}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
}

/* ------------------------------------------------------------------ */
/* Drafting lessons (admin-only, gestora-siloed)                       */
/* ------------------------------------------------------------------ */

interface DraftingLessonWire {
  id: string;
  gestora_id: string;
  branch: Branch;
  doc_type?: string | null;
  lesson: string;
  weight: number;
  created_at?: string | null;
}

/** The accumulated drafting lessons learned for one gestora (admin-only).
 * Optional branch filter. */
export async function getGestoraLessons(
  gestoraId: string,
  branch?: string,
): Promise<DraftingLesson[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubGestoraLessons(gestoraId, branch);
  }
  const rows = await apiFetch<DraftingLessonWire[]>(
    apiPaths.gestoraLessons(gestoraId, branch),
  );
  return rows.map((r) => ({
    id: r.id,
    gestoraId: r.gestora_id,
    branch: r.branch,
    docType: r.doc_type ?? null,
    lesson: r.lesson,
    weight: r.weight,
    createdAt: r.created_at ?? null,
  }));
}

export async function getUsers(): Promise<UserProfile[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return STUB_ALL_USERS;
  }
  return apiFetch<UserProfile[]>(apiPaths.users);
}

export async function inviteUser(input: {
  email: string;
  role: Role;
  gestoraId: string | null;
}): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    STUB_ALL_USERS.push({
      id: `u-${Date.now()}`,
      email: input.email,
      role: input.role,
      gestoraId: input.gestoraId,
    });
    return;
  }
  await apiFetch(apiPaths.users, { method: "POST", body: input });
}

/* ------------------------------------------------------------------ */
/* Counsel assignments (admin)                                         */
/* ------------------------------------------------------------------ */

interface CounselAssignmentWire {
  id: string;
  gestora_id: string;
  counsel_user_id: string;
  is_primary: boolean;
  counsel_email?: string | null;
  created_at?: string;
}

function mapCounselAssignment(wire: CounselAssignmentWire): CounselAssignment {
  return {
    id: wire.id,
    gestoraId: wire.gestora_id,
    counselUserId: wire.counsel_user_id,
    isPrimary: wire.is_primary,
    counselEmail: wire.counsel_email ?? null,
    createdAt: wire.created_at ?? "",
  };
}

export async function getCounselAssignments(
  gestoraId: string,
): Promise<CounselAssignment[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubCounselAssignments.filter((a) => a.gestoraId === gestoraId);
  }
  const rows = await apiFetch<CounselAssignmentWire[]>(
    apiPaths.counselAssignments(gestoraId),
  );
  return rows.map(mapCounselAssignment);
}

/** Assigns counsel to a gestora; a new primary demotes the previous one. */
export async function assignCounsel(input: {
  gestoraId: string;
  counselUserId: string;
  isPrimary: boolean;
}): Promise<CounselAssignment> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    if (input.isPrimary) {
      for (const a of stubCounselAssignments) {
        if (a.gestoraId === input.gestoraId) a.isPrimary = false;
      }
    }
    const existing = stubCounselAssignments.find(
      (a) =>
        a.gestoraId === input.gestoraId &&
        a.counselUserId === input.counselUserId,
    );
    if (existing) {
      existing.isPrimary = input.isPrimary;
      return { ...existing };
    }
    const counsel = STUB_ALL_USERS.find((u) => u.id === input.counselUserId);
    if (!counsel || counsel.role !== "counsel") {
      throw new ApiError(422, "Assigned user must have role 'counsel'");
    }
    const assignment: CounselAssignment = {
      id: `ca-${Date.now()}`,
      gestoraId: input.gestoraId,
      counselUserId: input.counselUserId,
      counselEmail: counsel.email,
      isPrimary: input.isPrimary,
      createdAt: nowIso(),
    };
    stubCounselAssignments.push(assignment);
    return assignment;
  }
  const row = await apiFetch<CounselAssignmentWire>(
    apiPaths.counselAssignmentCreate,
    {
      method: "POST",
      body: {
        gestora_id: input.gestoraId,
        counsel_user_id: input.counselUserId,
        is_primary: input.isPrimary,
      },
    },
  );
  return mapCounselAssignment(row);
}

export async function removeCounselAssignment(id: string): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const index = stubCounselAssignments.findIndex((a) => a.id === id);
    if (index >= 0) stubCounselAssignments.splice(index, 1);
    return;
  }
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${apiPaths.counselAssignment(id)}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
}

/* ------------------------------------------------------------------ */
/* Admin KPIs: quality (improvement #6) + counsel SLA (improvement #8)  */
/* ------------------------------------------------------------------ */

interface QualityStatsWire {
  count: number;
  avg_similarity: number | null;
  avg_refinements: number | null;
  pct_accepted_as_is: number | null;
  pct_validated: number | null;
}

function mapQualityStats(wire: QualityStatsWire): QualityStats {
  return {
    count: wire.count,
    avgSimilarity: wire.avg_similarity,
    avgRefinements: wire.avg_refinements,
    pctAcceptedAsIs: wire.pct_accepted_as_is,
    pctValidated: wire.pct_validated,
  };
}

/** Aggregated quality stats (admin-only). */
export async function getQualityReport(): Promise<QualityReport> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return STUB_QUALITY_REPORT;
  }
  const res = await apiFetch<{
    overall: QualityStatsWire;
    by_doc_type: Array<QualityStatsWire & { doc_type: string }>;
    by_gestora: Array<
      QualityStatsWire & { gestora_id: string; gestora_name?: string | null }
    >;
  }>(apiPaths.adminQuality);
  return {
    overall: mapQualityStats(res.overall),
    byDocType: res.by_doc_type.map((r) => ({
      docType: r.doc_type,
      ...mapQualityStats(r),
    })),
    byGestora: res.by_gestora.map((r) => ({
      gestoraId: r.gestora_id,
      gestoraName: r.gestora_name ?? null,
      ...mapQualityStats(r),
    })),
  };
}

interface SlaStatsWire {
  pending: number;
  past_sla: number;
  avg_validation_hours: number | null;
  reminders_sent: number;
  escalations_sent: number;
}

function mapSlaStats(wire: SlaStatsWire): SlaStats {
  return {
    pending: wire.pending,
    pastSla: wire.past_sla,
    avgValidationHours: wire.avg_validation_hours,
    remindersSent: wire.reminders_sent,
    escalationsSent: wire.escalations_sent,
  };
}

/** Counsel response metrics (admin-only). */
export async function getSlaReport(): Promise<SlaReport> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return STUB_SLA_REPORT;
  }
  const res = await apiFetch<{
    sla_hours: number;
    overall: SlaStatsWire;
    by_counsel: Array<SlaStatsWire & { counsel_email: string }>;
  }>(apiPaths.adminSla);
  return {
    slaHours: res.sla_hours,
    overall: mapSlaStats(res.overall),
    byCounsel: res.by_counsel.map((r) => ({
      counselEmail: r.counsel_email,
      ...mapSlaStats(r),
    })),
  };
}

/* ------------------------------------------------------------------ */
/* Billing over usage_events (improvement #7)                          */
/* ------------------------------------------------------------------ */

interface BillingRowWire {
  gestora_id: string;
  gestora_name?: string | null;
  subscription_tier: BillingRow["subscriptionTier"];
  docs_generated: number;
  docs_limit: number | null;
  overage_docs: number;
  exit_a_count: number;
  exit_b_requested: number;
  exit_b_validated: number;
  fund_count: number;
  funds_limit: number | null;
  over_funds_limit: boolean;
  estimated_overage_eur: number;
}

function mapBillingRow(wire: BillingRowWire): BillingRow {
  return {
    gestoraId: wire.gestora_id,
    gestoraName: wire.gestora_name ?? null,
    subscriptionTier: wire.subscription_tier,
    docsGenerated: wire.docs_generated,
    docsLimit: wire.docs_limit,
    overageDocs: wire.overage_docs,
    exitACount: wire.exit_a_count,
    exitBRequested: wire.exit_b_requested,
    exitBValidated: wire.exit_b_validated,
    fundCount: wire.fund_count,
    fundsLimit: wire.funds_limit,
    overFundsLimit: wire.over_funds_limit,
    estimatedOverageEur: wire.estimated_overage_eur,
  };
}

/** Per-gestora billing report for one period (admin-only; default current). */
export async function getBillingReport(period?: string): Promise<BillingReport> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubBillingReport(period);
  }
  const res = await apiFetch<{ period: string; rows: BillingRowWire[] }>(
    apiPaths.adminBilling(period),
  );
  return { period: res.period, rows: res.rows.map(mapBillingRow) };
}

/** Distinct billing periods in usage_events, newest first (admin-only). */
export async function getBillingPeriods(): Promise<string[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubBillingPeriods();
  }
  const res = await apiFetch<{ periods: string[] }>(apiPaths.adminBillingPeriods);
  return res.periods;
}

/** CSV export of the billing report as a Blob (admin-only). */
export async function downloadBillingCsv(period?: string): Promise<Blob> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return new Blob([stubBillingCsv(period)], { type: "text/csv;charset=utf-8" });
  }
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${apiPaths.adminBillingExport(period)}`, {
    headers,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
}

/* ------------------------------------------------------------------ */
/* GDPR data retention (improvement #10)                               */
/* ------------------------------------------------------------------ */

interface RetentionPolicyWire {
  gestora_id: string;
  months: number;
  is_default: boolean;
  updated_at?: string | null;
}

function mapRetentionPolicy(wire: RetentionPolicyWire): RetentionPolicy {
  return {
    gestoraId: wire.gestora_id,
    months: wire.months,
    isDefault: wire.is_default,
    updatedAt: wire.updated_at ?? null,
  };
}

/** The gestora's retention policy (platform default when none set). Admin-only. */
export async function getRetentionPolicy(
  gestoraId: string,
): Promise<RetentionPolicy> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubGetRetentionPolicy(gestoraId);
  }
  const res = await apiFetch<RetentionPolicyWire>(
    apiPaths.adminRetention(gestoraId),
  );
  return mapRetentionPolicy(res);
}

/** Upserts the gestora's retention policy (months, 6-120). Admin-only. */
export async function updateRetentionPolicy(
  gestoraId: string,
  months: number,
): Promise<RetentionPolicy> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubPutRetentionPolicy(gestoraId, months);
  }
  const res = await apiFetch<RetentionPolicyWire>(
    apiPaths.adminRetention(gestoraId),
    { method: "PUT", body: { months } },
  );
  return mapRetentionPolicy(res);
}

/** The client's own gestora consumption for the current period. */
export async function getMyUsage(): Promise<MyUsage> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubMyUsage();
  }
  const res = await apiFetch<{
    billing_period: string;
    subscription_tier: MyUsage["subscriptionTier"];
    docs_generated: number;
    docs_limit: number | null;
  }>(apiPaths.myUsage);
  return {
    billingPeriod: res.billing_period,
    subscriptionTier: res.subscription_tier,
    docsGenerated: res.docs_generated,
    docsLimit: res.docs_limit,
  };
}

/* ------------------------------------------------------------------ */
/* Tabular Review (010_tabular_reviews.sql) — gestora-siloed grid        */
/* ------------------------------------------------------------------ */

interface TabularColumnWire {
  id: string;
  review_id: string;
  position: number;
  name: string;
  question: string;
  col_type: TabularReviewDetail["columns"][number]["colType"];
  options?: string[] | null;
}

interface TabularDocumentWire {
  id: string;
  review_id: string;
  position: number;
  source_kind: TabularDocumentOption["sourceKind"];
  source_id: string;
  label?: string | null;
}

interface TabularCellWire {
  id: string;
  document_id: string;
  column_id: string;
  value?: string | null;
  reasoning?: string | null;
  citation?: { page: number | string | null; quote: string | null } | null;
  status: TabularReviewDetail["cells"][number]["status"];
  error?: string | null;
}

interface TabularReviewWire {
  id: string;
  gestora_id: string;
  fund_id?: string | null;
  created_by?: string | null;
  title: string;
  status: TabularReview["status"];
  // Collaboration (012_collaboration.sql): per-caller ownership/sharing flags.
  is_owner?: boolean | null;
  shared_with_me?: boolean | null;
  shared_by_email?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

interface TabularReviewDetailWire extends TabularReviewWire {
  columns: TabularColumnWire[];
  documents: TabularDocumentWire[];
  cells: TabularCellWire[];
}

function mapTabularReview(wire: TabularReviewWire): TabularReview {
  return {
    id: wire.id,
    gestoraId: wire.gestora_id,
    fundId: wire.fund_id ?? null,
    createdBy: wire.created_by ?? null,
    title: wire.title,
    status: wire.status,
    isOwner: wire.is_owner ?? null,
    sharedWithMe: wire.shared_with_me ?? null,
    sharedByEmail: wire.shared_by_email ?? null,
    createdAt: wire.created_at ?? null,
    updatedAt: wire.updated_at ?? null,
  };
}

function mapTabularDetail(wire: TabularReviewDetailWire): TabularReviewDetail {
  return {
    ...mapTabularReview(wire),
    columns: wire.columns.map((c) => ({
      id: c.id,
      reviewId: c.review_id,
      position: c.position,
      name: c.name,
      question: c.question,
      colType: c.col_type,
      options: c.options ?? null,
    })),
    documents: wire.documents.map((d) => ({
      id: d.id,
      reviewId: d.review_id,
      position: d.position,
      sourceKind: d.source_kind,
      sourceId: d.source_id,
      label: d.label ?? null,
    })),
    cells: wire.cells.map((c) => ({
      id: c.id,
      documentId: c.document_id,
      columnId: c.column_id,
      value: c.value ?? null,
      reasoning: c.reasoning ?? null,
      citation: c.citation ?? null,
      status: c.status,
      error: c.error ?? null,
    })),
  };
}

export async function getTabularReviews(): Promise<TabularReview[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubTabularReviews();
  }
  const rows = await apiFetch<TabularReviewWire[]>(apiPaths.tabularReviews);
  return rows.map(mapTabularReview);
}

export async function getTabularReview(
  id: string,
): Promise<TabularReviewDetail> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const review = stubTabularReview(id);
    if (!review) throw new ApiError(404, "Tabular review not found");
    return review;
  }
  const wire = await apiFetch<TabularReviewDetailWire>(apiPaths.tabularReview(id));
  return mapTabularDetail(wire);
}

export interface CreateTabularReviewInput {
  title: string;
  fundId?: string | null;
  columns: TabularColumnInput[];
  documents: TabularDocumentOption[];
}

export async function createTabularReview(
  input: CreateTabularReviewInput,
): Promise<TabularReviewDetail> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    return stubCreateTabularReview(input);
  }
  const wire = await apiFetch<TabularReviewDetailWire>(apiPaths.tabularReviews, {
    method: "POST",
    body: {
      title: input.title,
      fund_id: input.fundId ?? null,
      columns: input.columns.map((c) => ({
        name: c.name,
        question: c.question,
        col_type: c.colType,
        options: c.options ?? null,
      })),
      documents: input.documents.map((d) => ({
        source_kind: d.sourceKind,
        source_id: d.sourceId,
        label: d.label,
      })),
    },
  });
  return mapTabularDetail(wire);
}

/** Enqueues extraction (202): poll getTabularReviewStatus while 'running'. */
export async function runTabularReview(id: string): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    stubRunTabularReview(id);
    return;
  }
  await apiFetch(apiPaths.tabularReviewRun(id), { method: "POST" });
}

export async function getTabularReviewStatus(
  id: string,
): Promise<TabularReviewStatusInfo> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 4);
    return stubTabularReviewStatus(id);
  }
  const res = await apiFetch<{
    id: string;
    status: TabularReviewStatusInfo["status"];
    cell_total: number;
    cell_done: number;
    cell_error: number;
  }>(apiPaths.tabularReviewStatus(id));
  return {
    id: res.id,
    status: res.status,
    cellTotal: res.cell_total,
    cellDone: res.cell_done,
    cellError: res.cell_error,
  };
}

export async function addTabularColumn(
  id: string,
  column: TabularColumnInput,
): Promise<TabularReviewDetail> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubAddTabularColumn(id, column);
  }
  const wire = await apiFetch<TabularReviewDetailWire>(
    apiPaths.tabularReviewColumns(id),
    {
      method: "POST",
      body: {
        name: column.name,
        question: column.question,
        col_type: column.colType,
        options: column.options ?? null,
      },
    },
  );
  return mapTabularDetail(wire);
}

export async function deleteTabularColumn(
  id: string,
  columnId: string,
): Promise<TabularReviewDetail> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubDeleteTabularColumn(id, columnId);
  }
  const wire = await apiFetch<TabularReviewDetailWire>(
    apiPaths.tabularReviewColumn(id, columnId),
    { method: "DELETE" },
  );
  return mapTabularDetail(wire);
}

export async function deleteTabularDocument(
  id: string,
  documentId: string,
): Promise<TabularReviewDetail> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubDeleteTabularDocument(id, documentId);
  }
  const wire = await apiFetch<TabularReviewDetailWire>(
    apiPaths.tabularReviewDocument(id, documentId),
    { method: "DELETE" },
  );
  return mapTabularDetail(wire);
}

/** CSV export of the grid (values only) as a Blob. */
export async function downloadTabularReviewCsv(id: string): Promise<Blob> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return new Blob([stubTabularReviewCsv(id)], {
      type: "text/csv;charset=utf-8",
    });
  }
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${apiPaths.tabularReviewExport(id)}`, {
    headers,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
}

/** Documents the user can pick into a new review (precedents + generated). */
export async function getTabularDocumentOptions(): Promise<
  TabularDocumentOption[]
> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubTabularDocumentOptions();
  }
  // Reuse the precedents list as the picker source; each active version is one
  // selectable document. Generated documents can be added later via the same
  // shape (source_kind=request_document).
  const precedents = await apiFetch<
    Array<{
      id: string;
      doc_type: string;
      versions?: Array<{ id: string; status: string; version_number: number }>;
    }>
  >(apiPaths.precedents);
  const options: TabularDocumentOption[] = [];
  for (const p of precedents) {
    for (const v of p.versions ?? []) {
      options.push({
        sourceKind: "precedent_version",
        sourceId: v.id,
        label: `${docTypeLabel(p.doc_type)} v${v.version_number}`,
      });
    }
  }
  return options;
}

/* ------------------------------------------------------------------ */
/* Account & security (011_account_security.sql)                        */
/* ------------------------------------------------------------------ */

interface AccountProfileWire {
  id: string;
  email: string;
  role: AccountProfile["role"];
  gestora_id?: string | null;
  mfa_enabled: boolean;
}

function mapAccountProfile(wire: AccountProfileWire): AccountProfile {
  return {
    id: wire.id,
    email: wire.email,
    role: wire.role,
    gestoraId: wire.gestora_id ?? null,
    mfaEnabled: wire.mfa_enabled,
  };
}

/** The calling user's own profile, incl. the MFA status mirror. */
export async function getMyProfile(): Promise<AccountProfile> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubAccountProfile();
  }
  return mapAccountProfile(await apiFetch<AccountProfileWire>(apiPaths.me));
}

/** Mirrors the user's Supabase TOTP status onto the backend (display/overview).
 * Supabase Auth enforces the actual factor; this only reflects it. */
export async function setMyMfaEnabled(
  enabled: boolean,
): Promise<AccountProfile> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubSetMfaEnabled(enabled);
  }
  return mapAccountProfile(
    await apiFetch<AccountProfileWire>(apiPaths.meMfa, {
      method: "POST",
      body: { enabled },
    }),
  );
}

/** Downloads the requesting user's own data export (Art. 15/20) as a Blob. */
export async function exportMyData(): Promise<Blob> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    return new Blob([stubExportMyData()], {
      type: "application/json;charset=utf-8",
    });
  }
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${apiPaths.meExport}`, { headers });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
}

/** Self-service erasure/anonymisation (Art. 17). Confirmation phrase required. */
export async function deleteMyData(input: {
  confirm: string;
  mode: DeleteMode;
}): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY);
    stubDeleteMyData(input);
    return;
  }
  await apiFetch(apiPaths.meDelete, { method: "POST", body: input });
}

/* ------------------------------------------------------------------ */
/* Per-gestora model configuration (admin-only, BYO keys)              */
/* ------------------------------------------------------------------ */

interface ModelConfigWire {
  gestora_id: string;
  llm_provider?: string | null;
  llm_model?: string | null;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  ollama_base_url?: string | null;
  anthropic_key_set: boolean;
  openai_key_set: boolean;
  is_default: boolean;
  updated_at?: string | null;
}

function mapModelConfig(wire: ModelConfigWire): ModelConfig {
  return {
    gestoraId: wire.gestora_id,
    llmProvider: wire.llm_provider ?? null,
    llmModel: wire.llm_model ?? null,
    embeddingProvider: wire.embedding_provider ?? null,
    embeddingModel: wire.embedding_model ?? null,
    ollamaBaseUrl: wire.ollama_base_url ?? null,
    anthropicKeySet: wire.anthropic_key_set,
    openaiKeySet: wire.openai_key_set,
    isDefault: wire.is_default,
    updatedAt: wire.updated_at ?? null,
  };
}

/** The gestora's model-config override (platform default when none). Admin-only.
 * Never returns decrypted keys — only *_key_set booleans. */
export async function getModelConfig(
  gestoraId: string,
): Promise<ModelConfig> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubGetModelConfig(gestoraId);
  }
  return mapModelConfig(
    await apiFetch<ModelConfigWire>(apiPaths.adminModelConfig(gestoraId)),
  );
}

/** Upserts the gestora's model config. Key fields are write-only: a non-empty
 * string sets (encrypted at rest), "" clears, undefined leaves unchanged. */
export async function updateModelConfig(
  gestoraId: string,
  input: {
    llmProvider?: string;
    llmModel?: string;
    embeddingProvider?: string;
    embeddingModel?: string;
    ollamaBaseUrl?: string;
    anthropicApiKey?: string;
    openaiApiKey?: string;
  },
): Promise<ModelConfig> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubPutModelConfig(gestoraId, input);
  }
  const body: Record<string, unknown> = {};
  if (input.llmProvider !== undefined) body.llm_provider = input.llmProvider;
  if (input.llmModel !== undefined) body.llm_model = input.llmModel;
  if (input.embeddingProvider !== undefined)
    body.embedding_provider = input.embeddingProvider;
  if (input.embeddingModel !== undefined)
    body.embedding_model = input.embeddingModel;
  if (input.ollamaBaseUrl !== undefined)
    body.ollama_base_url = input.ollamaBaseUrl;
  if (input.anthropicApiKey !== undefined)
    body.anthropic_api_key = input.anthropicApiKey;
  if (input.openaiApiKey !== undefined) body.openai_api_key = input.openaiApiKey;
  return mapModelConfig(
    await apiFetch<ModelConfigWire>(apiPaths.adminModelConfig(gestoraId), {
      method: "PUT",
      body,
    }),
  );
}

/* ------------------------------------------------------------------ */
/* Collaboration / sharing (012_collaboration.sql) — single-gestora     */
/* ------------------------------------------------------------------ */

interface ColleagueWire {
  id: string;
  email: string;
  name: string;
}

interface ShareWire {
  id: string;
  gestora_id: string;
  shared_with_user_id: string;
  shared_with_email?: string | null;
  shared_with_name?: string | null;
  shared_by: string;
  shared_by_email?: string | null;
  created_at?: string | null;
}

function mapShare(wire: ShareWire): Share {
  return {
    id: wire.id,
    gestoraId: wire.gestora_id,
    sharedWithUserId: wire.shared_with_user_id,
    sharedWithEmail: wire.shared_with_email ?? null,
    sharedWithName: wire.shared_with_name ?? null,
    sharedBy: wire.shared_by,
    sharedByEmail: wire.shared_by_email ?? null,
    createdAt: wire.created_at ?? null,
  };
}

/** Same-gestora client colleagues for the share picker (excludes the caller). */
export async function getColleagues(): Promise<Colleague[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubColleagues();
  }
  const rows = await apiFetch<ColleagueWire[]>(apiPaths.colleagues);
  return rows.map((c) => ({ id: c.id, email: c.email, name: c.name }));
}

/** Collaborators on a request (owner + collaborators may view). */
export async function getRequestShares(id: string): Promise<Share[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubRequestShares(id);
  }
  const rows = await apiFetch<ShareWire[]>(apiPaths.requestShares(id));
  return rows.map(mapShare);
}

/** Shares a request with a same-gestora colleague (owner only; idempotent). */
export async function createRequestShare(
  id: string,
  userId: string,
): Promise<Share> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubCreateRequestShare(id, userId);
  }
  return mapShare(
    await apiFetch<ShareWire>(apiPaths.requestShares(id), {
      method: "POST",
      body: { user_id: userId },
    }),
  );
}

/** Revokes a colleague's access to a request (owner only). */
export async function deleteRequestShare(
  id: string,
  userId: string,
): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    stubDeleteRequestShare(id, userId);
    return;
  }
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${apiPaths.requestShare(id, userId)}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
}

/** Collaborators on a tabular review (owner + collaborators may view). */
export async function getReviewShares(id: string): Promise<Share[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    return stubReviewShares(id);
  }
  const rows = await apiFetch<ShareWire[]>(apiPaths.reviewShares(id));
  return rows.map(mapShare);
}

/** Shares a tabular review with a same-gestora colleague (owner only). */
export async function createReviewShare(
  id: string,
  userId: string,
): Promise<Share> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return stubCreateReviewShare(id, userId);
  }
  return mapShare(
    await apiFetch<ShareWire>(apiPaths.reviewShares(id), {
      method: "POST",
      body: { user_id: userId },
    }),
  );
}

/** Revokes a colleague's access to a tabular review (owner only). */
export async function deleteReviewShare(
  id: string,
  userId: string,
): Promise<void> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 3);
    stubDeleteReviewShare(id, userId);
    return;
  }
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${apiPaths.reviewShare(id, userId)}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
}

/** Triggers a browser download for a Blob. */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
