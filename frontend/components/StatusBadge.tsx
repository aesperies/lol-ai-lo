"use client";

import { useI18n } from "@/components/I18nProvider";
import { Badge, type BadgeTone } from "@/components/ui";
import type { RequestStatus } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

/** The 7 request statuses with distinct colors (SPEC.md). */
const STATUS_TONES: Record<RequestStatus, BadgeTone> = {
  parsing: "slate",
  confirmed: "sky",
  generating: "indigo",
  review_pending: "amber",
  counsel_review: "violet",
  validated: "emerald",
  delivered: "green",
};

export default function StatusBadge({ status }: { status: RequestStatus }) {
  const { t } = useI18n();
  return (
    <Badge tone={STATUS_TONES[status]}>
      {t(`status.${status}` as DictKey)}
    </Badge>
  );
}
