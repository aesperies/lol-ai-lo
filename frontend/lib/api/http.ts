"use client";

/**
 * Core of the typed fetch wrapper to the FastAPI backend (NEXT_PUBLIC_API_URL).
 *
 * ALL backend REST paths live in `apiPaths` below so they are easy to adjust
 * when the backend lands.
 *
 * Graceful degradation: in dev stub mode (NEXT_PUBLIC_SUPABASE_URL unset)
 * every domain function resolves against the in-memory stub store
 * (lib/stub-data.ts) with a simulated latency, so the whole UI is fully
 * navigable without a backend or Supabase. The stub store is loaded lazily
 * via `stubCall` (dynamic import) so it stays out of the production bundle
 * path when stub mode is off.
 */

import {
  getSupabaseBrowserClient,
  isStubMode,
  readDevRoleCookie,
} from "@/lib/supabase/client";
import type { DocumentVersionType } from "@/lib/types";

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
  requestVerifications: (id: string) => `/api/requests/${id}/verifications`,
  requestBranch: (id: string) => `/api/requests/${id}/branch`,
  counselEdit: (id: string) => `/api/requests/${id}/counsel/edit`,
  counselUpload: (id: string) => `/api/requests/${id}/counsel/upload`,
  validate: (id: string) => `/api/requests/${id}/validate`,
  comments: (id: string) => `/api/requests/${id}/comments`,
  counselQueue: "/api/counsel/queue",
  // In-app notifications bell (016_notifications.sql).
  notificationsInbox: "/api/notifications/inbox",
  notificationsUnreadCount: "/api/notifications/inbox/unread-count",
  notificationsRead: "/api/notifications/read",
  myCounsel: "/api/my/counsel",
  counselAssignments: (gestoraId: string) =>
    `/api/counsel-assignments?gestora_id=${gestoraId}`,
  counselAssignmentCreate: "/api/counsel-assignments",
  counselAssignment: (id: string) => `/api/counsel-assignments/${id}`,
  // Structured intake field specs per doc_type (improvement #5).
  docFields: (docType: string) =>
    `/api/doc-types/${encodeURIComponent(docType)}/fields`,
  funds: "/api/funds",
  fund: (id: string) => `/api/funds/${id}`,
  fundVehicles: (fundId: string) => `/api/funds/${fundId}/vehicles`,
  vehicle: (id: string) => `/api/vehicles/${id}`,
  gestoras: "/api/gestoras",
  precedents: "/api/precedents",
  precedentVersions: (precedentId: string) =>
    `/api/precedents/${precedentId}/versions`,
  // Version actions are keyed by version id alone (the backend resolves the
  // parent precedent): /api/precedents/versions/{versionId}/...
  precedentVersionActivate: (_precedentId: string, versionId: string) =>
    `/api/precedents/versions/${versionId}/activate`,
  precedentVersionSupersede: (_precedentId: string, versionId: string) =>
    `/api/precedents/versions/${versionId}/supersede`,
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
  // Gestora dashboard aggregates (Roadmap D, clients only).
  dashboardStats: "/api/dashboard/stats",
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
  // Chat Q&A sobre el RAG de la gestora (021_chat.sql).
  chatConversations: "/api/chat/conversations",
  chatConversation: (id: string) => `/api/chat/conversations/${id}`,
  chatMessages: (id: string) => `/api/chat/conversations/${id}/messages`,
  chatFeedback: (messageId: string) => `/api/chat/messages/${messageId}/feedback`,
  // Biblioteca del cliente (022).
  myLibrary: "/api/my/library",
  myLibraryUpload: "/api/my/library/upload",
  precedentVersionHtml: (versionId: string) =>
    `/api/precedents/versions/${versionId}/html`,
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
export async function authHeaders(): Promise<Record<string, string>> {
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

/** Extracts `detail` from a FastAPI error response and throws an ApiError. */
export async function throwApiError(res: Response): Promise<never> {
  let detail = res.statusText;
  try {
    const data = await res.json();
    detail = data.detail ?? detail;
  } catch {
    /* not JSON */
  }
  throw new ApiError(res.status, detail);
}

export async function apiFetch<T>(
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
  if (!res.ok) await throwApiError(res);
  return (await res.json()) as T;
}

/** Authenticated fetch of a binary/CSV endpoint, resolved to a Blob. */
export async function fetchBlob(
  path: string,
  init: { method?: string } = {},
): Promise<Blob> {
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    method: init.method ?? "GET",
    headers,
  });
  if (!res.ok) await throwApiError(res);
  return res.blob();
}

/** Authenticated multipart upload (Content-Type set by the browser).
 * Returns the raw Response so callers may parse a JSON body when relevant. */
export async function fetchMultipart(
  path: string,
  form: FormData,
  init: { method?: string } = {},
): Promise<Response> {
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    method: init.method ?? "POST",
    headers,
    body: form,
  });
  if (!res.ok) await throwApiError(res);
  return res;
}

/**
 * Authenticated POST to a Server-Sent-Events endpoint (chat streaming).
 *
 * Parses data-only SSE frames (`data: {json}\n\n`) incrementally and invokes
 * `onEvent` per frame. Resolves when the server closes the stream; rejects
 * with ApiError on a non-2xx response (before any frame is read).
 */
export async function fetchSse(
  path: string,
  body: unknown,
  onEvent: (event: unknown) => void,
): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(await authHeaders()),
  };
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) await throwApiError(res);
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        try {
          onEvent(JSON.parse(line.slice(5).trim()));
        } catch {
          /* frame incompleto o keep-alive: se ignora */
        }
      }
    }
  }
}

/** Authenticated fetch for endpoints without a JSON body (e.g. DELETE). */
export async function fetchVoid(
  path: string,
  init: { method?: string } = {},
): Promise<void> {
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${path}`, {
    method: init.method ?? "DELETE",
    headers,
  });
  if (!res.ok) await throwApiError(res);
}

/* ------------------------------------------------------------------ */
/* Stub mode                                                           */
/* ------------------------------------------------------------------ */

export const STUB_LATENCY = 600;

type StubModule = typeof import("@/lib/stub-data");

/**
 * Runs a stub-mode branch against the lazily-loaded in-memory stub store.
 *
 * The dynamic import keeps lib/stub-data.ts (and its ~2k lines of fixture
 * data) in a separate chunk that is only downloaded when stub mode is on;
 * the module instance is cached by the bundler, so stub state persists
 * across calls exactly like the previous static import.
 */
export async function stubCall<T>(
  fn: (stub: StubModule) => T | Promise<T>,
): Promise<T> {
  const stub = await import("@/lib/stub-data");
  return fn(stub);
}

/* ------------------------------------------------------------------ */
/* Shared flow constants                                               */
/* ------------------------------------------------------------------ */

/** Mirrors the backend `max_refinements` setting (config.py, default 3). */
export const MAX_REFINEMENTS = 3;

/** Mirrors the backend `sla_review_hours` setting (config.py, default 48):
 * promised counsel review turnaround for Exit B. */
export const SLA_REVIEW_HOURS = 48;
