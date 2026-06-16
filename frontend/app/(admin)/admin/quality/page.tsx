"use client";

/** Admin — generation quality KPIs and counsel-review SLA metrics. */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { Badge, Card, CardTitle, PageHeader, Spinner } from "@/components/ui";
import { getQualityReport, getSlaReport } from "@/lib/api";
import type { QualityReport, QualityStats, SlaReport } from "@/lib/types";

function fmtSimilarity(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

function fmtPct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function fmtHours(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} h`;
}

function QualityRow({
  label,
  stats,
  emphasize = false,
}: {
  label: string;
  stats: QualityStats;
  emphasize?: boolean;
}) {
  return (
    <tr
      className={
        emphasize
          ? "border-b border-ink-100 bg-ink-50 font-medium last:border-0"
          : "border-b border-ink-100 last:border-0"
      }
    >
      <td className="px-6 py-3 text-ink-800">{label}</td>
      <td className="px-6 py-3 text-right text-ink-600">{stats.count}</td>
      <td className="px-6 py-3 text-right text-ink-600">
        {fmtSimilarity(stats.avgSimilarity)}
      </td>
      <td className="px-6 py-3 text-right text-ink-600">
        {fmtPct(stats.pctAcceptedAsIs)}
      </td>
      <td className="px-6 py-3 text-right text-ink-600">
        {stats.avgRefinements === null ? "—" : stats.avgRefinements.toFixed(1)}
      </td>
    </tr>
  );
}

export default function AdminQualityPage() {
  const { t } = useI18n();

  const [quality, setQuality] = useState<QualityReport | null>(null);
  const [sla, setSla] = useState<SlaReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void Promise.allSettled([
      getQualityReport().then(setQuality),
      getSlaReport().then(setSla),
    ]).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("admin.quality.title")}
        subtitle={t("admin.quality.subtitle")}
      />

      <div className="space-y-8">
        <section>
          <div className="mb-3 flex items-baseline justify-between">
            <CardTitle>{t("admin.quality.qualityTitle")}</CardTitle>
            <span className="text-xs text-ink-400">
              {t("admin.quality.qualityHint")}
            </span>
          </div>
          {quality === null || quality.overall.count === 0 ? (
            <Card className="py-10 text-center text-sm text-ink-400">
              {t("admin.quality.empty")}
            </Card>
          ) : (
            <Card className="overflow-x-auto p-0">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-ink-200 text-xs uppercase tracking-wide text-ink-400">
                    <th scope="col" className="px-6 py-3 font-medium">
                      {t("intake.docType")}
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      {t("admin.quality.count")}
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      {t("admin.quality.avgSimilarity")}
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      {t("admin.quality.pctAcceptedAsIs")}
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      {t("admin.quality.avgRefinements")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {quality.byDocType.map((row) => (
                    <QualityRow
                      key={row.docType}
                      label={row.docType}
                      stats={row}
                    />
                  ))}
                  <QualityRow
                    label={t("admin.quality.overall")}
                    stats={quality.overall}
                    emphasize
                  />
                </tbody>
              </table>
            </Card>
          )}
        </section>

        <section>
          <div className="mb-3 flex items-baseline justify-between">
            <CardTitle>{t("admin.sla.title")}</CardTitle>
            {sla ? (
              <span className="text-xs text-ink-400">
                {t("admin.sla.target", { hours: sla.slaHours })}
              </span>
            ) : null}
          </div>
          {sla === null ||
          (sla.overall.pending === 0 && sla.byCounsel.length === 0) ? (
            <Card className="py-10 text-center text-sm text-ink-400">
              {t("admin.sla.empty")}
            </Card>
          ) : (
            <Card className="overflow-x-auto p-0">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-ink-200 text-xs uppercase tracking-wide text-ink-400">
                    <th scope="col" className="px-6 py-3 font-medium">
                      {t("admin.sla.counsel")}
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      {t("admin.sla.pending")}
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      {t("admin.sla.pastSla")}
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      {t("admin.sla.avgHours")}
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      {t("admin.sla.reminders")}
                    </th>
                    <th scope="col" className="px-6 py-3 text-right font-medium">
                      {t("admin.sla.escalations")}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sla.byCounsel.map((row) => (
                    <tr
                      key={row.counselEmail}
                      className="border-b border-ink-100 last:border-0"
                    >
                      <td className="px-6 py-3 font-medium text-ink-800">
                        {row.counselEmail}
                      </td>
                      <td className="px-6 py-3 text-right text-ink-600">
                        {row.pending}
                      </td>
                      <td className="px-6 py-3 text-right">
                        {row.pastSla > 0 ? (
                          <Badge tone="red">{row.pastSla}</Badge>
                        ) : (
                          <span className="text-ink-600">0</span>
                        )}
                      </td>
                      <td className="px-6 py-3 text-right text-ink-600">
                        {fmtHours(row.avgValidationHours)}
                      </td>
                      <td className="px-6 py-3 text-right text-ink-600">
                        {row.remindersSent}
                      </td>
                      <td className="px-6 py-3 text-right text-ink-600">
                        {row.escalationsSent}
                      </td>
                    </tr>
                  ))}
                  <tr className="border-b border-ink-100 bg-ink-50 font-medium last:border-0">
                    <td className="px-6 py-3 text-ink-800">
                      {t("admin.quality.overall")}
                    </td>
                    <td className="px-6 py-3 text-right text-ink-600">
                      {sla.overall.pending}
                    </td>
                    <td className="px-6 py-3 text-right">
                      {sla.overall.pastSla > 0 ? (
                        <Badge tone="red">{sla.overall.pastSla}</Badge>
                      ) : (
                        <span className="text-ink-600">0</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-right text-ink-600">
                      {fmtHours(sla.overall.avgValidationHours)}
                    </td>
                    <td className="px-6 py-3 text-right text-ink-600">
                      {sla.overall.remindersSent}
                    </td>
                    <td className="px-6 py-3 text-right text-ink-600">
                      {sla.overall.escalationsSent}
                    </td>
                  </tr>
                </tbody>
              </table>
            </Card>
          )}
        </section>
      </div>
    </div>
  );
}
