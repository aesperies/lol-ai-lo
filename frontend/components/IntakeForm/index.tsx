"use client";

import { useEffect, useId, useMemo, useState, type ChangeEvent } from "react";
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
import {
  getAssignedCounsel,
  getDocFields,
  getFunds,
  type CreateRequestInput,
} from "@/lib/api";
import { DOC_TYPE_CATALOG, docTypeGroupLabel } from "@/lib/catalog";
import type { DictKey } from "@/lib/i18n";
import type { AssignedCounsel, FieldSpec, Fund } from "@/lib/types";

export const FREETEXT_MIN = 50;
export const FREETEXT_MAX = 2000;

/**
 * CLIENT intake form (SPEC.md step 1):
 * - Fund dropdown (filtered by gestora server-side)
 * - Grouped document-type select (<optgroup>, exact catalog labels)
 * - Structured intake fields per doc_type ("Datos clave del documento",
 *   improvement #5): typed inputs from the registry, reset on type change;
 *   values are authoritative for the parser
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

  // Structured intake fields of the selected doc_type ([] = freetext-only).
  const [docFields, setDocFields] = useState<FieldSpec[]>([]);
  const [structuredValues, setStructuredValues] = useState<
    Record<string, string>
  >({});

  useEffect(() => {
    void getFunds().then(setFunds).catch(() => setFunds([]));
    void getAssignedCounsel().then(setCounsel).catch(() => setCounsel(null));
  }, []);

  // Changing the doc type loads its field specs and RESETS entered values.
  useEffect(() => {
    setStructuredValues({});
    setDocFields([]);
    if (!docType) return;
    let stale = false;
    void getDocFields(docType)
      .then((fields) => {
        if (!stale) setDocFields(fields);
      })
      .catch(() => {
        if (!stale) setDocFields([]);
      });
    return () => {
      stale = true;
    };
  }, [docType]);

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

  function setFieldValue(key: string, value: string) {
    setStructuredValues((prev) => ({ ...prev, [key]: value }));
  }

  /** Typed input per field spec: date, amount (EUR), percent (%), party,
   * select or plain text. */
  function structuredFieldInput(spec: FieldSpec) {
    const id = `${formId}-sf-${spec.key}`;
    const value = structuredValues[spec.key] ?? "";
    const onChange = (
      e: ChangeEvent<HTMLInputElement | HTMLSelectElement>,
    ) => setFieldValue(spec.key, e.target.value);

    if (spec.type === "select") {
      return (
        <Select id={id} value={value} onChange={onChange}>
          <option value="">{t("intake.selectPlaceholder")}</option>
          {(spec.options ?? []).map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </Select>
      );
    }
    if (spec.type === "date") {
      return <Input id={id} type="date" value={value} onChange={onChange} />;
    }
    if (spec.type === "amount" || spec.type === "percent") {
      const suffix = spec.type === "amount" ? "EUR" : "%";
      return (
        <div className="relative">
          <Input
            id={id}
            type="number"
            min={0}
            max={spec.type === "percent" ? 100 : undefined}
            step="any"
            className="pr-12"
            value={value}
            onChange={onChange}
          />
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs font-medium text-slate-400">
            {suffix}
          </span>
        </div>
      );
    }
    // party / text
    return (
      <Input
        id={id}
        value={value}
        onChange={onChange}
        placeholder={spec.type === "party" ? t("intake.partyPlaceholder") : undefined}
      />
    );
  }

  return (
    <Card>
      <form
        className="space-y-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (!valid || submitting) return;
          // Only non-empty structured values travel with the request.
          const cleaned = Object.entries(structuredValues)
            .map(([k, v]) => [k, v.trim()] as const)
            .filter(([, v]) => v.length > 0);
          onSubmit({
            fundId,
            docType,
            docTypeCustom:
              docType === "other" ? docTypeCustom.trim() : undefined,
            freetext: freetext.trim(),
            requiresCounsel,
            structuredFields:
              cleaned.length > 0 ? Object.fromEntries(cleaned) : undefined,
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

        {/* Structured fields per doc_type — between type select and freetext */}
        {docFields.length > 0 ? (
          <fieldset className="rounded-md border border-slate-200 bg-slate-50 p-4">
            <legend className="px-1 text-sm font-medium text-slate-800">
              {t("intake.structuredHeading")}
            </legend>
            <p className="mb-3 text-xs text-slate-500">
              {t("intake.structuredHint")}
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {docFields.map((spec) => (
                <div key={spec.key}>
                  <Label htmlFor={`${formId}-sf-${spec.key}`}>
                    {t(spec.labelI18nKey as DictKey)}
                    {spec.required ? (
                      <span className="ml-0.5 text-red-500" aria-hidden="true">
                        *
                      </span>
                    ) : (
                      <span className="ml-1 text-xs font-normal text-slate-400">
                        ({t("common.optional")})
                      </span>
                    )}
                  </Label>
                  {structuredFieldInput(spec)}
                  {spec.help ? (
                    <p className="mt-1 text-xs text-slate-400">{spec.help}</p>
                  ) : null}
                </div>
              ))}
            </div>
          </fieldset>
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
            placeholder={
              docFields.length > 0
                ? t("intake.freetextPlaceholderStructured")
                : t("intake.freetextPlaceholder")
            }
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
          {requiresCounsel ? (
            <div className="mt-3 border-t border-slate-200 pt-3 text-sm text-slate-700">
              {counsel ? (
                <>
                  <p>
                    <span className="font-medium">{t("intake.assignedCounsel")}:</span>{" "}
                    {counsel.name} — {counsel.email}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {t("intake.turnaround", { hours: counsel.turnaroundHours })}
                  </p>
                </>
              ) : (
                // No counsel assigned to this gestora (GET /api/my/counsel → null).
                <p className="text-xs text-slate-500">
                  {t("intake.noAssignedCounsel")}
                </p>
              )}
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
