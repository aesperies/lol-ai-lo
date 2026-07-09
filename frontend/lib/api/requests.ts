"use client";

/* ------------------------------------------------------------------ */
/* Requests — client flow                                               */
/* ------------------------------------------------------------------ */

import { docTypeLabel } from "@/lib/catalog";
import { isStubMode } from "@/lib/supabase/client";
import type {
  Branch,
  DocumentHtml,
  DocumentVersionType,
  GenerationJob,
  GenerationJobStatus,
  GenerationReview,
  Verification,
  ParsedParams,
  Refinement,
  RefinementStatus,
  RequestItem,
  ReviewIssue,
} from "@/lib/types";
import {
  ApiError,
  STUB_LATENCY,
  apiFetch,
  apiPaths,
  fetchBlob,
  stubCall,
} from "./http";
import {
  type ParsedParamsWire,
  type RequestWire,
  mapParsedParams,
  mapRequest,
  parsedParamsToWire,
} from "./wire";

export interface CreateRequestInput {
  fundId: string;
  /** Optional SPV/vehicle of the fund the document belongs to. */
  vehicleId?: string;
  docType: string;
  docTypeCustom?: string;
  freetext: string;
  requiresCounsel: boolean;
  /** Structured intake values (registry keys of the selected doc_type);
   * omit/undefined for freetext-only requests. */
  structuredFields?: Record<string, string>;
}

export async function createRequest(
  input: CreateRequestInput,
): Promise<RequestItem> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      const fund = stub.STUB_FUNDS.find((f) => f.id === input.fundId);
      const vehicle = input.vehicleId
        ? stub.STUB_VEHICLES.find((v) => v.id === input.vehicleId)
        : undefined;
      const req: RequestItem = {
        id: stub.nextRequestId(),
        fundId: input.fundId,
        fundName: fund?.name,
        vehicleId: vehicle?.id ?? null,
        vehicleName: vehicle?.name ?? null,
        gestoraId: fund?.gestoraId,
        userId: "u-client-1",
        requestedByName: "Lucía Fernández",
        docType: input.docType,
        docTypeLabel: docTypeLabel(input.docType),
        docTypeCustom: input.docTypeCustom ?? null,
        freetext: input.freetext,
        structuredFields: input.structuredFields ?? null,
        language: "es",
        status: "parsing",
        requiresCounsel: input.requiresCounsel,
        createdAt: stub.nowIso(),
        updatedAt: stub.nowIso(),
      };
      stub.stubRequests.unshift(req);
      return req;
    });
  }
  // snake_case body per the backend RequestCreate DTO. The intake counsel
  // toggle travels as validation_requested (SPEC "validación por abogado").
  return mapRequest(
    await apiFetch<RequestWire>(apiPaths.requests, {
      method: "POST",
      body: {
        fund_id: input.fundId,
        vehicle_id: input.vehicleId ?? null,
        doc_type: input.docType,
        doc_type_custom: input.docTypeCustom ?? null,
        freetext: input.freetext,
        validation_requested: input.requiresCounsel,
        structured_fields: input.structuredFields ?? null,
      },
    }),
  );
}

export async function parseRequest(id: string): Promise<ParsedParams> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(1200);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      const params = stub.stubParse(req);
      req.parsedParams = params;
      req.updatedAt = stub.nowIso();
      return params;
    });
  }
  // Backend wraps the result: { request, parsed_params } (both snake_case).
  const res = await apiFetch<{ parsed_params: ParsedParamsWire }>(
    apiPaths.parse(id),
    { method: "POST" },
  );
  return mapParsedParams(res.parsed_params);
}

export async function confirmRequest(
  id: string,
  params: ParsedParams,
  edited: boolean,
): Promise<RequestItem> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      // TODO backend: log `params_edited` audit action when edited === true.
      req.parsedParams = params;
      req.status = "confirmed";
      req.updatedAt = stub.nowIso();
      return req;
    });
  }
  // ConfirmParamsBody.parsed_params — send the (possibly edited) params in
  // wire format; the backend audits params_edited by comparing with stored.
  return mapRequest(
    await apiFetch<RequestWire>(apiPaths.confirm(id), {
      method: "POST",
      body: { parsed_params: edited ? parsedParamsToWire(params) : null },
    }),
  );
}

/** Enqueues generation (202): returns the job to poll via getGenerationJob. */
export async function generateRequest(id: string): Promise<GenerationJob> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      await stub.delay(STUB_LATENCY / 2);
      req.status = "generating";
      req.updatedAt = stub.nowIso();
      return stub.stubStartGenerationJob(req);
    });
  }
  const res = await apiFetch<{ job_id: string; status: GenerationJobStatus }>(
    apiPaths.generate(id),
    { method: "POST" },
  );
  return { id: res.job_id, status: res.status, attempts: 0 };
}

/** Latest generation job for a request (poll target of the 202 flow). */
export async function getGenerationJob(
  requestId: string,
): Promise<GenerationJob> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 4);
      const job = stub.stubPollGenerationJob(requestId);
      if (!job) throw new ApiError(404, "No generation job for this request");
      return job;
    });
  }
  const res = await apiFetch<{
    id: string;
    status: GenerationJobStatus;
    attempts: number;
    last_error?: string | null;
  }>(apiPaths.generationJob(requestId));
  return {
    id: res.id,
    status: res.status,
    attempts: res.attempts,
    lastError: res.last_error ?? null,
  };
}

export async function acknowledgeExitA(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      req.exitAAcknowledgedAt = stub.nowIso();
      req.status = "delivered";
      req.updatedAt = stub.nowIso();
      return req;
    });
  }
  // The backend re-verifies the explicit checkbox value (SPEC guardrail 5).
  return mapRequest(
    await apiFetch<RequestWire>(apiPaths.exitAAcknowledge(id), {
      method: "POST",
      body: { acknowledged: true },
    }),
  );
}

/* ------------------------------------------------------------------ */
/* Iterative refinements (improvement #4)                              */
/* ------------------------------------------------------------------ */

interface RefinementWire {
  id: string;
  request_id: string;
  iteration: number;
  instruction: string;
  status: RefinementStatus;
  error?: string | null;
  created_at?: string;
  applied_at?: string | null;
}

function mapRefinement(wire: RefinementWire): Refinement {
  return {
    id: wire.id,
    requestId: wire.request_id,
    iteration: wire.iteration,
    instruction: wire.instruction,
    status: wire.status,
    error: wire.error ?? null,
    createdAt: wire.created_at ?? "",
    appliedAt: wire.applied_at ?? null,
  };
}

/**
 * Requests one iterative refinement (202): the document is regenerated as a
 * new iteration. Poll getGenerationJob, then re-read getRefinements for the
 * applied/failed outcome.
 */
export async function createRefinement(
  id: string,
  instruction: string,
): Promise<{ refinementId: string; jobId: string; iteration: number }> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      return stub.stubStartRefinement(req, instruction);
    });
  }
  const res = await apiFetch<{
    refinement_id: string;
    job_id: string;
    iteration: number;
  }>(apiPaths.refinements(id), { method: "POST", body: { instruction } });
  return {
    refinementId: res.refinement_id,
    jobId: res.job_id,
    iteration: res.iteration,
  };
}

/** Refinement history for a request (oldest first). */
export async function getRefinements(id: string): Promise<Refinement[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 4);
      return stub.stubRefinements
        .filter((r) => r.requestId === id)
        .map((r) => ({ ...r }));
    });
  }
  const rows = await apiFetch<RefinementWire[]>(apiPaths.refinements(id));
  return rows.map(mapRefinement);
}

export async function requestExitB(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      req.status = "counsel_review";
      req.requiresCounsel = true;
      // SLA clock starts now (counsel dashboard chip / admin SLA report).
      req.counselRequestedAt = stub.nowIso();
      req.updatedAt = stub.nowIso();
      return req;
    });
  }
  return mapRequest(
    await apiFetch<RequestWire>(apiPaths.exitB(id), { method: "POST" }),
  );
}

export async function getRequests(): Promise<RequestItem[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return [...stub.stubRequests];
    });
  }
  const rows = await apiFetch<RequestWire[]>(apiPaths.requests);
  return rows.map(mapRequest);
}

export async function getRequest(id: string): Promise<RequestItem> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      return req;
    });
  }
  return mapRequest(await apiFetch<RequestWire>(apiPaths.request(id)));
}

/** Downloads a document version as a Blob (stub: plain-text .docx placeholder).
 * `iteration` selects an older refinement version; latest when omitted. */
export async function downloadDocument(
  id: string,
  type: DocumentVersionType,
  iteration?: number,
): Promise<Blob> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      const text =
        type === "redline"
          ? stub
              .stubRedline(req, iteration)
              .map((s) =>
                s.type === "ins"
                  ? `[+${s.text}+]`
                  : s.type === "del"
                    ? `[-${s.text}-]`
                    : s.text,
              )
              .join("")
          : stub.stubDraftText(req, iteration);
      return new Blob([text], { type: "text/plain;charset=utf-8" });
    });
  }
  return fetchBlob(apiPaths.documentDownload(id, type, iteration));
}

/** Safe HTML rendering of a document version for the in-browser viewer.
 * `iteration` selects an older refinement version; latest when omitted. */
export async function getDocumentHtml(
  id: string,
  type: DocumentVersionType,
  iteration?: number,
): Promise<DocumentHtml> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      const req = stub.findRequest(id);
      if (!req) throw new ApiError(404, "Request not found");
      return stub.stubDocumentHtml(req, type, iteration);
    });
  }
  return apiFetch<DocumentHtml>(apiPaths.documentHtml(id, type, iteration));
}

/* ------------------------------------------------------------------ */
/* Internal critic review trail + drafting branch (drafting-agents)    */
/* ------------------------------------------------------------------ */

interface ReviewIssueWire {
  severity: ReviewIssue["severity"];
  category: ReviewIssue["category"];
  problem: string;
  suggested_fix?: string | null;
  location?: string | null;
  citation?: { where?: string | null; quote?: string | null } | null;
  confidence?: number | null;
}

interface GenerationReviewWire {
  round: number;
  approved: boolean;
  issues: ReviewIssueWire[];
  created_at?: string | null;
}

function mapReviewIssue(wire: ReviewIssueWire): ReviewIssue {
  const citation =
    wire.citation && (wire.citation.where || wire.citation.quote)
      ? {
          where: wire.citation.where ?? "",
          quote: wire.citation.quote ?? "",
        }
      : undefined;
  return {
    severity: wire.severity,
    category: wire.category,
    problem: wire.problem,
    suggestedFix: wire.suggested_fix ?? undefined,
    location: wire.location ?? undefined,
    citation,
    confidence: wire.confidence ?? undefined,
  };
}

/** The critic review trail for a request (one entry per round). Empty when
 * the critic was skipped (LLM unreachable / disabled). */
export async function getRequestReviews(
  id: string,
): Promise<GenerationReview[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubRequestReviews(id);
    });
  }
  const rows = await apiFetch<GenerationReviewWire[]>(apiPaths.requestReviews(id));
  return rows.map((r) => ({
    round: r.round,
    approved: r.approved,
    issues: (r.issues ?? []).map(mapReviewIssue),
    createdAt: r.created_at ?? null,
  }));
}

/** The specialized drafting branch used for a request. */
export async function getRequestBranch(id: string): Promise<Branch> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 4);
      return stub.stubRequestBranch(id);
    });
  }
  const res = await apiFetch<{ doc_type: string; branch: Branch }>(
    apiPaths.requestBranch(id),
  );
  return res.branch;
}


/* ------------------------------------------------------------------ */
/* Verificador cruzado (020)                                           */
/* ------------------------------------------------------------------ */

interface VerificationWire {
  iteration: number;
  provider?: string | null;
  model?: string | null;
  findings: Verification["findings"];
  critical_count: number;
  forced_counsel: boolean;
  created_at?: string | null;
}

/** El rastro del verificador cruzado, una entrada por iteración. Vacío si el
 * verificador está desactivado o la solicitud es anterior a la feature. */
export async function getRequestVerifications(
  id: string,
): Promise<Verification[]> {
  if (isStubMode()) {
    return [];
  }
  const rows = await apiFetch<VerificationWire[]>(
    apiPaths.requestVerifications(id),
  );
  return rows.map((r) => ({
    iteration: r.iteration,
    provider: r.provider ?? undefined,
    model: r.model ?? undefined,
    findings: r.findings ?? [],
    criticalCount: r.critical_count,
    forcedCounsel: r.forced_counsel,
    createdAt: r.created_at ?? undefined,
  }));
}
