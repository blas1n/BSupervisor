"use client";

import type { ReactNode } from "react";
import { ProtectedRoute } from "@bsvibe/layout";
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
 */
const Spinner = (
  <div className="flex min-h-screen items-center justify-center bg-gray-950">
    <Loader2 className="h-8 w-8 animate-spin text-accent" />
  </div>
);

export default function ProtectedLayout({ children }: { children: ReactNode }) {
  return (
    <ProtectedRoute redirectTo="/login" fallback={Spinner}>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}
