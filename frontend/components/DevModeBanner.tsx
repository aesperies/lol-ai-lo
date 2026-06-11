"use client";

import { useI18n } from "@/components/I18nProvider";
import { useSession } from "@/components/SessionProvider";
import type { Role } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

const ROLES: Role[] = ["client", "counsel", "admin"];

/**
 * "Modo desarrollo" banner — visible whenever Supabase is not configured.
 * Lets the developer switch the simulated role on the fly.
 */
export default function DevModeBanner() {
  const { t } = useI18n();
  const { isStub, user, setStubRole } = useSession();

  if (!isStub) return null;

  return (
    <div className="border-b border-amber-300 bg-amber-50 px-4 py-2 text-xs text-amber-900">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{t("dev.banner")}</span>
        <span className="flex items-center gap-2">
          <span>{t("dev.bannerRole")}</span>
          {ROLES.map((role) => (
            <button
              key={role}
              type="button"
              onClick={() => setStubRole(role)}
              className={
                user?.role === role
                  ? "rounded-full bg-amber-600 px-2.5 py-0.5 font-semibold text-white"
                  : "rounded-full border border-amber-400 px-2.5 py-0.5 hover:bg-amber-100"
              }
            >
              {t(`role.${role}` as DictKey)}
            </button>
          ))}
        </span>
      </div>
    </div>
  );
}
