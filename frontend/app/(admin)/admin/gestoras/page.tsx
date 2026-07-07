"use client";

/**
 * Admin — gestoras (management companies) + counsel assignment per gestora.
 * Lives under /admin/gestoras so that middleware can protect the whole
 * /admin prefix for the admin role.
 *
 * The page is a composition of three sub-domains, each with its own state:
 * - GestoraForm: create a new gestora
 * - CounselAssignmentPanel: counsel assignment per gestora (Exit B routing)
 * - RetentionPolicyPanel: GDPR data retention for the selected gestora
 */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { Badge, Banner, Card, PageHeader, Spinner } from "@/components/ui";
import { getFunds, getGestoras } from "@/lib/api";
import type { Fund, Gestora } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";
import CounselAssignmentPanel from "./CounselAssignmentPanel";
import GestoraForm from "./GestoraForm";
import RetentionPolicyPanel from "./RetentionPolicyPanel";

export default function AdminGestorasPage() {
  const { t } = useI18n();

  const [gestoras, setGestoras] = useState<Gestora[] | null>(null);
  const [funds, setFunds] = useState<Fund[]>([]);
  const [notice, setNotice] = useState<string | null>(null);

  // Gestora selected for the counsel + retention sections below.
  const [selectedGestoraId, setSelectedGestoraId] = useState("");

  useEffect(() => {
    void getGestoras()
      .then((list) => {
        setGestoras(list);
        if (list.length > 0) setSelectedGestoraId((prev) => prev || list[0].id);
      })
      .catch(() => setGestoras([]));
    void getFunds().then(setFunds).catch(() => setFunds([]));
  }, []);

  return (
    <div>
      <PageHeader
        title={t("admin.gestoras.title")}
        subtitle={t("admin.gestoras.subtitle")}
      />

      {notice ? <Banner tone="info" className="mb-6">{notice}</Banner> : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {gestoras === null ? (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          ) : (
            <Card className="overflow-x-auto p-0">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-ink-200 text-xs uppercase tracking-wide text-ink-400">
                    <th scope="col" className="px-6 py-3 font-medium">{t("admin.gestoras.name")}</th>
                    <th scope="col" className="px-6 py-3 font-medium">{t("admin.gestoras.tier")}</th>
                    <th scope="col" className="px-6 py-3 font-medium">{t("admin.gestoras.billingEmail")}</th>
                    <th scope="col" className="px-6 py-3 font-medium">{t("admin.gestoras.funds")}</th>
                  </tr>
                </thead>
                <tbody>
                  {gestoras.map((g) => (
                    <tr key={g.id} className="border-b border-ink-100 last:border-0">
                      <td className="px-6 py-4 font-medium text-ink-800">{g.name}</td>
                      <td className="px-6 py-4">
                        <Badge tone={g.subscriptionTier === "growth" ? "indigo" : "slate"}>
                          {t(`tier.${g.subscriptionTier}` as DictKey)}
                        </Badge>
                      </td>
                      <td className="px-6 py-4 text-ink-600">{g.billingEmail}</td>
                      <td className="px-6 py-4 text-ink-600">
                        {funds.filter((f) => f.gestoraId === g.id).length}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>

        <GestoraForm
          onCreated={(created) => setGestoras((prev) => [...(prev ?? []), created])}
          onNotice={setNotice}
        />
      </div>

      {/* Counsel asignado (Exit B routing per gestora) */}
      <CounselAssignmentPanel
        gestoras={gestoras}
        gestoraId={selectedGestoraId}
        onGestoraChange={setSelectedGestoraId}
        onNotice={setNotice}
      />

      {/* GDPR data retention for the gestora selected in the section above */}
      <RetentionPolicyPanel gestoraId={selectedGestoraId} onNotice={setNotice} />
    </div>
  );
}
