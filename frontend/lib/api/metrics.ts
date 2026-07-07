"use client";

/* ------------------------------------------------------------------ */
/* Admin KPIs: quality (improvement #6) + counsel SLA (improvement #8)  */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type { QualityReport, QualityStats, SlaReport, SlaStats } from "@/lib/types";
import { STUB_LATENCY, apiFetch, apiPaths, stubCall } from "./http";

interface QualityStatsWire {
  count: number;
  avg_similarity: number | null;
  avg_refinements: number | null;
  pct_accepted_as_is: number | null;
  pct_validated: number | null;
}

function mapQualityStats(wire: QualityStatsWire): QualityStats {
  return {
    count: wire.count,
    avgSimilarity: wire.avg_similarity,
    avgRefinements: wire.avg_refinements,
    pctAcceptedAsIs: wire.pct_accepted_as_is,
    pctValidated: wire.pct_validated,
  };
}

/** Aggregated quality stats (admin-only). */
export async function getQualityReport(): Promise<QualityReport> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.STUB_QUALITY_REPORT;
    });
  }
  const res = await apiFetch<{
    overall: QualityStatsWire;
    by_doc_type: Array<QualityStatsWire & { doc_type: string }>;
    by_gestora: Array<
      QualityStatsWire & { gestora_id: string; gestora_name?: string | null }
    >;
  }>(apiPaths.adminQuality);
  return {
    overall: mapQualityStats(res.overall),
    byDocType: res.by_doc_type.map((r) => ({
      docType: r.doc_type,
      ...mapQualityStats(r),
    })),
    byGestora: res.by_gestora.map((r) => ({
      gestoraId: r.gestora_id,
      gestoraName: r.gestora_name ?? null,
      ...mapQualityStats(r),
    })),
  };
}

interface SlaStatsWire {
  pending: number;
  past_sla: number;
  avg_validation_hours: number | null;
  reminders_sent: number;
  escalations_sent: number;
}

function mapSlaStats(wire: SlaStatsWire): SlaStats {
  return {
    pending: wire.pending,
    pastSla: wire.past_sla,
    avgValidationHours: wire.avg_validation_hours,
    remindersSent: wire.reminders_sent,
    escalationsSent: wire.escalations_sent,
  };
}

/** Counsel response metrics (admin-only). */
export async function getSlaReport(): Promise<SlaReport> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.STUB_SLA_REPORT;
    });
  }
  const res = await apiFetch<{
    sla_hours: number;
    overall: SlaStatsWire;
    by_counsel: Array<SlaStatsWire & { counsel_email: string }>;
  }>(apiPaths.adminSla);
  return {
    slaHours: res.sla_hours,
    overall: mapSlaStats(res.overall),
    byCounsel: res.by_counsel.map((r) => ({
      counselEmail: r.counsel_email,
      ...mapSlaStats(r),
    })),
  };
}
