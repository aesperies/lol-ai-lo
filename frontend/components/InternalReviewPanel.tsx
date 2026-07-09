"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { Badge, Card, CardTitle, Spinner } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";
import {
  getRequestBranch,
  getRequestReviews,
  getRequestVerifications,
} from "@/lib/api";
import type {
  Branch,
  GenerationReview,
  ReviewIssue,
  ReviewIssueSeverity,
  Verification,
} from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

const SEVERITY_TONE: Record<ReviewIssueSeverity, BadgeTone> = {
  blocking: "red",
  major: "amber",
  minor: "slate",
};

/** A small "Agente: Cumplimiento" badge for a request's drafting branch. */
export function BranchBadge({ branch }: { branch: Branch }) {
  const { t } = useI18n();
  return (
    <Badge tone="indigo">
      {t("branch.badge", { branch: t(`branch.${branch}` as DictKey) })}
    </Badge>
  );
}

/** Resolves a request's branch and renders the badge (null until loaded). */
export function RequestBranchBadge({ requestId }: { requestId: string }) {
  const [branch, setBranch] = useState<Branch | null>(null);
  useEffect(() => {
    let cancelled = false;
    getRequestBranch(requestId)
      .then((b) => {
        if (!cancelled) setBranch(b);
      })
      .catch(() => {
        /* badge is non-blocking */
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);
  if (!branch) return null;
  return <BranchBadge branch={branch} />;
}

function IssueRow({ issue }: { issue: ReviewIssue }) {
  const { t } = useI18n();
  return (
    <li className="rounded-lg border border-ink-200 bg-ink-50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={SEVERITY_TONE[issue.severity]}>
          {t(`review.severity.${issue.severity}` as DictKey)}
        </Badge>
        <Badge tone="slate">
          {t(`review.category.${issue.category}` as DictKey)}
        </Badge>
        {typeof issue.confidence === "number" ? (
          <Badge tone="slate">
            {t("review.confidence")}: {Math.round(issue.confidence * 100)}%
          </Badge>
        ) : null}
        {issue.location ? (
          <span className="text-xs text-ink-400">{issue.location}</span>
        ) : null}
      </div>
      <p className="mt-2 text-sm text-ink-700">
        <span className="font-medium text-ink-500">{t("review.problem")}: </span>
        {issue.problem}
      </p>
      {issue.suggestedFix ? (
        <p className="mt-1 text-sm text-ink-600">
          <span className="font-medium text-ink-500">
            {t("review.suggestedFix")}:{" "}
          </span>
          {issue.suggestedFix}
        </p>
      ) : null}
      {issue.citation && (issue.citation.quote || issue.citation.where) ? (
        <div className="mt-2 border-l-2 border-ink-300 pl-2.5">
          {issue.citation.quote ? (
            <p className="text-sm italic text-ink-600">
              “{issue.citation.quote}”
            </p>
          ) : null}
          {issue.citation.where ? (
            <p className="mt-0.5 text-xs text-ink-400">
              {t("review.citationWhere")}: {issue.citation.where}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

/**
 * Verificador cruzado (020): badge de estado + hallazgos de la última pasada.
 * Sección no bloqueante dentro del panel de revisión interna — si el endpoint
 * falla o no hay pasadas, no se pinta nada.
 */
function VerificationSection({ requestId }: { requestId: string }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<Verification[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    getRequestVerifications(requestId)
      .then((v) => {
        if (!cancelled) setRows(v);
      })
      .catch(() => {
        /* la verificación es informativa; nunca rompe el panel */
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  if (!rows || rows.length === 0) return null;
  const last = rows[rows.length - 1];
  const warnings = last.findings.filter((f) => f.severity === "warning").length;

  let tone: BadgeTone = "emerald";
  let label = t("verification.clean");
  if (last.criticalCount > 0) {
    tone = "red";
    label = t("verification.critical", { count: last.criticalCount });
  } else if (warnings > 0) {
    tone = "amber";
    label = t("verification.warnings", { count: warnings });
  }

  return (
    <div className="mt-4 border-t border-ink-200 pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-ink-700">
          {t("verification.title")}
        </span>
        <Badge tone={tone}>{label}</Badge>
        {last.provider ? (
          <span className="text-xs text-ink-400">
            {t("verification.provider", { provider: last.provider })}
          </span>
        ) : (
          <span className="text-xs text-ink-400">
            {t("verification.deterministic")}
          </span>
        )}
      </div>
      {last.findings.length > 0 ? (
        <ul className="mt-2 space-y-2">
          {last.findings.map((finding, idx) => (
            <li
              key={idx}
              className="rounded-lg border border-ink-200 bg-ink-50 p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={finding.severity === "critical" ? "red" : "amber"}>
                  {finding.category.replaceAll("_", " ")}
                </Badge>
                <Badge tone="slate">
                  {t(`verification.layer.${finding.layer}` as DictKey)}
                </Badge>
                {finding.where ? (
                  <span className="text-xs text-ink-400">{finding.where}</span>
                ) : null}
              </div>
              <p className="mt-2 text-sm text-ink-700">{finding.problem}</p>
              {finding.quote ? (
                <p className="mt-1 border-l-2 border-ink-300 pl-2.5 text-sm italic text-ink-600">
                  “{finding.quote}”
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * Surfaces the automated critic outcome for a request (Feature 2), shared by
 * the client document view and the counsel review screen.
 *
 * - Status line + colored badge: approved / N issues fixed / referred to
 *   counsel (forced_counsel = last round not approved).
 * - Expandable list of issues per round (severity / category / problem / fix).
 * - Loading / empty / error states via i18n. No reviews (critic skipped) →
 *   neutral "sin revisión automática" line.
 */
export default function InternalReviewPanel({
  requestId,
}: {
  requestId: string;
}) {
  const { t } = useI18n();
  const [reviews, setReviews] = useState<GenerationReview[] | null>(null);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setReviews(null);
    setError(false);
    getRequestReviews(requestId)
      .then((rows) => {
        if (!cancelled) setReviews(rows);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  if (error) {
    return (
      <Card>
        <CardTitle>{t("review.title")}</CardTitle>
        <p className="mt-2 text-sm text-red-600">{t("review.error")}</p>
      </Card>
    );
  }

  if (reviews === null) {
    return (
      <Card>
        <CardTitle>{t("review.title")}</CardTitle>
        <div className="mt-3 flex items-center gap-2 text-sm text-ink-500">
          <Spinner className="h-4 w-4" />
          <span>{t("review.loading")}</span>
        </div>
      </Card>
    );
  }

  // No reviews persisted = critic skipped (LLM unreachable / disabled).
  // La verificación cruzada puede haber corrido igualmente (capa determinista).
  if (reviews.length === 0) {
    return (
      <Card>
        <CardTitle>{t("review.title")}</CardTitle>
        <p className="mt-2 text-sm text-ink-400">{t("review.none")}</p>
        <VerificationSection requestId={requestId} />
      </Card>
    );
  }

  const lastRound = reviews[reviews.length - 1];
  const forcedCounsel = !lastRound.approved;
  // Issues raised before the final round = issues the critic got fixed.
  const fixedCount = reviews
    .slice(0, -1)
    .reduce((sum, r) => sum + r.issues.length, 0);

  let statusKey: DictKey;
  let statusTone: BadgeTone;
  if (forcedCounsel) {
    statusKey = "review.forcedCounsel";
    statusTone = "violet";
  } else if (fixedCount > 0) {
    statusKey = fixedCount === 1 ? "review.fixed" : "review.fixedPlural";
    statusTone = "amber";
  } else {
    statusKey = "review.approved";
    statusTone = "emerald";
  }

  const hasAnyIssue = reviews.some((r) => r.issues.length > 0);

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>{t("review.title")}</CardTitle>
          <div className="mt-2">
            <Badge tone={statusTone}>{t(statusKey, { count: fixedCount })}</Badge>
          </div>
        </div>
        {hasAnyIssue ? (
          <button
            type="button"
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
            className="text-sm text-brand-700 underline-offset-2 hover:underline"
          >
            {open ? t("review.hideDetails") : t("review.showDetails")}
          </button>
        ) : null}
      </div>

      {open && hasAnyIssue ? (
        <div className="mt-4 space-y-4">
          {reviews.map((round) => (
            <div key={round.round}>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-ink-700">
                  {t("review.round", { n: round.round })}
                </span>
                {round.approved ? (
                  <Badge tone="emerald">{t("review.roundApproved")}</Badge>
                ) : (
                  <Badge tone="slate">
                    {t(
                      round.issues.length === 1
                        ? "review.roundIssues"
                        : "review.roundIssuesPlural",
                      { count: round.issues.length },
                    )}
                  </Badge>
                )}
              </div>
              {round.issues.length > 0 ? (
                <ul className="mt-2 space-y-2">
                  {round.issues.map((issue, idx) => (
                    <IssueRow key={idx} issue={issue} />
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      <VerificationSection requestId={requestId} />
    </Card>
  );
}
