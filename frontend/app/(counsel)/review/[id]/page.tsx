"use client";

import Link from "next/link";
import CounselReviewPanel from "@/components/CounselReviewPanel";
import { useI18n } from "@/components/I18nProvider";
import { Banner, Spinner } from "@/components/ui";
import { getReviewBundle } from "@/lib/api";
import { useAsync } from "@/lib/hooks";

export default function CounselReviewPage({
  params,
}: {
  params: { id: string };
}) {
  const { t } = useI18n();
  const { data: bundle, error } = useAsync(
    () => getReviewBundle(params.id),
    [params.id],
  );

  return (
    <div>
      <div className="mb-4">
        <Link href="/counsel" className="text-sm text-brand-700 hover:underline">
          ← {t("common.back")}
        </Link>
      </div>

      {error ? (
        <Banner tone="danger">{t("common.error")}</Banner>
      ) : bundle === null ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : (
        <CounselReviewPanel bundle={bundle} />
      )}
    </div>
  );
}
