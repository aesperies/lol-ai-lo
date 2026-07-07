"use client";

/* ------------------------------------------------------------------ */
/* Counsel assignments (admin)                                         */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type { CounselAssignment } from "@/lib/types";
import {
  ApiError,
  STUB_LATENCY,
  apiFetch,
  apiPaths,
  fetchVoid,
  stubCall,
} from "./http";

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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubCounselAssignments.filter(
        (a) => a.gestoraId === gestoraId,
      );
    });
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      if (input.isPrimary) {
        for (const a of stub.stubCounselAssignments) {
          if (a.gestoraId === input.gestoraId) a.isPrimary = false;
        }
      }
      const existing = stub.stubCounselAssignments.find(
        (a) =>
          a.gestoraId === input.gestoraId &&
          a.counselUserId === input.counselUserId,
      );
      if (existing) {
        existing.isPrimary = input.isPrimary;
        return { ...existing };
      }
      const counsel = stub.STUB_ALL_USERS.find(
        (u) => u.id === input.counselUserId,
      );
      if (!counsel || counsel.role !== "counsel") {
        throw new ApiError(422, "Assigned user must have role 'counsel'");
      }
      const assignment: CounselAssignment = {
        id: `ca-${Date.now()}`,
        gestoraId: input.gestoraId,
        counselUserId: input.counselUserId,
        counselEmail: counsel.email,
        isPrimary: input.isPrimary,
        createdAt: stub.nowIso(),
      };
      stub.stubCounselAssignments.push(assignment);
      return assignment;
    });
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const index = stub.stubCounselAssignments.findIndex((a) => a.id === id);
      if (index >= 0) stub.stubCounselAssignments.splice(index, 1);
    });
  }
  await fetchVoid(apiPaths.counselAssignment(id), { method: "DELETE" });
}
