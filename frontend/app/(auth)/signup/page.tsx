"use client";

import Link from "next/link";
import { useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { useSession } from "@/components/SessionProvider";
import { Banner, Button, Card, Input, Label } from "@/components/ui";
import { Wordmark, LogoMark } from "@/components/Logo";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

export default function SignupPage() {
  const { t } = useI18n();
  const { isStub } = useSession();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const supabase = getSupabaseBrowserClient();
      if (!supabase) return;
      // TODO: role + gestora assignment happens server-side (admin flow);
      // new sign-ups default to 'client' pending admin configuration.
      const { error: authError } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { name } },
      });
      if (authError) {
        setError(authError.message);
        return;
      }
      setSuccess(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel (desktop) */}
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-ink-900 p-12 text-white lg:flex">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-brand-700/30 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-24 -left-16 h-72 w-72 rounded-full bg-accent-500/15 blur-3xl"
        />
        <Wordmark className="[&_span]:text-white" markClassName="h-8 w-8" />
        <div className="relative max-w-md">
          <h2 className="font-display text-4xl font-semibold leading-tight">
            {t("app.tagline")}
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-white/70">
            {t("auth.signupSubtitle")}
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
              {t("auth.signupTitle")}
            </h1>
            <p className="mt-1 text-sm text-ink-400">
              {t("auth.signupSubtitle")}
            </p>

            {isStub ? (
              <div className="mt-6 space-y-4">
                <Banner tone="warning">{t("auth.signupDisabledStub")}</Banner>
                <p className="text-center text-sm text-ink-400">
                  <Link
                    href="/login"
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {t("auth.goLogin")}
                  </Link>
                </p>
              </div>
            ) : success ? (
              <div className="mt-6 space-y-4">
                <Banner tone="success">{t("auth.signupSuccess")}</Banner>
                <p className="text-center text-sm text-ink-400">
                  <Link
                    href="/login"
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {t("auth.goLogin")}
                  </Link>
                </p>
              </div>
            ) : (
              <form className="mt-6 space-y-4" onSubmit={handleSignup}>
                {error ? <Banner tone="danger">{error}</Banner> : null}
                <div>
                  <Label htmlFor="signup-name">{t("common.name")}</Label>
                  <Input
                    id="signup-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="signup-email">{t("common.email")}</Label>
                  <Input
                    id="signup-email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="signup-password">{t("common.password")}</Label>
                  <Input
                    id="signup-password"
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                <Button type="submit" className="w-full" disabled={submitting}>
                  {t("auth.signUp")}
                </Button>
                <p className="text-center text-sm text-ink-400">
                  {t("auth.hasAccount")}{" "}
                  <Link
                    href="/login"
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {t("auth.goLogin")}
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
