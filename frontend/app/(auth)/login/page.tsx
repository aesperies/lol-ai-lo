"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { roleHome, useSession } from "@/components/SessionProvider";
import { Banner, Button, Card, Input, Label } from "@/components/ui";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import type { Role } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

const STUB_ROLES: Role[] = ["client", "counsel", "admin"];

export default function LoginPage() {
  const { t } = useI18n();
  const { isStub, setStubRole } = useSession();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const supabase = getSupabaseBrowserClient();
      if (!supabase) return;
      const { data, error: authError } =
        await supabase.auth.signInWithPassword({ email, password });
      if (authError || !data.user) {
        setError(t("auth.invalidCredentials"));
        return;
      }
      // TODO: role should come from a custom JWT claim / users table.
      const role =
        (data.user.app_metadata?.role as Role | undefined) ??
        (data.user.user_metadata?.role as Role | undefined) ??
        "client";
      router.push(roleHome(role));
      router.refresh();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <p className="text-3xl font-bold tracking-tight text-brand-800">
            {t("app.name")}
          </p>
          <p className="mt-1 text-sm text-slate-500">{t("app.tagline")}</p>
        </div>

        <Card>
          <h1 className="text-lg font-semibold text-slate-900">
            {t("auth.loginTitle")}
          </h1>
          <p className="mt-1 text-sm text-slate-500">{t("auth.loginSubtitle")}</p>

          {isStub ? (
            <div className="mt-6 space-y-3">
              <Banner tone="warning">{t("dev.banner")}</Banner>
              <p className="text-sm font-medium text-slate-700">
                {t("dev.chooseRole")}
              </p>
              <div className="grid gap-2">
                {STUB_ROLES.map((role) => (
                  <Button
                    key={role}
                    variant="secondary"
                    className="justify-start"
                    onClick={() => setStubRole(role)}
                  >
                    {t("dev.enterAs", {
                      role: t(`role.${role}` as DictKey),
                    })}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            <form className="mt-6 space-y-4" onSubmit={handleLogin}>
              {error ? <Banner tone="danger">{error}</Banner> : null}
              <div>
                <Label htmlFor="login-email">{t("common.email")}</Label>
                <Input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor="login-password">{t("common.password")}</Label>
                <Input
                  id="login-password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              <Button type="submit" className="w-full" disabled={submitting}>
                {t("auth.signIn")}
              </Button>
              <p className="text-center text-sm text-slate-500">
                {t("auth.noAccount")}{" "}
                <Link href="/signup" className="font-medium text-brand-700 hover:underline">
                  {t("auth.goSignup")}
                </Link>
              </p>
            </form>
          )}
        </Card>

        <div className="mt-6 flex justify-center">
          <LanguageSwitcher />
        </div>
      </div>
    </div>
  );
}
