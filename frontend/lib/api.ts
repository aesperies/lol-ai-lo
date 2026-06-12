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
  delay,
  findRequest,
  nextRequestId,
  nowIso,
  stubAddComment,
  stubCounselAssignments,
  stubDocumentHtml,
  stubDraftText,
  stubGestoras,
  stubParse,
  stubPollGenerationJob,
  stubPrecedents,
  stubRedline,
  stubRefinements,
  stubRequests,
  stubReviewBundle,
  stubStartGenerationJob,
  stubStartRefinement,
} from "@/lib/stub-data";
import {
  getSupabaseBrowserClient,
  isStubMode,
  readDevRoleCookie,
} from "@/lib/supabase/client";
import type {
  AssignedCounsel,
  CounselAssignment,
  CounselComment,
  DocumentHtml,
  DocumentVersionType,
  Fund,
  GenerationJob,
  GenerationJobStatus,
  Gestora,
  ParsedParams,
  Precedent,
  RedlineSegment,
  Refinement,
  RefinementStatus,
  RequestItem,
  ReviewBundle,
  Role,
  SubscriptionTier,
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
    body: input,
  });
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
    req.updatedAt = nowIso();
    return req;
  }
  return apiFetch<RequestItem>(apiPaths.exitB(id), { method: "POST" });
}

export async function getRequests(): Promise<RequestItem[]> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    return [...stubRequests];
  }
  return apiFetch<RequestItem[]>(apiPaths.requests);
}

export async function getRequest(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    return req;
  }
  return apiFetch<RequestItem>(apiPaths.request(id));
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
