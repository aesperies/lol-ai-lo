"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Button,
  Card,
  Input,
  Label,
  Select,
  Textarea,
  Toggle,
} from "@/components/ui";
import { getAssignedCounsel, getFunds, type CreateRequestInput } from "@/lib/api";
import { DOC_TYPE_CATALOG, docTypeGroupLabel } from "@/lib/catalog";
import type { AssignedCounsel, Fund } from "@/lib/types";

export const FREETEXT_MIN = 50;
export const FREETEXT_MAX = 2000;

/**
 * CLIENT intake form (SPEC.md step 1):
 * - Fund dropdown (filtered by gestora server-side)
 * - Grouped document-type select (<optgroup>, exact catalog labels)
 * - Free text, min 50 / max 2000 chars with live counter
 * - Optional "validación por abogado" toggle (default OFF) showing the
 *   assigned counsel + estimated turnaround when enabled
 */
export default function IntakeForm({
  onSubmit,
  submitting,
}: {
  onSubmit: (input: CreateRequestInput) => void;
  submitting: boolean;
}) {
  const { t } = useI18n();
  const formId = useId();

  const [funds, setFunds] = useState<Fund[]>([]);
  const [counsel, setCounsel] = useState<AssignedCounsel | null>(null);

  const [fundId, setFundId] = useState("");
  const [docType, setDocType] = useState("");
  const [docTypeCustom, setDocTypeCustom] = useState("");
  const [freetext, setFreetext] = useState("");
  const [requiresCounsel, setRequiresCounsel] = useState(false); // default OFF

  useEffect(() => {
    void getFunds().then(setFunds).catch(() => setFunds([]));
    void getAssignedCounsel().then(setCounsel).catch(() => setCounsel(null));
  }, []);

  const charCount = freetext.length;
  const belowMin = charCount < FREETEXT_MIN;

  const valid = useMemo(
    () =>
      Boolean(fundId) &&
      Boolean(docType) &&
      !belowMin &&
      charCount <= FREETEXT_MAX &&
      (docType !== "other" || docTypeCustom.trim().length > 0),
    [fundId, docType, belowMin, charCount, docTypeCustom],
  );

  return (
    <Card>
      <form
        className="space-y-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (!valid || submitting) return;
          onSubmit({
            fundId,
            docType,
            docTypeCustom:
              docType === "other" ? docTypeCustom.trim() : undefined,
            freetext: freetext.trim(),
            requiresCounsel,
          });
        }}
      >
        {/* Fund */}
        <div>
          <Label htmlFor={`${formId}-fund`}>{t("intake.fund")}</Label>
          <Select
            id={`${formId}-fund`}
            value={fundId}
            onChange={(e) => setFundId(e.target.value)}
            required
          >
            <option value="" disabled>
              {t("intake.fundPlaceholder")}
            </option>
            {funds.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </Select>
        </div>

        {/* Document type — grouped dropdown with exact catalog labels */}
        <div>
          <Label htmlFor={`${formId}-doctype`}>{t("intake.docType")}</Label>
          <Select
            id={`${formId}-doctype`}
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            required
          >
            <option value="" disabled>
              {t("intake.docTypePlaceholder")}
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

        {/* Custom type description (only for "Other") */}
        {docType === "other" ? (
          <div>
            <Label htmlFor={`${formId}-custom`}>{t("intake.docTypeCustom")}</Label>
            <Input
              id={`${formId}-custom`}
              value={docTypeCustom}
              onChange={(e) => setDocTypeCustom(e.target.value)}
              placeholder={t("intake.docTypeCustomPlaceholder")}
              required
            />
          </div>
        ) : null}

        {/* Free text with live counter */}
        <div>
          <Label htmlFor={`${formId}-freetext`}>{t("intake.freetext")}</Label>
          <Textarea
            id={`${formId}-freetext`}
            rows={6}
            value={freetext}
            maxLength={FREETEXT_MAX}
            onChange={(e) => setFreetext(e.target.value)}
            placeholder={t("intake.freetextPlaceholder")}
            required
          />
          <div className="mt-1.5 flex items-center justify-between text-xs">
            <span className={belowMin && charCount > 0 ? "text-amber-600" : "text-slate-400"}>
              {belowMin ? t("intake.minChars", { min: FREETEXT_MIN }) : " "}
            </span>
            <span
              className={
                charCount >= FREETEXT_MAX
                  ? "font-medium text-red-600"
                  : belowMin
                    ? "text-amber-600"
                    : "text-slate-400"
              }
            >
              {t("intake.charCount", { count: charCount, max: FREETEXT_MAX })}
            </span>
          </div>
        </div>

        {/* Counsel validation toggle (default OFF) */}
        <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-slate-800">
                {t("intake.counselToggle")}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                {t("intake.counselHint")}
              </p>
            </div>
            <Toggle
              checked={requiresCounsel}
              onChange={setRequiresCounsel}
              label={t("intake.counselToggle")}
            />
          </div>
          {requiresCounsel && counsel ? (
            <div className="mt-3 border-t border-slate-200 pt-3 text-sm text-slate-700">
              <p>
                <span className="font-medium">{t("intake.assignedCounsel")}:</span>{" "}
                {counsel.name} — {counsel.firm}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                {t("intake.turnaround", { hours: counsel.turnaroundHours })}
              </p>
            </div>
          ) : null}
        </div>

        <div className="flex justify-end">
          <Button type="submit" disabled={!valid || submitting}>
            {t("intake.submit")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
