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
  return apiFetch<Fund[]>(apiPaths.funds);
}

export async function getGestoras(): Promise<Gestora[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return [...stub.stubGestoras];
    });
  }
  return apiFetch<Gestora[]>(apiPaths.gestoras);
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
  return apiFetch<Gestora>(apiPaths.gestoras, { method: "POST", body: input });
}

export async function getPrecedents(): Promise<Precedent[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return [...stub.stubPrecedents];
    });
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
  // TODO: multipart upload to the backend once the endpoint exists.
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
  return apiFetch<UserProfile[]>(apiPaths.users);
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
  await apiFetch(apiPaths.users, { method: "POST", body: input });
}
