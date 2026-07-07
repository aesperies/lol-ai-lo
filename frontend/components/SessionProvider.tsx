"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  getSupabaseBrowserClient,
  isStubMode,
  readDevRoleCookie,
  writeDevRoleCookie,
} from "@/lib/supabase/client";
import type { Role, UserProfile } from "@/lib/types";

/** Dev-stub users, loaded on demand so the 2100-line stub dataset stays in
 * its own async chunk and never ships eagerly to production users (lib/api
 * already dynamic-imports it; this was the last static import). */
async function stubUserForRole(role: Role | null): Promise<UserProfile | null> {
  if (!role) return null;
  const { STUB_USERS_BY_ROLE } = await import("@/lib/stub-data");
  return STUB_USERS_BY_ROLE[role] ?? null;
}

interface SessionContextValue {
  user: UserProfile | null;
  loading: boolean;
  isStub: boolean;
  /** Dev stub only: switch the simulated role. */
  setStubRole: (role: Role) => void;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function roleHome(role: Role): string {
  switch (role) {
    case "client":
      return "/dashboard";
    case "counsel":
      return "/counsel";
    case "admin":
      return "/admin/gestoras";
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const stub = isStubMode();
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;

    if (stub) {
      const role = readDevRoleCookie() as Role | null;
      stubUserForRole(role).then((stubUser) => {
        if (cancelled) return;
        setUser(stubUser);
        setLoading(false);
      });
      return () => {
        cancelled = true;
      };
    }

    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      setLoading(false);
      return;
    }

    supabase.auth.getUser().then(({ data }) => {
      if (cancelled) return;
      const u = data.user;
      if (u) {
        // TODO: role/gestora_id should come from a custom JWT claim or the
        // public.users table once backend auth wiring is final.
        const role =
          (u.app_metadata?.role as Role | undefined) ??
          (u.user_metadata?.role as Role | undefined) ??
          "client";
        setUser({
          id: u.id,
          email: u.email ?? "",
          role,
          gestoraId: (u.app_metadata?.gestora_id as string | undefined) ?? null,
          name: (u.user_metadata?.name as string | undefined) ?? undefined,
        });
      } else {
        setUser(null);
      }
      setLoading(false);
    });

    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      if (cancelled) return;
      if (!session) setUser(null);
    });

    return () => {
      cancelled = true;
      sub.subscription.unsubscribe();
    };
  }, [stub]);

  const setStubRole = useCallback(
    (role: Role) => {
      writeDevRoleCookie(role);
      void stubUserForRole(role).then((stubUser) => {
        setUser(stubUser);
        router.push(roleHome(role));
        router.refresh();
      });
    },
    [router],
  );

  const signOut = useCallback(async () => {
    if (stub) {
      writeDevRoleCookie(null);
      setUser(null);
    } else {
      await getSupabaseBrowserClient()?.auth.signOut();
      setUser(null);
    }
    router.push("/login");
  }, [router, stub]);

  const value = useMemo(
    () => ({ user, loading, isStub: stub, setStubRole, signOut }),
    [user, loading, stub, setStubRole, signOut],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
