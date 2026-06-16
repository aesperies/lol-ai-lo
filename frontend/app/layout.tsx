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
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&display=swap"
          rel="stylesheet"
        />
      </head>
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
