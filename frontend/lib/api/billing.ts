"use client";

/* ------------------------------------------------------------------ */
/* Billing over usage_events (improvement #7)                          */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type {
  BillingReport,
  BillingRow,
  MyUsage,
  RetentionPolicy,
} from "@/lib/types";
import { STUB_LATENCY, apiFetch, apiPaths, fetchBlob, stubCall } from "./http";

interface BillingRowWire {
  gestora_id: string;
  gestora_name?: string | null;
  subscription_tier: BillingRow["subscriptionTier"];
  docs_generated: number;
  docs_limit: number | null;
  overage_docs: number;
  exit_a_count: number;
  exit_b_requested: number;
  exit_b_validated: number;
  fund_count: number;
  funds_limit: number | null;
  over_funds_limit: boolean;
  estimated_overage_eur: number;
}

function mapBillingRow(wire: BillingRowWire): BillingRow {
  return {
    gestoraId: wire.gestora_id,
    gestoraName: wire.gestora_name ?? null,
    subscriptionTier: wire.subscription_tier,
    docsGenerated: wire.docs_generated,
    docsLimit: wire.docs_limit,
    overageDocs: wire.overage_docs,
    exitACount: wire.exit_a_count,
    exitBRequested: wire.exit_b_requested,
    exitBValidated: wire.exit_b_validated,
    fundCount: wire.fund_count,
    fundsLimit: wire.funds_limit,
    overFundsLimit: wire.over_funds_limit,
    estimatedOverageEur: wire.estimated_overage_eur,
  };
}

/** Per-gestora billing report for one period (admin-only; default current). */
export async function getBillingReport(period?: string): Promise<BillingReport> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubBillingReport(period);
    });
  }
  const res = await apiFetch<{ period: string; rows: BillingRowWire[] }>(
    apiPaths.adminBilling(period),
  );
  return { period: res.period, rows: res.rows.map(mapBillingRow) };
}

/** Distinct billing periods in usage_events, newest first (admin-only). */
export async function getBillingPeriods(): Promise<string[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubBillingPeriods();
    });
  }
  const res = await apiFetch<{ periods: string[] }>(apiPaths.adminBillingPeriods);
  return res.periods;
}

/** CSV export of the billing report as a Blob (admin-only). */
export async function downloadBillingCsv(period?: string): Promise<Blob> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return new Blob([stub.stubBillingCsv(period)], {
        type: "text/csv;charset=utf-8",
      });
    });
  }
  return fetchBlob(apiPaths.adminBillingExport(period));
}

/* ------------------------------------------------------------------ */
/* GDPR data retention (improvement #10)                               */
/* ------------------------------------------------------------------ */

interface RetentionPolicyWire {
  gestora_id: string;
  months: number;
  is_default: boolean;
  updated_at?: string | null;
}

function mapRetentionPolicy(wire: RetentionPolicyWire): RetentionPolicy {
  return {
    gestoraId: wire.gestora_id,
    months: wire.months,
    isDefault: wire.is_default,
    updatedAt: wire.updated_at ?? null,
  };
}

/** The gestora's retention policy (platform default when none set). Admin-only. */
export async function getRetentionPolicy(
  gestoraId: string,
): Promise<RetentionPolicy> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubGetRetentionPolicy(gestoraId);
    });
  }
  const res = await apiFetch<RetentionPolicyWire>(
    apiPaths.adminRetention(gestoraId),
  );
  return mapRetentionPolicy(res);
}

/** Upserts the gestora's retention policy (months, 6-120). Admin-only. */
export async function updateRetentionPolicy(
  gestoraId: string,
  months: number,
): Promise<RetentionPolicy> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubPutRetentionPolicy(gestoraId, months);
    });
  }
  const res = await apiFetch<RetentionPolicyWire>(
    apiPaths.adminRetention(gestoraId),
    { method: "PUT", body: { months } },
  );
  return mapRetentionPolicy(res);
}

/** The client's own gestora consumption for the current period. */
export async function getMyUsage(): Promise<MyUsage> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubMyUsage();
    });
  }
  const res = await apiFetch<{
    billing_period: string;
    subscription_tier: MyUsage["subscriptionTier"];
    docs_generated: number;
    docs_limit: number | null;
  }>(apiPaths.myUsage);
  return {
    billingPeriod: res.billing_period,
    subscriptionTier: res.subscription_tier,
    docsGenerated: res.docs_generated,
    docsLimit: res.docs_limit,
  };
}
