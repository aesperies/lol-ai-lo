"use client";

/** Counsel assignment per gestora (Exit B routing): gestora selector,
 * current assignments list (primary/backup) and assignment form. */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  Label,
  Select,
  Spinner,
  Toggle,
} from "@/components/ui";
import {
  assignCounsel,
  getCounselAssignments,
  getUsers,
  removeCounselAssignment,
} from "@/lib/api";
import type { CounselAssignment, Gestora, UserProfile } from "@/lib/types";

export default function CounselAssignmentPanel({
  gestoras,
  gestoraId,
  onGestoraChange,
  onNotice,
}: {
  gestoras: Gestora[] | null;
  gestoraId: string;
  onGestoraChange: (id: string) => void;
  onNotice: (msg: string | null) => void;
}) {
  const { t } = useI18n();

  const [counselUsers, setCounselUsers] = useState<UserProfile[]>([]);
  const [assignments, setAssignments] = useState<CounselAssignment[] | null>(null);
  const [assignCounselId, setAssignCounselId] = useState("");
  const [assignPrimary, setAssignPrimary] = useState(false);
  const [counselBusy, setCounselBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getUsers()
      .then((users) => {
        if (!cancelled) {
          setCounselUsers(users.filter((u) => u.role === "counsel"));
        }
      })
      .catch(() => {
        if (!cancelled) setCounselUsers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!gestoraId) return;
    let cancelled = false;
    setAssignments(null);
    void getCounselAssignments(gestoraId)
      .then((rows) => {
        if (!cancelled) setAssignments(rows);
      })
      .catch(() => {
        if (!cancelled) setAssignments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [gestoraId]);

  async function refreshAssignments() {
    const refreshed = await getCounselAssignments(gestoraId).catch(() => null);
    if (refreshed) setAssignments(refreshed);
  }

  async function handleAssign(e: React.FormEvent) {
    e.preventDefault();
    if (!gestoraId || !assignCounselId) return;
    setCounselBusy(true);
    onNotice(null);
    try {
      await assignCounsel({
        gestoraId,
        counselUserId: assignCounselId,
        isPrimary: assignPrimary,
      });
      setAssignCounselId("");
      setAssignPrimary(false);
      onNotice(t("admin.counsel.assigned"));
      await refreshAssignments();
    } catch {
      onNotice(t("common.error"));
    } finally {
      setCounselBusy(false);
    }
  }

  async function handleMakePrimary(assignment: CounselAssignment) {
    setCounselBusy(true);
    onNotice(null);
    try {
      // Re-assigning with isPrimary demotes the previous primary server-side.
      await assignCounsel({
        gestoraId: assignment.gestoraId,
        counselUserId: assignment.counselUserId,
        isPrimary: true,
      });
      onNotice(t("admin.counsel.assigned"));
      await refreshAssignments();
    } catch {
      onNotice(t("common.error"));
    } finally {
      setCounselBusy(false);
    }
  }

  async function handleRemove(assignment: CounselAssignment) {
    setCounselBusy(true);
    onNotice(null);
    try {
      await removeCounselAssignment(assignment.id);
      onNotice(t("admin.counsel.removed"));
      await refreshAssignments();
    } catch {
      onNotice(t("common.error"));
    } finally {
      setCounselBusy(false);
    }
  }

  return (
    <Card className="mt-6">
      <CardTitle className="mb-1">{t("admin.counsel.title")}</CardTitle>
      <p className="mb-4 text-xs text-ink-500">{t("admin.counsel.subtitle")}</p>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="mb-4 max-w-sm">
            <Label htmlFor="assign-gestora">{t("admin.users.gestora")}</Label>
            <Select
              id="assign-gestora"
              value={gestoraId}
              onChange={(e) => onGestoraChange(e.target.value)}
            >
              {(gestoras ?? []).map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </Select>
          </div>

          {assignments === null ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : assignments.length === 0 ? (
            <p className="text-sm text-ink-500">{t("admin.counsel.empty")}</p>
          ) : (
            <ul className="divide-y divide-ink-100">
              {assignments.map((a) => (
                <li key={a.id} className="flex items-center justify-between gap-4 py-3">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-ink-800">
                      {a.counselEmail ?? a.counselUserId}
                    </span>
                    <Badge tone={a.isPrimary ? "indigo" : "slate"}>
                      {a.isPrimary
                        ? t("admin.counsel.primary")
                        : t("admin.counsel.backup")}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    {!a.isPrimary ? (
                      <Button
                        variant="secondary"
                        onClick={() => void handleMakePrimary(a)}
                        disabled={counselBusy}
                      >
                        {t("admin.counsel.makePrimary")}
                      </Button>
                    ) : null}
                    <Button
                      variant="secondary"
                      onClick={() => void handleRemove(a)}
                      disabled={counselBusy}
                    >
                      {t("admin.counsel.remove")}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <form className="space-y-4 self-start" onSubmit={handleAssign}>
          <div>
            <Label htmlFor="assign-counsel">{t("role.counsel")}</Label>
            <Select
              id="assign-counsel"
              value={assignCounselId}
              onChange={(e) => setAssignCounselId(e.target.value)}
              required
            >
              <option value="" disabled>
                {t("admin.counsel.selectCounsel")}
              </option>
              {counselUsers.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name ?? u.email}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-sm text-ink-700">
              {t("admin.counsel.primary")}
            </span>
            <Toggle
              checked={assignPrimary}
              onChange={setAssignPrimary}
              label={t("admin.counsel.primary")}
            />
          </div>
          <Button
            type="submit"
            className="w-full"
            disabled={counselBusy || !assignCounselId}
          >
            {t("admin.counsel.assign")}
          </Button>
        </form>
      </div>
    </Card>
  );
}
