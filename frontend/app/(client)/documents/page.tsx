"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import StatusBadge from "@/components/StatusBadge";
import { Card, Label, PageHeader, Select, Spinner } from "@/components/ui";
import { getFunds, getRequests } from "@/lib/api";
import { DOC_TYPE_CATALOG, docTypeGroupLabel } from "@/lib/catalog";
import { REQUEST_STATUSES, type Fund, type RequestItem, type RequestStatus } from "@/lib/types";
import { useAsync } from "@/lib/hooks";
import type { DictKey } from "@/lib/i18n";

export default function DocumentsHistoryPage() {
  const { t } = useI18n();

  // Errors degrade to an empty list (same behavior as before).
  const { data: requests } = useAsync<RequestItem[]>(
    () => getRequests().catch(() => []),
    [],
  );
  const { data: fundsData } = useAsync<Fund[]>(
    () => getFunds().catch(() => []),
    [],
  );
  const funds = fundsData ?? [];
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [docTypeFilter, setDocTypeFilter] = useState<string>("");
  const [fundFilter, setFundFilter] = useState<string>("");

  const filtered = useMemo(() => {
    if (!requests) return [];
    return requests.filter(
      (r) =>
        (!statusFilter || r.status === statusFilter) &&
        (!docTypeFilter || r.docType === docTypeFilter) &&
        (!fundFilter || r.fundId === fundFilter),
    );
  }, [requests, statusFilter, docTypeFilter, fundFilter]);

  return (
    <div>
      <PageHeader title={t("documents.title")} subtitle={t("documents.subtitle")} />

      {/* Filters */}
      <Card className="mb-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <Label htmlFor="filter-status">{t("documents.filterStatus")}</Label>
            <Select
              id="filter-status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">{t("common.all")}</option>
              {REQUEST_STATUSES.map((s: RequestStatus) => (
                <option key={s} value={s}>
                  {t(`status.${s}` as DictKey)}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="filter-doctype">{t("documents.filterDocType")}</Label>
            <Select
              id="filter-doctype"
              value={docTypeFilter}
              onChange={(e) => setDocTypeFilter(e.target.value)}
            >
              <option value="">{t("common.all")}</option>
              {DOC_TYPE_CATALOG.map((group) => (
                <optgroup key={group.label} label={docTypeGroupLabel(group)}>
                  {group.options.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </Select>
          </div>
          <div>
            <Label htmlFor="filter-fund">{t("documents.filterFund")}</Label>
            <Select
              id="filter-fund"
              value={fundFilter}
              onChange={(e) => setFundFilter(e.target.value)}
            >
              <option value="">{t("common.all")}</option>
              {funds.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </Select>
          </div>
        </div>
      </Card>

      {requests === null ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : filtered.length === 0 ? (
        <Card className="text-center text-sm text-ink-500">
          {t("documents.empty")}
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
              {filtered.map((r) => (
                <tr key={r.id} className="border-b border-ink-100 last:border-0 hover:bg-ink-50">
                  <td className="px-6 py-4 font-medium text-ink-800">
                    {r.docTypeLabel ?? r.docType}
                  </td>
                  <td className="px-6 py-4 text-ink-600">
                    {r.fundName ?? r.fundId}
                    {r.vehicleName ? (
                      <span className="text-ink-400"> — {r.vehicleName}</span>
                    ) : null}
                  </td>
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
                      {t("documents.open")}
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
