"use client";

/**
 * Admin — gestoras (management companies) + counsel assignment per gestora.
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
  Toggle,
} from "@/components/ui";
import {
  assignCounsel,
  createGestora,
  getCounselAssignments,
  getFunds,
  getGestoras,
  getUsers,
  removeCounselAssignment,
} from "@/lib/api";
import type {
  CounselAssignment,
  Fund,
  Gestora,
  SubscriptionTier,
  UserProfile,
} from "@/lib/types";
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

  // Counsel assignment per gestora (Exit B routing).
  const [counselUsers, setCounselUsers] = useState<UserProfile[]>([]);
  const [assignGestoraId, setAssignGestoraId] = useState("");
  const [assignments, setAssignments] = useState<CounselAssignment[] | null>(null);
  const [assignCounselId, setAssignCounselId] = useState("");
  const [assignPrimary, setAssignPrimary] = useState(false);
  const [counselBusy, setCounselBusy] = useState(false);

  useEffect(() => {
    void getGestoras()
      .then((list) => {
        setGestoras(list);
        if (list.length > 0) setAssignGestoraId((prev) => prev || list[0].id);
      })
      .catch(() => setGestoras([]));
    void getFunds().then(setFunds).catch(() => setFunds([]));
    void getUsers()
      .then((users) => setCounselUsers(users.filter((u) => u.role === "counsel")))
      .catch(() => setCounselUsers([]));
  }, []);

  useEffect(() => {
    if (!assignGestoraId) return;
    setAssignments(null);
    void getCounselAssignments(assignGestoraId)
      .then(setAssignments)
      .catch(() => setAssignments([]));
  }, [assignGestoraId]);

  async function refreshAssignments() {
    const refreshed = await getCounselAssignments(assignGestoraId).catch(() => null);
    if (refreshed) setAssignments(refreshed);
  }

  async function handleAssign(e: React.FormEvent) {
    e.preventDefault();
    if (!assignGestoraId || !assignCounselId) return;
    setCounselBusy(true);
    setNotice(null);
    try {
      await assignCounsel({
        gestoraId: assignGestoraId,
        counselUserId: assignCounselId,
        isPrimary: assignPrimary,
      });
      setAssignCounselId("");
      setAssignPrimary(false);
      setNotice(t("admin.counsel.assigned"));
      await refreshAssignments();
    } catch {
      setNotice(t("common.error"));
    } finally {
      setCounselBusy(false);
    }
  }

  async function handleMakePrimary(assignment: CounselAssignment) {
    setCounselBusy(true);
    setNotice(null);
    try {
      // Re-assigning with isPrimary demotes the previous primary server-side.
      await assignCounsel({
        gestoraId: assignment.gestoraId,
        counselUserId: assignment.counselUserId,
        isPrimary: true,
      });
      setNotice(t("admin.counsel.assigned"));
      await refreshAssignments();
    } catch {
      setNotice(t("common.error"));
    } finally {
      setCounselBusy(false);
    }
  }

  async function handleRemove(assignment: CounselAssignment) {
    setCounselBusy(true);
    setNotice(null);
    try {
      await removeCounselAssignment(assignment.id);
      setNotice(t("admin.counsel.removed"));
      await refreshAssignments();
    } catch {
      setNotice(t("common.error"));
    } finally {
      setCounselBusy(false);
    }
  }

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

      {/* Counsel asignado (Exit B routing per gestora) */}
      <Card className="mt-6">
        <CardTitle className="mb-1">{t("admin.counsel.title")}</CardTitle>
        <p className="mb-4 text-xs text-slate-500">{t("admin.counsel.subtitle")}</p>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <div className="mb-4 max-w-sm">
              <Label htmlFor="assign-gestora">{t("admin.users.gestora")}</Label>
              <Select
                id="assign-gestora"
                value={assignGestoraId}
                onChange={(e) => setAssignGestoraId(e.target.value)}
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
              <p className="text-sm text-slate-500">{t("admin.counsel.empty")}</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {assignments.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-4 py-3">
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-medium text-slate-800">
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
              <span className="text-sm text-slate-700">
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
    </div>
  );
}
