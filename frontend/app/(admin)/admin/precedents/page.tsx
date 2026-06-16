"use client";

/**
 * Admin — precedent library: upload + version activate/supersede.
 * Activating a version supersedes the previously active one (rag_weight 0.3,
 * kept for RAG), mirroring the backend re-index rules in SPEC.md.
 */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardTitle,
  Label,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import {
  activatePrecedentVersion,
  getGestoras,
  getPrecedents,
  supersedePrecedentVersion,
  uploadModel,
  uploadPrecedent,
} from "@/lib/api";
import { DOC_TYPE_CATALOG, docTypeGroupLabel } from "@/lib/catalog";
import type { Gestora, Precedent } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

export default function AdminPrecedentsPage() {
  const { t } = useI18n();

  const [precedents, setPrecedents] = useState<Precedent[] | null>(null);
  const [gestoras, setGestoras] = useState<Gestora[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // "Modelos" (gestora master templates) vs "Precedentes" (everything else).
  const [tab, setTab] = useState<"precedents" | "models">("precedents");

  // Upload form
  const [uploadGestora, setUploadGestora] = useState("");
  const [uploadDocType, setUploadDocType] = useState("");
  const [uploadLanguage, setUploadLanguage] = useState("es");
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  async function refresh() {
    const list = await getPrecedents().catch(() => [] as Precedent[]);
    setPrecedents(list);
  }

  useEffect(() => {
    void refresh();
    void getGestoras().then(setGestoras).catch(() => setGestoras([]));
  }, []);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadFile || !uploadGestora || !uploadDocType) return;
    setBusy(true);
    setNotice(null);
    try {
      const input = {
        gestoraId: uploadGestora,
        docType: uploadDocType,
        language: uploadLanguage,
        file: uploadFile,
      };
      if (tab === "models") {
        await uploadModel(input);
        setNotice(t("admin.models.uploaded"));
      } else {
        await uploadPrecedent(input);
        setNotice(t("admin.precedents.uploaded"));
      }
      setUploadFile(null);
      await refresh();
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function handleActivate(precedentId: string, versionId: string) {
    setBusy(true);
    try {
      await activatePrecedentVersion(precedentId, versionId);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function handleSupersede(precedentId: string, versionId: string) {
    setBusy(true);
    try {
      await supersedePrecedentVersion(precedentId, versionId);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  const isModelTab = tab === "models";
  const visible = (precedents ?? []).filter((p) =>
    isModelTab ? p.source === "gestora_model" : p.source !== "gestora_model",
  );

  return (
    <div>
      <PageHeader
        title={
          isModelTab ? t("admin.models.title") : t("admin.precedents.title")
        }
        subtitle={
          isModelTab
            ? t("admin.models.subtitle")
            : t("admin.precedents.subtitle")
        }
      />

      {/* Modelos | Precedentes tabs */}
      <div className="mb-6 inline-flex rounded-md border border-slate-200 bg-slate-100 p-1">
        {(["precedents", "models"] as const).map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={tab === key}
            onClick={() => setTab(key)}
            className={
              tab === key
                ? "rounded px-3 py-1.5 text-sm font-medium bg-white text-slate-900 shadow-sm"
                : "rounded px-3 py-1.5 text-sm font-medium text-slate-500 hover:text-slate-700"
            }
          >
            {key === "models"
              ? t("admin.models.tabModels")
              : t("admin.models.tabPrecedents")}
          </button>
        ))}
      </div>

      {notice ? <Banner tone="info" className="mb-6">{notice}</Banner> : null}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Precedent / model list with versions */}
        <div className="space-y-4 lg:col-span-2">
          {precedents === null ? (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          ) : visible.length === 0 ? (
            <Card className="text-center text-sm text-slate-500">
              {isModelTab ? t("admin.models.empty") : t("common.empty")}
            </Card>
          ) : (
            visible.map((p) => (
              <Card key={p.id}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-800">
                      {p.docTypeLabel ?? p.docType}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {gestoras.find((g) => g.id === p.gestoraId)?.name ?? p.gestoraId}{" "}
                      · {p.language.toUpperCase()} ·{" "}
                      {t("admin.precedents.source")}:{" "}
                      {t(`precedentSource.${p.source}` as DictKey)}
                    </p>
                  </div>
                </div>
                <div className="mt-4 divide-y divide-slate-100 rounded-md border border-slate-200">
                  {p.versions.map((v) => (
                    <div
                      key={v.id}
                      className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 text-sm"
                    >
                      <div className="flex items-center gap-3">
                        <span className="font-medium text-slate-700">
                          {t("admin.precedents.version")} {v.versionNumber}
                        </span>
                        <Badge
                          tone={
                            v.status === "active"
                              ? "emerald"
                              : v.status === "superseded"
                                ? "slate"
                                : "amber"
                          }
                        >
                          {t(`precedentStatus.${v.status}` as DictKey)}
                        </Badge>
                        <span className="text-xs text-slate-400">
                          {t("admin.precedents.ragWeight")}: {v.ragWeight.toFixed(1)}
                        </span>
                      </div>
                      <div className="flex gap-2">
                        {v.status !== "active" ? (
                          <Button
                            variant="secondary"
                            className="px-2.5 py-1 text-xs"
                            disabled={busy}
                            onClick={() => void handleActivate(p.id, v.id)}
                          >
                            {t("admin.precedents.activate")}
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            className="px-2.5 py-1 text-xs"
                            disabled={busy}
                            onClick={() => void handleSupersede(p.id, v.id)}
                          >
                            {t("admin.precedents.supersede")}
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            ))
          )}
        </div>

        {/* Upload */}
        <Card className="self-start">
          <CardTitle className="mb-1">
            {isModelTab
              ? t("admin.models.upload")
              : t("admin.precedents.upload")}
          </CardTitle>
          <p className="mb-4 text-xs text-slate-500">
            {isModelTab
              ? t("admin.models.uploadHint")
              : t("admin.precedents.uploadHint")}
          </p>
          <form className="space-y-4" onSubmit={handleUpload}>
            <div>
              <Label htmlFor="up-gestora">{t("admin.users.gestora")}</Label>
              <Select
                id="up-gestora"
                value={uploadGestora}
                onChange={(e) => setUploadGestora(e.target.value)}
                required
              >
                <option value="" disabled>
                  —
                </option>
                {gestoras.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="up-doctype">{t("common.docType")}</Label>
              <Select
                id="up-doctype"
                value={uploadDocType}
                onChange={(e) => setUploadDocType(e.target.value)}
                required
              >
                <option value="" disabled>
                  —
                </option>
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
              <Label htmlFor="up-lang">{t("common.language")}</Label>
              <Select
                id="up-lang"
                value={uploadLanguage}
                onChange={(e) => setUploadLanguage(e.target.value)}
              >
                <option value="es">ES</option>
                <option value="en">EN</option>
                <option value="fr">FR</option>
                <option value="de">DE</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="up-file">.docx / .pdf</Label>
              <input
                id="up-file"
                type="file"
                accept=".docx,.pdf"
                required
                onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
              />
            </div>
            <Button type="submit" className="w-full" disabled={busy || !uploadFile}>
              {t("common.upload")}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
