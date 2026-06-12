"use client";

import { useEffect, useId, useState } from "react";
import DocumentHtmlViewer from "@/components/DocumentHtmlViewer";
import { useI18n } from "@/components/I18nProvider";
import StatusBadge from "@/components/StatusBadge";
import { Banner, Button, Card, CardTitle, Spinner, Textarea } from "@/components/ui";
import {
  MAX_REFINEMENTS,
  acknowledgeExitA,
  createRefinement,
  downloadDocument,
  getGenerationJob,
  getRefinements,
  getRequest,
  requestExitB,
  triggerBlobDownload,
} from "@/lib/api";
import type { Refinement, RequestItem } from "@/lib/types";

const JOB_POLL_INTERVAL_MS = 2000;
const INSTRUCTION_MIN = 5;
const INSTRUCTION_MAX = 1000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Step 5 of the master workflow — CLIENT reviews the generated document:
 * - In-browser viewer with "Borrador" | "Redline vs. Precedente" tabs
 *   (rendered HTML, no download needed)
 * - Version history: iteration selector (v0, v1, …) above the tabs; older
 *   versions are read-only (no Exit A/B, no refine)
 * - "Solicitar ajuste" (iterative refinement, collapsed by default): up to
 *   MAX_REFINEMENTS natural-language adjustments regenerate the document as
 *   a new iteration; an unclear instruction surfaces the reason inline with
 *   the previous document untouched; at the limit the client is directed to
 *   Exit B
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
  const [tab, setTab] = useState<"draft" | "redline">("draft");

  // Iterative refinements + version history.
  const [refinements, setRefinements] = useState<Refinement[]>([]);
  const [refineOpen, setRefineOpen] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [refining, setRefining] = useState(false);
  const [refineError, setRefineError] = useState<string | null>(null);
  const [refineNotice, setRefineNotice] = useState<string | null>(null);
  /** null = latest iteration (server default); a number = explicit version. */
  const [selectedIteration, setSelectedIteration] = useState<number | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  const isLevel3 = request.fallbackLevel === 3;
  const missingBlocked = Boolean(request.hasMissingFields);
  const exitAAvailable = !isLevel3 && !missingBlocked;

  const documentReady = [
    "review_pending",
    "counsel_review",
    "validated",
    "delivered",
  ].includes(request.status);

  useEffect(() => {
    if (!documentReady) return;
    let cancelled = false;
    getRefinements(request.id)
      .then((rows) => {
        if (!cancelled) setRefinements(rows);
      })
      .catch(() => {
        /* history is non-blocking; viewer still works without it */
      });
    return () => {
      cancelled = true;
    };
  }, [request.id, documentReady]);

  const appliedIterations = refinements
    .filter((r) => r.status === "applied")
    .map((r) => r.iteration)
    .sort((a, b) => a - b);
  const iterations = [0, ...appliedIterations];
  const latestIteration = iterations[iterations.length - 1];
  const viewIteration = selectedIteration ?? latestIteration;
  const viewingLatest = viewIteration === latestIteration;
  // Failed refinements created no iteration and are not billed: they do not
  // consume the quota (mirrors the backend limit check).
  const remaining = Math.max(
    0,
    MAX_REFINEMENTS - refinements.filter((r) => r.status !== "failed").length,
  );
  // Pass an explicit iteration only for older versions; the latest uses the
  // server default so it stays correct right after a refinement lands.
  const iterationParam = viewingLatest ? undefined : viewIteration;

  async function handleDownload(type: "draft" | "redline") {
    setError(null);
    try {
      const blob = await downloadDocument(request.id, type, iterationParam);
      triggerBlobDownload(
        blob,
        `${request.id}_${type}${viewingLatest ? "" : `_v${viewIteration}`}.docx`, // stub returns plain text; backend returns real .docx
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

  /** Enqueues the refinement (202) and polls the generation job until done,
   * then refreshes the history + viewer (same pattern as new-request). */
  async function handleRefine() {
    const text = instruction.trim();
    if (text.length < INSTRUCTION_MIN || text.length > INSTRUCTION_MAX) return;
    setRefining(true);
    setRefineError(null);
    setRefineNotice(null);
    try {
      await createRefinement(request.id, text);
      for (;;) {
        await sleep(JOB_POLL_INTERVAL_MS);
        const job = await getGenerationJob(request.id);
        if (job.status !== "succeeded" && job.status !== "failed") continue;

        const [updated, rows] = await Promise.all([
          getRequest(request.id),
          getRefinements(request.id),
        ]);
        setRefinements(rows);
        onRequestUpdate?.(updated);
        const latest = rows[rows.length - 1];
        if (job.status === "failed" || latest?.status === "failed") {
          // [REFINEMENT-UNCLEAR] or job failure: previous document untouched,
          // reason shown inline.
          setRefineError(latest?.error ?? job.lastError ?? t("refine.failed"));
        } else {
          setInstruction("");
          setSelectedIteration(null); // jump to the new latest iteration
          setRefreshToken((n) => n + 1);
          setRefineNotice(t("refine.applied"));
        }
        return;
      }
    } catch {
      setRefineError(t("common.error"));
    } finally {
      setRefining(false);
    }
  }

  if (!documentReady) {
    return (
      <Card>
        <Banner tone="info">{t("viewer.notReadyYet")}</Banner>
      </Card>
    );
  }

  const instructionLength = instruction.trim().length;

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

        {/* Version history: iteration selector (v0, v1, …) above the tabs */}
        {iterations.length > 1 ? (
          <div className="mt-6 flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-slate-500">
              {t("viewer.versionLabel")}:
            </span>
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-1">
              {iterations.map((it) => {
                const active = viewIteration === it;
                return (
                  <button
                    key={it}
                    type="button"
                    aria-pressed={active}
                    onClick={() =>
                      setSelectedIteration(it === latestIteration ? null : it)
                    }
                    className={
                      active
                        ? "rounded px-2.5 py-1 text-xs font-medium bg-white text-slate-900 shadow-sm"
                        : "rounded px-2.5 py-1 text-xs font-medium text-slate-500 hover:text-slate-700"
                    }
                  >
                    v{it}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}

        {/* Older versions are read-only */}
        {!viewingLatest ? (
          <Banner tone="warning" className="mt-4">
            {t("viewer.oldVersionBanner")}
          </Banner>
        ) : null}

        {/* In-browser viewer: Borrador | Redline vs. Precedente tabs */}
        <div className="mt-6">
          <div
            role="tablist"
            className="mb-3 inline-flex rounded-md border border-slate-200 bg-slate-100 p-1"
          >
            {(["draft", "redline"] as const).map((type) => (
              <button
                key={type}
                type="button"
                role="tab"
                aria-selected={tab === type}
                onClick={() => setTab(type)}
                className={
                  tab === type
                    ? "rounded px-3 py-1.5 text-sm font-medium bg-white text-slate-900 shadow-sm"
                    : "rounded px-3 py-1.5 text-sm font-medium text-slate-500 hover:text-slate-700"
                }
              >
                {type === "draft"
                  ? t("viewer.tabDraft")
                  : t("viewer.tabRedline")}
              </button>
            ))}
          </div>
          <DocumentHtmlViewer
            requestId={request.id}
            versionType={tab}
            iteration={iterationParam}
            refreshToken={refreshToken}
          />
        </div>

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
      {refineNotice ? <Banner tone="success">{refineNotice}</Banner> : null}

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

      {/* Solicitar ajuste — iterative refinement (latest version only) */}
      {request.status === "review_pending" && viewingLatest ? (
        <Card>
          <button
            type="button"
            aria-expanded={refineOpen}
            onClick={() => setRefineOpen((open) => !open)}
            className="flex w-full items-center justify-between gap-3 text-left"
          >
            <div>
              <CardTitle>{t("refine.title")}</CardTitle>
              <p className="mt-0.5 text-xs text-slate-500">
                {t("refine.remaining", { count: remaining })}
              </p>
            </div>
            <span aria-hidden="true" className="text-lg text-slate-400">
              {refineOpen ? "−" : "+"}
            </span>
          </button>

          {refineOpen ? (
            remaining > 0 ? (
              <div className="mt-4 space-y-3">
                <p className="text-sm text-slate-500">{t("refine.desc")}</p>
                <Textarea
                  rows={3}
                  maxLength={INSTRUCTION_MAX}
                  value={instruction}
                  disabled={refining}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder={t("refine.placeholder")}
                />
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
                  <span>
                    {t("intake.charCount", {
                      count: instruction.length,
                      max: INSTRUCTION_MAX,
                    })}
                  </span>
                  {instructionLength > 0 && instructionLength < INSTRUCTION_MIN ? (
                    <span>{t("intake.minChars", { min: INSTRUCTION_MIN })}</span>
                  ) : null}
                </div>

                {/* [REFINEMENT-UNCLEAR] / failure reason, previous doc untouched */}
                {refineError ? (
                  <Banner tone="danger">
                    <strong className="font-semibold">{t("refine.failed")}</strong>{" "}
                    {refineError}
                  </Banner>
                ) : null}

                {refining ? (
                  <div className="flex items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                    <Spinner className="h-4 w-4" />
                    <span>
                      {t("refine.processing")}{" "}
                      <span className="text-xs text-slate-400">
                        {t("refine.processingHint")}
                      </span>
                    </span>
                  </div>
                ) : (
                  <Button
                    disabled={
                      busy !== null ||
                      instructionLength < INSTRUCTION_MIN ||
                      instructionLength > INSTRUCTION_MAX
                    }
                    onClick={() => void handleRefine()}
                  >
                    {t("refine.submit")}
                  </Button>
                )}
              </div>
            ) : (
              <Banner tone="info" className="mt-4">
                {t("refine.limitReached")}
              </Banner>
            )
          ) : null}
        </Card>
      ) : null}

      {/* Exit panels — only while pending the client's decision, latest version */}
      {request.status === "review_pending" && viewingLatest ? (
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
                  disabled={!acknowledged || busy !== null || refining}
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
                disabled={busy !== null || refining}
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
