"use client";

import { DemoBanner, useAutoDemoSession } from "@bsvibe/demo";
import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Layout } from "@/src/components/Layout";

const DEMO_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "https://api-demo-supervisor.bsvibe.dev";

/**
 * Demo mode equivalent of ``ProtectedLayout``. Auto-bootstraps a demo
 * session on mount, shows the demo banner, and renders the same
 * ``<Layout>`` shell — no prod auth flow.
 *
 * Selected at build time when ``NEXT_PUBLIC_BSVIBE_DEMO=1``.
 */
export default function DemoLayout({ children }: { children: ReactNode }) {
  const { loading, error } = useAutoDemoSession(DEMO_API_URL);

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-gray-950 text-gray-400">
        <Loader2 className="h-8 w-8 animate-spin text-accent" />
        <p className="text-sm">Setting up your demo sandbox…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950 text-gray-100">
        <div className="text-center p-8">
          <h1 className="text-xl font-bold mb-2">Demo unavailable</h1>
          <p className="text-sm text-gray-400">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <DemoBanner productName="BSupervisor" locale="en" />
      <Layout>{children}</Layout>
    </>
  );
}
