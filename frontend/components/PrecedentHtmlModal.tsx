"use client";

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { Banner, CardTitle, Spinner } from "@/components/ui";
import { getPrecedentVersionHtml } from "@/lib/api";
import { docTypeLabel } from "@/lib/catalog";
import type { PrecedentVersionHtml } from "@/lib/types";

/**
 * Visor del documento fuente de una cita o de la biblioteca (022): trae el
 * HTML seguro de una versión de precedente (render server-side con whitelist
 * de tags) y lo muestra en un overlay ancho. Si la versión no es renderizable
 * (PDF → 409), enseña el `fallback` (p. ej. el snippet de la cita).
 */
export default function PrecedentHtmlModal({
  versionId,
  title,
  fallback,
  onClose,
}: {
  versionId: string | null;
  title?: string;
  /** Texto a mostrar cuando la versión no puede renderizarse (PDF). */
  fallback?: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [doc, setDoc] = useState<PrecedentVersionHtml | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!versionId) return;
    let cancelled = false;
    setDoc(null);
    setFailed(false);
    getPrecedentVersionHtml(versionId)
      .then((data) => {
        if (!cancelled) setDoc(data);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [versionId]);

  useEffect(() => {
    if (!versionId) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [versionId, onClose]);

  if (!versionId) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title ?? t("chat.viewSource")}
        className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-xl border border-ink-200 bg-surface p-6 shadow-elevated"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-4">
          <CardTitle>
            {title ?? (doc ? docTypeLabel(doc.docType) : t("chat.viewSource"))}
          </CardTitle>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-ink-500 hover:bg-ink-100 hover:text-ink-900"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {failed ? (
          fallback ? (
            <blockquote className="overflow-auto rounded-md border border-ink-200 bg-ink-50 px-4 py-3 text-sm italic text-ink-700">
              «{fallback}»
            </blockquote>
          ) : (
            <Banner tone="danger">{t("common.error")}</Banner>
          )
        ) : !doc ? (
          <div className="flex items-center justify-center gap-3 py-12 text-sm text-ink-500">
            <Spinner className="h-4 w-4" />
            {t("common.loading")}
          </div>
        ) : (
          <article
            className="doc-html flex-1 overflow-auto rounded-md border border-ink-200 bg-white px-8 py-7 shadow-inner"
            dangerouslySetInnerHTML={{ __html: doc.html }}
          />
        )}
      </div>
    </div>
  );
}
