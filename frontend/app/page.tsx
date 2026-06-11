"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { roleHome, useSession } from "@/components/SessionProvider";
import { Spinner } from "@/components/ui";

/** Root: redirect to the role's home, or /login when unauthenticated. */
export default function RootPage() {
  const { user, loading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? roleHome(user.role) : "/login");
  }, [loading, user, router]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Spinner />
    </div>
  );
}
