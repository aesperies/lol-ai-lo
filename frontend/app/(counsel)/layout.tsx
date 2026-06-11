"use client";

import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";

export default function CounselLayout({ children }: { children: ReactNode }) {
  return <AppShell role="counsel">{children}</AppShell>;
}
