"use client";

/**
 * Biblioteca del cliente (022): los documentos del silo de la gestora,
 * organizados por fondo, año, trimestre y tipo de documentación.
 *
 * - Jerarquía: [Fondo o Tipo] → Año → Trimestre, con filas ordenadas por tipo.
 * - Filtros por los cuatro ejes; la fecha usada es document_date (fecha del
 *   documento, editable al subir) con created_at como respaldo.
 * - Subida por el cliente: el documento entra como BORRADOR y no alimenta el
 *   RAG hasta que el admin lo active.
 */

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import PrecedentHtmlModal from "@/components/PrecedentHtmlModal";
import {
  Badge,
  Banner,
  Button,
  Card,
  Input,
  Label,
  Modal,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import { getFunds, getMyLibrary, uploadLibraryDocument } from "@/lib/api";
import { DOC_TYPE_CATALOG, docTypeGroupLabel, docTypeLabel } from "@/lib/catalog";
import type { Fund, LibraryItem } from "@/lib/types";

type PrimaryGroup = "fund" | "type";

const ALL = "__all__";
const NO_FUND = "__none__";

function itemDate(item: LibraryItem): string {
  return item.documentDate ?? item.createdAt?.slice(0, 10) ?? "";
}

function itemYear(item: LibraryItem): string {
  return itemDate(item).slice(0, 4) || "—";
}

function itemQuarter(item: LibraryItem): number {
  const month = Number(itemDate(item).slice(5, 7));
  return month >= 1 && month <= 12 ? Math.floor((month - 1) / 3) + 1 : 0;
}

const STATUS_TONE = { draft: "amber", active: "emerald", superseded: "slate" } as const;

function StatusBadge({ status }: { status: LibraryItem["versionStatus"] }) {
  const { t } = useI18n();
  if (!status) return null;
  return <Badge tone={STATUS_TONE[status]}>{t(`library.status.${status}`)}</Badge>;
}

/* ------------------------------------------------------------------ */
/* Upload modal                                                        */
/* ------------------------------------------------------------------ */

function UploadModal({
  open,
  funds,
  onClose,
  onUploaded,
}: {
  open: boolean;
  funds: Fund[];
  onClose: () => void;
  onUploaded: () => void;
}) {
  const { t } = useI18n();
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("");
  const [fundId, setFundId] = useState("");
  const [documentDate, setDocumentDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!file || !docType || busy) return;
    setBusy(true);
    setError(null);
    try {
      await uploadLibraryDocument({
        file,
        docType,
        language: "es",
        fundId: fundId || null,
        documentDate: documentDate || null,
      });
      onUploaded();
      onClose();
      setFile(null);
      setDocType("");
      setFundId("");
      setDocumentDate("");
    } catch {
      setError(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={t("library.uploadTitle")}>
      <div className="flex flex-col gap-3">
        {error ? <Banner tone="danger">{error}</Banner> : null}
        <div>
          <Label htmlFor="lib-file">{t("library.uploadFile")}</Label>
          <Input
            id="lib-file"
            type="file"
            accept=".docx,.pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>
        <div>
          <Label htmlFor="lib-doctype">{t("common.docType")}</Label>
          <Select
            id="lib-doctype"
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
          >
            <option value="" disabled>
              —
            </option>
            {DOC_TYPE_CATALOG.map((group) => (
              <optgroup key={group.label} label={docTypeGroupLabel(group)}>
                {group.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="lib-fund">{t("library.uploadFund")}</Label>
          <Select
            id="lib-fund"
            value={fundId}
            onChange={(e) => setFundId(e.target.value)}
          >
            <option value="">—</option>
            {funds.map((fund) => (
              <option key={fund.id} value={fund.id}>
                {fund.name}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="lib-date">{t("library.uploadDate")}</Label>
          <Input
            id="lib-date"
            type="date"
            value={documentDate}
            onChange={(e) => setDocumentDate(e.target.value)}
          />
        </div>
        <p className="text-xs text-ink-400">{t("library.uploadNote")}</p>
        <div className="mt-1 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => void submit()} disabled={!file || !docType || busy}>
            {busy ? <Spinner className="h-4 w-4 text-white" /> : t("library.upload")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function LibraryPage() {
  const { t } = useI18n();
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [funds, setFunds] = useState<Fund[]>([]);
  const [primary, setPrimary] = useState<PrimaryGroup>("fund");
  const [fundFilter, setFundFilter] = useState(ALL);
  const [yearFilter, setYearFilter] = useState(ALL);
  const [quarterFilter, setQuarterFilter] = useState(ALL);
  const [typeFilter, setTypeFilter] = useState(ALL);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploaded, setUploaded] = useState(false);
  const [viewing, setViewing] = useState<LibraryItem | null>(null);

  async function refresh() {
    setItems(await getMyLibrary().catch(() => []));
  }

  useEffect(() => {
    void refresh();
    void getFunds()
      .then(setFunds)
      .catch(() => setFunds([]));
  }, []);

  const filtered = useMemo(() => {
    if (!items) return [];
    return items.filter((item) => {
      if (fundFilter !== ALL && (item.fundId ?? NO_FUND) !== fundFilter) return false;
      if (yearFilter !== ALL && itemYear(item) !== yearFilter) return false;
      if (quarterFilter !== ALL && String(itemQuarter(item)) !== quarterFilter) return false;
      if (typeFilter !== ALL && item.docType !== typeFilter) return false;
      return true;
    });
  }, [items, fundFilter, yearFilter, quarterFilter, typeFilter]);

  /** Jerarquía primaria → año (desc) → trimestre (desc), filas por tipo. */
  const grouped = useMemo(() => {
    const byPrimary = new Map<string, Map<string, Map<number, LibraryItem[]>>>();
    for (const item of filtered) {
      const primaryKey =
        primary === "fund"
          ? (item.fundName ?? t("library.noFund"))
          : docTypeLabel(item.docType);
      const years = byPrimary.get(primaryKey) ?? new Map();
      byPrimary.set(primaryKey, years);
      const quarters = years.get(itemYear(item)) ?? new Map();
      years.set(itemYear(item), quarters);
      const rows = quarters.get(itemQuarter(item)) ?? [];
      quarters.set(itemQuarter(item), rows);
      rows.push(item);
    }
    return Array.from(byPrimary.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([primaryKey, years]) => ({
        primaryKey,
        years: Array.from(years.entries())
          .sort(([a], [b]) => b.localeCompare(a))
          .map(([year, quarters]) => ({
            year,
            quarters: Array.from(quarters.entries())
              .sort(([a], [b]) => b - a)
              .map(([quarter, rows]) => ({
                quarter,
                rows: rows.sort((a: LibraryItem, b: LibraryItem) =>
                  docTypeLabel(a.docType).localeCompare(docTypeLabel(b.docType)),
                ),
              })),
          })),
      }));
  }, [filtered, primary, t]);

  const yearOptions = useMemo(
    () => Array.from(new Set((items ?? []).map(itemYear))).sort().reverse(),
    [items],
  );
  const typeOptions = useMemo(
    () => Array.from(new Set((items ?? []).map((i) => i.docType))).sort(),
    [items],
  );
  const fundOptions = useMemo(() => {
    const entries = new Map<string, string>();
    for (const item of items ?? []) {
      entries.set(item.fundId ?? NO_FUND, item.fundName ?? t("library.noFund"));
    }
    return Array.from(entries.entries());
  }, [items, t]);

  if (items === null) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={t("library.title")}
        subtitle={t("library.subtitle")}
        actions={
          <Button onClick={() => setUploadOpen(true)}>{t("library.upload")}</Button>
        }
      />

      {uploaded ? (
        <Banner tone="success" className="mb-4">
          {t("library.uploadSuccess")}
        </Banner>
      ) : null}

      {/* Filtros por los cuatro ejes + agrupación primaria */}
      <Card className="mb-6 p-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Select value={fundFilter} onChange={(e) => setFundFilter(e.target.value)}>
            <option value={ALL}>{t("library.filterAllFunds")}</option>
            {fundOptions.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </Select>
          <Select value={yearFilter} onChange={(e) => setYearFilter(e.target.value)}>
            <option value={ALL}>{t("library.filterAllYears")}</option>
            {yearOptions.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </Select>
          <Select
            value={quarterFilter}
            onChange={(e) => setQuarterFilter(e.target.value)}
          >
            <option value={ALL}>{t("library.filterAllQuarters")}</option>
            {[1, 2, 3, 4].map((quarter) => (
              <option key={quarter} value={String(quarter)}>
                {t("library.quarter", { q: quarter })}
              </option>
            ))}
          </Select>
          <Select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
            <option value={ALL}>{t("library.filterAllTypes")}</option>
            {typeOptions.map((docType) => (
              <option key={docType} value={docType}>
                {docTypeLabel(docType)}
              </option>
            ))}
          </Select>
          <Select
            value={primary}
            onChange={(e) => setPrimary(e.target.value as PrimaryGroup)}
            aria-label={t("library.groupBy")}
          >
            <option value="fund">
              {t("library.groupBy")}: {t("library.groupFund")}
            </option>
            <option value="type">
              {t("library.groupBy")}: {t("library.groupType")}
            </option>
          </Select>
        </div>
      </Card>

      {grouped.length === 0 ? (
        <Card>
          <p className="text-sm text-ink-400">{t("library.empty")}</p>
        </Card>
      ) : (
        <div className="flex flex-col gap-6">
          {grouped.map((group) => (
            <Card key={group.primaryKey} className="p-5">
              <h2 className="mb-3 text-base font-semibold text-ink-900">
                {group.primaryKey}
              </h2>
              {group.years.map((yearGroup) => (
                <div key={yearGroup.year} className="mb-3">
                  <h3 className="mb-1 text-sm font-semibold text-ink-600">
                    {yearGroup.year}
                  </h3>
                  {yearGroup.quarters.map((quarterGroup) => (
                    <div key={quarterGroup.quarter} className="mb-2 pl-3">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="text-xs font-semibold uppercase tracking-wide text-ink-400">
                          {quarterGroup.quarter > 0
                            ? t("library.quarter", { q: quarterGroup.quarter })
                            : "—"}
                        </span>
                        <span className="text-xs text-ink-300">
                          {t("library.count", { count: quarterGroup.rows.length })}
                        </span>
                      </div>
                      <ul className="divide-y divide-ink-100 rounded-lg border border-ink-100">
                        {quarterGroup.rows.map((item) => (
                          <li
                            key={item.id}
                            className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
                          >
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium text-ink-800">
                                {docTypeLabel(item.docType)}
                              </p>
                              <p className="text-xs text-ink-400">
                                {primary === "type" && item.fundName
                                  ? `${item.fundName} · `
                                  : ""}
                                {itemDate(item) || "—"}
                                {item.language ? ` · ${item.language}` : ""}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              <StatusBadge status={item.versionStatus} />
                              {item.isDocx && item.versionId ? (
                                <Button
                                  variant="ghost"
                                  className="px-2 py-1 text-xs"
                                  onClick={() => setViewing(item)}
                                >
                                  {t("library.view")}
                                </Button>
                              ) : null}
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              ))}
            </Card>
          ))}
        </div>
      )}

      <UploadModal
        open={uploadOpen}
        funds={funds}
        onClose={() => setUploadOpen(false)}
        onUploaded={() => {
          setUploaded(true);
          void refresh();
        }}
      />
      <PrecedentHtmlModal
        versionId={viewing?.versionId ?? null}
        title={viewing ? docTypeLabel(viewing.docType) : undefined}
        onClose={() => setViewing(null)}
      />
    </div>
  );
}
