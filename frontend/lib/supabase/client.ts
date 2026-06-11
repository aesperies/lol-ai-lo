"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Browser-side Supabase client.
 * Graceful degradation: when NEXT_PUBLIC_SUPABASE_URL is unset the app runs
 * in dev stub mode ("modo desarrollo") — a banner is shown and a simulated
 * session (selectable role) is used so every page renders without Supabase.
 */

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

/** True when Supabase env vars are present. */
export function isSupabaseConfigured(): boolean {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}

/** True when running in dev stub mode (no Supabase). */
export function isStubMode(): boolean {
  return !isSupabaseConfigured();
}

let browserClient: SupabaseClient | null = null;

/** Returns the browser Supabase client, or null in dev stub mode. */
export function getSupabaseBrowserClient(): SupabaseClient | null {
  if (!isSupabaseConfigured()) return null;
  if (!browserClient) {
    // TODO: real Supabase project credentials go in frontend/.env.local
    browserClient = createBrowserClient(SUPABASE_URL!, SUPABASE_ANON_KEY!);
  }
  return browserClient;
}

/** Cookie used by the dev stub session (read by middleware.ts as well). */
export const DEV_ROLE_COOKIE = "lolailo_dev_role";

export function readDevRoleCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${DEV_ROLE_COOKIE}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

export function writeDevRoleCookie(role: string | null): void {
  if (typeof document === "undefined") return;
  if (role === null) {
    document.cookie = `${DEV_ROLE_COOKIE}=; path=/; max-age=0`;
  } else {
    document.cookie = `${DEV_ROLE_COOKIE}=${encodeURIComponent(role)}; path=/; max-age=86400`;
  }
}
