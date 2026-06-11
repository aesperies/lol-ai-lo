"use client";

/**
 * Admin — gestoras (management companies).
 * Lives under /admin/gestoras so that middleware can protect the whole
 * /admin prefix for the admin role.
 */

import { useEffect, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardTitle,
  Input,
  Label,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import { createGestora, getFunds, getGestoras } from "@/lib/api";
import type { Fund, Gestora, SubscriptionTier } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

const TIERS: SubscriptionTier[] = ["starter", "growth", "custom"];

export default function AdminGestorasPage() {
  const { t } = useI18n();

  const [gestoras, setGestoras] = useState<Gestora[] | null>(null);
  const [funds, setFunds] = useState<Fund[]>([]);
  const [name, setName] = useState("");
  const [tier, setTier] = useState<SubscriptionTier>("starter");
  const [billingEmail, setBillingEmail] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getGestoras().then(setGestoras).catch(() => setGestoras([]));
    void getFunds().then(setFunds).catch(() => setFunds([]));
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const created = await createGestora({
        name: name.trim(),
        subscriptionTier: tier,
        billingEmail: billingEmail.trim(),
      });
      setGestoras((prev) => [...(prev ?? []), created]);
      setName("");
      setBillingEmail("");
      setTier("starter");
      setNotice(t("admin.gestoras.created"));
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

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
                  <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
                    <th className="px-6 py-3 font-medium">{t("admin.gestoras.name")}</th>
                    <th className="px-6 py-3 font-medium">{t("admin.gestoras.tier")}</th>
                    <th className="px-6 py-3 font-medium">{t("admin.gestoras.billingEmail")}</th>
                    <th className="px-6 py-3 font-medium">{t("admin.gestoras.funds")}</th>
                  </tr>
                </thead>
                <tbody>
                  {gestoras.map((g) => (
                    <tr key={g.id} className="border-b border-slate-100 last:border-0">
                      <td className="px-6 py-4 font-medium text-slate-800">{g.name}</td>
                      <td className="px-6 py-4">
                        <Badge tone={g.subscriptionTier === "growth" ? "indigo" : "slate"}>
                          {t(`tier.${g.subscriptionTier}` as DictKey)}
                        </Badge>
                      </td>
                      <td className="px-6 py-4 text-slate-600">{g.billingEmail}</td>
                      <td className="px-6 py-4 text-slate-600">
                        {funds.filter((f) => f.gestoraId === g.id).length}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>

        <Card>
          <CardTitle className="mb-4">{t("admin.gestoras.new")}</CardTitle>
          <form className="space-y-4" onSubmit={handleCreate}>
            <div>
              <Label htmlFor="gestora-name">{t("admin.gestoras.name")}</Label>
              <Input
                id="gestora-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="gestora-tier">{t("admin.gestoras.tier")}</Label>
              <Select
                id="gestora-tier"
                value={tier}
                onChange={(e) => setTier(e.target.value as SubscriptionTier)}
              >
                {TIERS.map((tr) => (
                  <option key={tr} value={tr}>
                    {t(`tier.${tr}` as DictKey)}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="gestora-billing">{t("admin.gestoras.billingEmail")}</Label>
              <Input
                id="gestora-billing"
                type="email"
                value={billingEmail}
                onChange={(e) => setBillingEmail(e.target.value)}
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={busy}>
              {t("admin.gestoras.create")}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
