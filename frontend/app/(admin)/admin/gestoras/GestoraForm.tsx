"use client";

/** "Nueva gestora" creation form (right column of the admin gestoras page). */

import { useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { Button, Card, CardTitle, Input, Label, Select } from "@/components/ui";
import { createGestora } from "@/lib/api";
import type { Gestora, SubscriptionTier } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

const TIERS: SubscriptionTier[] = ["starter", "growth", "custom"];

export default function GestoraForm({
  onCreated,
  onNotice,
}: {
  onCreated: (created: Gestora) => void;
  onNotice: (msg: string | null) => void;
}) {
  const { t } = useI18n();

  const [name, setName] = useState("");
  const [tier, setTier] = useState<SubscriptionTier>("starter");
  const [billingEmail, setBillingEmail] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onNotice(null);
    try {
      const created = await createGestora({
        name: name.trim(),
        subscriptionTier: tier,
        billingEmail: billingEmail.trim(),
      });
      onCreated(created);
      setName("");
      setBillingEmail("");
      setTier("starter");
      onNotice(t("admin.gestoras.created"));
    } catch {
      onNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
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
  );
}
