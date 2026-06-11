"use client";

/** Admin — platform users and roles. */

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
import { getGestoras, getUsers, inviteUser } from "@/lib/api";
import type { Gestora, Role, UserProfile } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

const ROLES: Role[] = ["client", "counsel", "admin"];

export default function AdminUsersPage() {
  const { t } = useI18n();

  const [users, setUsers] = useState<UserProfile[] | null>(null);
  const [gestoras, setGestoras] = useState<Gestora[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("client");
  const [gestoraId, setGestoraId] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getUsers().then(setUsers).catch(() => setUsers([]));
    void getGestoras().then(setGestoras).catch(() => setGestoras([]));
  }, []);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      // gestora_id is NULL for admin/counsel users (schema rule).
      await inviteUser({
        email: email.trim(),
        role,
        gestoraId: role === "client" ? gestoraId || null : null,
      });
      setNotice(t("admin.users.invited"));
      setEmail("");
      const refreshed = await getUsers().catch(() => null);
      if (refreshed) setUsers(refreshed);
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title={t("admin.users.title")} subtitle={t("admin.users.subtitle")} />

      {notice ? <Banner tone="info" className="mb-6">{notice}</Banner> : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {users === null ? (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          ) : (
            <Card className="overflow-x-auto p-0">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
                    <th className="px-6 py-3 font-medium">{t("common.email")}</th>
                    <th className="px-6 py-3 font-medium">{t("common.role")}</th>
                    <th className="px-6 py-3 font-medium">{t("admin.users.gestora")}</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-b border-slate-100 last:border-0">
                      <td className="px-6 py-4 font-medium text-slate-800">
                        {u.email}
                        {u.name ? (
                          <span className="block text-xs font-normal text-slate-400">
                            {u.name}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-6 py-4">
                        <Badge
                          tone={
                            u.role === "admin"
                              ? "red"
                              : u.role === "counsel"
                                ? "violet"
                                : "sky"
                          }
                        >
                          {t(`role.${u.role}` as DictKey)}
                        </Badge>
                      </td>
                      <td className="px-6 py-4 text-slate-600">
                        {u.gestoraId
                          ? (gestoras.find((g) => g.id === u.gestoraId)?.name ?? u.gestoraId)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>

        <Card className="self-start">
          <CardTitle className="mb-4">{t("admin.users.invite")}</CardTitle>
          <form className="space-y-4" onSubmit={handleInvite}>
            <div>
              <Label htmlFor="invite-email">{t("common.email")}</Label>
              <Input
                id="invite-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="invite-role">{t("common.role")}</Label>
              <Select
                id="invite-role"
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {t(`role.${r}` as DictKey)}
                  </option>
                ))}
              </Select>
            </div>
            {role === "client" ? (
              <div>
                <Label htmlFor="invite-gestora">{t("admin.users.gestora")}</Label>
                <Select
                  id="invite-gestora"
                  value={gestoraId}
                  onChange={(e) => setGestoraId(e.target.value)}
                  required
                >
                  <option value="" disabled>
                    —
                  </option>
                  {gestoras.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </Select>
              </div>
            ) : null}
            <Button type="submit" className="w-full" disabled={busy}>
              {t("admin.users.invite")}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
