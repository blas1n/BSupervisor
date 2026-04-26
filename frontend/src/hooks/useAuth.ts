'use client';

/**
 * BSupervisor auth hook — Phase A consumer of `@bsvibe/auth`.
 *
 * The shared `@bsvibe/auth` package exposes `<AuthProvider>` + `useAuth()`
 * with cookie-SSO semantics (silent `/api/session` check + 401 = logged-out).
 * BSupervisor wraps that with two product-specific helpers:
 *
 * - `login()` / `logout()` — redirect-based interactions with the auth app,
 *   not part of the shared hook surface (each product owns its post-logout URL).
 * - `getAccessToken()` — short-lived token cache used by `@bsvibe/api`'s
 *   bearer-mode fetch. Calls `/api/session` directly so any consumer can
 *   ask for a token outside React (e.g. inside an axios interceptor).
 *
 * The legacy local `useAuth` shape (`{ user, loading, login, logout }`) is
 * preserved so existing components keep compiling. The richer
 * `@bsvibe/auth` surface (`tenants`, `activeTenant`, `hasPermission`,
 * `switchTenant`) is also re-exported for new code.
 */

import { useAuth as useAuthShared } from '@bsvibe/auth';

const AUTH_URL = process.env.NEXT_PUBLIC_BSVIBE_AUTH_URL ?? 'https://auth.bsvibe.dev';

interface SessionResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

let cachedToken: { value: string; expiresAt: number } | null = null;

/** Return a cached `access_token` or fetch a new one from `/api/session`. */
export async function getAccessToken(): Promise<string | null> {
  if (cachedToken && Date.now() < cachedToken.expiresAt - 30_000) {
    return cachedToken.value;
  }
  try {
    const res = await fetch(`${AUTH_URL}/api/session`, { credentials: 'include' });
    if (!res.ok) return null;
    const data: SessionResponse = await res.json();
    cachedToken = {
      value: data.access_token,
      expiresAt: Date.now() + data.expires_in * 1000,
    };
    return data.access_token;
  } catch {
    return null;
  }
}

export function clearTokenCache() {
  cachedToken = null;
}

/**
 * BSupervisor-flavoured `useAuth` — re-exposes the shared hook plus
 * `login()` / `logout()` redirects so the existing component tree
 * (`Layout.tsx`, `Login.tsx`, etc.) keeps working unchanged.
 */
export function useAuth() {
  const shared = useAuthShared();

  function login() {
    window.location.href = `${AUTH_URL}/login`;
  }

  async function logout() {
    await fetch(`${AUTH_URL}/api/session`, {
      method: 'DELETE',
      credentials: 'include',
    });
    clearTokenCache();
    window.location.href = 'https://bsvibe.dev/';
  }

  // Map the shared `User` shape (no role/tenantId) into the legacy local
  // shape used by BSupervisor components. The `role` / `tenantId` fields
  // come from `activeTenant` instead of the JWT app_metadata.
  const user = shared.user
    ? {
        id: shared.user.id,
        email: shared.user.email,
        tenantId: shared.activeTenant?.id ?? '',
        role: shared.activeTenant?.role ?? 'member',
      }
    : null;

  return {
    user,
    loading: shared.isLoading,
    login,
    logout,
    // Forward the richer shared surface for new code paths.
    tenants: shared.tenants,
    activeTenant: shared.activeTenant,
    hasPermission: shared.hasPermission,
    switchTenant: shared.switchTenant,
    refresh: shared.refresh,
    error: shared.error,
  };
}
