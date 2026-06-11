"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import CounselReviewPanel from "@/components/CounselReviewPanel";
import { useI18n } from "@/components/I18nProvider";
import { Banner, Spinner } from "@/components/ui";
import { getReviewBundle } from "@/lib/api";
import type { ReviewBundle } from "@/lib/types";

export default function CounselReviewPage({
  params,
}: {
  params: { id: string };
}) {
  const { t } = useI18n();
  const [bundle, setBundle] = useState<ReviewBundle | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    void getReviewBundle(params.id)
      .then(setBundle)
      .catch(() => setError(true));
  }, [params.id]);

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
