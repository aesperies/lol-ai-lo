"use client";

/**
 * Counsel dashboard — pending reviews queue, most urgent first (server-side
 * ordering), each row showing the backend-computed SLA urgency badge (green
 * "en plazo" · amber "mitad de SLA" · red "SLA vencido") plus filters by
 * gestora and urgency and a pending/overdue counter.
 *
 * Assignment policy sections: the queue only contains this lawyer's own
 * gestoras (assignment="mine") plus the pool of gestoras with NO lawyer
 * assigned yet (assignment="pool", amber-highlighted — any counsel may pick
 * them up). Filters apply to both sections; empty sections are hidden.
 *
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

/** One queue row; pool rows get the amber border + "no assigned lawyer" badge. */
function QueueCard({ item }: { item: CounselQueueItem }) {
  const { t } = useI18n();
  const pool = item.assignment === "pool";
  return (
    // !border: Card sets border-ink-200 and stylesheet order, not class
    // order, decides ties between two border-color utilities.
    <Card className={pool ? "!border-amber-400" : undefined}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="font-medium text-ink-800">
            {item.docTypeLabel ?? item.docType}
          </p>
          <p className="mt-0.5 text-sm text-ink-500">
            {item.gestoraName
              ? `${item.gestoraName} — ${item.fundName ?? ""}`
              : item.fundName}
          </p>
          <p className="mt-0.5 text-xs text-ink-400">
            {t("counsel.requestedBy")}: {item.requestedByName ?? item.userId} —{" "}
            {new Date(item.createdAt).toLocaleDateString()}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {pool ? (
            <Badge tone="amber">{t("counsel.sections.poolBadge")}</Badge>
          ) : null}
          <UrgencyBadge item={item} />
          <StatusBadge status={item.status} />
          <Link href={`/review/${item.id}`}>
            <Button>{t("counsel.review")}</Button>
          </Link>
        </div>
      </div>
    </Card>
  );
}

/** A titled queue section; hidden entirely when it has no rows. */
function QueueSection({
  title,
  hint,
  items,
}: {
  title: string;
  hint?: string;
  items: CounselQueueItem[];
}) {
  if (items.length === 0) return null;
  return (
    <section>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
        {title}
      </h2>
      {hint ? <p className="mt-0.5 text-xs text-ink-400">{hint}</p> : null}
      <div className="mt-3 space-y-4">
        {items.map((r) => (
          <QueueCard key={r.id} item={r} />
        ))}
      </div>
    </section>
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

  // Assignment policy sections; filters above apply to both.
  const mine = filtered.filter((i) => i.assignment !== "pool");
  const pool = filtered.filter((i) => i.assignment === "pool");

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
            <div className="space-y-8">
              <QueueSection title={t("counsel.sections.mine")} items={mine} />
              <QueueSection
                title={t("counsel.sections.pool")}
                hint={t("counsel.sections.poolHint")}
                items={pool}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
