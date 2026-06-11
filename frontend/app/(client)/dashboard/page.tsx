"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import StatusBadge from "@/components/StatusBadge";
import { Button, Card, PageHeader, Spinner } from "@/components/ui";
import { getRequests } from "@/lib/api";
import type { RequestItem } from "@/lib/types";

export default function ClientDashboardPage() {
  const { t } = useI18n();
  const [requests, setRequests] = useState<RequestItem[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    void getRequests()
      .then(setRequests)
      .catch(() => {
        setError(true);
        setRequests([]);
      });
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

      {requests === null ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : requests.length === 0 ? (
        <Card className="text-center text-sm text-slate-500">
          {error ? t("common.error") : t("dashboard.empty")}
        </Card>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
                <th className="px-6 py-3 font-medium">{t("common.docType")}</th>
                <th className="px-6 py-3 font-medium">{t("common.fund")}</th>
                <th className="px-6 py-3 font-medium">{t("common.status")}</th>
                <th className="px-6 py-3 font-medium">{t("common.date")}</th>
                <th className="px-6 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-6 py-4 font-medium text-slate-800">
                    {r.docTypeLabel ?? r.docType}
                    {r.docTypeCustom ? (
                      <span className="block text-xs font-normal text-slate-400">
                        {r.docTypeCustom}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-6 py-4 text-slate-600">{r.fundName ?? r.fundId}</td>
                  <td className="px-6 py-4">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-6 py-4 text-slate-500">
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
