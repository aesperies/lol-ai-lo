"use client";

/** GDPR data-retention policy editor for the selected gestora
 * (improvement #10). */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  Input,
  Label,
  Spinner,
} from "@/components/ui";
import { getRetentionPolicy, updateRetentionPolicy } from "@/lib/api";
import type { RetentionPolicy } from "@/lib/types";
import { RETENTION_MONTHS_MAX, RETENTION_MONTHS_MIN } from "@/lib/types";

export default function RetentionPolicyPanel({
  gestoraId,
  onNotice,
}: {
  gestoraId: string;
  onNotice: (msg: string | null) => void;
}) {
  const { t } = useI18n();

  const [retention, setRetention] = useState<RetentionPolicy | null>(null);
  const [retentionMonths, setRetentionMonths] = useState("");
  const [retentionBusy, setRetentionBusy] = useState(false);

  useEffect(() => {
    if (!gestoraId) return;
    let cancelled = false;
    setRetention(null);
    void getRetentionPolicy(gestoraId)
      .then((p) => {
        if (cancelled) return;
        setRetention(p);
        setRetentionMonths(String(p.months));
      })
      .catch(() => {
        if (!cancelled) setRetention(null);
      });
    return () => {
      cancelled = true;
    };
  }, [gestoraId]);

  async function handleSaveRetention(e: React.FormEvent) {
    e.preventDefault();
    const months = Number(retentionMonths);
    if (
      !Number.isInteger(months) ||
      months < RETENTION_MONTHS_MIN ||
      months > RETENTION_MONTHS_MAX
    ) {
      onNotice(t("admin.retention.invalid"));
      return;
    }
    setRetentionBusy(true);
    onNotice(null);
    try {
      const saved = await updateRetentionPolicy(gestoraId, months);
      setRetention(saved);
      setRetentionMonths(String(saved.months));
      onNotice(t("admin.retention.saved"));
    } catch {
      onNotice(t("common.error"));
    } finally {
      setRetentionBusy(false);
    }
  }

  return (
    <Card className="mt-6">
      <CardTitle className="mb-1">{t("admin.retention.title")}</CardTitle>
      <p className="mb-4 text-xs text-ink-500">
        {t("admin.retention.subtitle")}
      </p>

      {retention === null ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : (
        <form
          className="flex flex-wrap items-end gap-4"
          onSubmit={handleSaveRetention}
        >
          <div>
            <Label htmlFor="retention-months">
              {t("admin.retention.months")}
            </Label>
            <Input
              id="retention-months"
              type="number"
              min={RETENTION_MONTHS_MIN}
              max={RETENTION_MONTHS_MAX}
              value={retentionMonths}
              onChange={(e) => setRetentionMonths(e.target.value)}
              className="w-32"
              required
            />
            <p className="mt-1 text-xs text-ink-400">
              {t("admin.retention.hint")}
            </p>
          </div>
          <div className="pb-5">
            <Badge tone={retention.isDefault ? "slate" : "indigo"}>
              {retention.isDefault
                ? t("admin.retention.default")
                : t("admin.retention.custom")}
            </Badge>
          </div>
          <Button type="submit" className="mb-5" disabled={retentionBusy}>
            {t("admin.retention.save")}
          </Button>
        </form>
      )}
    </Card>
  );
}
