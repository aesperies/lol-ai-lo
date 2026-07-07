"use client";

/**
 * Shared wire types + mappers for the FastAPI backend.
 *
 * The backend speaks snake_case (its DTOs mirror the Postgres rows); the UI
 * types (lib/types.ts) are camelCase. Every module that returns a domain type
 * from a real API call MUST map through here — casting the raw response to a
 * camelCase type compiles fine but leaves every field undefined at runtime.
 */

import { docTypeLabel } from "@/lib/catalog";
import type {
  AppLanguage,
  CounselComment,
  Fund,
  Gestora,
  ParsedParams,
  Precedent,
  PrecedentVersion,
  RequestItem,
  RequestStatus,
  ReviewBundle,
  UserProfile,
} from "@/lib/types";

/* ------------------------------------------------------------------ */
/* Requests                                                            */
/* ------------------------------------------------------------------ */

export interface ParsedParamsWire {
  language?: string | null;
  doc_type_confirmed?: string | null;
  parties?: Array<{ role: string; name: string }> | null;
  key_dates?: Array<{ label: string; date: string }> | null;
  jurisdiction?: string | null;
  governing_law?: string | null;
  key_terms?: Array<{ field: string; value: string }> | null;
  summary?: string | null;
  confidence?: number | null;
  unclear_fields?: string[] | null;
  generation_ready?: boolean | null;
  /** Set by the backend parser only when the request is unclassifiable. */
  message?: string | null;
}

export function mapParsedParams(wire: ParsedParamsWire): ParsedParams {
  return {
    language: (wire.language ?? "es") as AppLanguage,
    docTypeConfirmed: wire.doc_type_confirmed ?? "",
    parties: wire.parties ?? [],
    keyDates: wire.key_dates ?? [],
    jurisdiction: wire.jurisdiction ?? "",
    governingLaw: wire.governing_law ?? "",
    keyTerms: wire.key_terms ?? [],
    summary: wire.summary ?? "",
    confidence: wire.confidence ?? 0,
    unclearFields: wire.unclear_fields ?? [],
    generationReady: wire.generation_ready ?? false,
    unclassifiable: Boolean(wire.message),
  };
}

/** Inverse mapping for POST bodies (confirm sends the edited params back). */
export function parsedParamsToWire(params: ParsedParams): ParsedParamsWire {
  return {
    language: params.language,
    doc_type_confirmed: params.docTypeConfirmed,
    parties: params.parties.map(({ role, name }) => ({ role, name })),
    key_dates: params.keyDates.map(({ label, date }) => ({ label, date })),
    jurisdiction: params.jurisdiction,
    governing_law: params.governingLaw,
    key_terms: params.keyTerms.map(({ field, value }) => ({ field, value })),
    summary: params.summary,
    confidence: params.confidence,
    unclear_fields: params.unclearFields,
    generation_ready: params.generationReady,
  };
}

export interface RequestWire {
  id: string;
  fund_id: string;
  fund_name?: string | null;
  user_id: string;
  doc_type: string;
  doc_type_custom?: string | null;
  freetext: string;
  language?: string | null;
  parsed_params?: ParsedParamsWire | null;
  structured_fields?: Record<string, string> | null;
  status: RequestStatus;
  requires_counsel: boolean;
  exit_a_acknowledged_at?: string | null;
  counsel_requested_at?: string | null;
  counsel_validated_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  is_owner?: boolean | null;
  shared_with_me?: boolean | null;
  shared_by_email?: string | null;
}

export function mapRequest(wire: RequestWire): RequestItem {
  return {
    id: wire.id,
    fundId: wire.fund_id,
    fundName: wire.fund_name ?? undefined,
    userId: wire.user_id,
    docType: wire.doc_type,
    docTypeLabel: docTypeLabel(wire.doc_type),
    docTypeCustom: wire.doc_type_custom ?? null,
    freetext: wire.freetext,
    structuredFields: wire.structured_fields ?? null,
    language: (wire.language ?? "es") as AppLanguage,
    parsedParams: wire.parsed_params ? mapParsedParams(wire.parsed_params) : null,
    status: wire.status,
    requiresCounsel: wire.requires_counsel,
    exitAAcknowledgedAt: wire.exit_a_acknowledged_at ?? null,
    counselRequestedAt: wire.counsel_requested_at ?? null,
    counselValidatedAt: wire.counsel_validated_at ?? null,
    isOwner: wire.is_owner ?? null,
    sharedWithMe: wire.shared_with_me ?? null,
    sharedByEmail: wire.shared_by_email ?? null,
    createdAt: wire.created_at ?? "",
    updatedAt: wire.updated_at ?? "",
  };
}

/* ------------------------------------------------------------------ */
/* Directory (gestoras / funds / users)                                */
/* ------------------------------------------------------------------ */

export interface GestoraWire {
  id: string;
  name: string;
  drive_folder_id?: string | null;
  subscription_tier: Gestora["subscriptionTier"];
  billing_email?: string | null;
  created_at?: string | null;
}

export function mapGestora(wire: GestoraWire): Gestora {
  return {
    id: wire.id,
    name: wire.name,
    driveFolderId: wire.drive_folder_id ?? null,
    subscriptionTier: wire.subscription_tier,
    billingEmail: wire.billing_email ?? "",
    createdAt: wire.created_at ?? "",
  };
}

export interface FundWire {
  id: string;
  gestora_id: string;
  name: string;
  jurisdiction: string;
  created_at?: string | null;
}

export function mapFund(wire: FundWire): Fund {
  return {
    id: wire.id,
    gestoraId: wire.gestora_id,
    name: wire.name,
    jurisdiction: wire.jurisdiction,
    createdAt: wire.created_at ?? "",
  };
}

export interface UserWire {
  id: string;
  email: string;
  role: UserProfile["role"];
  gestora_id?: string | null;
}

export function mapUser(wire: UserWire): UserProfile {
  return {
    id: wire.id,
    email: wire.email,
    role: wire.role,
    gestoraId: wire.gestora_id ?? null,
  };
}

/* ------------------------------------------------------------------ */
/* Precedents (with embedded versions)                                 */
/* ------------------------------------------------------------------ */

export interface PrecedentVersionWire {
  id: string;
  precedent_id: string;
  version_number: number;
  file_path: string;
  status: PrecedentVersion["status"];
  rag_weight: number;
  activated_at?: string | null;
  superseded_at?: string | null;
  created_by?: string | null;
}

export interface PrecedentWire {
  id: string;
  gestora_id?: string | null;
  fund_id?: string | null;
  doc_type: string;
  language: string;
  source: Precedent["source"];
  created_at?: string | null;
  versions?: PrecedentVersionWire[] | null;
}

export function mapPrecedentVersion(wire: PrecedentVersionWire): PrecedentVersion {
  return {
    id: wire.id,
    precedentId: wire.precedent_id,
    versionNumber: wire.version_number,
    filePath: wire.file_path,
    status: wire.status,
    ragWeight: wire.rag_weight,
    activatedAt: wire.activated_at ?? null,
    supersededAt: wire.superseded_at ?? null,
    createdBy: wire.created_by ?? null,
  };
}

export function mapPrecedent(wire: PrecedentWire): Precedent {
  return {
    id: wire.id,
    gestoraId: wire.gestora_id ?? "",
    fundId: wire.fund_id ?? null,
    docType: wire.doc_type,
    docTypeLabel: docTypeLabel(wire.doc_type),
    language: wire.language as AppLanguage,
    source: wire.source,
    createdAt: wire.created_at ?? "",
    versions: (wire.versions ?? []).map(mapPrecedentVersion),
  };
}

/* ------------------------------------------------------------------ */
/* Counsel review bundle + comments                                    */
/* ------------------------------------------------------------------ */

export interface CounselCommentWire {
  id: string;
  request_id: string;
  author: string;
  text: string;
  created_at?: string | null;
}

export function mapCounselComment(wire: CounselCommentWire): CounselComment {
  return {
    id: wire.id,
    requestId: wire.request_id,
    author: wire.author,
    text: wire.text,
    createdAt: wire.created_at ?? "",
  };
}

export interface ReviewBundleWire {
  request: RequestWire;
  draft_text: string;
  redline?: Array<{ type: "eq" | "ins" | "del"; text: string }> | null;
  comments?: CounselCommentWire[] | null;
}

export function mapReviewBundle(wire: ReviewBundleWire): ReviewBundle {
  return {
    request: mapRequest(wire.request),
    draftText: wire.draft_text,
    redline: wire.redline ?? [],
    comments: (wire.comments ?? []).map(mapCounselComment),
  };
}
