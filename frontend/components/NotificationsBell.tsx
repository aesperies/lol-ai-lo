"use client";

/**
 * In-app notifications bell (header, all roles): unread badge polled every
 * 60s + dropdown inbox. Clicking a notification linked to a request marks it
 * read and navigates to the role-appropriate page (/documents/{id} for
 * clients, /review/{id} for counsel/admin).
 */

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { useSession } from "@/components/SessionProvider";
import { Spinner } from "@/components/ui";
import {
  getNotifications,
  getUnreadCount,
  markNotificationsRead,
} from "@/lib/api";
import type { AppNotification } from "@/lib/types";

/** Badge refresh cadence (bell unread counter). */
const UNREAD_POLL_INTERVAL_MS = 60_000;

export default function NotificationsBell() {
  const { t } = useI18n();
  const { user } = useSession();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Unread badge: fetch on mount + poll every 60s; interval and in-flight
  // resolutions are dropped on unmount (no setState after cleanup).
  useEffect(() => {
    let cancelled = false;
    const refresh = () => {
      getUnreadCount().then(
        (n) => {
          if (!cancelled) setUnread(n);
        },
        () => {
          /* graceful degradation: keep the last known badge */
        },
      );
    };
    refresh();
    const id = setInterval(refresh, UNREAD_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Close the panel on any click outside of the bell/panel.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  // Load the inbox when the panel opens (also refreshes the badge).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setItems(null);
    getNotifications().then(
      (rows) => {
        if (cancelled) return;
        setItems(rows);
        setUnread(rows.filter((n) => !n.readAt).length);
      },
      () => {
        if (!cancelled) setItems([]);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [open]);

  function relativeTime(iso: string | null): string {
    if (!iso) return "";
    const mins = Math.max(
      0,
      Math.round((Date.now() - new Date(iso).getTime()) / 60_000),
    );
    if (mins < 1) return t("notifications.justNow");
    if (mins < 60) return t("notifications.minutesAgo", { m: mins });
    const hours = Math.round(mins / 60);
    if (hours < 24) return t("notifications.hoursAgo", { h: hours });
    return t("notifications.daysAgo", { d: Math.round(hours / 24) });
  }

  async function markAllRead() {
    await markNotificationsRead(null);
    const readAt = new Date().toISOString();
    setItems((prev) =>
      prev ? prev.map((n) => ({ ...n, readAt: n.readAt ?? readAt })) : prev,
    );
    setUnread(0);
  }

  function openNotification(n: AppNotification) {
    if (!n.readAt) {
      // Fire-and-forget: the local state is updated optimistically.
      void markNotificationsRead([n.id]).catch(() => undefined);
      setItems((prev) =>
        prev
          ? prev.map((it) =>
              it.id === n.id
                ? { ...it, readAt: new Date().toISOString() }
                : it,
            )
          : prev,
      );
      setUnread((u) => Math.max(0, u - 1));
    }
    if (n.requestId) {
      setOpen(false);
      router.push(
        user?.role === "client"
          ? `/documents/${n.requestId}`
          : `/review/${n.requestId}`,
      );
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-label={t("notifications.title")}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((o) => !o)}
        className="relative inline-flex h-9 w-9 items-center justify-center rounded-lg text-ink-500 transition-colors hover:bg-ink-100 hover:text-ink-800"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M18 9a6 6 0 10-12 0c0 4.5-1.5 6-2.5 7h17c-1-1-2.5-2.5-2.5-7z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M10 19.5a2.2 2.2 0 004 0"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
        {unread > 0 ? (
          <span
            aria-hidden="true"
            className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold leading-none text-white"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </button>

      {open ? (
        <div
          role="menu"
          aria-label={t("notifications.title")}
          className="absolute right-0 top-full z-40 mt-2 w-80 overflow-hidden rounded-xl border border-ink-200 bg-surface shadow-elevated"
        >
          <div className="flex items-center justify-between gap-4 border-b border-ink-200 px-4 py-2.5">
            <span className="text-sm font-semibold text-ink-900">
              {t("notifications.title")}
            </span>
            {items?.some((n) => !n.readAt) ? (
              <button
                type="button"
                onClick={() => void markAllRead()}
                className="text-xs text-brand-700 underline-offset-2 hover:underline"
              >
                {t("notifications.markAllRead")}
              </button>
            ) : null}
          </div>

          {items === null ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : items.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-ink-500">
              {t("notifications.empty")}
            </p>
          ) : (
            <ul className="max-h-96 overflow-y-auto">
              {items.map((n) => (
                <li key={n.id} className="border-b border-ink-100 last:border-b-0">
                  <button
                    type="button"
                    onClick={() => openNotification(n)}
                    className={`block w-full px-4 py-3 text-left transition-colors hover:bg-ink-100 ${
                      n.readAt ? "" : "bg-brand-50/60"
                    }`}
                  >
                    <span className="flex items-start justify-between gap-3">
                      <span
                        className={`text-sm ${
                          n.readAt
                            ? "text-ink-600"
                            : "font-semibold text-ink-900"
                        }`}
                      >
                        {n.title}
                      </span>
                      {!n.readAt ? (
                        <span
                          aria-hidden="true"
                          className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-brand-600"
                        />
                      ) : null}
                    </span>
                    {n.body ? (
                      <span className="mt-0.5 line-clamp-2 block text-xs text-ink-500">
                        {n.body}
                      </span>
                    ) : null}
                    <span className="mt-1 block text-[11px] text-ink-400">
                      {relativeTime(n.createdAt)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
