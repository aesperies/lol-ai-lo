"use client";

import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";

export default function ClientLayout({ children }: { children: ReactNode }) {
  return <AppShell role="client">{children}</AppShell>;
}
