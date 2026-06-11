"use client";

import { useState } from "react";
import DocumentViewer from "@/components/DocumentViewer";
import { useI18n } from "@/components/I18nProvider";
import IntakeForm from "@/components/IntakeForm";
import ParsedParamsReview from "@/components/ParsedParamsReview";
import { Banner, Card, PageHeader, Spinner } from "@/components/ui";
import {
  confirmRequest,
  createRequest,
  generateRequest,
  parseRequest,
  type CreateRequestInput,
} from "@/lib/api";
import type { ParsedParams, RequestItem } from "@/lib/types";

/**
 * Client-side flow state machine (SPEC.md master workflow):
 *   intake → parsing (spinner) → params review → confirmed → generating → ready (Exit A/B)
 */
type FlowStep =
  | "intake"
  | "parsing"
  | "params"
  | "generating"
  | "ready";

export default function NewRequestPage() {
  const { t } = useI18n();

  const [step, setStep] = useState<FlowStep>("intake");
  const [request, setRequest] = useState<RequestItem | null>(null);
  const [params, setParams] = useState<ParsedParams | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  async function handleConfirm(confirmed: ParsedParams, edited: boolean) {
    if (!request) return;
    setBusy(true);
    setError(null);
    try {
      // Guardrail 2: never generate without generation_ready + confirmation.
      const confirmedReq = await confirmRequest(request.id, confirmed, edited);
      setRequest(confirmedReq);
      setStep("generating");
      const generated = await generateRequest(request.id);
      setRequest({ ...generated });
      setStep("ready");
    } catch {
      setError(t("common.error"));
      setStep("params");
    } finally {
      setBusy(false);
    }
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
          <p className="text-sm font-medium text-slate-700">{t("flow.parsing")}</p>
          <p className="text-xs text-slate-400">{t("flow.parsingHint")}</p>
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
          <p className="text-sm font-medium text-slate-700">{t("flow.generating")}</p>
          <p className="text-xs text-slate-400">{t("flow.generatingHint")}</p>
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
