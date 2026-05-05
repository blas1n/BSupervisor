"use client";

import type { ReactNode } from "react";
import { isDemoMode } from "@bsvibe/demo";
import { ProtectedRoute } from "@bsvibe/layout";
import { AuthProviderClient } from "@/src/components/AuthProviderClient";
import DemoLayout from "@/src/components/DemoLayout";
import { Layout } from "@/src/components/Layout";
import { Loader2 } from "lucide-react";

/**
 * Phase A — auth gate delegated to `@bsvibe/layout` `ProtectedRoute`.
 *
 * The shared component implements the BSNexus Phase Z pattern
 * (`useEffect + router.replace`) so every product inherits the same
 * "no navigation during render" discipline. BSupervisor still owns the
 * inner `<Layout>` (sidebar / header branding) until that is rolled
 * into a shared `<AppShell>` slot.
 *
 * Build-time switch — when ``NEXT_PUBLIC_BSVIBE_DEMO=1`` the demo
 * layout is rendered instead and the prod auth flow is fully tree-
 * shaken from the bundle.
 */
const Spinner = (
  <div className="flex min-h-screen items-center justify-center bg-gray-950">
    <Loader2 className="h-8 w-8 animate-spin text-accent" />
  </div>
);

const AUTH_URL = process.env.NEXT_PUBLIC_BSVIBE_AUTH_URL ?? "https://auth.bsvibe.dev";

export default function ProtectedLayout({ children }: { children: ReactNode }) {
  if (isDemoMode()) {
    return <DemoLayout>{children}</DemoLayout>;
  }
  return (
    <AuthProviderClient authUrl={AUTH_URL}>
      <ProtectedRoute redirectTo="/login" fallback={Spinner}>
        <Layout>{children}</Layout>
      </ProtectedRoute>
    </AuthProviderClient>
  );
}
