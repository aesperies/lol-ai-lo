"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Banner,
  Button,
  Card,
  CardTitle,
  Input,
  Label,
  Select,
  Spinner,
} from "@/components/ui";
import { PageHeader } from "@/components/ui";
import {
  createTabularReview,
  getFunds,
  getTabularDocumentOptions,
  runTabularReview,
} from "@/lib/api";
import { COL_TYPES, type ColType, type Fund, type TabularDocumentOption } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

interface ColumnDraft {
  name: string;
  question: string;
  colType: ColType;
  options: string;
}

function emptyColumn(): ColumnDraft {
  return { name: "", question: "", colType: "text", options: "" };
}

export default function NewTabularReviewPage() {
  const { t } = useI18n();
  const router = useRouter();

  const [title, setTitle] = useState("");
  const [fundId, setFundId] = useState("");
  const [funds, setFunds] = useState<Fund[]>([]);
  const [docOptions, setDocOptions] = useState<TabularDocumentOption[] | null>(
    null,
  );
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const [columns, setColumns] = useState<ColumnDraft[]>([emptyColumn()]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void getFunds().then(setFunds).catch(() => setFunds([]));
    void getTabularDocumentOptions()
      .then(setDocOptions)
      .catch(() => setDocOptions([]));
  }, []);

  function toggleDoc(sourceId: string) {
    setSelectedDocs((prev) => {
      const next = new Set(prev);
      if (next.has(sourceId)) next.delete(sourceId);
      else next.add(sourceId);
      return next;
    });
  }

  function updateColumn(index: number, patch: Partial<ColumnDraft>) {
    setColumns((prev) =>
      prev.map((c, i) => (i === index ? { ...c, ...patch } : c)),
    );
  }

  function removeColumn(index: number) {
    setColumns((prev) => prev.filter((_, i) => i !== index));
  }

  async function submit(run: boolean) {
    setError(null);
    if (!title.trim()) {
      setError(t("tabular.needTitle"));
      return;
    }
    const docs = (docOptions ?? []).filter((d) =>
      selectedDocs.has(d.sourceId),
    );
    if (docs.length === 0) {
      setError(t("tabular.needDocuments"));
      return;
    }
    const cleanColumns = columns
      .filter((c) => c.name.trim() && c.question.trim())
      .map((c) => ({
        name: c.name.trim(),
        question: c.question.trim(),
        colType: c.colType,
        options:
          c.colType === "tag"
            ? c.options
                .split(",")
                .map((o) => o.trim())
                .filter(Boolean)
            : null,
      }));
    if (cleanColumns.length === 0) {
      setError(t("tabular.needColumns"));
      return;
    }

    setSubmitting(true);
    try {
      const review = await createTabularReview({
        title: title.trim(),
        fundId: fundId || null,
        columns: cleanColumns,
        documents: docs,
      });
      if (run) {
        await runTabularReview(review.id);
      }
      router.push(`/tabular-reviews/${review.id}`);
    } catch {
      setError(t("common.error"));
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader title={t("tabular.newTitle")} subtitle={t("tabular.newSubtitle")} />

      {error ? (
        <Banner tone="danger" className="mb-6">
          {error}
        </Banner>
      ) : null}

      <div className="space-y-6">
        <Card>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="title">{t("tabular.fieldTitle")}</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder={t("tabular.fieldTitlePlaceholder")}
              />
            </div>
            <div>
              <Label htmlFor="fund">{t("tabular.fieldFund")}</Label>
              <Select
                id="fund"
                value={fundId}
                onChange={(e) => setFundId(e.target.value)}
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

        <Card>
          <CardTitle>{t("tabular.pickDocuments")}</CardTitle>
          <p className="mb-4 mt-1 text-xs text-slate-500">
            {t("tabular.pickDocumentsHint")}
          </p>
          {docOptions === null ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : docOptions.length === 0 ? (
            <p className="text-sm text-slate-500">{t("tabular.noDocuments")}</p>
          ) : (
            <ul className="space-y-2">
              {docOptions.map((d) => (
                <li key={d.sourceId}>
                  <label className="flex items-center gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={selectedDocs.has(d.sourceId)}
                      onChange={() => toggleDoc(d.sourceId)}
                      className="h-4 w-4 rounded border-slate-300 text-brand-700 focus:ring-brand-500"
                    />
                    <span className="text-slate-800">{d.label}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardTitle>{t("tabular.defineColumns")}</CardTitle>
          <div className="mt-4 space-y-4">
            {columns.map((col, index) => (
              <div
                key={index}
                className="rounded-md border border-slate-200 p-4"
              >
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <Label htmlFor={`name-${index}`}>
                      {t("tabular.columnName")}
                    </Label>
                    <Input
                      id={`name-${index}`}
                      value={col.name}
                      onChange={(e) =>
                        updateColumn(index, { name: e.target.value })
                      }
                    />
                  </div>
                  <div>
                    <Label htmlFor={`type-${index}`}>
                      {t("tabular.columnType")}
                    </Label>
                    <Select
                      id={`type-${index}`}
                      value={col.colType}
                      onChange={(e) =>
                        updateColumn(index, {
                          colType: e.target.value as ColType,
                        })
                      }
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
                  <Label htmlFor={`question-${index}`}>
                    {t("tabular.columnQuestion")}
                  </Label>
                  <Input
                    id={`question-${index}`}
                    value={col.question}
                    onChange={(e) =>
                      updateColumn(index, { question: e.target.value })
                    }
                  />
                </div>
                {col.colType === "tag" ? (
                  <div className="mt-3">
                    <Label htmlFor={`options-${index}`}>
                      {t("tabular.columnOptions")}
                    </Label>
                    <Input
                      id={`options-${index}`}
                      value={col.options}
                      onChange={(e) =>
                        updateColumn(index, { options: e.target.value })
                      }
                    />
                  </div>
                ) : null}
                {columns.length > 1 ? (
                  <div className="mt-3 text-right">
                    <Button
                      variant="ghost"
                      type="button"
                      onClick={() => removeColumn(index)}
                    >
                      {t("tabular.removeColumn")}
                    </Button>
                  </div>
                ) : null}
              </div>
            ))}
            <Button
              variant="secondary"
              type="button"
              onClick={() => setColumns((prev) => [...prev, emptyColumn()])}
            >
              {t("tabular.addColumnRow")}
            </Button>
          </div>
        </Card>

        <div className="flex items-center justify-end gap-3">
          <Button
            variant="secondary"
            type="button"
            disabled={submitting}
            onClick={() => void submit(false)}
          >
            {t("tabular.create")}
          </Button>
          <Button
            type="button"
            disabled={submitting}
            onClick={() => void submit(true)}
          >
            {submitting ? <Spinner className="h-4 w-4 text-white" /> : null}
            {t("tabular.createAndRun")}
          </Button>
        </div>
      </div>
    </div>
  );
}
