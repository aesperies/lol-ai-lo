"use client";

/** Share a request or tabular review with same-gestora colleagues (read access).
 * Owner-only management; collaborators get view access (enforced server-side). */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { Badge, Button, Modal, Select, Spinner } from "@/components/ui";
import {
  createRequestShare,
  createReviewShare,
  deleteRequestShare,
  deleteReviewShare,
  getColleagues,
  getRequestShares,
  getReviewShares,
} from "@/lib/api";
import type { Colleague, Share } from "@/lib/types";

type Kind = "request" | "review";

export default function ShareDialog({
  open,
  onClose,
  kind,
  resourceId,
}: {
  open: boolean;
  onClose: () => void;
  kind: Kind;
  resourceId: string;
}) {
  const { t } = useI18n();
  const [colleagues, setColleagues] = useState<Colleague[]>([]);
  const [shares, setShares] = useState<Share[] | null>(null);
  const [pick, setPick] = useState("");
  const [busy, setBusy] = useState(false);

  const listShares = kind === "request" ? getRequestShares : getReviewShares;
  const addShare = kind === "request" ? createRequestShare : createReviewShare;
  const removeShare =
    kind === "request" ? deleteRequestShare : deleteReviewShare;

  useEffect(() => {
    if (!open) return;
    setShares(null);
    void getColleagues().then(setColleagues).catch(() => setColleagues([]));
    void listShares(resourceId).then(setShares).catch(() => setShares([]));
  }, [open, resourceId, kind]);

  // Colleagues not already shared with.
  const sharedIds = new Set((shares ?? []).map((s) => s.sharedWithUserId));
  const available = colleagues.filter((c) => !sharedIds.has(c.id));

  async function handleAdd() {
    if (!pick) return;
    setBusy(true);
    try {
      const created = await addShare(resourceId, pick);
      setShares((prev) => [...(prev ?? []), created]);
      setPick("");
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(userId: string) {
    setBusy(true);
    try {
      await removeShare(resourceId, userId);
      setShares((prev) =>
        (prev ?? []).filter((s) => s.sharedWithUserId !== userId),
      );
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={t("share.title")}>
      <p className="mb-4 text-sm text-ink-500">{t("share.note")}</p>

      <div className="mb-5 flex items-end gap-2">
        <div className="flex-1">
          <Select
            value={pick}
            onChange={(e) => setPick(e.target.value)}
            aria-label={t("share.addColleague")}
          >
            <option value="">{t("share.selectColleague")}</option>
            {available.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.email}
              </option>
            ))}
          </Select>
        </div>
        <Button onClick={() => void handleAdd()} disabled={busy || !pick}>
          {t("share.add")}
        </Button>
      </div>

      <div className="text-xs font-medium uppercase tracking-wide text-ink-400">
        {t("share.collaborators")}
      </div>
      {shares === null ? (
        <div className="flex justify-center py-6">
          <Spinner />
        </div>
      ) : shares.length === 0 ? (
        <p className="py-4 text-sm text-ink-400">{t("share.empty")}</p>
      ) : (
        <ul className="mt-2 divide-y divide-ink-100">
          {shares.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between gap-3 py-2.5"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-ink-800">
                  {s.sharedWithName ?? s.sharedWithEmail}
                </div>
                {s.sharedWithEmail ? (
                  <div className="truncate text-xs text-ink-400">
                    {s.sharedWithEmail}
                  </div>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                <Badge tone="slate">{t("share.viewer")}</Badge>
                <Button
                  variant="ghost"
                  onClick={() => void handleRemove(s.sharedWithUserId)}
                  disabled={busy}
                >
                  {t("share.remove")}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
