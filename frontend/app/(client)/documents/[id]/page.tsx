"use client";

import Link from "next/link";
import { useState } from "react";
import DocumentViewer from "@/components/DocumentViewer";
import { useI18n } from "@/components/I18nProvider";
import ShareDialog from "@/components/ShareDialog";
import { Badge, Banner, Button, PageHeader, Spinner } from "@/components/ui";
import { getRequest } from "@/lib/api";
import { useAsync } from "@/lib/hooks";
import type { RequestItem } from "@/lib/types";

export default function DocumentDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const { t } = useI18n();
  const { data, error } = useAsync(
    () => getRequest(params.id).then((r) => ({ ...r })),
    [params.id],
  );
  // Local override so DocumentViewer status updates (Exit A/B, refinements)
  // are reflected without re-fetching.
  const [updated, setUpdated] = useState<RequestItem | null>(null);
  const request = updated && updated.id === params.id ? updated : data;
  const [shareOpen, setShareOpen] = useState(false);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-4">
        <Link href="/documents" className="text-sm text-brand-700 hover:underline">
          ← {t("common.back")}
        </Link>
      </div>

      {error ? (
        <Banner tone="danger">{t("common.error")}</Banner>
      ) : request == null ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <>
          <PageHeader
            title={request.docTypeLabel ?? request.docType}
            subtitle={request.fundName}
            actions={
              request.sharedWithMe ? (
                <Badge tone="violet">
                  {request.sharedByEmail
                    ? t("share.sharedByYou", { who: request.sharedByEmail })
                    : t("share.sharedWithYou")}
                </Badge>
              ) : request.isOwner === false ? null : (
                <Button variant="secondary" onClick={() => setShareOpen(true)}>
                  {t("share.button")}
                </Button>
              )
            }
          />
          <DocumentViewer
            request={request}
            onRequestUpdate={(next) => setUpdated({ ...next })}
          />
          <ShareDialog
            open={shareOpen}
            onClose={() => setShareOpen(false)}
            kind="request"
            resourceId={request.id}
          />
        </>
      )}
    </div>
  );
}
