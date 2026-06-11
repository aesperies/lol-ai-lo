"use client";

/**
 * Counsel dashboard — pending reviews queue.
 * NOTE: lives at /counsel (not /dashboard) because Next.js route groups do
 * not namespace URLs and /dashboard belongs to the client area; middleware
 * protects /counsel and /review for the counsel role.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import StatusBadge from "@/components/StatusBadge";
import { Button, Card, PageHeader, Spinner } from "@/components/ui";
import { getCounselQueue } from "@/lib/api";
import type { RequestItem } from "@/lib/types";

export default function CounselDashboardPage() {
  const { t } = useI18n();
  const [queue, setQueue] = useState<RequestItem[] | null>(null);

  useEffect(() => {
    void getCounselQueue().then(setQueue).catch(() => setQueue([]));
  }, []);

  return (
    <div>
      <PageHeader
        title={t("counsel.queueTitle")}
        subtitle={t("counsel.queueSubtitle")}
      />

      {queue === null ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : queue.length === 0 ? (
        <Card className="text-center text-sm text-slate-500">
          {t("counsel.queueEmpty")}
        </Card>
      ) : (
        <div className="space-y-4">
          {queue.map((r) => (
            <Card key={r.id}>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="font-medium text-slate-800">
                    {r.docTypeLabel ?? r.docType}
                  </p>
                  <p className="mt-0.5 text-sm text-slate-500">{r.fundName}</p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {t("counsel.requestedBy")}: {r.requestedByName ?? r.userId} —{" "}
                    {new Date(r.createdAt).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-3">
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
    </div>
  );
}
