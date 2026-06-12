"use client";

import { useMemo, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { Badge, Banner, Button, Card, CardTitle, Input, Label } from "@/components/ui";
import type { ParsedParams } from "@/lib/types";

/**
 * Step 3 of the master workflow: the client confirms (or edits inline) the
 * parameters extracted by the intake parser.
 *
 * - Fields listed in `unclearFields` are highlighted with the [UNCLEAR] badge.
 * - Editing an unclear field resolves it; the confirm button stays disabled
 *   until `generationReady` (i.e., no unclear fields remain).
 * - Entries originating from structured intake fields (source:
 *   'client_confirmed') are authoritative and carry a "confirmado" chip.
 * - If the parser could not classify the request, the verbatim
 *   unclassifiable message is shown instead.
 */
export default function ParsedParamsReview({
  initialParams,
  onConfirm,
  onBackToIntake,
  confirming,
}: {
  initialParams: ParsedParams;
  onConfirm: (params: ParsedParams, edited: boolean) => void;
  onBackToIntake: () => void;
  confirming: boolean;
}) {
  const { t } = useI18n();
  const [params, setParams] = useState<ParsedParams>(initialParams);
  const [edited, setEdited] = useState(false);

  const generationReady = useMemo(
    () =>
      !params.unclassifiable &&
      params.unclearFields.length === 0 &&
      (params.generationReady || edited),
    [params, edited],
  );

  function isUnclear(field: string): boolean {
    return params.unclearFields.includes(field);
  }

  /** Apply an edit and mark the touched parser field as resolved. */
  function applyEdit(field: string, mutate: (draft: ParsedParams) => void) {
    setParams((prev) => {
      const draft: ParsedParams = JSON.parse(JSON.stringify(prev));
      mutate(draft);
      draft.unclearFields = draft.unclearFields.filter((f) => f !== field);
      draft.generationReady = !draft.unclassifiable && draft.unclearFields.length === 0;
      return draft;
    });
    setEdited(true);
  }

  if (params.unclassifiable) {
    return (
      <Card>
        <Banner tone="danger">{t("params.unclassifiable")}</Banner>
        <div className="mt-4 flex justify-end">
          <Button variant="secondary" onClick={onBackToIntake}>
            {t("params.backToIntake")}
          </Button>
        </div>
      </Card>
    );
  }

  const unclearBadge = (
    <Badge tone="amber" className="ml-2">
      {t("params.unclearBadge")}
    </Badge>
  );

  /** Small chip on structured-origin values (authoritative client input). */
  const confirmedChip = (
    <Badge tone="emerald" className="text-[10px]">
      {t("params.confirmedChip")}
    </Badge>
  );

  return (
    <Card>
      <div className="mb-6">
        <CardTitle>{t("params.title")}</CardTitle>
        <p className="mt-1 text-sm text-slate-500">{t("params.subtitle")}</p>
      </div>

      {/* Parser summary */}
      <div className="mb-6 rounded-md border border-slate-200 bg-slate-50 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
          {t("params.summary")}
        </p>
        <p className="mt-1 text-sm leading-relaxed text-slate-700">
          {params.summary || "—"}
        </p>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
          <span>
            {t("params.docTypeConfirmed")}:{" "}
            <span className="font-medium text-slate-700">
              {params.docTypeConfirmed}
            </span>
          </span>
          <span>
            {t("params.languageDetected")}:{" "}
            <span className="font-medium uppercase text-slate-700">
              {params.language}
            </span>
          </span>
          <span>
            {t("params.confidence")}:{" "}
            <span className="font-medium text-slate-700">
              {(params.confidence * 100).toFixed(0)}%
            </span>
          </span>
        </div>
      </div>

      {params.unclearFields.length > 0 ? (
        <Banner tone="warning" className="mb-6">
          {t("params.unclearHint")}
        </Banner>
      ) : null}

      <div className="space-y-6">
        {/* Parties */}
        <fieldset>
          <legend className="mb-2 flex items-center text-sm font-medium text-slate-700">
            {t("params.parties")}
            {isUnclear("parties") ? unclearBadge : null}
          </legend>
          <div className="space-y-2">
            {params.parties.map((party, i) => (
              <div
                key={i}
                className={
                  isUnclear("parties")
                    ? "grid grid-cols-1 gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 sm:grid-cols-2"
                    : "grid grid-cols-1 gap-2 sm:grid-cols-2"
                }
              >
                <div>
                  <Label className="flex items-center gap-2 text-xs text-slate-500">
                    {t("params.partyRole")}
                    {party.source === "client_confirmed" ? confirmedChip : null}
                  </Label>
                  <Input
                    value={party.role}
                    onChange={(e) =>
                      applyEdit("parties", (d) => {
                        d.parties[i].role = e.target.value;
                      })
                    }
                  />
                </div>
                <div>
                  <Label className="text-xs text-slate-500">
                    {t("params.partyName")}
                  </Label>
                  <Input
                    value={party.name}
                    onChange={(e) =>
                      applyEdit("parties", (d) => {
                        d.parties[i].name = e.target.value;
                      })
                    }
                  />
                </div>
              </div>
            ))}
          </div>
        </fieldset>

        {/* Key dates */}
        <fieldset>
          <legend className="mb-2 flex items-center text-sm font-medium text-slate-700">
            {t("params.keyDates")}
            {isUnclear("key_dates") ? unclearBadge : null}
          </legend>
          <div className="space-y-2">
            {params.keyDates.length === 0 ? (
              <p className="text-sm text-slate-400">—</p>
            ) : (
              params.keyDates.map((kd, i) => (
                <div
                  key={i}
                  className={
                    isUnclear("key_dates")
                      ? "grid grid-cols-1 gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 sm:grid-cols-2"
                      : "grid grid-cols-1 gap-2 sm:grid-cols-2"
                  }
                >
                  {kd.source === "client_confirmed" ? (
                    <div className="sm:col-span-2">{confirmedChip}</div>
                  ) : null}
                  <Input
                    value={kd.label}
                    onChange={(e) =>
                      applyEdit("key_dates", (d) => {
                        d.keyDates[i].label = e.target.value;
                      })
                    }
                  />
                  <Input
                    value={kd.date}
                    onChange={(e) =>
                      applyEdit("key_dates", (d) => {
                        d.keyDates[i].date = e.target.value;
                      })
                    }
                  />
                </div>
              ))
            )}
          </div>
        </fieldset>

        {/* Jurisdiction + governing law */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <Label className="flex items-center">
              {t("params.jurisdiction")}
              {isUnclear("jurisdiction") ? unclearBadge : null}
            </Label>
            <Input
              className={isUnclear("jurisdiction") ? "border-amber-400 bg-amber-50" : ""}
              value={params.jurisdiction}
              onChange={(e) =>
                applyEdit("jurisdiction", (d) => {
                  d.jurisdiction = e.target.value;
                })
              }
            />
          </div>
          <div>
            <Label className="flex items-center">
              {t("params.governingLaw")}
              {isUnclear("governing_law") ? unclearBadge : null}
            </Label>
            <Input
              className={isUnclear("governing_law") ? "border-amber-400 bg-amber-50" : ""}
              value={params.governingLaw}
              onChange={(e) =>
                applyEdit("governing_law", (d) => {
                  d.governingLaw = e.target.value;
                })
              }
            />
          </div>
        </div>

        {/* Key terms */}
        <fieldset>
          <legend className="mb-2 flex items-center text-sm font-medium text-slate-700">
            {t("params.keyTerms")}
            {isUnclear("key_terms") ? unclearBadge : null}
          </legend>
          <div className="space-y-2">
            {params.keyTerms.length === 0 ? (
              <p className="text-sm text-slate-400">—</p>
            ) : (
              params.keyTerms.map((term, i) => (
                <div key={i} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {term.source === "client_confirmed" ? (
                    <div className="sm:col-span-2">{confirmedChip}</div>
                  ) : null}
                  <Input
                    value={term.field}
                    onChange={(e) =>
                      applyEdit("key_terms", (d) => {
                        d.keyTerms[i].field = e.target.value;
                      })
                    }
                  />
                  <Input
                    value={term.value}
                    onChange={(e) =>
                      applyEdit("key_terms", (d) => {
                        d.keyTerms[i].value = e.target.value;
                      })
                    }
                  />
                </div>
              ))
            )}
          </div>
        </fieldset>
      </div>

      {!generationReady ? (
        <Banner tone="warning" className="mt-6">
          {t("params.notReady")}
        </Banner>
      ) : null}

      <div className="mt-6 flex items-center justify-between gap-4">
        <p className="text-xs text-slate-400">
          {edited ? t("params.editedNote") : " "}
        </p>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onBackToIntake}>
            {t("params.backToIntake")}
          </Button>
          {/* Confirm disabled until generation_ready (guardrail 2) */}
          <Button
            disabled={!generationReady || confirming}
            onClick={() => onConfirm(params, edited)}
          >
            {t("params.confirm")}
          </Button>
        </div>
      </div>
    </Card>
  );
}
