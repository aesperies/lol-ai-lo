"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import DocumentViewer from "@/components/DocumentViewer";
import { useI18n } from "@/components/I18nProvider";
import { Banner, PageHeader, Spinner } from "@/components/ui";
import { getRequest } from "@/lib/api";
import type { RequestItem } from "@/lib/types";

export default function DocumentDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { t } = useI18n();
  const [request, setRequest] = useState<RequestItem | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    void getRequest(params.id)
      .then((r) => setRequest({ ...r }))
      .catch(() => setError(true));
  }, [params.id]);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4">
        <Link href="/documents" className="text-sm text-brand-700 hover:underline">
          ← {t("common.back")}
        </Link>
      </div>

      {error ? (
        <Banner tone="danger">{t("common.error")}</Banner>
      ) : request === null ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <>
          <PageHeader
            title={request.docTypeLabel ?? request.docType}
            subtitle={request.fundName}
          />
          <DocumentViewer
            request={request}
            onRequestUpdate={(updated) => setRequest({ ...updated })}
          />
        </>
      )}
    </div>
  );
}
