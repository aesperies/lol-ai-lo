"use client";

/* ------------------------------------------------------------------ */
/* Reference data / admin + doc-type field specs                       */
/* ------------------------------------------------------------------ */

import { docTypeLabel } from "@/lib/catalog";
import { isStubMode } from "@/lib/supabase/client";
import type {
  FieldSpec,
  Fund,
  Gestora,
  Precedent,
  Role,
  SubscriptionTier,
  UserProfile,
  Vehicle,
  VehicleType,
} from "@/lib/types";
import {
  STUB_LATENCY,
  apiFetch,
  apiPaths,
  fetchMultipart,
  fetchVoid,
  stubCall,
} from "./http";
import {
  type FundWire,
  type GestoraWire,
  type PrecedentWire,
  type UserWire,
  type VehicleWire,
  mapFund,
  mapGestora,
  mapPrecedent,
  mapUser,
  mapVehicle,
} from "./wire";

/** Structured intake field specs for a doc_type ([] = freetext-only). */
export async function getDocFields(docType: string): Promise<FieldSpec[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubDocFields(docType);
    });
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

export async function getFunds(): Promise<Fund[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.STUB_FUNDS;
    });
  }
  const rows = await apiFetch<FundWire[]>(apiPaths.funds);
  return rows.map(mapFund);
}

/** Register a new fund/vehicle. Clients create it in their own gestora. */
export async function createFund(input: {
  name: string;
  jurisdiction?: string;
}): Promise<Fund> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const fund: Fund = {
        id: `f-${Date.now()}`,
        gestoraId: stub.STUB_GESTORA.id,
        name: input.name,
        jurisdiction: input.jurisdiction ?? "España",
        createdAt: new Date().toISOString(),
      };
      stub.STUB_FUNDS.push(fund);
      return fund;
    });
  }
  const row = await apiFetch<FundWire>(apiPaths.funds, {
    method: "POST",
    // Plain object: apiFetch JSON-stringifies the body itself.
    body: {
      name: input.name,
      jurisdiction: input.jurisdiction ?? "España",
    },
  });
  return mapFund(row);
}

/** Rename / re-jurisdiction a fund (PATCH /api/funds/{id}). */
export async function updateFund(
  id: string,
  input: { name?: string; jurisdiction?: string },
): Promise<Fund> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubUpdateFund(id, input);
    });
  }
  const row = await apiFetch<FundWire>(apiPaths.fund(id), {
    method: "PATCH",
    body: {
      name: input.name ?? null,
      jurisdiction: input.jurisdiction ?? null,
    },
  });
  return mapFund(row);
}

/** Delete a fund (DELETE /api/funds/{id}); 409 while it has requests. */
export async function deleteFund(id: string): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      stub.stubDeleteFund(id);
    });
  }
  await fetchVoid(apiPaths.fund(id), { method: "DELETE" });
}

/* ------------------------------------------------------------------ */
/* SPVs / vehicles (015_vehicles.sql)                                  */
/* ------------------------------------------------------------------ */

export interface VehicleInput {
  name?: string;
  vehicleType?: VehicleType;
  jurisdiction?: string;
}

/** The fund's SPVs/vehicles (GET /api/funds/{id}/vehicles). */
export async function getVehicles(fundId: string): Promise<Vehicle[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubGetVehicles(fundId);
    });
  }
  const rows = await apiFetch<VehicleWire[]>(apiPaths.fundVehicles(fundId));
  return rows.map(mapVehicle);
}

/** Register an SPV/vehicle under a fund (POST /api/funds/{id}/vehicles). */
export async function createVehicle(
  fundId: string,
  input: VehicleInput & { name: string },
): Promise<Vehicle> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubCreateVehicle(fundId, input);
    });
  }
  const row = await apiFetch<VehicleWire>(apiPaths.fundVehicles(fundId), {
    method: "POST",
    body: {
      name: input.name,
      vehicle_type: input.vehicleType ?? "spv",
      jurisdiction: input.jurisdiction ?? null,
    },
  });
  return mapVehicle(row);
}

/** Edit an SPV/vehicle (PATCH /api/vehicles/{id}). */
export async function updateVehicle(
  id: string,
  input: VehicleInput,
): Promise<Vehicle> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubUpdateVehicle(id, input);
    });
  }
  const row = await apiFetch<VehicleWire>(apiPaths.vehicle(id), {
    method: "PATCH",
    body: {
      name: input.name ?? null,
      vehicle_type: input.vehicleType ?? null,
      jurisdiction: input.jurisdiction ?? null,
    },
  });
  return mapVehicle(row);
}

/** Delete an SPV/vehicle (DELETE /api/vehicles/{id}); 409 while referenced. */
export async function deleteVehicle(id: string): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      stub.stubDeleteVehicle(id);
    });
  }
  await fetchVoid(apiPaths.vehicle(id), { method: "DELETE" });
}

export async function getGestoras(): Promise<Gestora[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return [...stub.stubGestoras];
    });
  }
  const rows = await apiFetch<GestoraWire[]>(apiPaths.gestoras);
  return rows.map(mapGestora);
}

export async function createGestora(input: {
  name: string;
  subscriptionTier: SubscriptionTier;
  billingEmail: string;
}): Promise<Gestora> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      const gestora: Gestora = {
        id: `g-${Date.now()}`,
        name: input.name,
        driveFolderId: null,
        subscriptionTier: input.subscriptionTier,
        billingEmail: input.billingEmail,
        createdAt: stub.nowIso(),
      };
      stub.stubGestoras.push(gestora);
      return gestora;
    });
  }
  return mapGestora(
    await apiFetch<GestoraWire>(apiPaths.gestoras, {
      method: "POST",
      body: {
        name: input.name,
        subscription_tier: input.subscriptionTier,
        billing_email: input.billingEmail,
      },
    }),
  );
}

export async function getPrecedents(): Promise<Precedent[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return [...stub.stubPrecedents];
    });
  }
  const rows = await apiFetch<PrecedentWire[]>(apiPaths.precedents);
  return rows.map(mapPrecedent);
}

export async function uploadPrecedent(input: {
  gestoraId: string;
  docType: string;
  language: string;
  file: File;
}): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      stub.stubPrecedents.push({
        id: `p-${Date.now()}`,
        gestoraId: input.gestoraId,
        fundId: null,
        docType: input.docType,
        docTypeLabel: docTypeLabel(input.docType),
        language: input.language as Precedent["language"],
        source: "manual_upload",
        createdAt: stub.nowIso(),
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
    });
  }
  const form = new FormData();
  form.append("gestora_id", input.gestoraId);
  form.append("doc_type", input.docType);
  form.append("language", input.language);
  form.append("file", input.file);
  await fetchMultipart(apiPaths.precedents, form);
}

export async function activatePrecedentVersion(
  precedentId: string,
  versionId: string,
): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const precedent = stub.stubPrecedents.find((p) => p.id === precedentId);
      if (!precedent) return;
      for (const v of precedent.versions) {
        if (v.id === versionId) {
          v.status = "active";
          v.ragWeight = 1.0;
          v.activatedAt = stub.nowIso();
        } else if (v.status === "active") {
          v.status = "superseded";
          v.ragWeight = 0.3;
          v.supersededAt = stub.nowIso();
        }
      }
    });
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const precedent = stub.stubPrecedents.find((p) => p.id === precedentId);
      const version = precedent?.versions.find((v) => v.id === versionId);
      if (version) {
        version.status = "superseded";
        version.ragWeight = 0.3;
        version.supersededAt = stub.nowIso();
      }
    });
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      stub.stubUploadModel(input);
    });
  }
  const form = new FormData();
  form.append("gestora_id", input.gestoraId);
  form.append("doc_type", input.docType);
  form.append("language", input.language);
  form.append("source", "gestora_model");
  form.append("file", input.file);
  await fetchMultipart(apiPaths.precedents, form);
}

/* ------------------------------------------------------------------ */
/* Users (admin)                                                       */
/* ------------------------------------------------------------------ */

export async function getUsers(): Promise<UserProfile[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.STUB_ALL_USERS;
    });
  }
  const rows = await apiFetch<UserWire[]>(apiPaths.users);
  return rows.map(mapUser);
}

export async function inviteUser(input: {
  email: string;
  role: Role;
  gestoraId: string | null;
}): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      stub.STUB_ALL_USERS.push({
        id: `u-${Date.now()}`,
        email: input.email,
        role: input.role,
        gestoraId: input.gestoraId,
      });
    });
  }
  await apiFetch(apiPaths.users, {
    method: "POST",
    body: { email: input.email, role: input.role, gestora_id: input.gestoraId },
  });
}
