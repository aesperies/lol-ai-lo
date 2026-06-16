"use client";

/**
 * Admin — review playbooks: human-authored rules injected into the automated
 * reviewer (critic). STRICTLY gestora-siloed. Select a gestora, then create /
 * edit / activate / deactivate / delete its playbooks.
 */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardTitle,
  Input,
  Label,
  PageHeader,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import {
  createPlaybook,
  deletePlaybook,
  getGestoras,
  getPlaybooks,
  setPlaybookActive,
  updatePlaybook,
} from "@/lib/api";
import { DOC_TYPE_CATALOG, docTypeGroupLabel } from "@/lib/catalog";
import { BRANCHES } from "@/lib/types";
import type { Gestora, ReviewPlaybook } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

const EMPTY_FORM = {
  title: "",
  content: "",
  branch: "",
  docType: "",
};

export default function AdminPlaybooksPage() {
  const { t } = useI18n();

  const [gestoras, setGestoras] = useState<Gestora[]>([]);
  const [gestoraId, setGestoraId] = useState("");
  const [playbooks, setPlaybooks] = useState<ReviewPlaybook[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Create / edit form.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [file, setFile] = useState<File | null>(null);

  useEffect(() => {
    void getGestoras()
      .then((list) => {
        setGestoras(list);
        if (list.length > 0) setGestoraId((prev) => prev || list[0].id);
      })
      .catch(() => setGestoras([]));
  }, []);

  async function refresh(id: string) {
    setPlaybooks(null);
    const list = await getPlaybooks(id).catch(() => [] as ReviewPlaybook[]);
    setPlaybooks(list);
  }

  useEffect(() => {
    if (gestoraId) void refresh(gestoraId);
  }, [gestoraId]);

  function resetForm() {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setFile(null);
  }

  function startEdit(pb: ReviewPlaybook) {
    setEditingId(pb.id);
    setForm({
      title: pb.title,
      content: pb.content,
      branch: pb.branch ?? "",
      docType: pb.docType ?? "",
    });
    setFile(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!gestoraId || !form.title.trim() || !form.content.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      if (editingId) {
        await updatePlaybook(editingId, {
          title: form.title,
          content: form.content,
          branch: form.branch || null,
          docType: form.docType || null,
        });
        setNotice(t("admin.playbooks.updated"));
      } else {
        await createPlaybook({
          gestoraId,
          title: form.title,
          content: form.content,
          branch: form.branch || null,
          docType: form.docType || null,
          file,
        });
        setNotice(t("admin.playbooks.created"));
      }
      resetForm();
      await refresh(gestoraId);
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleActive(pb: ReviewPlaybook) {
    setBusy(true);
    try {
      await setPlaybookActive(pb.id, !pb.isActive);
      await refresh(gestoraId);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(pb: ReviewPlaybook) {
    if (!window.confirm(t("admin.playbooks.deleteConfirm"))) return;
    setBusy(true);
    try {
      await deletePlaybook(pb.id);
      if (editingId === pb.id) resetForm();
      await refresh(gestoraId);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title={t("admin.playbooks.title")}
        subtitle={t("admin.playbooks.subtitle")}
      />

      <div className="mb-6 max-w-sm">
        <Label htmlFor="pb-gestora">{t("admin.playbooks.selectGestora")}</Label>
        <Select
          id="pb-gestora"
          value={gestoraId}
          onChange={(e) => {
            setGestoraId(e.target.value);
            resetForm();
          }}
        >
          {gestoras.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </Select>
      </div>

      {notice ? <Banner tone="info" className="mb-6">{notice}</Banner> : null}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Playbook list */}
        <div className="space-y-4 lg:col-span-2">
          {playbooks === null ? (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          ) : playbooks.length === 0 ? (
            <Card className="text-center text-sm text-ink-500">
              {t("admin.playbooks.empty")}
            </Card>
          ) : (
            playbooks.map((pb) => (
              <Card key={pb.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-ink-800">{pb.title}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <Badge tone={pb.isActive ? "emerald" : "slate"}>
                        {pb.isActive
                          ? t("admin.playbooks.active")
                          : t("admin.playbooks.inactive")}
                      </Badge>
                      <span className="text-xs text-ink-400">
                        {t("admin.playbooks.scope")}:{" "}
                        {pb.branch
                          ? t(`branch.${pb.branch}` as DictKey)
                          : t("admin.playbooks.scopeAll")}
                      </span>
                      {pb.filePath ? (
                        <span className="text-xs text-ink-400">
                          · {t("admin.playbooks.hasFile")}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      className="px-2.5 py-1 text-xs"
                      disabled={busy}
                      onClick={() => startEdit(pb)}
                    >
                      {t("common.edit")}
                    </Button>
                    <Button
                      variant="ghost"
                      className="px-2.5 py-1 text-xs"
                      disabled={busy}
                      onClick={() => void handleToggleActive(pb)}
                    >
                      {pb.isActive
                        ? t("admin.playbooks.deactivate")
                        : t("admin.playbooks.activate")}
                    </Button>
                    <Button
                      variant="ghost"
                      className="px-2.5 py-1 text-xs text-red-600"
                      disabled={busy}
                      onClick={() => void handleDelete(pb)}
                    >
                      {t("admin.playbooks.delete")}
                    </Button>
                  </div>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm text-ink-600">
                  {pb.content}
                </p>
              </Card>
            ))
          )}
        </div>

        {/* Create / edit form */}
        <Card className="self-start">
          <CardTitle className="mb-4">
            {editingId
              ? t("admin.playbooks.edit")
              : t("admin.playbooks.create")}
          </CardTitle>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <Label htmlFor="pb-title">{t("admin.playbooks.titleField")}</Label>
              <Input
                id="pb-title"
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                required
              />
            </div>
            <div>
              <Label htmlFor="pb-content">{t("admin.playbooks.content")}</Label>
              <Textarea
                id="pb-content"
                rows={5}
                value={form.content}
                onChange={(e) =>
                  setForm((f) => ({ ...f, content: e.target.value }))
                }
                required
              />
              <p className="mt-1 text-xs text-ink-400">
                {t("admin.playbooks.contentHint")}
              </p>
            </div>
            <div>
              <Label htmlFor="pb-branch">{t("admin.playbooks.branch")}</Label>
              <Select
                id="pb-branch"
                value={form.branch}
                onChange={(e) =>
                  setForm((f) => ({ ...f, branch: e.target.value }))
                }
              >
                <option value="">{t("admin.playbooks.anyBranch")}</option>
                {BRANCHES.map((b) => (
                  <option key={b} value={b}>
                    {t(`branch.${b}` as DictKey)}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="pb-doctype">{t("admin.playbooks.docType")}</Label>
              <Select
                id="pb-doctype"
                value={form.docType}
                onChange={(e) =>
                  setForm((f) => ({ ...f, docType: e.target.value }))
                }
              >
                <option value="">{t("admin.playbooks.anyDocType")}</option>
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
            {!editingId ? (
              <div>
                <Label htmlFor="pb-file">{t("admin.playbooks.file")}</Label>
                <input
                  id="pb-file"
                  type="file"
                  accept=".docx,.pdf"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="block w-full text-sm text-ink-600 file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
                />
              </div>
            ) : null}
            <div className="flex gap-2">
              <Button
                type="submit"
                disabled={busy || !form.title.trim() || !form.content.trim()}
              >
                {t("admin.playbooks.save")}
              </Button>
              {editingId ? (
                <Button type="button" variant="ghost" onClick={resetForm}>
                  {t("admin.playbooks.cancel")}
                </Button>
              ) : null}
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}
