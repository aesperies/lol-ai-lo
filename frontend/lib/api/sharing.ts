"use client";

/* ------------------------------------------------------------------ */
/* Collaboration / sharing (012_collaboration.sql) — single-gestora     */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type { Colleague, Share } from "@/lib/types";
import { STUB_LATENCY, apiFetch, apiPaths, fetchVoid, stubCall } from "./http";

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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubColleagues();
    });
  }
  const rows = await apiFetch<ColleagueWire[]>(apiPaths.colleagues);
  return rows.map((c) => ({ id: c.id, email: c.email, name: c.name }));
}

/** Collaborators on a request (owner + collaborators may view). */
export async function getRequestShares(id: string): Promise<Share[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubRequestShares(id);
    });
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubCreateRequestShare(id, userId);
    });
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      stub.stubDeleteRequestShare(id, userId);
    });
  }
  await fetchVoid(apiPaths.requestShare(id, userId), { method: "DELETE" });
}

/** Collaborators on a tabular review (owner + collaborators may view). */
export async function getReviewShares(id: string): Promise<Share[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubReviewShares(id);
    });
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubCreateReviewShare(id, userId);
    });
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      stub.stubDeleteReviewShare(id, userId);
    });
  }
  await fetchVoid(apiPaths.reviewShare(id, userId), { method: "DELETE" });
}
