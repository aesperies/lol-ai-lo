"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useI18n } from "@/components/I18nProvider";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { useSession } from "@/components/SessionProvider";
import { Spinner } from "@/components/ui";
import type { Role } from "@/lib/types";
import type { DictKey } from "@/lib/i18n";

interface NavItem {
  href: string;
  labelKey: DictKey;
}

const NAV_BY_ROLE: Record<Role, NavItem[]> = {
  client: [
    { href: "/dashboard", labelKey: "nav.dashboard" },
    { href: "/new-request", labelKey: "nav.newRequest" },
    { href: "/documents", labelKey: "nav.documents" },
    { href: "/tabular-reviews", labelKey: "nav.tabular" },
    { href: "/account/security", labelKey: "nav.account" },
  ],
  counsel: [{ href: "/counsel", labelKey: "nav.counselQueue" }],
  admin: [
    { href: "/admin/gestoras", labelKey: "nav.gestoras" },
    { href: "/admin/precedents", labelKey: "nav.precedents" },
    { href: "/admin/playbooks", labelKey: "nav.playbooks" },
    { href: "/admin/lessons", labelKey: "nav.lessons" },
    { href: "/admin/users", labelKey: "nav.users" },
    { href: "/admin/quality", labelKey: "nav.quality" },
    { href: "/admin/billing", labelKey: "nav.billing" },
    { href: "/admin/model-config", labelKey: "nav.modelConfig" },
  ],
};

/**
 * App chrome (header + nav) for authenticated areas. Performs a client-side
 * role guard as a complement to middleware.ts (useful in dev stub mode and
 * for instant feedback on role switches).
 */
export default function AppShell({
  role,
  children,
}: {
  role: Role;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const { user, loading, signOut } = useSession();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace("/login");
    } else if (user.role !== role) {
      router.replace(
        user.role === "client"
          ? "/dashboard"
          : user.role === "counsel"
            ? "/counsel"
            : "/admin/gestoras",
      );
    }
  }, [loading, user, role, router]);

  if (loading || !user || user.role !== role) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Spinner />
      </div>
    );
  }

  const nav = NAV_BY_ROLE[role];

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-6 px-4">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-lg font-bold tracking-tight text-brand-800">
                {t("app.name")}
              </span>
              <span className="hidden text-xs text-slate-400 sm:inline">
                {t("app.tagline")}
              </span>
            </Link>
            <nav className="flex items-center gap-1">
              {nav.map((item) => {
                const active =
                  pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={
                      active
                        ? "rounded-md bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-800"
                        : "rounded-md px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
                    }
                  >
                    {t(item.labelKey)}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            <span className="hidden text-xs text-slate-500 md:inline">
              {user.name ?? user.email}
            </span>
            <button
              type="button"
              onClick={() => void signOut()}
              className="text-xs text-slate-500 underline-offset-2 hover:text-slate-800 hover:underline"
            >
              {t("common.logout")}
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-10">{children}</main>
    </div>
  );
}
