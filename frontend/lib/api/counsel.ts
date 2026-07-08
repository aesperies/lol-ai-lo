"use client";

/* ------------------------------------------------------------------ */
/* Counsel                                                             */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type {
  AssignedCounsel,
  CounselComment,
  CounselQueueItem,
  RequestItem,
  ReviewBundle,
  SlaUrgency,
} from "@/lib/types";
import {
  ApiError,
  STUB_LATENCY,
  apiFetch,
  apiPaths,
  fetchMultipart,
  stubCall,
} from "./http";
import {
  type CounselCommentWire,
  type CounselQueueItemWire,
  type RequestWire,
  type ReviewBundleWire,
  mapCounselComment,
  mapCounselQueueItem,
  mapRequest,
  mapReviewBundle,
} from "./wire";

export interface CounselQueueFilters {
  gestoraId?: string;
  urgency?: SlaUrgency;
}

/** Pending counsel reviews, most urgent first (server-side ordering). */
export async function getCounselQueue(
  filters: CounselQueueFilters = {},
): Promise<CounselQueueItem[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubCounselQueue(filters);
    });
  }
  const params = new URLSearchParams();
  if (filters.gestoraId) params.set("gestora_id", filters.gestoraId);
  if (filters.urgency) params.set("urgency", filters.urgency);
  const qs = params.toString();
  const rows = await apiFetch<CounselQueueItemWire[]>(
    `${apiPaths.counselQueue}${qs ? `?${qs}` : ""}`,
  );
  return rows.map(mapCounselQueueItem);
}

export async function getReviewBundle(id: string): Promise<ReviewBundle> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      return stub.stubReviewBundle(req);
    });
  }
  return mapReviewBundle(
    await apiFetch<ReviewBundleWire>(apiPaths.reviewBundle(id)),
  );
}

export async function saveCounselEdit(
  id: string,
  text: string,
): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      // Stub: counsel_edit version is kept server-side in the real backend.
    });
  }
  await apiFetch(apiPaths.counselEdit(id), { method: "POST", body: { text } });
}

export async function uploadCounselDocx(
  id: string,
  file: File,
): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
    });
  }
  const form = new FormData();
  form.append("file", file);
  await fetchMultipart(apiPaths.counselUpload(id), form);
}

export async function addComment(
  id: string,
  text: string,
): Promise<CounselComment> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubAddComment(id, "María Llopis", text);
    });
  }
  return mapCounselComment(
    await apiFetch<CounselCommentWire>(apiPaths.comments(id), {
      method: "POST",
      body: { text },
    }),
  );
}

export async function validateRequest(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      // Counsel-validated docs enter the precedent library automatically.
      req.status = "delivered";
      // SLA clock stops now (counsel response metrics).
      req.counselValidatedAt = stub.nowIso();
      req.updatedAt = stub.nowIso();
      return req;
    });
  }
  return mapRequest(
    await apiFetch<RequestWire>(apiPaths.validate(id), { method: "POST" }),
  );
}

/** The requesting client's gestora's assigned counsel, or null when none. */
export async function getAssignedCounsel(): Promise<AssignedCounsel | null> {
  if (isStubMode()) {
    return stubCall((stub) => stub.STUB_ASSIGNED_COUNSEL);
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
