"use client";

/* ------------------------------------------------------------------ */
/* Account & security (011_account_security.sql)                        */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type { AccountProfile, DeleteMode, ModelConfig } from "@/lib/types";
import { STUB_LATENCY, apiFetch, apiPaths, fetchBlob, stubCall } from "./http";

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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubAccountProfile();
    });
  }
  return mapAccountProfile(await apiFetch<AccountProfileWire>(apiPaths.me));
}

/** Mirrors the user's Supabase TOTP status onto the backend (display/overview).
 * Supabase Auth enforces the actual factor; this only reflects it. */
export async function setMyMfaEnabled(
  enabled: boolean,
): Promise<AccountProfile> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubSetMfaEnabled(enabled);
    });
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      return new Blob([stub.stubExportMyData()], {
        type: "application/json;charset=utf-8",
      });
    });
  }
  return fetchBlob(apiPaths.meExport);
}

/** Self-service erasure/anonymisation (Art. 17). Confirmation phrase required. */
export async function deleteMyData(input: {
  confirm: string;
  mode: DeleteMode;
}): Promise<void> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      stub.stubDeleteMyData(input);
    });
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
  mistral_key_set?: boolean;
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
    mistralKeySet: wire.mistral_key_set ?? false,
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
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubGetModelConfig(gestoraId);
    });
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
    mistralApiKey?: string;
    openaiApiKey?: string;
  },
): Promise<ModelConfig> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubPutModelConfig(gestoraId, input);
    });
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
  if (input.mistralApiKey !== undefined)
    body.mistral_api_key = input.mistralApiKey;
  if (input.openaiApiKey !== undefined) body.openai_api_key = input.openaiApiKey;
  return mapModelConfig(
    await apiFetch<ModelConfigWire>(apiPaths.adminModelConfig(gestoraId), {
      method: "PUT",
      body,
    }),
  );
}
