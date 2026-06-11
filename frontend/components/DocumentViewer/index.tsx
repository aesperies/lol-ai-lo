"use client";

import { useId, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import StatusBadge from "@/components/StatusBadge";
import { Banner, Button, Card, CardTitle } from "@/components/ui";
import {
  acknowledgeExitA,
  downloadDocument,
  requestExitB,
  triggerBlobDownload,
} from "@/lib/api";
import type { RequestItem } from "@/lib/types";

/**
 * Step 5 of the master workflow — CLIENT reviews the generated document:
 * - [Descargar Borrador] + [Descargar Redline vs. Precedente]
 * - EXIT A "Me vale": verbatim acknowledgment checkbox (guardrail 9) +
 *   [Confirmar y Descargar]
 * - EXIT B "Validación por abogado": [Solicitar Validación]
 * - Level-3 fallback (no precedent) shows the verbatim warning banner and
 *   hides Exit A entirely (guardrail 10)
 * - [MISSING] fields block Exit A (guardrail 5)
 * - SLP disclaimer shown verbatim on every generated document
 */
export default function DocumentViewer({
  request,
  onRequestUpdate,
}: {
  request: RequestItem;
  onRequestUpdate?: (req: RequestItem) => void;
}) {
  const { t } = useI18n();
  const ackId = useId();

  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState<"exitA" | "exitB" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isLevel3 = request.fallbackLevel === 3;
  const missingBlocked = Boolean(request.hasMissingFields);
  const exitAAvailable = !isLevel3 && !missingBlocked;

  const documentReady = [
    "review_pending",
    "counsel_review",
    "validated",
    "delivered",
  ].includes(request.status);

  async function handleDownload(type: "draft" | "redline") {
    setError(null);
    try {
      const blob = await downloadDocument(request.id, type);
      triggerBlobDownload(
        blob,
        `${request.id}_${type}.docx`, // stub returns plain text; backend returns real .docx
      );
    } catch {
      setError(t("common.error"));
    }
  }

  async function handleExitA() {
    if (!acknowledged || !exitAAvailable) return;
    setBusy("exitA");
    setError(null);
    try {
      const updated = await acknowledgeExitA(request.id);
      onRequestUpdate?.(updated);
      // Exit A delivery = the client downloads the draft after acknowledging.
      await handleDownload("draft");
    } catch {
      setError(t("common.error"));
    } finally {
      setBusy(null);
    }
  }

  async function handleExitB() {
    setBusy("exitB");
    setError(null);
    try {
      const updated = await requestExitB(request.id);
      onRequestUpdate?.(updated);
    } catch {
      setError(t("common.error"));
    } finally {
      setBusy(null);
    }
  }

  if (!documentReady) {
    return (
      <Card>
        <Banner tone="info">{t("viewer.notReadyYet")}</Banner>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <CardTitle>{t("viewer.title")}</CardTitle>
            <p className="mt-1 text-sm text-slate-500">
              {request.docTypeLabel ?? request.docType} — {request.fundName}
            </p>
          </div>
          <StatusBadge status={request.status} />
        </div>

        {/* Level-3 warning (verbatim) — forces Exit B */}
        {isLevel3 ? (
          <Banner tone="danger" className="mt-4">
            <strong className="font-semibold">{t("viewer.level3Warning")}</strong>
          </Banner>
        ) : null}

        {/* [MISSING] fields block Exit A */}
        {!isLevel3 && missingBlocked ? (
          <Banner tone="warning" className="mt-4">
            {t("viewer.missingBlocksExitA")}
          </Banner>
        ) : null}

        {/* Draft + redline downloads */}
        <div className="mt-6 flex flex-wrap gap-3">
          <Button variant="secondary" onClick={() => void handleDownload("draft")}>
            ⬇ {t("viewer.downloadDraft")}
          </Button>
          <Button variant="secondary" onClick={() => void handleDownload("redline")}>
            ⬇ {t("viewer.downloadRedline")}
          </Button>
        </div>
      </Card>

      {error ? <Banner tone="danger">{error}</Banner> : null}

      {/* Status-specific notes for terminal / in-review states */}
      {request.status === "counsel_review" ? (
        <Banner tone="info">{t("viewer.counselReviewNote")}</Banner>
      ) : null}
      {request.status === "validated" ? (
        <Banner tone="success">{t("viewer.validatedNote")}</Banner>
      ) : null}
      {request.status === "delivered" ? (
        <Banner tone="success">
          {request.requiresCounsel
            ? t("viewer.validatedNote")
            : t("viewer.deliveredNote")}
        </Banner>
      ) : null}

      {/* Exit panels — only while pending the client's decision */}
      {request.status === "review_pending" ? (
        <div
          className={
            exitAAvailable ? "grid gap-6 lg:grid-cols-2" : "grid gap-6"
          }
        >
          {/* EXIT A — hidden entirely on Level 3 (guardrail 10) */}
          {exitAAvailable ? (
            <Card className="border-emerald-200">
              <CardTitle className="text-emerald-800">
                {t("viewer.exitATitle")}
              </CardTitle>
              <p className="mt-1 text-sm text-slate-500">{t("viewer.exitADesc")}</p>
              <label
                htmlFor={ackId}
                className="mt-4 flex cursor-pointer items-start gap-3 rounded-md border border-slate-200 bg-slate-50 p-3"
              >
                <input
                  id={ackId}
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(e) => setAcknowledged(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-700 focus:ring-brand-500"
                />
                {/* Verbatim acknowledgment text (SPEC.md) */}
                <span className="text-sm leading-relaxed text-slate-700">
                  {t("viewer.exitAAck")}
                </span>
              </label>
              <div className="mt-4">
                <Button
                  disabled={!acknowledged || busy !== null}
                  onClick={() => void handleExitA()}
                >
                  {t("viewer.exitAConfirm")}
                </Button>
              </div>
            </Card>
          ) : null}

          {/* EXIT B */}
          <Card className="border-violet-200">
            <CardTitle className="text-violet-800">
              {t("viewer.exitBTitle")}
            </CardTitle>
            <p className="mt-1 text-sm text-slate-500">{t("viewer.exitBDesc")}</p>
            <div className="mt-4">
              <Button
                variant={exitAAvailable ? "secondary" : "primary"}
                disabled={busy !== null}
                onClick={() => void handleExitB()}
              >
                {t("viewer.exitBRequest")}
              </Button>
            </div>
          </Card>
        </div>
      ) : null}

      {/* SLP disclaimer — verbatim, on every generated document */}
      <p className="border-t border-slate-200 pt-4 text-xs leading-relaxed text-slate-400">
        {t("viewer.disclaimer")}
      </p>
    </div>
  );
}
