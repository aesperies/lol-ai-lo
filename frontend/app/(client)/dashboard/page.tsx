"use client";

import Link from "next/link";
import { useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import StatusBadge from "@/components/StatusBadge";
import { Button, Card, PageHeader, Spinner, UsageBar } from "@/components/ui";
import { getDashboardStats, getMyUsage, getRequests } from "@/lib/api";
import { docTypeLabel } from "@/lib/catalog";
import { useAsync } from "@/lib/hooks";
import type { DictKey } from "@/lib/i18n";
import type {
  DashboardActivityItem,
  DashboardStats,
  MyUsage,
} from "@/lib/types";

/** Small monthly-consumption widget (improvement #7). Hidden when the
 * /api/my/usage call fails — consumption is informative, never blocking. */
function UsageWidget({ usage }: { usage: MyUsage }) {
  const { t } = useI18n();
  const pct =
    usage.docsLimit === null || usage.docsLimit === 0
      ? null
      : (usage.docsGenerated / usage.docsLimit) * 100;
  return (
    <Card className="mb-6 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-400">
          {t("dashboard.usageTitle")}
        </span>
        <span className="text-sm text-ink-700">
          {usage.docsLimit === null
            ? t("dashboard.usageUnlimited", { used: usage.docsGenerated })
            : t("dashboard.usage", {
                used: usage.docsGenerated,
                limit: usage.docsLimit,
              })}
        </span>
      </div>
      {pct !== null ? <UsageBar pct={pct} className="mt-2" /> : null}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Enriched dashboard (GET /api/dashboard/stats, Roadmap D)            */
/* ------------------------------------------------------------------ */

function StatCard({
  label,
  value,
  secondary,
}: {
  label: string;
  value: number;
  secondary?: string;
}) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-400">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold text-ink-900">{value}</p>
      {secondary ? (
        <p className="mt-0.5 text-xs text-ink-400">{secondary}</p>
      ) : null}
    </Card>
  );
}

/** Row of 4 status-count metric cards, with delivered-this-month and the mean
 * validation turnaround as secondary lines where they fit. */
function StatsRow({ stats }: { stats: DashboardStats }) {
  const { t } = useI18n();
  return (
    <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
      <StatCard
        label={t("dashboard.stats.inProgress")}
        value={stats.counts.inProgress}
      />
      <StatCard
        label={t("dashboard.stats.awaitingYou")}
        value={stats.counts.awaitingYou}
      />
      <StatCard
        label={t("dashboard.stats.inCounselReview")}
        value={stats.counts.inCounselReview}
        secondary={
          stats.avgValidationHours === null
            ? undefined
            : t("dashboard.stats.avgValidation", {
                hours: stats.avgValidationHours,
              })
        }
      />
      <StatCard
        label={t("dashboard.stats.ready")}
        value={stats.counts.ready}
        secondary={t("dashboard.stats.deliveredThisMonth", {
          n: stats.counts.deliveredThisMonth,
        })}
      />
    </div>
  );
}

/** Upcoming counsel-SLA deadlines (soonest first); hidden when none. */
function DeadlinesCard({ stats }: { stats: DashboardStats }) {
  const { t } = useI18n();
  if (stats.upcomingDeadlines.length === 0) return null;
  return (
    <Card className="mb-6 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-400">
          {t("dashboard.deadlines.title")}
        </span>
        <span className="text-xs text-ink-400">
          {t("dashboard.deadlines.subtitle", {
            sla: Math.round(stats.slaHours),
          })}
        </span>
      </div>
      <ul className="mt-3 divide-y divide-ink-100">
        {stats.upcomingDeadlines.map((d) => (
          <li key={d.requestId}>
            <Link
              href={`/documents/${d.requestId}`}
              className="flex flex-wrap items-center justify-between gap-2 py-2.5 hover:bg-ink-50"
            >
              <span className="text-sm font-medium text-ink-800">
                {docTypeLabel(d.docType)}
                {d.fundName ? (
                  <span className="ml-2 font-normal text-ink-500">
                    {d.fundName}
                  </span>
                ) : null}
              </span>
              {d.overdue ? (
                <span className="text-sm font-semibold text-red-600">
                  {t("dashboard.deadlines.overdue")}
                </span>
              ) : (
                <span className="text-sm text-ink-600">
                  {t("dashboard.deadlines.hoursLeft", {
                    hours: Math.max(0, Math.round(d.hoursRemaining)),
                  })}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Humanized labels for the most common audit actions; anything else falls
 * back to the raw literal (the audit enum keeps growing). */
const ACTIVITY_ACTION_KEYS: Record<string, DictKey> = {
  document_requested: "dashboard.activity.action.document_requested",
  params_confirmed: "dashboard.activity.action.params_confirmed",
  document_generated: "dashboard.activity.action.document_generated",
  counsel_requested: "dashboard.activity.action.counsel_requested",
  counsel_comment_added: "dashboard.activity.action.counsel_comment_added",
  document_validated: "dashboard.activity.action.document_validated",
  draft_downloaded: "dashboard.activity.action.draft_downloaded",
  final_downloaded: "dashboard.activity.action.final_downloaded",
  exit_a_acknowledged: "dashboard.activity.action.exit_a_acknowledged",
  precedent_uploaded: "dashboard.activity.action.precedent_uploaded",
  fund_created: "dashboard.activity.action.fund_created",
};

/** Compact collapsible recent-activity trail (gestora audit log). */
function ActivityCard({ items }: { items: DashboardActivityItem[] }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <Card className="mt-6 p-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="text-xs font-medium uppercase tracking-wide text-ink-400">
          {t("dashboard.activity.title")}
        </span>
        <span className="text-xs font-medium text-brand-700">
          {open ? t("dashboard.activity.hide") : t("dashboard.activity.show")}
        </span>
      </button>
      {open ? (
        <ul className="mt-3 divide-y divide-ink-100">
          {items.map((a, i) => {
            const key = ACTIVITY_ACTION_KEYS[a.action];
            return (
              <li
                key={`${a.action}-${a.timestamp ?? i}`}
                className="flex flex-wrap items-center justify-between gap-2 py-1.5"
              >
                <span className="text-sm text-ink-700">
                  {key ? t(key) : a.action}
                </span>
                <span className="text-xs text-ink-400">
                  {a.timestamp
                    ? new Date(a.timestamp).toLocaleString()
                    : null}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
    </Card>
  );
}

export default function ClientDashboardPage() {
  const { t } = useI18n();
  const { data, error } = useAsync(() => getRequests(), []);
  // On error, fall back to an empty list so the error card renders
  // (same behavior as before).
  const requests = data ?? (error ? [] : null);
  // Graceful: hide the widget entirely if the usage call fails.
  const { data: usage } = useAsync<MyUsage | null>(() => getMyUsage(), []);
  // Graceful too: the enriched cards are informative, never blocking.
  const { data: stats } = useAsync<DashboardStats | null>(
    () => getDashboardStats(),
    [],
  );

  return (
    <div>
      <PageHeader
        title={t("dashboard.title")}
        subtitle={t("dashboard.subtitle")}
        actions={
          <Link href="/new-request">
            <Button>{t("dashboard.cta")}</Button>
          </Link>
        }
      />

      {stats !== null ? (
        <>
          <StatsRow stats={stats} />
          <DeadlinesCard stats={stats} />
        </>
      ) : null}

      {usage !== null ? <UsageWidget usage={usage} /> : null}

      {requests === null ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : requests.length === 0 ? (
        <Card className="text-center text-sm text-ink-500">
          {error ? t("common.error") : t("dashboard.empty")}
        </Card>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-ink-200 text-xs uppercase tracking-wide text-ink-400">
                <th scope="col" className="px-6 py-3 font-medium">{t("common.docType")}</th>
                <th scope="col" className="px-6 py-3 font-medium">{t("common.fund")}</th>
                <th scope="col" className="px-6 py-3 font-medium">{t("common.status")}</th>
                <th scope="col" className="px-6 py-3 font-medium">{t("common.date")}</th>
                <th scope="col" className="px-6 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id} className="border-b border-ink-100 last:border-0 hover:bg-ink-50">
                  <td className="px-6 py-4 font-medium text-ink-800">
                    {r.docTypeLabel ?? r.docType}
                    {r.docTypeCustom ? (
                      <span className="block text-xs font-normal text-ink-400">
                        {r.docTypeCustom}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-6 py-4 text-ink-600">{r.fundName ?? r.fundId}</td>
                  <td className="px-6 py-4">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-6 py-4 text-ink-500">
                    {new Date(r.createdAt).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Link
                      href={`/documents/${r.id}`}
                      className="text-sm font-medium text-brand-700 hover:underline"
                    >
                      {t("dashboard.viewDocument")}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {stats !== null ? <ActivityCard items={stats.recentActivity} /> : null}
    </div>
  );
}
