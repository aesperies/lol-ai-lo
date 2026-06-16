"use client";

/** Account — GDPR data-subject rights: export + erasure/anonymisation. */

import { useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Banner,
  Button,
  Card,
  CardTitle,
  Input,
  Label,
  PageHeader,
  Select,
} from "@/components/ui";
import { deleteMyData, exportMyData, triggerBlobDownload } from "@/lib/api";
import { DATA_DELETE_CONFIRMATION, type DeleteMode } from "@/lib/types";

export default function AccountPrivacyPage() {
  const { t } = useI18n();

  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [mode, setMode] = useState<DeleteMode>("anonymize");
  const [confirm, setConfirm] = useState("");

  async function handleExport() {
    setBusy(true);
    setNotice(null);
    try {
      const blob = await exportMyData();
      triggerBlobDownload(blob, "lolailo-mis-datos.json");
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(e: React.FormEvent) {
    e.preventDefault();
    if (confirm !== DATA_DELETE_CONFIRMATION) return;
    setBusy(true);
    setNotice(null);
    try {
      await deleteMyData({ confirm, mode });
      setConfirm("");
      setNotice(t("account.privacy.deleted"));
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title={t("account.privacy.title")}
        subtitle={t("account.privacy.subtitle")}
      />

      {notice ? (
        <Banner tone="info" className="mb-6">
          {notice}
        </Banner>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle className="mb-2">{t("account.privacy.export")}</CardTitle>
          <p className="mb-4 text-sm text-ink-600">
            {t("account.privacy.exportHint")}
          </p>
          <Button onClick={() => void handleExport()} disabled={busy}>
            {t("account.privacy.export")}
          </Button>
        </Card>

        <Card>
          <CardTitle className="mb-2">{t("account.privacy.delete")}</CardTitle>
          <p className="mb-4 text-sm text-ink-600">
            {t("account.privacy.deleteHint")}
          </p>
          <form className="space-y-4" onSubmit={handleDelete}>
            <div>
              <Label htmlFor="delete-mode">{t("account.privacy.mode")}</Label>
              <Select
                id="delete-mode"
                value={mode}
                onChange={(e) => setMode(e.target.value as DeleteMode)}
              >
                <option value="anonymize">
                  {t("account.privacy.modeAnonymize")}
                </option>
                <option value="erase">{t("account.privacy.modeErase")}</option>
              </Select>
            </div>
            <div>
              <Label htmlFor="delete-confirm">
                {t("account.privacy.confirmLabel", {
                  phrase: DATA_DELETE_CONFIRMATION,
                })}
              </Label>
              <Input
                id="delete-confirm"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder={DATA_DELETE_CONFIRMATION}
              />
            </div>
            <Button
              type="submit"
              variant="danger"
              disabled={busy || confirm !== DATA_DELETE_CONFIRMATION}
            >
              {t("account.privacy.confirmCta")}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
