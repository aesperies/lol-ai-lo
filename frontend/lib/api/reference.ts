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
} from "@/lib/types";
import {
  STUB_LATENCY,
  apiFetch,
  apiPaths,
  fetchMultipart,
  stubCall,
} from "./http";
import {
  type FundWire,
  type GestoraWire,
  type PrecedentWire,
  type UserWire,
  mapFund,
  mapGestora,
  mapPrecedent,
  mapUser,
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
    body: JSON.stringify({
      name: input.name,
      jurisdiction: input.jurisdiction ?? "España",
    }),
  });
  return mapFund(row);
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
