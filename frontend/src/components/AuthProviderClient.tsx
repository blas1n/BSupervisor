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
 *
 * The shim's `fetchImpl` also bridges two production gaps:
 *
 *  1. Hash-token capture — after an SSO redirect the token lands in the
 *     URL hash; `consumeHashTokens()` (called at module load) persists it
 *     to localStorage so `readStoredSession()` can resolve it.
 *  2. `user` synthesis — `auth.bsvibe.dev/api/session` returns
 *     `access_token` / `tenants` / `active_tenant_id` but NO `user`
 *     object. `@bsvibe/auth`'s `AuthProvider` does `setUser(data.user ?? null)`,
 *     so a live session with a valid cookie still resolves `user = null`
 *     and `ProtectedRoute` bounces to `/login` forever. We backfill `user`
 *     from the session's `access_token` JWT (`sub` + `email`) so the gate
 *     can settle.
 */

import { AuthProvider } from "@bsvibe/auth";
import type { ReactNode } from "react";
import { consumeHashTokens, readStoredSession } from "@/src/hooks/useAuth";

// Capture any SSO-redirect tokens sitting in the URL hash as early as
// possible — before `AuthProvider` mounts and runs its first
// `/api/session` refresh — so the stored-session path resolves on the
// very first render after login.
if (typeof window !== "undefined") {
  consumeHashTokens();
}

/** Decode a JWT payload without verifying the signature. */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    let base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const pad = base64.length % 4;
    if (pad) base64 += "=".repeat(4 - pad);
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

/**
 * Backfill a `user` object onto an `/api/session` response body when the
 * auth server omits it. Derives `id` / `email` from the `access_token`
 * JWT. Leaves the body untouched when `user` is already present.
 */
function withSynthesizedUser(body: Record<string, unknown>): Record<string, unknown> {
  if (body.user || typeof body.access_token !== "string") return body;
  const payload = decodeJwtPayload(body.access_token);
  if (!payload) return body;
  const id = typeof payload.sub === "string" ? payload.sub : "";
  const email = typeof payload.email === "string" ? payload.email : "";
  if (!id && !email) return body;
  return { ...body, user: { id, email } };
}

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

      // No stored session — fall through to the live cookie-based
      // `/api/session`, then backfill the missing `user` object so the
      // shared `AuthProvider` can resolve a logged-in state.
      const res = await fetch(input, init);
      if (!res.ok) return res;
      try {
        const body = (await res.clone().json()) as Record<string, unknown>;
        return new Response(JSON.stringify(withSynthesizedUser(body)), {
          status: res.status,
          headers: { "Content-Type": "application/json" },
        });
      } catch {
        return res;
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
