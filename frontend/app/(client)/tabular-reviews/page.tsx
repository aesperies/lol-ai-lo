"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import TabularStatusBadge from "@/components/TabularStatusBadge";
import { Button, Card, PageHeader, Spinner } from "@/components/ui";
import { getTabularReviews } from "@/lib/api";
import type { TabularReview } from "@/lib/types";

export default function TabularReviewsPage() {
  const { t } = useI18n();
  const [reviews, setReviews] = useState<TabularReview[] | null>(null);

  useEffect(() => {
    void getTabularReviews()
      .then(setReviews)
      .catch(() => setReviews([]));
  }, []);

  return (
    <div>
      <PageHeader
        title={t("tabular.title")}
        subtitle={t("tabular.subtitle")}
        actions={
          <Link href="/tabular-reviews/new">
            <Button>{t("tabular.new")}</Button>
          </Link>
        }
      />

      {reviews === null ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : reviews.length === 0 ? (
        <Card className="text-center text-sm text-slate-500">
          {t("tabular.empty")}
        </Card>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
                <th className="px-6 py-3 font-medium">{t("common.name")}</th>
                <th className="px-6 py-3 font-medium">{t("common.status")}</th>
                <th className="px-6 py-3 font-medium">{t("common.date")}</th>
                <th className="px-6 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {reviews.map((r) => (
                <tr
                  key={r.id}
                  className="border-b border-slate-100 last:border-0 hover:bg-slate-50"
                >
                  <td className="px-6 py-4 font-medium text-slate-800">
                    {r.title}
                  </td>
                  <td className="px-6 py-4">
                    <TabularStatusBadge status={r.status} />
                  </td>
                  <td className="px-6 py-4 text-slate-500">
                    {r.createdAt
                      ? new Date(r.createdAt).toLocaleDateString()
                      : "—"}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Link
                      href={`/tabular-reviews/${r.id}`}
                      className="text-sm font-medium text-brand-700 hover:underline"
                    >
                      {t("tabular.open")}
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
