"use client";

/* ------------------------------------------------------------------ */
/* In-app notifications — bell inbox (016_notifications.sql)           */
/* ------------------------------------------------------------------ */

import { isStubMode } from "@/lib/supabase/client";
import type { AppNotification } from "@/lib/types";
import { STUB_LATENCY, apiFetch, apiPaths, stubCall } from "./http";
import { type NotificationWire, mapNotification } from "./wire";

/** The caller's notifications, newest first (backend caps at 50). */
export async function getNotifications(): Promise<AppNotification[]> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubGetNotifications();
    });
  }
  const rows = await apiFetch<NotificationWire[]>(apiPaths.notificationsInbox);
  return rows.map(mapNotification);
}

/** Bell badge: how many notifications are unread. */
export async function getUnreadCount(): Promise<number> {
  if (isStubMode()) {
    return stubCall((stub) => stub.stubUnreadCount());
  }
  const res = await apiFetch<{ unread: number }>(
    apiPaths.notificationsUnreadCount,
  );
  return res.unread;
}

/** Mark the given notifications read (null = ALL). Returns how many changed. */
export async function markNotificationsRead(
  ids: string[] | null,
): Promise<number> {
  if (isStubMode()) {
    return stubCall(async (stub) => {
      await stub.delay(STUB_LATENCY / 3);
      return stub.stubMarkNotificationsRead(ids);
    });
  }
  const res = await apiFetch<{ marked: number }>(apiPaths.notificationsRead, {
    method: "POST",
    body: { ids },
  });
  return res.marked;
}
