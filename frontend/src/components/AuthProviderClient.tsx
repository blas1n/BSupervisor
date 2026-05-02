"use client";

/**
 * Phase A workaround — `@bsvibe/auth`'s compiled `dist/useAuth.js` is
 * missing the `'use client'` directive even though the TS source uses
 * React Hooks. Until the upstream package builds it back in, we wrap
 * `AuthProvider` in a tiny client-side shim so Next.js's RSC boundary
 * is happy.
 *
 * Follow-up: surface as a `bsvibe-frontend-lib` issue — every consumer
 * will hit this on the first Next.js build.
 */

import { AuthProvider } from "@bsvibe/auth";
import type { ReactNode } from "react";
import { readStoredSession } from "@/src/hooks/useAuth";

function createSessionAwareFetch(authUrl: string): typeof fetch {
  const sessionUrl = `${authUrl.replace(/\/+$/, "")}/api/session`;

  return async (input, init) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

    if (url === sessionUrl) {
      const storedSession = readStoredSession();
      if (storedSession) {
        return new Response(JSON.stringify(storedSession), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
    }

    return fetch(input, init);
  };
}

export function AuthProviderClient({
  authUrl,
  children,
}: {
  authUrl: string;
  children: ReactNode;
}) {
  return (
    <AuthProvider authUrl={authUrl} fetchImpl={createSessionAwareFetch(authUrl)}>
      {children}
    </AuthProvider>
  );
}
