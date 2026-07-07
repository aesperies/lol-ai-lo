"use client";

import Link from "next/link";
import { useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { roleHome, useSession } from "@/components/SessionProvider";
import { Banner, Button, Card, Input, Label } from "@/components/ui";
import { LogoMark } from "@/components/Logo";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import type { Role } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

const STUB_ROLES: Role[] = ["client", "counsel", "admin"];

export default function LoginPage() {
  const { t } = useI18n();
  const { isStub, setStubRole } = useSession();

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
      // Full navigation (not router.push): guarantees the just-written auth
      // cookies travel with the request the middleware inspects — a soft RSC
      // navigation can race the cookie write and bounce back to /login.
      window.location.assign(roleHome(role));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel (desktop) — constant dark slab in both themes (Legora-like) */}
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-[#14241c] p-12 text-white lg:flex">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-[#2f5d49]/40 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-24 -left-16 h-72 w-72 rounded-full bg-[#a87f3f]/15 blur-3xl"
        />
        <span className="relative font-display text-xl font-semibold tracking-tight text-white">
          Lol<span className="text-[#cda86a]">·AI·</span>lo
        </span>
        <div className="relative max-w-md">
          <h2 className="font-display text-4xl font-semibold leading-tight">
            {t("app.tagline")}
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-white/65">
            {t("auth.loginSubtitle")}
          </p>
        </div>
        <p className="relative text-xs text-white/40">
          Lol-AI-lo Legal SLP · {t("app.name")}
        </p>
      </aside>

      {/* Form column */}
      <div className="flex min-h-screen flex-col items-center justify-center px-4 py-12">
        <div className="w-full max-w-md animate-fade-in-up">
          <div className="mb-8 flex justify-center lg:hidden">
            <LogoMark className="h-12 w-12" />
          </div>

          <Card className="shadow-elevated">
          <h1 className="font-display text-xl font-semibold text-ink-900">
            {t("auth.loginTitle")}
          </h1>
          <p className="mt-1 text-sm text-ink-400">{t("auth.loginSubtitle")}</p>

          {isStub ? (
            <div className="mt-6 space-y-3">
              <Banner tone="warning">{t("dev.banner")}</Banner>
              <p className="text-sm font-medium text-ink-700">
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
              <p className="text-center text-sm text-ink-400">
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
    </div>
  );
}
