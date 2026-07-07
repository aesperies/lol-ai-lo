"use client";

import { useState } from "react";
import DocumentViewer from "@/components/DocumentViewer";
import { useI18n } from "@/components/I18nProvider";
import IntakeForm from "@/components/IntakeForm";
import ParsedParamsReview from "@/components/ParsedParamsReview";
import { Banner, Button, Card, PageHeader, Spinner } from "@/components/ui";
import {
  confirmRequest,
  createRequest,
  generateRequest,
  getGenerationJob,
  getRequest,
  parseRequest,
  type CreateRequestInput,
} from "@/lib/api";
import { isAbortError, pollUntil, useUnmountSignal } from "@/lib/hooks";
import type { ParsedParams, RequestItem } from "@/lib/types";

/**
 * Client-side flow state machine (SPEC.md master workflow):
 *   intake → parsing (spinner) → params review → confirmed → generating
 *   (async job, polled every 2s) → ready (Exit A/B) | generation_failed (retry)
 */
type FlowStep =
  | "intake"
  | "parsing"
  | "params"
  | "generating"
  | "generation_failed"
  | "ready";

export default function NewRequestPage() {
  const { t } = useI18n();
  const getSignal = useUnmountSignal();

  const [step, setStep] = useState<FlowStep>("intake");
  const [request, setRequest] = useState<RequestItem | null>(null);
  const [params, setParams] = useState<ParsedParams | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleIntakeSubmit(input: CreateRequestInput) {
    setBusy(true);
    setError(null);
    try {
      const req = await createRequest(input);
      setRequest(req);
      setStep("parsing");
      const parsed = await parseRequest(req.id);
      setParams(parsed);
      setStep("params");
    } catch {
      setError(t("common.error"));
      setStep("intake");
    } finally {
      setBusy(false);
    }
  }

  /** Enqueues the generation job (202) and polls it until terminal state.
   * The poll aborts as soon as the component unmounts (navigation away),
   * so no further API calls or setState happen after unmount. */
  async function generateAndPoll(requestId: string) {
    const signal = getSignal();
    setBusy(true);
    setError(null);
    setJobError(null);
    setStep("generating");
    try {
      await generateRequest(requestId);
      const job = await pollUntil({
        fn: () => getGenerationJob(requestId),
        done: (j) => j.status === "succeeded" || j.status === "failed",
        signal,
      });
      if (job.status === "succeeded") {
        const updated = await getRequest(requestId);
        if (signal.aborted) return;
        setRequest({ ...updated });
        setStep("ready");
      } else {
        setJobError(job.lastError ?? null);
        setStep("generation_failed");
      }
    } catch (err) {
      if (isAbortError(err) || signal.aborted) return;
      setError(t("common.error"));
      setStep("params");
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  async function handleConfirm(confirmed: ParsedParams, edited: boolean) {
    if (!request) return;
    setBusy(true);
    setError(null);
    try {
      // Guardrail 2: never generate without generation_ready + confirmation.
      const confirmedReq = await confirmRequest(request.id, confirmed, edited);
      setRequest(confirmedReq);
    } catch {
      setError(t("common.error"));
      setStep("params");
      setBusy(false);
      return;
    }
    await generateAndPoll(request.id);
  }

  function handleBackToIntake() {
    setRequest(null);
    setParams(null);
    setError(null);
    setStep("intake");
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t("intake.title")} subtitle={t("intake.subtitle")} />

      {error ? <Banner tone="danger" className="mb-6">{error}</Banner> : null}

      {step === "intake" ? (
        <IntakeForm onSubmit={(input) => void handleIntakeSubmit(input)} submitting={busy} />
      ) : null}

      {step === "parsing" ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-center">
          <Spinner className="h-8 w-8" />
          <p className="text-sm font-medium text-ink-700">{t("flow.parsing")}</p>
          <p className="text-xs text-ink-400">{t("flow.parsingHint")}</p>
        </Card>
      ) : null}

      {step === "params" && params ? (
        <ParsedParamsReview
          initialParams={params}
          onConfirm={(p, edited) => void handleConfirm(p, edited)}
          onBackToIntake={handleBackToIntake}
          confirming={busy}
        />
      ) : null}

      {step === "generating" ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-center">
          <Spinner className="h-8 w-8" />
          <p className="text-sm font-medium text-ink-700">{t("flow.generating")}</p>
          <p className="text-xs text-ink-400">{t("flow.generatingHint")}</p>
        </Card>
      ) : null}

      {step === "generation_failed" && request ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-center">
          <p className="text-sm font-medium text-red-700">
            {t("flow.generationFailed")}
          </p>
          <p className="text-xs text-ink-400">{t("flow.generationFailedHint")}</p>
          {jobError ? (
            <p className="max-w-md text-xs text-ink-400">{jobError}</p>
          ) : null}
          <Button
            onClick={() => void generateAndPoll(request.id)}
            disabled={busy}
          >
            {t("flow.retry")}
          </Button>
        </Card>
      ) : null}

      {step === "ready" && request ? (
        <DocumentViewer
          request={request}
          onRequestUpdate={(updated) => setRequest({ ...updated })}
        />
      ) : null}
    </div>
  );
}
