"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { Badge, Card, CardTitle, Spinner } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";
import { getRequestBranch, getRequestReviews } from "@/lib/api";
import type {
  Branch,
  GenerationReview,
  ReviewIssue,
  ReviewIssueSeverity,
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
    <li className="rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={SEVERITY_TONE[issue.severity]}>
          {t(`review.severity.${issue.severity}` as DictKey)}
        </Badge>
        <Badge tone="slate">
          {t(`review.category.${issue.category}` as DictKey)}
        </Badge>
        {issue.location ? (
          <span className="text-xs text-slate-400">{issue.location}</span>
        ) : null}
      </div>
      <p className="mt-2 text-sm text-slate-700">
        <span className="font-medium text-slate-500">{t("review.problem")}: </span>
        {issue.problem}
      </p>
      {issue.suggestedFix ? (
        <p className="mt-1 text-sm text-slate-600">
          <span className="font-medium text-slate-500">
            {t("review.suggestedFix")}:{" "}
          </span>
          {issue.suggestedFix}
        </p>
      ) : null}
    </li>
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
        <p className="mt-2 text-sm text-rose-600">{t("review.error")}</p>
      </Card>
    );
  }

  if (reviews === null) {
    return (
      <Card>
        <CardTitle>{t("review.title")}</CardTitle>
        <div className="mt-3 flex items-center gap-2 text-sm text-slate-500">
          <Spinner className="h-4 w-4" />
          <span>{t("review.loading")}</span>
        </div>
      </Card>
    );
  }

  // No reviews persisted = critic skipped (LLM unreachable / disabled).
  if (reviews.length === 0) {
    return (
      <Card>
        <CardTitle>{t("review.title")}</CardTitle>
        <p className="mt-2 text-sm text-slate-400">{t("review.none")}</p>
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
                <span className="text-sm font-medium text-slate-700">
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
    </Card>
  );
}
