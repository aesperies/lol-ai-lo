"use client";

/** Account — two-factor authentication (TOTP via Supabase Auth). */

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
  Spinner,
} from "@/components/ui";
import { getMyProfile, setMyMfaEnabled } from "@/lib/api";
import { getSupabaseBrowserClient, isStubMode } from "@/lib/supabase/client";
import type { AccountProfile } from "@/lib/types";

export default function AccountSecurityPage() {
  const { t } = useI18n();

  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // Live TOTP enrollment (Supabase mode only).
  const [enrolling, setEnrolling] = useState(false);
  const [factorId, setFactorId] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [code, setCode] = useState("");

  const stub = isStubMode();

  useEffect(() => {
    void getMyProfile().then(setProfile).catch(() => setProfile(null));
  }, []);

  async function reflect(enabled: boolean) {
    const updated = await setMyMfaEnabled(enabled).catch(() => null);
    if (updated) setProfile(updated);
  }

  // --- Dev stub mode: just toggle the mirrored status for the demo. ---
  async function toggleDemo() {
    setBusy(true);
    await reflect(!(profile?.mfaEnabled ?? false));
    setBusy(false);
  }

  // --- Supabase mode: real TOTP enroll → verify → reflect. ---
  async function startEnroll() {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) return;
    setBusy(true);
    setNotice(null);
    try {
      const { data, error } = await supabase.auth.mfa.enroll({
        factorType: "totp",
      });
      if (error) throw error;
      setFactorId(data.id);
      setQr(data.totp?.qr_code ?? null);
      setSecret(data.totp?.secret ?? null);
      setEnrolling(true);
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function verifyEnroll() {
    const supabase = getSupabaseBrowserClient();
    if (!supabase || !factorId) return;
    setBusy(true);
    setNotice(null);
    try {
      const challenge = await supabase.auth.mfa.challenge({ factorId });
      if (challenge.error) throw challenge.error;
      const verify = await supabase.auth.mfa.verify({
        factorId,
        challengeId: challenge.data.id,
        code,
      });
      if (verify.error) throw verify.error;
      await reflect(true);
      setEnrolling(false);
      setCode("");
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  async function disableMfa() {
    const supabase = getSupabaseBrowserClient();
    setBusy(true);
    setNotice(null);
    try {
      if (supabase) {
        const { data } = await supabase.auth.mfa.listFactors();
        for (const f of data?.totp ?? []) {
          await supabase.auth.mfa.unenroll({ factorId: f.id });
        }
      }
      await reflect(false);
    } catch {
      setNotice(t("common.error"));
    } finally {
      setBusy(false);
    }
  }

  if (profile === null) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    );
  }

  const enabled = profile.mfaEnabled;

  return (
    <div>
      <PageHeader
        title={t("account.security.title")}
        subtitle={t("account.security.subtitle")}
      />

      {notice ? (
        <Banner tone="danger" className="mb-6">
          {notice}
        </Banner>
      ) : null}

      <Card className="max-w-xl">
        <div className="mb-4 flex items-center justify-between">
          <CardTitle>{t("account.security.mfaStatus")}</CardTitle>
          <Badge tone={enabled ? "emerald" : "slate"}>
            {enabled ? t("account.security.mfaOn") : t("account.security.mfaOff")}
          </Badge>
        </div>

        {stub ? (
          <div className="space-y-4">
            <Banner tone="info">{t("account.security.devNotice")}</Banner>
            <Button onClick={() => void toggleDemo()} disabled={busy}>
              {enabled
                ? t("account.security.disable")
                : t("account.security.enable")}
            </Button>
          </div>
        ) : enabled ? (
          <Button variant="danger" onClick={() => void disableMfa()} disabled={busy}>
            {t("account.security.disable")}
          </Button>
        ) : enrolling ? (
          <div className="space-y-4">
            <p className="text-sm text-ink-600">
              {t("account.security.enroll")}
            </p>
            {qr ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={qr} alt="TOTP QR" className="h-44 w-44" />
            ) : null}
            {secret ? (
              <p className="font-mono text-xs text-ink-500">{secret}</p>
            ) : null}
            <div>
              <Label htmlFor="totp-code">{t("account.security.code")}</Label>
              <Input
                id="totp-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                inputMode="numeric"
                maxLength={6}
                className="w-40"
              />
            </div>
            <Button onClick={() => void verifyEnroll()} disabled={busy || code.length < 6}>
              {t("account.security.verify")}
            </Button>
          </div>
        ) : (
          <Button onClick={() => void startEnroll()} disabled={busy}>
            {t("account.security.enable")}
          </Button>
        )}
      </Card>
    </div>
  );
}
