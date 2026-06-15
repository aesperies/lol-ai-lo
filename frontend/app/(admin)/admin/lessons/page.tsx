"use client";

/**
 * Admin — accumulated drafting lessons per gestora (read-only). What each
 * gestora's specialized drafter has learned from validated documents. Lessons
 * are STRICTLY siloed per gestora (noted in the UI copy).
 */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Badge,
  Banner,
  Card,
  Label,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import { getGestoras, getGestoraLessons } from "@/lib/api";
import { docTypeLabel } from "@/lib/catalog";
import { BRANCHES } from "@/lib/types";
import type { DraftingLesson, Gestora } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

export default function AdminLessonsPage() {
  const { t } = useI18n();

  const [gestoras, setGestoras] = useState<Gestora[]>([]);
  const [gestoraId, setGestoraId] = useState("");
  const [branch, setBranch] = useState("");
  const [lessons, setLessons] = useState<DraftingLesson[] | null>(null);

  useEffect(() => {
    void getGestoras()
      .then((list) => {
        setGestoras(list);
        if (list.length > 0) setGestoraId((prev) => prev || list[0].id);
      })
      .catch(() => setGestoras([]));
  }, []);

  useEffect(() => {
    if (!gestoraId) return;
    let cancelled = false;
    setLessons(null);
    getGestoraLessons(gestoraId, branch || undefined)
      .then((rows) => {
        if (!cancelled) setLessons(rows);
      })
      .catch(() => {
        if (!cancelled) setLessons([]);
      });
    return () => {
      cancelled = true;
    };
  }, [gestoraId, branch]);

  return (
    <div>
      <PageHeader
        title={t("admin.lessons.title")}
        subtitle={t("admin.lessons.subtitle")}
      />

      <Banner tone="info" className="mb-6">
        {t("admin.lessons.siloNote")}
      </Banner>

      <div className="mb-6 flex flex-wrap gap-4">
        <div className="min-w-[16rem]">
          <Label htmlFor="le-gestora">{t("admin.lessons.selectGestora")}</Label>
          <Select
            id="le-gestora"
            value={gestoraId}
            onChange={(e) => setGestoraId(e.target.value)}
          >
            {gestoras.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="min-w-[16rem]">
          <Label htmlFor="le-branch">{t("admin.lessons.filterBranch")}</Label>
          <Select
            id="le-branch"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
          >
            <option value="">{t("admin.lessons.allBranches")}</option>
            {BRANCHES.map((b) => (
              <option key={b} value={b}>
                {t(`branch.${b}` as DictKey)}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {lessons === null ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : lessons.length === 0 ? (
        <Card className="text-center text-sm text-slate-500">
          {t("admin.lessons.empty")}
        </Card>
      ) : (
        <div className="space-y-3">
          {lessons.map((l) => (
            <Card key={l.id}>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="indigo">
                  {t(`branch.${l.branch}` as DictKey)}
                </Badge>
                {l.docType ? (
                  <span className="text-xs text-slate-400">
                    {docTypeLabel(l.docType)}
                  </span>
                ) : null}
                <span className="text-xs text-slate-400">
                  · {t("admin.lessons.weight")}: {l.weight.toFixed(1)}
                </span>
              </div>
              <p className="mt-2 text-sm text-slate-700">{l.lesson}</p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
