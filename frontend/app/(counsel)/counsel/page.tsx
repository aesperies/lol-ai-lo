"use client";

/**
 * Counsel dashboard — pending reviews queue, most urgent first (server-side
 * ordering), each row showing the backend-computed SLA urgency badge (green
 * "en plazo" · amber "mitad de SLA" · red "SLA vencido") plus filters by
 * gestora and urgency and a pending/overdue counter.
 * NOTE: lives at /counsel (not /dashboard) because Next.js route groups do
 * not namespace URLs and /dashboard belongs to the client area; middleware
 * protects /counsel and /review for the counsel role.
 */

import Link from "next/link";
import { useMemo, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import StatusBadge from "@/components/StatusBadge";
import { Badge, Button, Card, PageHeader, Select, Spinner } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";
import { getCounselQueue } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { CounselQueueItem, SlaUrgency } from "@/lib/types";
import { SLA_URGENCIES } from "@/lib/types";

const URGENCY_TONE: Record<SlaUrgency, BadgeTone> = {
  green: "green",
  amber: "amber",
  red: "red",
};

/** Server-computed SLA badge: urgency label + rounded pending hours. */
function UrgencyBadge({ item }: { item: CounselQueueItem }) {
  const { t } = useI18n();
  const label = t(`counsel.urgency.${item.urgency}`);
  const hours =
    item.hoursPending === null
      ? null
      : t("counsel.urgency.hours", {
          hours: Math.round(item.hoursPending),
          sla: Math.round(item.slaHours),
        });
  return (
    <Badge tone={URGENCY_TONE[item.urgency]}>
      {hours ? `${label} · ${hours}` : label}
    </Badge>
  );
}

export default function CounselDashboardPage() {
  const { t } = useI18n();
  // Single unfiltered fetch: the queue is small, so gestora options and the
  // pending/overdue counter stay stable while filters narrow the list
  // client-side (the endpoint also accepts ?gestora_id=&urgency= if needed).
  const { data: queue, loading } = useAsync(() => getCounselQueue(), []);
  const [gestoraFilter, setGestoraFilter] = useState("");
  const [urgencyFilter, setUrgencyFilter] = useState("");

  // Gestora options derived from the queue itself (id → name).
  const gestoraOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const item of queue ?? []) {
      if (item.gestoraId && !seen.has(item.gestoraId)) {
        seen.set(item.gestoraId, item.gestoraName ?? item.gestoraId);
      }
    }
    return Array.from(seen, ([id, name]) => ({ id, name }));
  }, [queue]);

  const filtered = useMemo(
    () =>
      (queue ?? []).filter(
        (item) =>
          (!gestoraFilter || item.gestoraId === gestoraFilter) &&
          (!urgencyFilter || item.urgency === urgencyFilter),
      ),
    [queue, gestoraFilter, urgencyFilter],
  );

  const overdue = (queue ?? []).filter((i) => i.urgency === "red").length;

  return (
    <div>
      <PageHeader
        title={t("counsel.queueTitle")}
        subtitle={t("counsel.queueSubtitle")}
      />

      {queue === null || loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <>
          <div className="mb-6 flex flex-wrap items-center gap-3">
            <Select
              aria-label={t("counsel.filterGestora")}
              value={gestoraFilter}
              onChange={(e) => setGestoraFilter(e.target.value)}
              className="w-auto min-w-[13rem]"
            >
              <option value="">{t("counsel.allGestoras")}</option>
              {gestoraOptions.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </Select>
            <Select
              aria-label={t("counsel.filterUrgency")}
              value={urgencyFilter}
              onChange={(e) => setUrgencyFilter(e.target.value)}
              className="w-auto min-w-[11rem]"
            >
              <option value="">{t("counsel.allUrgencies")}</option>
              {SLA_URGENCIES.map((u) => (
                <option key={u} value={u}>
                  {t(`counsel.urgency.${u}`)}
                </option>
              ))}
            </Select>
            <span className="ml-auto text-sm text-ink-500">
              {t("counsel.pending", { n: queue.length, overdue })}
            </span>
          </div>

          {filtered.length === 0 ? (
            <Card className="text-center text-sm text-ink-500">
              {t("counsel.queueEmpty")}
            </Card>
          ) : (
            <div className="space-y-4">
              {filtered.map((r) => (
                <Card key={r.id}>
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <p className="font-medium text-ink-800">
                        {r.docTypeLabel ?? r.docType}
                      </p>
                      <p className="mt-0.5 text-sm text-ink-500">
                        {r.gestoraName
                          ? `${r.gestoraName} — ${r.fundName ?? ""}`
                          : r.fundName}
                      </p>
                      <p className="mt-0.5 text-xs text-ink-400">
                        {t("counsel.requestedBy")}: {r.requestedByName ?? r.userId}{" "}
                        — {new Date(r.createdAt).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <UrgencyBadge item={r} />
                      <StatusBadge status={r.status} />
                      <Link href={`/review/${r.id}`}>
                        <Button>{t("counsel.review")}</Button>
                      </Link>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
