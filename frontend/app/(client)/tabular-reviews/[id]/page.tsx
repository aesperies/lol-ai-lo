"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import TabularStatusBadge from "@/components/TabularStatusBadge";
import {
  Badge,
  Banner,
  Button,
  Card,
  Input,
  Label,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import {
  addTabularColumn,
  deleteTabularColumn,
  downloadTabularReviewCsv,
  getTabularReview,
  getTabularReviewStatus,
  runTabularReview,
  triggerBlobDownload,
} from "@/lib/api";
import {
  COL_TYPES,
  type ColType,
  type TabularCell,
  type TabularReviewDetail,
} from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

/** One grid cell: typed value + a citation affordance (page + quote on expand). */
function CellView({ cell }: { cell: TabularCell | undefined }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  if (!cell || cell.status === "pending") {
    return <span className="text-xs text-slate-400">{t("tabular.cellPending")}</span>;
  }
  if (cell.status === "error") {
    return (
      <span className="text-xs text-red-600" title={cell.error ?? undefined}>
        {t("tabular.cellError")}
      </span>
    );
  }

  const hasCitation = Boolean(cell.citation && (cell.citation.quote || cell.citation.page != null));
  return (
    <div className="space-y-1">
      <div className="flex items-start gap-2">
        <span className="font-medium text-slate-800">
          {cell.value || t("tabular.cellEmpty")}
        </span>
        {hasCitation ? (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="mt-0.5 text-slate-400 hover:text-brand-700"
            aria-label={t("tabular.citation")}
            title={t("tabular.citation")}
          >
            <svg
              className="h-3.5 w-3.5"
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        ) : null}
      </div>
      {open && cell.citation ? (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-2 text-xs text-slate-600">
          <div className="mb-1 font-medium text-slate-500">
            {cell.citation.page != null
              ? t("tabular.citationPage", { page: String(cell.citation.page) })
              : t("tabular.citationNoPage")}
          </div>
          {cell.citation.quote ? (
            <blockquote className="border-l-2 border-slate-300 pl-2 italic">
              “{cell.citation.quote}”
            </blockquote>
          ) : null}
          {cell.reasoning ? (
            <div className="mt-1 text-slate-500">
              <span className="font-medium">{t("tabular.reasoning")}: </span>
              {cell.reasoning}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default function TabularReviewDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { t } = useI18n();
  const reviewId = params.id;

  const [review, setReview] = useState<TabularReviewDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [addingColumn, setAddingColumn] = useState(false);
  const [newColName, setNewColName] = useState("");
  const [newColQuestion, setNewColQuestion] = useState("");
  const [newColType, setNewColType] = useState<ColType>("text");
  const [newColOptions, setNewColOptions] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await getTabularReview(reviewId);
      setReview(data);
      return data;
    } catch {
      setNotFound(true);
      return null;
    }
  }, [reviewId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll status while the review is running; reload the grid when it settles.
  useEffect(() => {
    if (!review || review.status !== "running") return;
    pollRef.current = setInterval(() => {
      void getTabularReviewStatus(reviewId).then((status) => {
        if (status.status !== "running") {
          if (pollRef.current) clearInterval(pollRef.current);
          void load();
        }
      });
    }, 1500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [review, reviewId, load]);

  async function handleRun() {
    setRunning(true);
    try {
      await runTabularReview(reviewId);
      await load();
    } finally {
      setRunning(false);
    }
  }

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await downloadTabularReviewCsv(reviewId);
      triggerBlobDownload(blob, `tabular-review-${reviewId}.csv`);
    } finally {
      setExporting(false);
    }
  }

  async function handleAddColumn() {
    if (!newColName.trim() || !newColQuestion.trim()) return;
    const updated = await addTabularColumn(reviewId, {
      name: newColName.trim(),
      question: newColQuestion.trim(),
      colType: newColType,
      options:
        newColType === "tag"
          ? newColOptions
              .split(",")
              .map((o) => o.trim())
              .filter(Boolean)
          : null,
    });
    setReview(updated);
    setAddingColumn(false);
    setNewColName("");
    setNewColQuestion("");
    setNewColType("text");
    setNewColOptions("");
  }

  async function handleDeleteColumn(columnId: string) {
    const updated = await deleteTabularColumn(reviewId, columnId);
    setReview(updated);
  }

  if (notFound) {
    return (
      <div>
        <Banner tone="danger">{t("common.error")}</Banner>
        <div className="mt-4">
          <Link href="/tabular-reviews" className="text-sm text-brand-700 hover:underline">
            {t("common.back")}
          </Link>
        </div>
      </div>
    );
  }

  if (!review) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  const cellByPos = new Map<string, TabularCell>();
  for (const c of review.cells) cellByPos.set(`${c.documentId}:${c.columnId}`, c);
  const errorCount = review.cells.filter((c) => c.status === "error").length;
  const doneCount = review.cells.filter((c) => c.status === "done").length;
  const isRunning = review.status === "running";

  return (
    <div>
      <PageHeader
        title={review.title}
        subtitle={t("tabular.subtitle")}
        actions={
          <div className="flex items-center gap-2">
            <TabularStatusBadge status={review.status} />
            <Button
              variant="secondary"
              onClick={() => void handleExport()}
              disabled={exporting}
            >
              {t("tabular.exportCsv")}
            </Button>
            <Button onClick={() => void handleRun()} disabled={running || isRunning}>
              {isRunning ? (
                <>
                  <Spinner className="h-4 w-4 text-white" />
                  {t("tabular.running")}
                </>
              ) : (
                t("tabular.run")
              )}
            </Button>
          </div>
        }
      />

      <div className="mb-4 flex items-center gap-3 text-xs text-slate-500">
        <span>
          {t("tabular.progress", {
            done: String(doneCount),
            total: String(review.cells.length),
          })}
        </span>
        {errorCount > 0 ? (
          <Badge tone="red">
            {t("tabular.errorCount", { count: String(errorCount) })}
          </Badge>
        ) : null}
      </div>

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
              <th className="sticky left-0 bg-white px-4 py-3 font-medium">
                {t("tabular.document")}
              </th>
              {review.columns.map((col) => (
                <th key={col.id} className="px-4 py-3 font-medium align-top">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="text-slate-700">{col.name}</div>
                      <div className="mt-0.5 normal-case font-normal text-[11px] text-slate-400">
                        {t(`coltype.${col.colType}` as DictKey)}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleDeleteColumn(col.id)}
                      className="text-slate-300 hover:text-red-600"
                      aria-label={t("tabular.removeColumn")}
                      title={t("tabular.removeColumn")}
                    >
                      ×
                    </button>
                  </div>
                </th>
              ))}
              <th className="px-4 py-3">
                {addingColumn ? null : (
                  <Button
                    variant="ghost"
                    type="button"
                    onClick={() => setAddingColumn(true)}
                  >
                    {t("tabular.addColumn")}
                  </Button>
                )}
              </th>
            </tr>
          </thead>
          <tbody>
            {review.documents.map((doc) => (
              <tr
                key={doc.id}
                className="border-b border-slate-100 last:border-0 align-top"
              >
                <td className="sticky left-0 bg-white px-4 py-4 font-medium text-slate-700">
                  {doc.label ?? doc.sourceId}
                </td>
                {review.columns.map((col) => (
                  <td key={col.id} className="px-4 py-4">
                    <CellView cell={cellByPos.get(`${doc.id}:${col.id}`)} />
                  </td>
                ))}
                <td />
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {addingColumn ? (
        <Card className="mt-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="new-col-name">{t("tabular.columnName")}</Label>
              <Input
                id="new-col-name"
                value={newColName}
                onChange={(e) => setNewColName(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="new-col-type">{t("tabular.columnType")}</Label>
              <Select
                id="new-col-type"
                value={newColType}
                onChange={(e) => setNewColType(e.target.value as ColType)}
              >
                {COL_TYPES.map((ct) => (
                  <option key={ct} value={ct}>
                    {t(`coltype.${ct}` as DictKey)}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="mt-3">
            <Label htmlFor="new-col-question">{t("tabular.columnQuestion")}</Label>
            <Input
              id="new-col-question"
              value={newColQuestion}
              onChange={(e) => setNewColQuestion(e.target.value)}
            />
          </div>
          {newColType === "tag" ? (
            <div className="mt-3">
              <Label htmlFor="new-col-options">{t("tabular.columnOptions")}</Label>
              <Input
                id="new-col-options"
                value={newColOptions}
                onChange={(e) => setNewColOptions(e.target.value)}
              />
            </div>
          ) : null}
          <div className="mt-4 flex justify-end gap-2">
            <Button
              variant="secondary"
              type="button"
              onClick={() => setAddingColumn(false)}
            >
              {t("common.cancel")}
            </Button>
            <Button type="button" onClick={() => void handleAddColumn()}>
              {t("tabular.addColumn")}
            </Button>
          </div>
        </Card>
      ) : null}

      <div className="mt-6">
        <Link
          href="/tabular-reviews"
          className="text-sm text-brand-700 hover:underline"
        >
          {t("common.back")}
        </Link>
      </div>
    </div>
  );
}
