import type { Metadata } from "next";
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { getMessages, setRequestLocale } from "next-intl/server";
import { BSVibeIntlProvider, isSupportedLocale } from "@bsvibe/i18n";
import { AuthProviderClient } from "@/src/components/AuthProviderClient";
import "./globals.css";

export const metadata: Metadata = {
  title: "BSupervisor",
};

const AUTH_URL = process.env.NEXT_PUBLIC_BSVIBE_AUTH_URL ?? "https://auth.bsvibe.dev";

export function generateStaticParams() {
  return [{ locale: "ko" }, { locale: "en" }];
}

/**
 * Root layout for BSupervisor — Phase C wraps the existing chrome with
 * `BSVibeIntlProvider` so any client component can call `useT()`. The
 * `[locale]` segment is provided by next-intl middleware
 * (`localePrefix: 'as-needed'`, default `en`); ko routes live under
 * `/ko/...`. The shared package default is `ko`, but BSupervisor pins `en`
 * to preserve the existing English UI/e2e regressions.
 */
export default async function RootLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!isSupportedLocale(locale)) {
    notFound();
  }
  // Tell next-intl which locale this server render is for so any RSC
  // `getTranslations()` calls in nested layouts/pages resolve correctly.
  setRequestLocale(locale);
  const messages = await getMessages();

  return (
    <html lang={locale}>
      <head>
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-gray-950 text-gray-100 antialiased">
        <BSVibeIntlProvider locale={locale} messages={messages}>
          <AuthProviderClient authUrl={AUTH_URL}>{children}</AuthProviderClient>
        </BSVibeIntlProvider>
      </body>
    </html>
  );
}
