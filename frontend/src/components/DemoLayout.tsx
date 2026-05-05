"use client";

import { AuthProvider } from "@bsvibe/auth";
import { DemoBanner, useAutoDemoSession } from "@bsvibe/demo";
import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { Layout } from "@/src/components/Layout";
import { injectDemoToken } from "@/src/hooks/useAuth";

const DEMO_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "https://api-demo-supervisor.bsvibe.dev";

const AUTH_URL = process.env.NEXT_PUBLIC_BSVIBE_AUTH_URL ?? "https://auth.bsvibe.dev";

// Demo identity: <Layout> calls useAuth() (from @bsvibe/auth) to populate
// the sidebar / tenant switcher / "sign out" button. In demo mode the
// shared AuthProvider is not in the tree, so useAuth() throws and the
// page bails out with "Application error". Provide a stub session via
// fetchImpl so the shared provider resolves a demo user.
const DEMO_SESSION = {
  access_token: "demo",
  refresh_token: "",
  expires_in: 7200,
  user: { id: "demo-user", email: "demo@bsvibe.dev" },
  tenants: [{ id: "demo", name: "Demo sandbox", role: "viewer" }],
  active_tenant_id: "demo",
};

const demoFetch: typeof fetch = async (input, init) => {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.toString()
        : input.url;
  if (url === `${AUTH_URL.replace(/\/+$/, "")}/api/session`) {
    return new Response(JSON.stringify(DEMO_SESSION), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }
  return fetch(input, init);
};

/**
 * Demo mode equivalent of ``ProtectedLayout``. Auto-bootstraps a demo
 * session on mount, shows the demo banner, and renders the same
 * ``<Layout>`` shell — no prod auth flow.
 *
 * Selected at build time when ``NEXT_PUBLIC_BSVIBE_DEMO=1``.
 */
export default function DemoLayout({ children }: { children: ReactNode }) {
  const { loading, error } = useAutoDemoSession(DEMO_API_URL, {
    onSessionReady: ({ token, expiresIn }) => {
      // Park the demo JWT in BSupervisor's local cachedToken so
      // `getAccessToken()` (consumed by @bsvibe/api fetch wrappers)
      // returns it. The demoFetch above answers the auth.bsvibe.dev
      // probe, but the dashboard data fetches still go to the demo
      // backend and need Authorization.
      injectDemoToken(token, expiresIn);
    },
  });

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
    <AuthProvider authUrl={AUTH_URL} fetchImpl={demoFetch}>
      <DemoBanner productName="BSupervisor" locale="en" />
      <Layout>{children}</Layout>
    </AuthProvider>
  );
}
