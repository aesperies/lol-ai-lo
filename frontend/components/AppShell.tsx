"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useI18n } from "@/components/I18nProvider";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import NotificationsBell from "@/components/NotificationsBell";
import ThemeToggle from "@/components/ThemeToggle";
import { Wordmark } from "@/components/Logo";
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
    { href: "/chat", labelKey: "nav.chat" },
    { href: "/funds", labelKey: "nav.funds" },
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
  const [mobileOpen, setMobileOpen] = useState(false);

  // Close the mobile menu on navigation.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

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

  function navLinkClass(active: boolean): string {
    return active
      ? "rounded-lg bg-brand-50 px-3 py-1.5 text-sm font-medium text-brand-800"
      : "rounded-lg px-3 py-1.5 text-sm text-ink-500 transition-colors hover:bg-ink-100 hover:text-ink-800";
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-ink-200 bg-surface/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-4">
          <div className="flex items-center gap-8">
            <Link href="/" aria-label={t("app.name")}>
              <Wordmark />
            </Link>
            <nav
              aria-label="Principal"
              className="hidden items-center gap-1 md:flex"
            >
              {nav.map((item) => {
                const active =
                  pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={navLinkClass(active)}
                  >
                    {t(item.labelKey)}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <NotificationsBell />
            <ThemeToggle />
            <LanguageSwitcher />
            <span className="hidden text-xs text-ink-400 lg:inline">
              {user.name ?? user.email}
            </span>
            <button
              type="button"
              onClick={() => void signOut()}
              className="hidden text-xs text-ink-400 underline-offset-2 hover:text-ink-800 hover:underline md:inline"
            >
              {t("common.logout")}
            </button>
            <button
              type="button"
              aria-label="Menú"
              aria-expanded={mobileOpen}
              onClick={() => setMobileOpen((o) => !o)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-ink-200 text-ink-600 hover:bg-ink-50 md:hidden"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                {mobileOpen ? (
                  <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                ) : (
                  <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {mobileOpen ? (
          <nav
            aria-label="Principal"
            className="border-t border-ink-200 bg-surface px-4 py-3 md:hidden"
          >
            <div className="flex flex-col gap-1">
              {nav.map((item) => {
                const active =
                  pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={navLinkClass(active)}
                  >
                    {t(item.labelKey)}
                  </Link>
                );
              })}
              <button
                type="button"
                onClick={() => void signOut()}
                className="mt-2 rounded-lg px-3 py-1.5 text-left text-sm text-ink-500 hover:bg-ink-100"
              >
                {t("common.logout")}
              </button>
            </div>
          </nav>
        ) : null}
      </header>
      <main className="mx-auto max-w-6xl animate-fade-in-up px-4 py-10">
        {children}
      </main>
    </div>
  );
}
