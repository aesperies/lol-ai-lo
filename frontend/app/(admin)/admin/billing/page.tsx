"use client";

/** Admin — billing dashboard over usage_events (improvement #7): per-gestora
 * monthly consumption, tier limits, overage and CSV export. */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Badge,
  Button,
  Card,
  PageHeader,
  Select,
  Spinner,
  UsageBar,
} from "@/components/ui";
import {
  downloadBillingCsv,
  getBillingPeriods,
  getBillingReport,
  triggerBlobDownload,
} from "@/lib/api";
import type { BillingReport, BillingRow } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

function usagePct(row: BillingRow): number | null {
  if (row.docsLimit === null || row.docsLimit === 0) return null;
  return (row.docsGenerated / row.docsLimit) * 100;
}

function fmtEur(value: number): string {
  return `${value.toLocaleString("es-ES", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} €`;
}

export default function AdminBillingPage() {
  const { t } = useI18n();

  const [periods, setPeriods] = useState<string[]>([]);
  const [period, setPeriod] = useState<string | null>(null);
  const [report, setReport] = useState<BillingReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    void getBillingPeriods()
      .then((list) => {
        setPeriods(list);
        setPeriod(list[0] ?? null);
      })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (period === null) return;
    setLoading(true);
    void getBillingReport(period)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, [period]);

  async function handleExport(): Promise<void> {
    if (period === null) return;
    setExporting(true);
    try {
      const blob = await downloadBillingCsv(period);
      triggerBlobDownload(blob, `billing-${period}.csv`);
    } catch {
      /* surfaced by the unchanged table; nothing actionable here */
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <PageHeader
        title={t("admin.billing.title")}
        subtitle={t("admin.billing.subtitle")}
        actions={
          <>
            <Select
              aria-label={t("admin.billing.period")}
              className="w-36"
              value={period ?? ""}
              onChange={(e) => setPeriod(e.target.value)}
              disabled={periods.length === 0}
            >
              {periods.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
            <Button
              variant="secondary"
              onClick={() => void handleExport()}
              disabled={exporting || period === null}
            >
              {t("admin.billing.exportCsv")}
            </Button>
          </>
        }
      />

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : report === null || report.rows.length === 0 ? (
        <Card className="py-10 text-center text-sm text-ink-400">
          {t("admin.billing.empty")}
        </Card>
      ) : (
        <>
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-ink-200 text-xs uppercase tracking-wide text-ink-400">
                  <th scope="col" className="px-6 py-3 font-medium">
                    {t("admin.billing.gestora")}
                  </th>
                  <th scope="col" className="px-6 py-3 font-medium">
                    {t("admin.billing.tier")}
                  </th>
                  <th scope="col" className="px-6 py-3 font-medium">
                    {t("admin.billing.docs")}
                  </th>
                  <th scope="col" className="px-6 py-3 text-right font-medium">
                    {t("admin.billing.overage")}
                  </th>
                  <th scope="col" className="px-6 py-3 text-right font-medium">
                    {t("admin.billing.exitA")}
                  </th>
                  <th scope="col" className="px-6 py-3 text-right font-medium">
                    {t("admin.billing.exitB")}
                  </th>
                  <th scope="col" className="px-6 py-3 text-right font-medium">
                    {t("admin.billing.overageEur")}
                  </th>
                  <th scope="col" className="px-6 py-3 text-right font-medium">
                    {t("admin.billing.funds")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {report.rows.map((row) => {
                  const pct = usagePct(row);
                  return (
                    <tr
                      key={row.gestoraId}
                      className="border-b border-ink-100 last:border-0"
                    >
                      <td className="px-6 py-4 font-medium text-ink-800">
                        {row.gestoraName ?? row.gestoraId}
                      </td>
                      <td className="px-6 py-4">
                        <Badge
                          tone={
                            row.subscriptionTier === "growth"
                              ? "indigo"
                              : row.subscriptionTier === "custom"
                                ? "violet"
                                : "slate"
                          }
                        >
                          {t(`tier.${row.subscriptionTier}` as DictKey)}
                        </Badge>
                      </td>
                      <td className="px-6 py-4">
                        <div className="min-w-[10rem]">
                          <div className="mb-1 text-ink-700">
                            {row.docsGenerated} /{" "}
                            {row.docsLimit ?? t("admin.billing.unlimited")}
                          </div>
                          {pct !== null ? <UsageBar pct={pct} /> : null}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        {row.overageDocs > 0 ? (
                          <Badge tone="red">+{row.overageDocs}</Badge>
                        ) : (
                          <span className="text-ink-600">0</span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-right text-ink-600">
                        {row.exitACount}
                      </td>
                      <td className="px-6 py-4 text-right text-ink-600">
                        {row.exitBRequested} / {row.exitBValidated}
                      </td>
                      <td className="px-6 py-4 text-right text-ink-600">
                        {row.estimatedOverageEur > 0 ? (
                          <span className="font-medium text-ink-800">
                            {fmtEur(row.estimatedOverageEur)}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-6 py-4 text-right">
                        {row.overFundsLimit ? (
                          <span title={t("admin.billing.overFunds")}>
                            <Badge tone="red">
                              {row.fundCount} /{" "}
                              {row.fundsLimit ?? t("admin.billing.unlimited")}
                            </Badge>
                          </span>
                        ) : (
                          <span className="text-ink-600">
                            {row.fundCount} /{" "}
                            {row.fundsLimit ?? t("admin.billing.unlimited")}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
          <p className="mt-3 text-xs text-ink-400">
            {t("admin.billing.pricesTbdHint")}
          </p>
        </>
      )}
    </div>
  );
}
