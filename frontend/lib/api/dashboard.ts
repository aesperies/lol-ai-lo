"use client";

/* ------------------------------------------------------------------ */
/* Gestora dashboard aggregates (GET /api/dashboard/stats, Roadmap D)  */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type {
  DashboardActivityItem,
  DashboardDeadline,
  DashboardStats,
} from "@/lib/types";
import { STUB_LATENCY, apiFetch, apiPaths, stubCall } from "./http";

/** Wire shape of backend/api/dashboard.py DashboardStatsOut (snake_case). */
interface DashboardStatsWire {
  counts: {
    in_progress: number;
    awaiting_you: number;
    in_counsel_review: number;
    ready: number;
    delivered_this_month: number;
  };
  upcoming_deadlines: Array<{
    request_id: string;
    doc_type: string;
    fund_name?: string | null;
    deadline?: string | null;
    hours_remaining: number;
    overdue: boolean;
  }>;
  avg_validation_hours?: number | null;
  sla_hours: number;
  recent_activity: Array<{
    action: string;
    timestamp?: string | null;
    resource_type?: string | null;
    resource_id?: string | null;
  }>;
  funds_count: number;
}

function mapDeadline(
  wire: DashboardStatsWire["upcoming_deadlines"][number],
): DashboardDeadline {
  return {
    requestId: wire.request_id,
    docType: wire.doc_type,
    fundName: wire.fund_name ?? null,
    deadline: wire.deadline ?? null,
    hoursRemaining: wire.hours_remaining,
    overdue: wire.overdue,
  };
}

function mapActivity(
  wire: DashboardStatsWire["recent_activity"][number],
): DashboardActivityItem {
  return {
    action: wire.action,
    timestamp: wire.timestamp ?? null,
    resourceType: wire.resource_type ?? null,
    resourceId: wire.resource_id ?? null,
  };
}

/** One-call dashboard aggregates for the caller's gestora (clients only):
 * status counts, upcoming counsel-SLA deadlines, mean validation turnaround
 * and recent audit activity. */
export async function getDashboardStats(): Promise<DashboardStats> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 2);
      return stub.stubDashboardStats();
    });
  }
  const res = await apiFetch<DashboardStatsWire>(apiPaths.dashboardStats);
  return {
    counts: {
      inProgress: res.counts.in_progress,
      awaitingYou: res.counts.awaiting_you,
      inCounselReview: res.counts.in_counsel_review,
      ready: res.counts.ready,
      deliveredThisMonth: res.counts.delivered_this_month,
    },
    upcomingDeadlines: res.upcoming_deadlines.map(mapDeadline),
    avgValidationHours: res.avg_validation_hours ?? null,
    slaHours: res.sla_hours,
    recentActivity: res.recent_activity.map(mapActivity),
    fundsCount: res.funds_count,
  };
}
