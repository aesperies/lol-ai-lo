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
  stubDraftText,
  stubFallbackLevel,
  stubGestoras,
  stubHasMissing,
  stubParse,
  stubPrecedents,
  stubRedline,
  stubRequests,
  stubReviewBundle,
} from "@/lib/stub-data";
import {
  getSupabaseBrowserClient,
  isStubMode,
  readDevRoleCookie,
} from "@/lib/supabase/client";
import type {
  AssignedCounsel,
  CounselComment,
  DocumentVersionType,
  Fund,
  Gestora,
  ParsedParams,
  Precedent,
  RedlineSegment,
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
  exitAAcknowledge: (id: string) => `/api/requests/${id}/exit-a/acknowledge`,
  exitB: (id: string) => `/api/requests/${id}/exit-b`,
  documentDownload: (id: string, type: DocumentVersionType) =>
    `/api/requests/${id}/documents/${type}/download`,
  reviewBundle: (id: string) => `/api/requests/${id}/review`,
  counselEdit: (id: string) => `/api/requests/${id}/counsel-edit`,
  counselUpload: (id: string) => `/api/requests/${id}/counsel-upload`,
  validate: (id: string) => `/api/requests/${id}/validate`,
  comments: (id: string) => `/api/requests/${id}/comments`,
  counselQueue: "/api/counsel/queue",
  assignedCounsel: "/api/counsel/assigned",
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

export async function generateRequest(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    req.status = "generating";
    await delay(1800);
    req.fallbackLevel = stubFallbackLevel(req.docType);
    req.hasMissingFields = stubHasMissing(req);
    req.status = "review_pending";
    req.updatedAt = nowIso();
    return req;
  }
  return apiFetch<RequestItem>(apiPaths.generate(id), { method: "POST" });
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

/** Downloads a document version as a Blob (stub: plain-text .docx placeholder). */
export async function downloadDocument(
  id: string,
  type: DocumentVersionType,
): Promise<Blob> {
  if (isStubMode()) {
    await delay(STUB_LATENCY / 2);
    const req = findRequest(id);
    if (!req) throw new ApiError(404, "Request not found");
    const text =
      type === "redline"
        ? stubRedline(req)
            .map((s) =>
              s.type === "ins"
                ? `[+${s.text}+]`
                : s.type === "del"
                  ? `[-${s.text}-]`
                  : s.text,
            )
            .join("")
        : stubDraftText(req);
    return new Blob([text], { type: "text/plain;charset=utf-8" });
  }
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${apiPaths.documentDownload(id, type)}`, {
    headers,
  });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.blob();
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

export async function getAssignedCounsel(): Promise<AssignedCounsel> {
  if (isStubMode()) {
    return STUB_ASSIGNED_COUNSEL;
  }
  // TODO: backend endpoint returning the counsel assigned to the gestora + SLA.
  return apiFetch<AssignedCounsel>(apiPaths.assignedCounsel);
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
