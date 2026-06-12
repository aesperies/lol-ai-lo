"use client";

/**
 * Dev stub data layer ("modo desarrollo").
 * Used by lib/api.ts when NEXT_PUBLIC_SUPABASE_URL is unset so that every
 * page and the full intake → parse → confirm → generate → Exit A/B flow can
 * be exercised without Supabase or the FastAPI backend.
 *
 * In-memory only: state resets on full page reload (good enough for dev).
 */

import { docTypeLabel } from "@/lib/catalog";
import type {
  AssignedCounsel,
  CounselAssignment,
  CounselComment,
  DocumentHtml,
  DocumentVersionType,
  FallbackLevel,
  Fund,
  GenerationJob,
  Gestora,
  ParsedParams,
  Precedent,
  RedlineSegment,
  Refinement,
  RequestItem,
  ReviewBundle,
  UserProfile,
} from "@/lib/types";

export const STUB_GESTORA: Gestora = {
  id: "g-demo-1",
  name: "Iberia Venture Partners SGEIC, S.A.",
  driveFolderId: null,
  subscriptionTier: "growth",
  billingEmail: "facturacion@iberiavp.es",
  createdAt: "2026-01-15T09:00:00Z",
};

export const STUB_FUNDS: Fund[] = [
  {
    id: "f-1",
    gestoraId: STUB_GESTORA.id,
    name: "Iberia Ventures Fund I, FCRE",
    jurisdiction: "España",
    createdAt: "2026-01-15T09:05:00Z",
  },
  {
    id: "f-2",
    gestoraId: STUB_GESTORA.id,
    name: "Iberia Ventures Fund II, FCRE",
    jurisdiction: "España",
    createdAt: "2026-02-01T10:00:00Z",
  },
];

export const STUB_USERS_BY_ROLE: Record<string, UserProfile> = {
  client: {
    id: "u-client-1",
    email: "lucia.fernandez@iberiavp.es",
    role: "client",
    gestoraId: STUB_GESTORA.id,
    name: "Lucía Fernández",
  },
  counsel: {
    id: "u-counsel-1",
    email: "maria.llopis@lolailolegal.es",
    role: "counsel",
    gestoraId: null,
    name: "María Llopis",
  },
  admin: {
    id: "u-admin-1",
    email: "admin@lolailo.es",
    role: "admin",
    gestoraId: null,
    name: "Equipo Lol-AI-lo",
  },
};

export const STUB_ALL_USERS: UserProfile[] = [
  STUB_USERS_BY_ROLE.client,
  {
    id: "u-client-2",
    email: "jorge.molina@iberiavp.es",
    role: "client",
    gestoraId: STUB_GESTORA.id,
    name: "Jorge Molina",
  },
  STUB_USERS_BY_ROLE.counsel,
  STUB_USERS_BY_ROLE.admin,
];

// TODO backend: turnaround is fixed at 48h for now (configurable later).
export const STUB_ASSIGNED_COUNSEL: AssignedCounsel = {
  name: "María Llopis",
  email: "maria.llopis@lolailolegal.es",
  isPrimary: true,
  turnaroundHours: 48,
};

export const stubCounselAssignments: CounselAssignment[] = [
  {
    id: "ca-1",
    gestoraId: STUB_GESTORA.id,
    counselUserId: "u-counsel-1",
    counselEmail: "maria.llopis@lolailolegal.es",
    isPrimary: true,
    createdAt: "2026-02-01T09:00:00Z",
  },
];

/* ------------------------------------------------------------------ */
/* Mutable in-memory store                                             */
/* ------------------------------------------------------------------ */

let requestSeq = 100;

const now = () => new Date().toISOString();

export const stubRequests: RequestItem[] = [
  {
    id: "r-1",
    fundId: "f-1",
    fundName: STUB_FUNDS[0].name,
    gestoraId: STUB_GESTORA.id,
    userId: "u-client-1",
    requestedByName: "Lucía Fernández",
    docType: "nda",
    docTypeLabel: docTypeLabel("nda"),
    freetext:
      "NDA mutuo entre Iberia Ventures Fund I y la startup Solaria Robotics SL para evaluar una posible inversión serie A. Duración 2 años, ley española.",
    language: "es",
    status: "delivered",
    requiresCounsel: false,
    exitAAcknowledgedAt: "2026-06-01T12:30:00Z",
    fallbackLevel: 0,
    hasMissingFields: false,
    createdAt: "2026-06-01T12:00:00Z",
    updatedAt: "2026-06-01T12:30:00Z",
  },
  {
    id: "r-2",
    fundId: "f-1",
    fundName: STUB_FUNDS[0].name,
    gestoraId: STUB_GESTORA.id,
    userId: "u-client-1",
    requestedByName: "Lucía Fernández",
    docType: "llamada_capital",
    docTypeLabel: docTypeLabel("llamada_capital"),
    freetext:
      "Llamada de capital del 15% del compromiso total de los inversores del Fund I, pago en 10 días hábiles, para la inversión aprobada en Solaria Robotics SL por importe de 1.500.000 EUR.",
    language: "es",
    status: "counsel_review",
    requiresCounsel: true,
    fallbackLevel: 0,
    hasMissingFields: false,
    createdAt: "2026-06-08T09:00:00Z",
    updatedAt: "2026-06-08T09:20:00Z",
  },
  {
    id: "r-3",
    fundId: "f-2",
    fundName: STUB_FUNDS[1].name,
    gestoraId: STUB_GESTORA.id,
    userId: "u-client-1",
    requestedByName: "Lucía Fernández",
    docType: "term_sheet",
    docTypeLabel: docTypeLabel("term_sheet"),
    freetext:
      "Term sheet no vinculante para inversión de 2.000.000 EUR en la sociedad Quantum Foods SL, valoración pre-money de 8.000.000 EUR, con derecho de tanteo y cláusula antidilución weighted average.",
    language: "es",
    status: "review_pending",
    requiresCounsel: false,
    fallbackLevel: 0,
    hasMissingFields: false,
    createdAt: "2026-06-10T16:00:00Z",
    updatedAt: "2026-06-10T16:02:00Z",
  },
  {
    id: "r-4",
    fundId: "f-2",
    fundName: STUB_FUNDS[1].name,
    gestoraId: STUB_GESTORA.id,
    userId: "u-client-2",
    requestedByName: "Jorge Molina",
    docType: "notificacion_aifmd",
    docTypeLabel: docTypeLabel("notificacion_aifmd"),
    freetext:
      "Notificación AIFMD a la CNMV para la comercialización del Fund II en Francia y Alemania a partir del 1 de septiembre de 2026, bajo el pasaporte de comercialización del artículo 32.",
    language: "es",
    status: "review_pending",
    requiresCounsel: false,
    fallbackLevel: 3,
    hasMissingFields: false,
    createdAt: "2026-06-11T08:30:00Z",
    updatedAt: "2026-06-11T08:33:00Z",
  },
];

export const stubPrecedents: Precedent[] = [
  {
    id: "p-1",
    gestoraId: STUB_GESTORA.id,
    fundId: "f-1",
    docType: "nda",
    docTypeLabel: docTypeLabel("nda"),
    language: "es",
    source: "manual_upload",
    createdAt: "2026-02-10T10:00:00Z",
    versions: [
      {
        id: "pv-1a",
        precedentId: "p-1",
        versionNumber: 1,
        filePath: "/gestoras/g-demo-1/precedents/nda_v1.docx",
        status: "superseded",
        ragWeight: 0.3,
        activatedAt: "2026-02-10T10:05:00Z",
        supersededAt: "2026-04-02T09:00:00Z",
        createdBy: "u-admin-1",
      },
      {
        id: "pv-1b",
        precedentId: "p-1",
        versionNumber: 2,
        filePath: "/gestoras/g-demo-1/precedents/nda_v2.docx",
        status: "active",
        ragWeight: 1.0,
        activatedAt: "2026-04-02T09:00:00Z",
        createdBy: "u-admin-1",
      },
    ],
  },
  {
    id: "p-2",
    gestoraId: STUB_GESTORA.id,
    fundId: null,
    docType: "llamada_capital",
    docTypeLabel: docTypeLabel("llamada_capital"),
    language: "es",
    source: "validated_output",
    createdAt: "2026-03-20T15:00:00Z",
    versions: [
      {
        id: "pv-2a",
        precedentId: "p-2",
        versionNumber: 1,
        filePath: "/gestoras/g-demo-1/precedents/capital_call_v1.docx",
        status: "active",
        ragWeight: 1.0,
        activatedAt: "2026-03-20T15:05:00Z",
        createdBy: "u-counsel-1",
      },
    ],
  },
  {
    id: "p-3",
    gestoraId: STUB_GESTORA.id,
    fundId: null,
    docType: "term_sheet",
    docTypeLabel: docTypeLabel("term_sheet"),
    language: "es",
    source: "slp_curated",
    createdAt: "2026-01-20T11:00:00Z",
    versions: [
      {
        id: "pv-3a",
        precedentId: "p-3",
        versionNumber: 1,
        filePath: "/lol-ai-lo-templates/slp-curated/es/term_sheet.docx",
        status: "draft",
        ragWeight: 0.7,
        createdBy: "u-admin-1",
      },
    ],
  },
];

export const stubGestoras: Gestora[] = [
  STUB_GESTORA,
  {
    id: "g-demo-2",
    name: "Atlantique Capital Gestion SAS",
    driveFolderId: null,
    subscriptionTier: "starter",
    billingEmail: "billing@atlantique.fr",
    createdAt: "2026-03-01T09:00:00Z",
  },
];

const stubComments: CounselComment[] = [
  {
    id: "c-1",
    requestId: "r-2",
    author: "María Llopis",
    text: "Revisar el plazo de pago: el reglamento del fondo fija 12 días hábiles, no 10.",
    createdAt: "2026-06-09T10:00:00Z",
  },
];

/* ------------------------------------------------------------------ */
/* Stub behaviors                                                      */
/* ------------------------------------------------------------------ */

export function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export function nextRequestId(): string {
  requestSeq += 1;
  return `r-${requestSeq}`;
}

export function findRequest(id: string): RequestItem | undefined {
  return stubRequests.find((r) => r.id === id);
}

export function nowIso(): string {
  return now();
}

/**
 * Simulated intake parser. Deterministic heuristics good enough to demo:
 * - doc_type 'other' + vague text → unclassifiable
 * - short freetext → low-confidence [UNCLEAR] fields, generation_ready false
 * - otherwise ready, with parties/dates/terms naively derived
 */
export function stubParse(req: RequestItem): ParsedParams {
  const text = req.freetext;

  if (req.docType === "other" && !req.docTypeCustom && text.length < 120) {
    return {
      language: "es",
      docTypeConfirmed: "other",
      parties: [],
      keyDates: [],
      jurisdiction: "",
      governingLaw: "",
      keyTerms: [],
      summary: "",
      confidence: 0.3,
      unclearFields: ["doc_type", "parties"],
      generationReady: false,
      unclassifiable: true,
    };
  }

  const lowConfidence = text.length < 80;
  const hasAmount = /\d/.test(text);

  return {
    language: "es",
    docTypeConfirmed:
      req.docType === "other"
        ? (req.docTypeCustom ?? "other")
        : docTypeLabel(req.docType),
    parties: [
      { role: "Fondo", name: req.fundName ?? "Fondo" },
      {
        role: "Contraparte",
        name: lowConfidence ? "" : "Según descripción de la solicitud",
      },
    ],
    keyDates: [{ label: "Fecha de firma", date: "2026-07-01" }],
    jurisdiction: "España",
    governingLaw: "Ley española",
    keyTerms: hasAmount
      ? [{ field: "Importe", value: "Según descripción" }]
      : [],
    summary: `Solicitud de ${
      req.docType === "other"
        ? (req.docTypeCustom ?? "documento")
        : docTypeLabel(req.docType)
    } para ${req.fundName ?? "el fondo"}. ${text.slice(0, 140)}${text.length > 140 ? "…" : ""}`,
    confidence: lowConfidence ? 0.55 : 0.92,
    unclearFields: lowConfidence ? ["parties", "key_dates"] : [],
    generationReady: !lowConfidence,
  };
}

/** Simulated fallback level: regulatory notifications have no precedent (Level 3 → forces Exit B). */
export function stubFallbackLevel(docType: string): FallbackLevel {
  if (docType === "notificacion_aifmd" || docType === "comunicacion_regulador")
    return 3;
  if (docType === "other") return 2;
  if (stubPrecedents.some((p) => p.docType === docType)) return 0;
  return 1;
}

/** Simulated [MISSING] detection: no figures in the freetext → a [MISSING: importe] field. */
export function stubHasMissing(req: RequestItem): boolean {
  return !/\d/.test(req.freetext);
}

/* ------------------------------------------------------------------ */
/* Simulated async generation jobs (202 + poll)                        */
/* ------------------------------------------------------------------ */

/** Include this marker in the freetext to demo a failed generation job. */
export const STUB_FAIL_GENERATION_MARKER = "[demo:fail]";

/** Include this marker in a refinement instruction to demo the
 * [REFINEMENT-UNCLEAR] failure path (previous iteration stays intact). */
export const STUB_UNCLEAR_REFINEMENT_MARKER = "[demo:unclear]";

interface StubJob extends GenerationJob {
  requestId: string;
  polls: number;
  /** Set when the job was started by a refinement (not the initial generation). */
  refinementId?: string;
}

let jobSeq = 0;
const stubJobs = new Map<string, StubJob>();

/** Starts a simulated generation job for a request (status 'queued'). */
export function stubStartGenerationJob(req: RequestItem): GenerationJob {
  jobSeq += 1;
  const job: StubJob = {
    id: `job-${jobSeq}`,
    requestId: req.id,
    status: "queued",
    attempts: 0,
    lastError: null,
    polls: 0,
  };
  stubJobs.set(req.id, job);
  return { id: job.id, status: job.status, attempts: job.attempts };
}

/**
 * Each poll advances the simulated job: queued → running → succeeded after
 * ~2 polls (or failed when the freetext contains STUB_FAIL_GENERATION_MARKER,
 * mirroring the backend's final-failure revert to 'confirmed').
 *
 * Refinement jobs (job.refinementId set) instead resolve the refinement:
 * applied → new iteration, or — instruction containing
 * STUB_UNCLEAR_REFINEMENT_MARKER — failed with a surfaced reason while the
 * previous iteration stays intact (the job itself succeeds, like the
 * backend's handled [REFINEMENT-UNCLEAR] outcome).
 */
export function stubPollGenerationJob(requestId: string): GenerationJob | undefined {
  const job = stubJobs.get(requestId);
  const req = findRequest(requestId);
  if (!job || !req) return undefined;
  job.polls += 1;

  if (job.status === "queued") {
    job.status = "running";
    job.attempts = 1;
  } else if (job.status === "running" && job.polls >= 2) {
    const refinement = job.refinementId
      ? stubRefinements.find((r) => r.id === job.refinementId)
      : undefined;
    if (refinement) {
      job.status = "succeeded";
      if (refinement.instruction.includes(STUB_UNCLEAR_REFINEMENT_MARKER)) {
        refinement.status = "failed";
        refinement.error =
          "La instrucción es ambigua: especifica el cambio exacto que debe aplicarse (demo).";
      } else {
        refinement.status = "applied";
        refinement.appliedAt = nowIso();
      }
      req.status = "review_pending"; // previous draft stays valid on failure
    } else if (req.freetext.includes(STUB_FAIL_GENERATION_MARKER)) {
      job.status = "failed";
      job.attempts = 3;
      job.lastError = "Error simulado de generación (demo).";
      req.status = "confirmed"; // backend reverts so the client can retry
    } else {
      job.status = "succeeded";
      req.fallbackLevel = stubFallbackLevel(req.docType);
      req.hasMissingFields = stubHasMissing(req);
      req.status = "review_pending";
    }
    req.updatedAt = nowIso();
  }
  return { id: job.id, status: job.status, attempts: job.attempts, lastError: job.lastError };
}

/* ------------------------------------------------------------------ */
/* Simulated iterative refinements (improvement #4)                    */
/* ------------------------------------------------------------------ */

let refinementSeq = 0;

export const stubRefinements: Refinement[] = [];

function stubAppliedRefinements(requestId: string, upTo?: number): Refinement[] {
  return stubRefinements.filter(
    (r) =>
      r.requestId === requestId &&
      r.status === "applied" &&
      (upTo === undefined || r.iteration <= upTo),
  );
}

/** Highest applied iteration for a request (0 = original generation). */
export function stubLatestIteration(requestId: string): number {
  return stubAppliedRefinements(requestId).reduce(
    (max, r) => Math.max(max, r.iteration),
    0,
  );
}

/**
 * Starts a simulated refinement: creates the pending refinements row and an
 * async job to poll (same 202 + poll contract as the initial generation).
 */
export function stubStartRefinement(
  req: RequestItem,
  instruction: string,
): { refinementId: string; jobId: string; iteration: number } {
  refinementSeq += 1;
  const iteration =
    stubRefinements
      .filter((r) => r.requestId === req.id)
      .reduce((max, r) => Math.max(max, r.iteration), 0) + 1;
  const refinement: Refinement = {
    id: `ref-${refinementSeq}`,
    requestId: req.id,
    iteration,
    instruction,
    status: "pending",
    error: null,
    createdAt: nowIso(),
    appliedAt: null,
  };
  stubRefinements.push(refinement);
  req.status = "generating";
  req.updatedAt = nowIso();
  const job = stubStartGenerationJob(req);
  const stubJob = stubJobs.get(req.id);
  if (stubJob) stubJob.refinementId = refinement.id;
  return { refinementId: refinement.id, jobId: job.id, iteration };
}

/**
 * Draft text for a given refinement iteration (default: latest applied).
 * Refined iterations visibly change the SEGUNDA clause and append one
 * "Ajuste vN" note per applied refinement, so the demo shows real diffs.
 */
export function stubDraftText(req: RequestItem, iteration?: number): string {
  const upTo = iteration ?? stubLatestIteration(req.id);
  const applied = stubAppliedRefinements(req.id, upTo);
  const label = req.docTypeLabel ?? docTypeLabel(req.docType);
  const segunda =
    applied.length > 0
      ? "El plazo de preaviso será de quince (15) días naturales. [DEVIATION: ajuste solicitado por el cliente]"
      : req.hasMissingFields
        ? "[MISSING: importe]"
        : "Según los términos confirmados en la solicitud.";
  return [
    `${label.toUpperCase()}`,
    ``,
    `Fondo: ${req.fundName ?? ""}`,
    `Gestora: ${STUB_GESTORA.name}`,
    `Jurisdicción: España — Ley aplicable: Ley española`,
    ``,
    `EXPONEN`,
    ``,
    `I. Que el presente documento se otorga en el marco de la operativa del fondo arriba indicado, conforme a las instrucciones del cliente: "${req.freetext.slice(0, 200)}${req.freetext.length > 200 ? "…" : ""}"`,
    ``,
    `II. Que las partes se reconocen mutuamente capacidad legal suficiente para suscribir el presente documento.`,
    ``,
    `CLÁUSULAS`,
    ``,
    `PRIMERA. Objeto. ${label} otorgado conforme a los estándares de mercado de venture capital europeo de 2026.`,
    ``,
    `SEGUNDA. Plazos y condiciones. ${segunda}`,
    ``,
    `TERCERA. Ley aplicable y jurisdicción. Este documento se rige por la ley española y las partes se someten a los juzgados y tribunales de Madrid.`,
    ...applied.map((r) => [``, `— Ajuste v${r.iteration} aplicado: ${r.instruction} —`]).flat(),
    ``,
    `— Documento generado por Lol-AI-lo (borrador${upTo > 0 ? ` v${upTo}` : ""}) —`,
  ].join("\n");
}

/** Redline vs the SAME original precedent base, cumulative per iteration. */
export function stubRedline(req: RequestItem, iteration?: number): RedlineSegment[] {
  const upTo = iteration ?? stubLatestIteration(req.id);
  const applied = stubAppliedRefinements(req.id, upTo);
  return [
    { type: "eq", text: "CLÁUSULAS\n\nPRIMERA. Objeto. " },
    { type: "del", text: "Acuerdo de confidencialidad entre las partes identificadas en el precedente. " },
    {
      type: "ins",
      text: `${req.docTypeLabel ?? docTypeLabel(req.docType)} otorgado conforme a los estándares de mercado de venture capital europeo de 2026. `,
    },
    { type: "eq", text: "\n\nSEGUNDA. Plazos y condiciones. " },
    { type: "del", text: "El plazo de vigencia será de dos (2) años. " },
    {
      type: "ins",
      text:
        applied.length > 0
          ? "El plazo de preaviso será de quince (15) días naturales. "
          : req.hasMissingFields
            ? "[MISSING: importe] "
            : "Según los términos confirmados en la solicitud. ",
    },
    {
      type: "eq",
      text: "\n\nTERCERA. Ley aplicable y jurisdicción. Este documento se rige por la ley española y las partes se someten a los juzgados y tribunales de Madrid.",
    },
    ...applied.map(
      (r): RedlineSegment => ({
        type: "ins",
        text: `\n\n— Ajuste v${r.iteration} aplicado: ${r.instruction} —`,
      }),
    ),
  ];
}

/* ------------------------------------------------------------------ */
/* Simulated in-browser document HTML (mirrors services/docx_html.py)  */
/* ------------------------------------------------------------------ */

function stubEscapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

/** ALL-CAPS short lines become headings, like the backend heuristic. */
function stubIsHeading(line: string): boolean {
  return (
    line.length > 0 &&
    line.length <= 100 &&
    line === line.toUpperCase() &&
    /[A-ZÁÉÍÓÚÑ]/.test(line)
  );
}

/**
 * Demo HTML for the in-browser viewer (same whitelist + fixed class names as
 * the backend converter: p/h2/ins.rl-ins/del.rl-del/br only, text escaped).
 */
export function stubDocumentHtml(
  req: RequestItem,
  type: DocumentVersionType,
  iteration?: number,
): DocumentHtml {
  if (type === "redline") {
    const segments = stubRedline(req, iteration);
    const inline = segments
      .map((s) => {
        const text = stubEscapeHtml(s.text).replaceAll("\n", "<br/>");
        if (s.type === "ins") return `<ins class="rl-ins">${text}</ins>`;
        if (s.type === "del") return `<del class="rl-del">${text}</del>`;
        return text;
      })
      .join("");
    return {
      html: `<h2>REDLINE VS. PRECEDENTE</h2>\n<p>${inline}</p>`,
      stats: {
        insertions: segments.filter((s) => s.type === "ins").length,
        deletions: segments.filter((s) => s.type === "del").length,
      },
    };
  }
  const blocks = stubDraftText(req, iteration)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) =>
      stubIsHeading(line)
        ? `<h2>${stubEscapeHtml(line)}</h2>`
        : `<p>${stubEscapeHtml(line)}</p>`,
    );
  return { html: blocks.join("\n"), stats: { insertions: 0, deletions: 0 } };
}

export function stubReviewBundle(req: RequestItem): ReviewBundle {
  return {
    request: req,
    draftText: stubDraftText(req),
    redline: stubRedline(req),
    comments: stubComments.filter((c) => c.requestId === req.id),
  };
}

export function stubAddComment(
  requestId: string,
  author: string,
  text: string,
): CounselComment {
  const comment: CounselComment = {
    id: `c-${Date.now()}`,
    requestId,
    author,
    text,
    createdAt: now(),
  };
  stubComments.push(comment);
  return comment;
}
