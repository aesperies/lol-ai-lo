"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { Banner, Spinner } from "@/components/ui";
import { getDocumentHtml } from "@/lib/api";
import type { DocumentHtml, DocumentVersionType } from "@/lib/types";

/**
 * In-browser document viewer: fetches the backend's safe-HTML rendering of a
 * stored .docx version (GET .../documents/{type}/html) and shows it in a
 * page-like article with legal-document typography.
 *
 * The HTML is produced server-side from a fixed tag whitelist with all text
 * content escaped (services/docx_html.py); in stub mode it comes from
 * stubDocumentHtml, which follows the same contract.
 *
 * Redlines get a legend bar ("X inserciones · Y eliminaciones") and the
 * ins.rl-ins / del.rl-del styles defined in globals.css.
 */
export default function DocumentHtmlViewer({
  requestId,
  versionType,
  iteration,
  refreshToken,
}: {
  requestId: string;
  versionType: DocumentVersionType;
  /** Refinement iteration to view; latest when omitted (version history). */
  iteration?: number;
  /** Bump to force a re-fetch (e.g. after a refinement created a new iteration). */
  refreshToken?: number;
}) {
  const { t } = useI18n();
  const [doc, setDoc] = useState<DocumentHtml | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setDoc(null);
    setFailed(false);
    getDocumentHtml(requestId, versionType, iteration)
      .then((data) => {
        if (!cancelled) setDoc(data);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [requestId, versionType, iteration, refreshToken]);

  if (failed) {
    return <Banner tone="danger">{t("htmlViewer.error")}</Banner>;
  }

  if (!doc) {
    return (
      <div className="flex items-center justify-center gap-3 rounded-md border border-ink-200 bg-ink-50 py-12 text-sm text-ink-500">
        <Spinner className="h-4 w-4" />
        {t("htmlViewer.loading")}
      </div>
    );
  }

  return (
    <div>
      {/* Redline legend: insertion / deletion counts */}
      {versionType === "redline" ? (
        <div className="mb-3 flex flex-wrap items-center gap-3 rounded-md border border-ink-200 bg-ink-50 px-3 py-2 text-xs text-ink-600">
          <span className="inline-flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 rounded-sm bg-emerald-200 ring-1 ring-emerald-400"
              aria-hidden="true"
            />
            <span
              className="h-2.5 w-2.5 rounded-sm bg-red-100 ring-1 ring-red-300"
              aria-hidden="true"
            />
          </span>
          <span className="font-medium">
            {t("htmlViewer.legend", {
              ins: doc.stats.insertions,
              del: doc.stats.deletions,
            })}
          </span>
        </div>
      ) : null}

      {/* Page-like white card. The HTML is server-rendered from a fixed tag
          whitelist with all text escaped — safe to inject. */}
      <article
        className="doc-html max-h-[560px] overflow-auto rounded-md border border-ink-200 bg-white px-8 py-7 shadow-inner"
        dangerouslySetInnerHTML={{ __html: doc.html }}
      />
    </div>
  );
}
