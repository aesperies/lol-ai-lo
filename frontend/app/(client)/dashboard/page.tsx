"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import StatusBadge from "@/components/StatusBadge";
import { Button, Card, PageHeader, Spinner, UsageBar } from "@/components/ui";
import { getMyUsage, getRequests } from "@/lib/api";
import type { MyUsage, RequestItem } from "@/lib/types";

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

export default function ClientDashboardPage() {
  const { t } = useI18n();
  const [requests, setRequests] = useState<RequestItem[] | null>(null);
  const [usage, setUsage] = useState<MyUsage | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    void getRequests()
      .then(setRequests)
      .catch(() => {
        setError(true);
        setRequests([]);
      });
    // Graceful: hide the widget entirely if the usage call fails.
    void getMyUsage()
      .then(setUsage)
      .catch(() => setUsage(null));
  }, []);

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
    </div>
  );
}
