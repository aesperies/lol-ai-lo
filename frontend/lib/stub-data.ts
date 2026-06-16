"use client";

/**
 * Dev stub data layer ("modo desarrollo").
 * Used by lib/api.ts when NEXT_PUBLIC_SUPABASE_URL is unset so that every
 * page and the full intake → parse → confirm → generate → Exit A/B flow can
 * be exercised without Supabase or the FastAPI backend.
 *
 * In-memory only: state resets on full page reload (good enough for dev).
 */

import { DOC_TYPE_CATALOG, docTypeLabel } from "@/lib/catalog";
import { translate, type DictKey } from "@/lib/i18n";
import type {
  AssignedCounsel,
  BillingReport,
  BillingRow,
  Branch,
  CounselAssignment,
  CounselComment,
  DocumentHtml,
  DocumentVersionType,
  DraftingLesson,
  FallbackLevel,
  FieldSpec,
  Fund,
  GenerationJob,
  GenerationReview,
  Gestora,
  MyUsage,
  ParsedDate,
  ParsedParams,
  ParsedParty,
  ParsedTerm,
  Precedent,
  QualityReport,
  RedlineSegment,
  Refinement,
  RequestItem,
  RetentionPolicy,
  ReviewBundle,
  ReviewPlaybook,
  SlaReport,
  TabularColumn,
  TabularColumnInput,
  TabularDocumentOption,
  TabularDocumentRef,
  TabularReview,
  TabularReviewDetail,
  TabularReviewStatusInfo,
  UserProfile,
} from "@/lib/types";
import { RETENTION_MONTHS_DEFAULT } from "@/lib/types";

/** Relative timestamp so the SLA demo chips stay meaningful over time. */
function hoursAgoIso(hours: number): string {
  return new Date(Date.now() - hours * 3_600_000).toISOString();
}

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
/* Structured intake fields (mirror of backend/models/doc_fields.py)   */
/* ------------------------------------------------------------------ */

/**
 * Per-doc_type structured field registry, keyed by the frontend slugs of
 * lib/catalog.ts (the backend additionally accepts the catalog labels).
 * Doc types absent here are freetext-only.
 */
export const STUB_DOC_TYPE_FIELDS: Record<string, FieldSpec[]> = {
  llamada_capital: [
    { key: "importe_total", labelI18nKey: "docfields.importe_total", type: "amount", required: true },
    { key: "fecha_limite_pago", labelI18nKey: "docfields.fecha_limite_pago", type: "date", required: true },
    { key: "porcentaje_compromiso", labelI18nKey: "docfields.porcentaje_compromiso", type: "percent", required: true, help: "0-100" },
    { key: "numero_llamada", labelI18nKey: "docfields.numero_llamada", type: "text", required: false },
  ],
  distribucion_inversores: [
    { key: "importe", labelI18nKey: "docfields.importe", type: "amount", required: true },
    { key: "fecha", labelI18nKey: "docfields.fecha", type: "date", required: true },
    { key: "concepto", labelI18nKey: "docfields.concepto", type: "select", required: true, options: ["desinversión", "dividendos", "intereses", "otro"] },
  ],
  nda: [
    { key: "contraparte", labelI18nKey: "docfields.contraparte", type: "party", required: true },
    { key: "duracion_meses", labelI18nKey: "docfields.duracion_meses", type: "text", required: true },
    { key: "modalidad", labelI18nKey: "docfields.modalidad", type: "select", required: true, options: ["unilateral", "recíproco"] },
  ],
  acta_reunion_consejo: [
    { key: "fecha_reunion", labelI18nKey: "docfields.fecha_reunion", type: "date", required: true },
    { key: "asistentes", labelI18nKey: "docfields.asistentes", type: "text", required: true },
    { key: "acuerdos_principales", labelI18nKey: "docfields.acuerdos_principales", type: "text", required: true },
  ],
  nombramiento_cese_administrador: [
    { key: "persona", labelI18nKey: "docfields.persona", type: "party", required: true },
    { key: "cargo", labelI18nKey: "docfields.cargo", type: "text", required: true },
    { key: "tipo", labelI18nKey: "docfields.tipo", type: "select", required: true, options: ["nombramiento", "cese"] },
    { key: "fecha_efecto", labelI18nKey: "docfields.fecha_efecto", type: "date", required: true },
  ],
  poder_especial: [
    { key: "apoderado", labelI18nKey: "docfields.apoderado", type: "party", required: true },
    { key: "facultades", labelI18nKey: "docfields.facultades", type: "text", required: true },
    { key: "vigencia", labelI18nKey: "docfields.vigencia", type: "date", required: false },
  ],
  term_sheet: [
    { key: "compania_objetivo", labelI18nKey: "docfields.compania_objetivo", type: "party", required: true },
    { key: "importe_inversion", labelI18nKey: "docfields.importe_inversion", type: "amount", required: true },
    { key: "valoracion_premoney", labelI18nKey: "docfields.valoracion_premoney", type: "amount", required: false },
    { key: "tipo_instrumento", labelI18nKey: "docfields.tipo_instrumento", type: "select", required: true, options: ["equity", "convertible", "SAFE"] },
  ],
  side_letter_inversor: [
    { key: "inversor", labelI18nKey: "docfields.inversor", type: "party", required: true },
    { key: "derechos_solicitados", labelI18nKey: "docfields.derechos_solicitados", type: "text", required: true },
  ],
  certificado_participacion_inversor: [
    { key: "inversor", labelI18nKey: "docfields.inversor", type: "party", required: true },
    { key: "fecha_referencia", labelI18nKey: "docfields.fecha_referencia", type: "date", required: true },
  ],
  extension_periodo_inversion: [
    { key: "nueva_fecha", labelI18nKey: "docfields.nueva_fecha", type: "date", required: true },
    { key: "justificacion", labelI18nKey: "docfields.justificacion", type: "text", required: false },
  ],
  extension_plazo_fondo: [
    { key: "nueva_fecha", labelI18nKey: "docfields.nueva_fecha", type: "date", required: true },
    { key: "justificacion", labelI18nKey: "docfields.justificacion", type: "text", required: false },
  ],
};

/** Structured field specs for a doc_type ([] = freetext-only). */
export function stubDocFields(docType: string): FieldSpec[] {
  return STUB_DOC_TYPE_FIELDS[docType] ?? [];
}

function fieldLabelEs(spec: FieldSpec): string {
  return translate("es", spec.labelI18nKey as DictKey);
}

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
    // Ámbar SLA chip: past half the 48h SLA, not yet over it.
    counselRequestedAt: hoursAgoIso(30),
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
  {
    id: "r-5",
    fundId: "f-2",
    fundName: STUB_FUNDS[1].name,
    gestoraId: STUB_GESTORA.id,
    userId: "u-client-2",
    requestedByName: "Jorge Molina",
    docType: "side_letter_inversor",
    docTypeLabel: docTypeLabel("side_letter_inversor"),
    freetext:
      "Side letter con el inversor institucional Pensions Nord para el Fund II reconociendo derechos de información trimestral ampliada y co-inversión preferente.",
    language: "es",
    status: "counsel_review",
    requiresCounsel: true,
    // Verde SLA chip: well within the first half of the 48h SLA.
    counselRequestedAt: hoursAgoIso(4),
    fallbackLevel: 1,
    hasMissingFields: false,
    createdAt: hoursAgoIso(5),
    updatedAt: hoursAgoIso(4),
  },
  {
    id: "r-6",
    fundId: "f-1",
    fundName: STUB_FUNDS[0].name,
    gestoraId: STUB_GESTORA.id,
    userId: "u-client-1",
    requestedByName: "Lucía Fernández",
    docType: "waiver_renuncia",
    docTypeLabel: docTypeLabel("waiver_renuncia"),
    freetext:
      "Waiver puntual de la restricción de transmisión de participaciones del artículo 9 del reglamento del Fund I a favor del inversor Faro Capital, para una transmisión entre vehículos del mismo grupo.",
    language: "es",
    status: "counsel_review",
    requiresCounsel: true,
    // Rojo SLA chip: pending past the 48h SLA ("SLA superado").
    counselRequestedAt: hoursAgoIso(55),
    fallbackLevel: 0,
    hasMissingFields: false,
    createdAt: hoursAgoIso(56),
    updatedAt: hoursAgoIso(55),
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
  // Gestora master template (modelos/): outranks regular precedents as the
  // generation base. Shown in the admin "Modelos" tab, distinct from precedents.
  {
    id: "p-4",
    gestoraId: STUB_GESTORA.id,
    fundId: null,
    docType: "nda",
    docTypeLabel: docTypeLabel("nda"),
    language: "es",
    source: "gestora_model",
    createdAt: "2026-02-01T09:00:00Z",
    versions: [
      {
        id: "pv-4a",
        precedentId: "p-4",
        versionNumber: 1,
        filePath: "/gestoras/g-demo-1/modelos/nda_modelo_v1.docx",
        status: "active",
        ragWeight: 1.0,
        activatedAt: "2026-02-01T09:05:00Z",
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
 * - structured fields filled → higher confidence, no [UNCLEAR], the values
 *   merged as authoritative (source: 'client_confirmed'), mirroring the
 *   backend deterministic post-merge.
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

  // Non-empty structured values, paired with their registry spec.
  const structured = stubDocFields(req.docType)
    .map((spec) => ({ spec, value: (req.structuredFields?.[spec.key] ?? "").trim() }))
    .filter(({ value }) => value.length > 0);

  const lowConfidence = text.length < 80 && structured.length === 0;
  const hasAmount = /\d/.test(text);

  const parties: ParsedParty[] = [
    { role: "Fondo", name: req.fundName ?? "Fondo" },
    {
      role: "Contraparte",
      name: lowConfidence ? "" : "Según descripción de la solicitud",
    },
  ];
  const keyDates: ParsedDate[] = [{ label: "Fecha de firma", date: "2026-07-01" }];
  const keyTerms: ParsedTerm[] = hasAmount
    ? [{ field: "Importe", value: "Según descripción" }]
    : [];

  // Authoritative merge (mirrors backend merge_structured_into_parsed):
  // party → parties, date → key_dates, anything else → key_terms.
  for (const { spec, value } of structured) {
    const label = fieldLabelEs(spec);
    if (spec.type === "party") {
      parties.push({ role: label, name: value, source: "client_confirmed" });
    } else if (spec.type === "date") {
      keyDates.push({ label, date: value, source: "client_confirmed" });
    } else {
      keyTerms.push({ field: label, value, source: "client_confirmed" });
    }
  }

  return {
    language: "es",
    docTypeConfirmed:
      req.docType === "other"
        ? (req.docTypeCustom ?? "other")
        : docTypeLabel(req.docType),
    parties,
    keyDates,
    jurisdiction: "España",
    governingLaw: "Ley española",
    keyTerms,
    summary: `Solicitud de ${
      req.docType === "other"
        ? (req.docTypeCustom ?? "documento")
        : docTypeLabel(req.docType)
    } para ${req.fundName ?? "el fondo"}. ${text.slice(0, 140)}${text.length > 140 ? "…" : ""}`,
    // Structured values are client-confirmed → demo shows higher confidence.
    confidence: structured.length > 0 ? 0.97 : lowConfidence ? 0.55 : 0.92,
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
    `TERCERA. Ley aplicable y jurisdicción. Este documento se rige por la ley española y las partes se someten a los juzgados y tribunales de Madrid. [SOURCE: precedent "Cláusula Décima" | "se someten a los juzgados y tribunales de Madrid"]`,
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

/** Wrap [SOURCE: …] citation markers in <sup class="doc-source">, mirroring
 * the backend converter (services/docx_html.py) so the stub viewer styles the
 * grounding citations the same way. Runs on already-escaped text. */
function stubWrapSourceMarkers(escaped: string): string {
  return escaped.replace(
    /\[SOURCE:[^\]]*?"[^"]*?"\s*\]/g,
    (m) => `<sup class="doc-source">${m}</sup>`,
  );
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
        : `<p>${stubWrapSourceMarkers(stubEscapeHtml(line))}</p>`,
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

/* ------------------------------------------------------------------ */
/* Drafting-agents demo data: critic trail, branches, lessons, playbooks */
/* ------------------------------------------------------------------ */

/** Resolve a doc_type to its drafting branch the way the backend does:
 * match the catalog group label against the known branch substrings. */
const GROUP_LABEL_TO_BRANCH: Array<[string, Branch]> = [
  ["Gobierno Corporativo", "gobierno_corporativo"],
  ["Operaciones de Fondo", "operaciones_de_fondo"],
  ["Gestión de Portfolio", "gestion_de_portfolio"],
  ["Cumplimiento y Regulatorio", "cumplimiento_regulatorio"],
  ["Contratos con Terceros", "contratos_terceros"],
];

export function stubBranchForDocType(docType: string): Branch {
  for (const group of DOC_TYPE_CATALOG) {
    if (!group.options.some((o) => o.value === docType)) continue;
    for (const [needle, branch] of GROUP_LABEL_TO_BRANCH) {
      if (group.label.includes(needle)) return branch;
    }
  }
  return "generic";
}

export function stubRequestBranch(id: string): Branch {
  const req = findRequest(id);
  return stubBranchForDocType(req?.docType ?? "other");
}

/** Per-request critic review trails. r-3 (term sheet, review_pending) has a
 * fixed major issue in round 0 then an approved round 1 — so the client
 * DocumentViewer demo shows a populated InternalReviewPanel. r-2 was derived
 * to counsel (forced_counsel demo). */
const stubReviews: Record<string, GenerationReview[]> = {
  "r-3": [
    {
      round: 0,
      approved: false,
      createdAt: "2026-06-10T16:01:00Z",
      issues: [
        {
          severity: "major",
          category: "consistency",
          problem:
            "La valoración pre-money (8.000.000 EUR) no coincide con el porcentaje de participación implícito por la inversión de 2.000.000 EUR.",
          suggestedFix:
            "Recalcular el porcentaje de participación post-money y alinear la cláusula económica.",
          location: "Cláusula 2 (Economía)",
          citation: {
            where: "Cláusula 2 (Economía)",
            quote: "valoración pre-money de 8.000.000 EUR",
          },
        },
      ],
    },
    {
      round: 1,
      approved: true,
      createdAt: "2026-06-10T16:02:00Z",
      issues: [],
    },
  ],
  // Waiver derived to counsel: critic exhausted its budget (forced_counsel).
  "r-6": [
    {
      round: 0,
      approved: false,
      createdAt: hoursAgoIso(56),
      issues: [
        {
          severity: "blocking",
          category: "legal",
          problem:
            "El waiver no identifica la cláusula del reglamento del fondo que se renuncia ni el alcance temporal de la renuncia.",
          suggestedFix:
            "Citar el artículo 9 del reglamento y limitar la renuncia a la transmisión concreta descrita.",
          location: "Parte dispositiva",
          citation: {
            where: "Parte dispositiva",
            quote: "se renuncia a los derechos derivados del reglamento del fondo",
          },
        },
      ],
    },
    {
      round: 1,
      approved: false,
      createdAt: hoursAgoIso(56),
      issues: [
        {
          severity: "major",
          category: "completeness",
          problem: "Sigue faltando la firma del órgano de gobierno competente.",
          suggestedFix: "Añadir el bloque de firma del consejo.",
          location: "Cierre",
        },
      ],
    },
  ],
};

export function stubRequestReviews(id: string): GenerationReview[] {
  return (stubReviews[id] ?? []).map((r) => ({
    ...r,
    issues: r.issues.map((i) => ({ ...i })),
  }));
}

/** Accumulated drafting lessons (gestora-siloed) across several branches. */
export const stubLessons: DraftingLesson[] = [
  {
    id: "l-1",
    gestoraId: STUB_GESTORA.id,
    branch: "operaciones_de_fondo",
    docType: "llamada_capital",
    lesson:
      "En las llamadas de capital, expresar siempre el plazo de pago en días hábiles y anclarlo a la cláusula de drawdown del LPA.",
    weight: 1.0,
    createdAt: "2026-05-02T10:00:00Z",
  },
  {
    id: "l-2",
    gestoraId: STUB_GESTORA.id,
    branch: "gestion_de_portfolio",
    docType: "term_sheet",
    lesson:
      "En term sheets no vinculantes, marcar explícitamente las carve-outs vinculantes (confidencialidad, exclusividad, ley aplicable y costes).",
    weight: 1.2,
    createdAt: "2026-05-18T14:30:00Z",
  },
  {
    id: "l-3",
    gestoraId: STUB_GESTORA.id,
    branch: "cumplimiento_regulatorio",
    docType: "notificacion_aifmd",
    lesson:
      "En notificaciones AIFMD, citar el artículo de pasaporte aplicable y la autoridad competente de cada jurisdicción de comercialización.",
    weight: 1.0,
    createdAt: "2026-05-25T09:15:00Z",
  },
  {
    id: "l-4",
    gestoraId: STUB_GESTORA.id,
    branch: "contratos_terceros",
    docType: "side_letter_inversor",
    lesson:
      "En side letters, vincular cada disposición a la cláusula del LPA que modifica y confirmar la consistencia MFN.",
    weight: 1.0,
    createdAt: "2026-06-01T11:00:00Z",
  },
  {
    id: "l-5",
    gestoraId: STUB_GESTORA.id,
    branch: "gobierno_corporativo",
    docType: "acta_reunion_consejo",
    lesson:
      "En actas de consejo, recoger siempre el quórum de constitución y de votación y la mayoría con la que se aprueba cada acuerdo.",
    weight: 0.9,
    createdAt: "2026-06-05T08:45:00Z",
  },
];

export function stubGestoraLessons(
  gestoraId: string,
  branch?: string,
): DraftingLesson[] {
  return stubLessons
    .filter((l) => l.gestoraId === gestoraId)
    .filter((l) => !branch || l.branch === branch)
    .map((l) => ({ ...l }));
}

/** Human-authored review playbooks injected into the critic. */
export const stubPlaybooksData: ReviewPlaybook[] = [
  {
    id: "pb-1",
    gestoraId: STUB_GESTORA.id,
    branch: "operaciones_de_fondo",
    docType: null,
    title: "Reglas de llamadas de capital",
    content:
      "Verificar que el plazo de pago no sea inferior a 10 días hábiles y que se identifique la cuenta de pago y las consecuencias del impago.",
    filePath: null,
    isActive: true,
    createdBy: "u-admin-1",
    createdAt: "2026-04-10T10:00:00Z",
    updatedAt: "2026-04-10T10:00:00Z",
  },
  {
    id: "pb-2",
    gestoraId: STUB_GESTORA.id,
    branch: null,
    docType: null,
    title: "Cláusula de confidencialidad obligatoria",
    content:
      "Todos los documentos deben incluir una cláusula de confidencialidad acorde con la política interna de la gestora.",
    filePath: null,
    isActive: false,
    createdBy: "u-admin-1",
    createdAt: "2026-03-22T09:00:00Z",
    updatedAt: "2026-05-01T09:00:00Z",
  },
];

export function stubPlaybooks(gestoraId: string): ReviewPlaybook[] {
  return stubPlaybooksData
    .filter((p) => p.gestoraId === gestoraId)
    .map((p) => ({ ...p }));
}

export function stubCreatePlaybook(input: {
  gestoraId: string;
  title: string;
  content: string;
  branch?: string | null;
  docType?: string | null;
  file?: File | null;
}): ReviewPlaybook {
  const pb: ReviewPlaybook = {
    id: `pb-${Date.now()}`,
    gestoraId: input.gestoraId,
    branch: (input.branch ?? null) as ReviewPlaybook["branch"],
    docType: input.docType ?? null,
    title: input.title,
    content: input.content,
    filePath: input.file ? `/gestoras/${input.gestoraId}/playbooks/${input.file.name}` : null,
    isActive: true,
    createdBy: "u-admin-1",
    createdAt: now(),
    updatedAt: now(),
  };
  stubPlaybooksData.unshift(pb);
  return { ...pb };
}

export function stubUpdatePlaybook(
  id: string,
  fields: { title?: string; content?: string; branch?: string | null; docType?: string | null },
): ReviewPlaybook {
  const pb = stubPlaybooksData.find((p) => p.id === id);
  if (!pb) throw new Error("Playbook not found");
  if (fields.title !== undefined) pb.title = fields.title;
  if (fields.content !== undefined) pb.content = fields.content;
  if (fields.branch !== undefined) pb.branch = fields.branch as ReviewPlaybook["branch"];
  if (fields.docType !== undefined) pb.docType = fields.docType;
  pb.updatedAt = now();
  return { ...pb };
}

export function stubSetPlaybookActive(id: string, active: boolean): ReviewPlaybook {
  const pb = stubPlaybooksData.find((p) => p.id === id);
  if (!pb) throw new Error("Playbook not found");
  pb.isActive = active;
  pb.updatedAt = now();
  return { ...pb };
}

export function stubDeletePlaybook(id: string): void {
  const index = stubPlaybooksData.findIndex((p) => p.id === id);
  if (index >= 0) stubPlaybooksData.splice(index, 1);
}

export function stubUploadModel(input: {
  gestoraId: string;
  docType: string;
  language: string;
  file: File;
}): void {
  const id = `p-${Date.now()}`;
  stubPrecedents.push({
    id,
    gestoraId: input.gestoraId,
    fundId: null,
    docType: input.docType,
    docTypeLabel: docTypeLabel(input.docType),
    language: input.language as Precedent["language"],
    source: "gestora_model",
    createdAt: now(),
    versions: [
      {
        id: `pv-${Date.now()}`,
        precedentId: id,
        versionNumber: 1,
        filePath: `/gestoras/${input.gestoraId}/modelos/${input.file.name}`,
        status: "draft",
        ragWeight: 0.0,
        createdBy: "u-admin-1",
      },
    ],
  });
}

/* ------------------------------------------------------------------ */
/* Admin KPI demo data: quality (#6) + counsel SLA (#8)                 */
/* ------------------------------------------------------------------ */

/** Demo numbers for GET /api/admin/quality. */
export const STUB_QUALITY_REPORT: QualityReport = {
  overall: {
    count: 23,
    avgSimilarity: 0.94,
    avgRefinements: 0.7,
    pctAcceptedAsIs: 0.61,
    pctValidated: 0.39,
  },
  byDocType: [
    {
      docType: docTypeLabel("nda"),
      count: 8,
      avgSimilarity: 0.98,
      avgRefinements: 0.3,
      pctAcceptedAsIs: 0.88,
      pctValidated: 0.12,
    },
    {
      docType: docTypeLabel("llamada_capital"),
      count: 7,
      avgSimilarity: 0.95,
      avgRefinements: 0.6,
      pctAcceptedAsIs: 0.57,
      pctValidated: 0.43,
    },
    {
      docType: docTypeLabel("term_sheet"),
      count: 5,
      avgSimilarity: 0.91,
      avgRefinements: 1.2,
      pctAcceptedAsIs: 0.4,
      pctValidated: 0.6,
    },
    {
      docType: docTypeLabel("notificacion_aifmd"),
      count: 3,
      avgSimilarity: 0.84,
      avgRefinements: 1.3,
      pctAcceptedAsIs: 0, // Level 3 always forces Exit B
      pctValidated: 1,
    },
  ],
  byGestora: [
    {
      gestoraId: STUB_GESTORA.id,
      gestoraName: STUB_GESTORA.name,
      count: 17,
      avgSimilarity: 0.95,
      avgRefinements: 0.6,
      pctAcceptedAsIs: 0.65,
      pctValidated: 0.35,
    },
    {
      gestoraId: "g-demo-2",
      gestoraName: "Atlantique Capital Gestion SAS",
      count: 6,
      avgSimilarity: 0.9,
      avgRefinements: 1.0,
      pctAcceptedAsIs: 0.5,
      pctValidated: 0.5,
    },
  ],
};

/** Demo numbers for GET /api/admin/sla (mirrors the 48h review SLA). */
export const STUB_SLA_REPORT: SlaReport = {
  slaHours: 48,
  overall: {
    pending: 3,
    pastSla: 1,
    avgValidationHours: 21.4,
    remindersSent: 2,
    escalationsSent: 1,
  },
  byCounsel: [
    {
      counselEmail: "maria.llopis@lolailolegal.es",
      pending: 3,
      pastSla: 1,
      avgValidationHours: 19.8,
      remindersSent: 2,
      escalationsSent: 0,
    },
    {
      counselEmail: "carlos.duran@lolailolegal.es",
      pending: 0,
      pastSla: 0,
      avgValidationHours: 26.5,
      remindersSent: 0,
      escalationsSent: 1,
    },
  ],
};

/* ------------------------------------------------------------------ */
/* Billing demo data (improvement #7)                                  */
/* ------------------------------------------------------------------ */

/** Current billing period (YYYY-MM, UTC) — mirrors the backend derivation. */
export function stubCurrentPeriod(): string {
  return new Date().toISOString().slice(0, 7);
}

/** The period before the current one (YYYY-MM). */
function stubPreviousPeriod(): string {
  const date = new Date();
  date.setUTCDate(1);
  date.setUTCMonth(date.getUTCMonth() - 1);
  return date.toISOString().slice(0, 7);
}

/** Demo periods for the selector (newest first). */
export function stubBillingPeriods(): string[] {
  return [stubCurrentPeriod(), stubPreviousPeriod()];
}

/**
 * Demo rows: Iberia (growth, 64/75 docs) shows the AMBER bar (≥80%);
 * Atlantique (starter, 24/20 docs + 3/2 funds) shows the RED over-limit
 * state with overage docs and an estimated overage amount.
 */
function stubBillingRowsCurrent(): BillingRow[] {
  return [
    {
      gestoraId: STUB_GESTORA.id,
      gestoraName: STUB_GESTORA.name,
      subscriptionTier: "growth",
      docsGenerated: 64,
      docsLimit: 75,
      overageDocs: 0,
      exitACount: 38,
      exitBRequested: 17,
      exitBValidated: 15,
      fundCount: 2,
      fundsLimit: 5,
      overFundsLimit: false,
      estimatedOverageEur: 0,
    },
    {
      gestoraId: "g-demo-2",
      gestoraName: "Atlantique Capital Gestion SAS",
      subscriptionTier: "starter",
      docsGenerated: 24,
      docsLimit: 20,
      overageDocs: 4,
      exitACount: 9,
      exitBRequested: 6,
      exitBValidated: 5,
      fundCount: 3,
      fundsLimit: 2,
      overFundsLimit: true,
      estimatedOverageEur: 180,
    },
  ];
}

/** Both gestoras comfortably under their limits (green bars). */
function stubBillingRowsPrevious(): BillingRow[] {
  return stubBillingRowsCurrent().map((row) => ({
    ...row,
    docsGenerated: Math.round((row.docsLimit ?? 0) * 0.4),
    overageDocs: 0,
    exitACount: Math.round(row.exitACount * 0.4),
    exitBRequested: Math.round(row.exitBRequested * 0.4),
    exitBValidated: Math.round(row.exitBValidated * 0.4),
    fundCount: Math.min(row.fundCount, row.fundsLimit ?? row.fundCount),
    overFundsLimit: false,
    estimatedOverageEur: 0,
  }));
}

/** Demo report for GET /api/admin/billing?period=… */
export function stubBillingReport(period?: string): BillingReport {
  const effective = period ?? stubCurrentPeriod();
  return {
    period: effective,
    rows:
      effective === stubCurrentPeriod()
        ? stubBillingRowsCurrent()
        : stubBillingRowsPrevious(),
  };
}

/** Demo CSV for GET /api/admin/billing/export (columns match the JSON). */
export function stubBillingCsv(period?: string): string {
  const report = stubBillingReport(period);
  const header =
    "gestora_id,gestora_name,subscription_tier,docs_generated,docs_limit," +
    "overage_docs,exit_a_count,exit_b_requested,exit_b_validated,fund_count," +
    "funds_limit,over_funds_limit,estimated_overage_eur";
  const lines = report.rows.map((r) =>
    [
      r.gestoraId,
      `"${r.gestoraName ?? ""}"`,
      r.subscriptionTier,
      r.docsGenerated,
      r.docsLimit ?? "",
      r.overageDocs,
      r.exitACount,
      r.exitBRequested,
      r.exitBValidated,
      r.fundCount,
      r.fundsLimit ?? "",
      r.overFundsLimit,
      r.estimatedOverageEur,
    ].join(","),
  );
  return [header, ...lines].join("\n");
}

/** Demo numbers for GET /api/my/usage (the stub client's gestora, growth). */
export function stubMyUsage(): MyUsage {
  return {
    billingPeriod: stubCurrentPeriod(),
    subscriptionTier: "growth",
    docsGenerated: 64,
    docsLimit: 75,
  };
}

/* ------------------------------------------------------------------ */
/* GDPR retention policies (improvement #10)                           */
/* ------------------------------------------------------------------ */

/** Explicit per-gestora policies; absence = platform default (60 months). */
const stubRetentionPolicies = new Map<string, number>();

export function stubGetRetentionPolicy(gestoraId: string): RetentionPolicy {
  const months = stubRetentionPolicies.get(gestoraId);
  return {
    gestoraId,
    months: months ?? RETENTION_MONTHS_DEFAULT,
    isDefault: months === undefined,
    updatedAt: months === undefined ? null : nowIso(),
  };
}

export function stubPutRetentionPolicy(
  gestoraId: string,
  months: number,
): RetentionPolicy {
  stubRetentionPolicies.set(gestoraId, months);
  return { gestoraId, months, isDefault: false, updatedAt: nowIso() };
}

/* ------------------------------------------------------------------ */
/* Tabular Review (010_tabular_reviews.sql) — demo grid                  */
/* ------------------------------------------------------------------ */

/** Documents pickable into a new review (precedents + generated docs). */
const STUB_TABULAR_DOC_OPTIONS: TabularDocumentOption[] = [
  {
    sourceKind: "precedent_version",
    sourceId: "pv-demo-acta-1",
    label: "Acta de Consejo — Iberia Fund I (2026-03)",
  },
  {
    sourceKind: "precedent_version",
    sourceId: "pv-demo-acta-2",
    label: "Acta de Consejo — Iberia Fund I (2026-04)",
  },
  {
    sourceKind: "request_document",
    sourceId: "doc-demo-capcall-1",
    label: "Llamada de Capital — Iberia Fund II (borrador)",
  },
  {
    sourceKind: "request_document",
    sourceId: "doc-demo-distrib-1",
    label: "Distribución a Inversores — Iberia Fund II (final)",
  },
];

export function stubTabularDocumentOptions(): TabularDocumentOption[] {
  return STUB_TABULAR_DOC_OPTIONS.map((o) => ({ ...o }));
}

const stubTabularReviewStore: TabularReviewDetail[] = [
  (() => {
    const reviewId = "tr-demo-1";
    const columns: TabularColumn[] = [
      {
        id: "trc-1",
        reviewId,
        position: 0,
        name: "Importe",
        question: "¿Cuál es el importe principal del documento?",
        colType: "monetary",
        options: null,
      },
      {
        id: "trc-2",
        reviewId,
        position: 1,
        name: "Fecha",
        question: "¿Cuál es la fecha del acuerdo?",
        colType: "date",
        options: null,
      },
      {
        id: "trc-3",
        reviewId,
        position: 2,
        name: "¿Quórum?",
        question: "¿Se alcanzó el quórum necesario?",
        colType: "yes_no",
        options: null,
      },
      {
        id: "trc-4",
        reviewId,
        position: 3,
        name: "Jurisdicción",
        question: "¿Cuál es la jurisdicción aplicable?",
        colType: "tag",
        options: ["España", "Francia", "Alemania", "Luxemburgo"],
      },
    ];
    const documents: TabularDocumentRef[] = [
      {
        id: "trd-1",
        reviewId,
        position: 0,
        sourceKind: "precedent_version",
        sourceId: "pv-demo-acta-1",
        label: "Acta de Consejo — Iberia Fund I (2026-03)",
      },
      {
        id: "trd-2",
        reviewId,
        position: 1,
        sourceKind: "precedent_version",
        sourceId: "pv-demo-acta-2",
        label: "Acta de Consejo — Iberia Fund I (2026-04)",
      },
      {
        id: "trd-3",
        reviewId,
        position: 2,
        sourceKind: "request_document",
        sourceId: "doc-demo-capcall-1",
        label: "Llamada de Capital — Iberia Fund II (borrador)",
      },
    ];
    const cells: TabularReviewDetail["cells"] = [
      // Row 1
      {
        id: "trx-1",
        documentId: "trd-1",
        columnId: "trc-1",
        value: "€500.000",
        reasoning: "El acta aprueba una llamada de capital por ese importe.",
        citation: {
          page: 1,
          quote: "se aprueba una llamada de capital por importe de 500.000 euros",
        },
        status: "done",
        error: null,
      },
      {
        id: "trx-2",
        documentId: "trd-1",
        columnId: "trc-2",
        value: "2026-03-15",
        reasoning: "La reunión del consejo se celebró en esa fecha.",
        citation: { page: 1, quote: "reunido el consejo el 15 de marzo de 2026" },
        status: "done",
        error: null,
      },
      {
        id: "trx-3",
        documentId: "trd-1",
        columnId: "trc-3",
        value: "yes",
        reasoning: "Asistieron todos los consejeros.",
        citation: { page: 1, quote: "con la asistencia de la totalidad de los consejeros" },
        status: "done",
        error: null,
      },
      {
        id: "trx-4",
        documentId: "trd-1",
        columnId: "trc-4",
        value: "España",
        reasoning: "El acta se rige por la legislación española.",
        citation: { page: 2, quote: "de conformidad con la legislación española aplicable" },
        status: "done",
        error: null,
      },
      // Row 2
      {
        id: "trx-5",
        documentId: "trd-2",
        columnId: "trc-1",
        value: "€750.000",
        reasoning: "Segunda llamada de capital aprobada.",
        citation: { page: 1, quote: "una segunda llamada de capital de 750.000 euros" },
        status: "done",
        error: null,
      },
      {
        id: "trx-6",
        documentId: "trd-2",
        columnId: "trc-2",
        value: "2026-04-20",
        reasoning: "Fecha de la reunión del consejo.",
        citation: { page: 1, quote: "el 20 de abril de 2026" },
        status: "done",
        error: null,
      },
      {
        id: "trx-7",
        documentId: "trd-2",
        columnId: "trc-3",
        value: "yes",
        reasoning: "Quórum alcanzado por mayoría.",
        citation: { page: 1, quote: "alcanzado el quórum reglamentario" },
        status: "done",
        error: null,
      },
      {
        id: "trx-8",
        documentId: "trd-2",
        columnId: "trc-4",
        value: "España",
        reasoning: "Misma jurisdicción que el acta anterior.",
        citation: { page: 2, quote: "legislación española" },
        status: "done",
        error: null,
      },
      // Row 3 — includes one error cell to exercise the error state.
      {
        id: "trx-9",
        documentId: "trd-3",
        columnId: "trc-1",
        value: "€1.200.000",
        reasoning: "Importe total de la llamada de capital.",
        citation: { page: null, quote: "importe total de 1.200.000 euros" },
        status: "done",
        error: null,
      },
      {
        id: "trx-10",
        documentId: "trd-3",
        columnId: "trc-2",
        value: "2026-05-02",
        reasoning: "Fecha de emisión de la notificación.",
        citation: { page: null, quote: "con fecha 2 de mayo de 2026" },
        status: "done",
        error: null,
      },
      {
        id: "trx-11",
        documentId: "trd-3",
        columnId: "trc-3",
        value: null,
        reasoning: null,
        citation: null,
        status: "error",
        error: "El servicio de IA no pudo procesar esta celda.",
      },
      {
        id: "trx-12",
        documentId: "trd-3",
        columnId: "trc-4",
        value: "España",
        reasoning: "Documento sujeto a derecho español.",
        citation: { page: null, quote: "derecho español" },
        status: "done",
        error: null,
      },
    ];
    return {
      id: reviewId,
      gestoraId: STUB_GESTORA.id,
      fundId: STUB_FUNDS[0].id,
      createdBy: "u-client-1",
      title: "Comparativa de actas y llamadas de capital",
      status: "complete",
      createdAt: hoursAgoIso(30),
      updatedAt: hoursAgoIso(29),
      columns,
      documents,
      cells,
    };
  })(),
];

function cloneTabularDetail(r: TabularReviewDetail): TabularReviewDetail {
  return {
    ...r,
    columns: r.columns.map((c) => ({ ...c })),
    documents: r.documents.map((d) => ({ ...d })),
    cells: r.cells.map((c) => ({ ...c })),
  };
}

export function stubTabularReviews(): TabularReview[] {
  return stubTabularReviewStore.map((r) => ({
    id: r.id,
    gestoraId: r.gestoraId,
    fundId: r.fundId,
    createdBy: r.createdBy,
    title: r.title,
    status: r.status,
    createdAt: r.createdAt,
    updatedAt: r.updatedAt,
  }));
}

export function stubTabularReview(id: string): TabularReviewDetail | undefined {
  const found = stubTabularReviewStore.find((r) => r.id === id);
  return found ? cloneTabularDetail(found) : undefined;
}

function findStubReview(id: string): TabularReviewDetail {
  const found = stubTabularReviewStore.find((r) => r.id === id);
  if (!found) throw new Error("Tabular review not found");
  return found;
}

export function stubCreateTabularReview(input: {
  title: string;
  fundId?: string | null;
  columns: TabularColumnInput[];
  documents: TabularDocumentOption[];
}): TabularReviewDetail {
  const reviewId = `tr-${Date.now()}`;
  const columns: TabularColumn[] = input.columns.map((c, i) => ({
    id: `trc-${Date.now()}-${i}`,
    reviewId,
    position: i,
    name: c.name,
    question: c.question,
    colType: c.colType,
    options: c.options ?? null,
  }));
  const documents: TabularDocumentRef[] = input.documents.map((d, i) => ({
    id: `trd-${Date.now()}-${i}`,
    reviewId,
    position: i,
    sourceKind: d.sourceKind,
    sourceId: d.sourceId,
    label: d.label,
  }));
  const cells: TabularReviewDetail["cells"] = [];
  for (const d of documents) {
    for (const c of columns) {
      cells.push({
        id: `trx-${d.id}-${c.id}`,
        documentId: d.id,
        columnId: c.id,
        value: null,
        reasoning: null,
        citation: null,
        status: "pending",
        error: null,
      });
    }
  }
  const review: TabularReviewDetail = {
    id: reviewId,
    gestoraId: STUB_GESTORA.id,
    fundId: input.fundId ?? null,
    createdBy: "u-client-1",
    title: input.title,
    status: "draft",
    createdAt: nowIso(),
    updatedAt: nowIso(),
    columns,
    documents,
    cells,
  };
  stubTabularReviewStore.unshift(review);
  return cloneTabularDetail(review);
}

/** Demo "extraction": fills every pending cell with a plausible typed value. */
export function stubRunTabularReview(id: string): void {
  const review = findStubReview(id);
  review.status = "running";
  for (const cell of review.cells) {
    if (cell.status !== "pending") continue;
    const col = review.columns.find((c) => c.id === cell.columnId);
    cell.status = "done";
    cell.value =
      col?.colType === "monetary"
        ? "€500.000"
        : col?.colType === "date"
          ? "2026-06-01"
          : col?.colType === "percent"
            ? "12,5%"
            : col?.colType === "number"
              ? "3"
              : col?.colType === "yes_no"
                ? "yes"
                : col?.colType === "tag"
                  ? (col.options?.[0] ?? "N/D")
                  : "Valor extraído de ejemplo";
    cell.reasoning = "Valor extraído del documento (modo demostración).";
    cell.citation = {
      page: 1,
      quote: "fragmento textual de ejemplo del documento",
    };
    cell.error = null;
  }
  review.status = "complete";
  review.updatedAt = nowIso();
}

export function stubTabularReviewStatus(id: string): TabularReviewStatusInfo {
  const review = findStubReview(id);
  return {
    id,
    status: review.status,
    cellTotal: review.cells.length,
    cellDone: review.cells.filter((c) => c.status === "done").length,
    cellError: review.cells.filter((c) => c.status === "error").length,
  };
}

export function stubAddTabularColumn(
  id: string,
  column: TabularColumnInput,
): TabularReviewDetail {
  const review = findStubReview(id);
  const position =
    review.columns.reduce((max, c) => Math.max(max, c.position), -1) + 1;
  const newColumn: TabularColumn = {
    id: `trc-${Date.now()}`,
    reviewId: id,
    position,
    name: column.name,
    question: column.question,
    colType: column.colType,
    options: column.options ?? null,
  };
  review.columns.push(newColumn);
  for (const d of review.documents) {
    review.cells.push({
      id: `trx-${d.id}-${newColumn.id}`,
      documentId: d.id,
      columnId: newColumn.id,
      value: null,
      reasoning: null,
      citation: null,
      status: "pending",
      error: null,
    });
  }
  review.updatedAt = nowIso();
  return cloneTabularDetail(review);
}

export function stubDeleteTabularColumn(
  id: string,
  columnId: string,
): TabularReviewDetail {
  const review = findStubReview(id);
  review.columns = review.columns.filter((c) => c.id !== columnId);
  review.cells = review.cells.filter((c) => c.columnId !== columnId);
  review.updatedAt = nowIso();
  return cloneTabularDetail(review);
}

export function stubDeleteTabularDocument(
  id: string,
  documentId: string,
): TabularReviewDetail {
  const review = findStubReview(id);
  review.documents = review.documents.filter((d) => d.id !== documentId);
  review.cells = review.cells.filter((c) => c.documentId !== documentId);
  review.updatedAt = nowIso();
  return cloneTabularDetail(review);
}

export function stubTabularReviewCsv(id: string): string {
  const review = findStubReview(id);
  const byPos = new Map<string, string>();
  for (const c of review.cells) {
    byPos.set(`${c.documentId}:${c.columnId}`, c.value ?? "");
  }
  const escape = (s: string) =>
    /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  const lines: string[] = [];
  lines.push("# Citas (página + cita textual) disponibles solo en la aplicación.");
  lines.push(
    ["Documento", ...review.columns.map((c) => c.name)].map(escape).join(","),
  );
  for (const d of review.documents) {
    const row = [
      d.label ?? d.sourceId,
      ...review.columns.map((c) => byPos.get(`${d.id}:${c.id}`) ?? ""),
    ];
    lines.push(row.map(escape).join(","));
  }
  return lines.join("\n");
}
