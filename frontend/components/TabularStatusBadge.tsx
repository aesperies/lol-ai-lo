"use client";

import { useI18n } from "@/components/I18nProvider";
import { Badge, type BadgeTone } from "@/components/ui";
import type { TabularReviewStatus } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

/** The 4 tabular-review statuses with distinct colors (010_tabular_reviews.sql). */
const STATUS_TONES: Record<TabularReviewStatus, BadgeTone> = {
  draft: "slate",
  running: "indigo",
  complete: "emerald",
  failed: "red",
};

export default function TabularStatusBadge({
  status,
}: {
  status: TabularReviewStatus;
}) {
  const { t } = useI18n();
  return (
    <Badge tone={STATUS_TONES[status]}>
      {t(`tabularStatus.${status}` as DictKey)}
    </Badge>
  );
}
