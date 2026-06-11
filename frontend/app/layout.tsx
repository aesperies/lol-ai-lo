import type { Metadata } from "next";
import type { ReactNode } from "react";
import DevModeBanner from "@/components/DevModeBanner";
import { I18nProvider } from "@/components/I18nProvider";
import { SessionProvider } from "@/components/SessionProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lol-AI-lo",
  description:
    "Plataforma de generación y validación de documentación para fund servicers europeos.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body>
        <I18nProvider>
          <SessionProvider>
            <DevModeBanner />
            {children}
          </SessionProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
