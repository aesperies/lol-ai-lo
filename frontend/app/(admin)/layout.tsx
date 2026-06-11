"use client";

import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AppShell role="admin">{children}</AppShell>;
}
