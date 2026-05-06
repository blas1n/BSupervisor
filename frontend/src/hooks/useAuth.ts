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

import { useEffect, useState } from 'react';
import { useAuth as useAuthShared } from '@bsvibe/auth';

const AUTH_URL = process.env.NEXT_PUBLIC_BSVIBE_AUTH_URL ?? 'https://auth.bsvibe.dev';
const LS_ACCESS_TOKEN = 'bsupervisor_access_token';
const LS_REFRESH_TOKEN = 'bsupervisor_refresh_token';
const LS_EXPIRES_AT = 'bsupervisor_expires_at';

interface SessionResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user?: {
    id: string;
    email: string;
  };
  tenants?: Array<{
    id: string;
    name: string;
    role: string;
  }>;
  active_tenant_id?: string;
}

let cachedToken: { value: string; expiresAt: number } | null = null;

function decodeJwt(token: string): Record<string, unknown> {
  const parts = token.split('.');
  let base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
  const pad = base64.length % 4;
  if (pad) base64 += '='.repeat(4 - pad);
  return JSON.parse(atob(base64));
}

function readStoredToken(): { value: string; refreshToken: string; expiresAt: number } | null {
  if (typeof window === 'undefined') return null;
  const value = localStorage.getItem(LS_ACCESS_TOKEN);
  const refreshToken = localStorage.getItem(LS_REFRESH_TOKEN) ?? '';
  const expiresAt = Number(localStorage.getItem(LS_EXPIRES_AT) ?? '0');
  if (!value || !Number.isFinite(expiresAt) || Date.now() >= expiresAt - 30_000) return null;
  return { value, refreshToken, expiresAt };
}

export function readStoredSession(): SessionResponse | null {
  const stored = readStoredToken();
  if (!stored) return null;
  const payload = decodeJwt(stored.value) as {
    sub?: string;
    email?: string;
    app_metadata?: { tenant_id?: string; role?: string };
  };
  const tenantId = payload.app_metadata?.tenant_id ?? '';
  const role = payload.app_metadata?.role ?? 'member';
  return {
    access_token: stored.value,
    refresh_token: stored.refreshToken,
    expires_in: Math.max(1, Math.floor((stored.expiresAt - Date.now()) / 1000)),
    user: {
      id: payload.sub ?? '',
      email: payload.email ?? '',
    },
    tenants: tenantId ? [{ id: tenantId, name: 'BSVibe', role }] : [],
    active_tenant_id: tenantId || undefined,
  };
}

/** Return a cached `access_token` or fetch a new one from `/api/session`. */
export async function getAccessToken(): Promise<string | null> {
  if (cachedToken && Date.now() < cachedToken.expiresAt - 30_000) {
    return cachedToken.value;
  }
  const stored = readStoredToken();
  if (stored) {
    cachedToken = { value: stored.value, expiresAt: stored.expiresAt };
    return stored.value;
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
  if (typeof window !== 'undefined') {
    localStorage.removeItem(LS_ACCESS_TOKEN);
    localStorage.removeItem(LS_REFRESH_TOKEN);
    localStorage.removeItem(LS_EXPIRES_AT);
  }
}

/**
 * Inject a demo session JWT into the auth token cache so getAccessToken()
 * returns the demo Bearer for every fetch — without this, the demo shell
 * loads but every dashboard fetch goes out unauth'd.
 *
 * Wire from DemoLayout via @bsvibe/demo 0.3 onSessionReady.
 */
export function injectDemoToken(token: string, expiresIn: number): void {
  const expiresAt = Date.now() + expiresIn * 1000;
  cachedToken = { value: token, expiresAt };
  if (typeof window !== 'undefined') {
    localStorage.setItem(LS_ACCESS_TOKEN, token);
    localStorage.setItem(LS_EXPIRES_AT, String(expiresAt));
  }
}

/**
 * BSupervisor-flavoured `useAuth` — re-exposes the shared hook plus
 * `login()` / `logout()` redirects so the existing component tree
 * (`Layout.tsx`, `Login.tsx`, etc.) keeps working unchanged.
 */
export function useAuth() {
  const shared = useAuthShared();
  // The shared offline stub hardcodes a single fake tenant. Fetch
  // /api/session ourselves so the sidebar shows the real workspace
  // name + the full multi-tenant list (drives the SidebarTenantSwitcher
  // dropdown). Best-effort — falls back to the stub on failure.
  type LiveTenant = { id: string; name: string; role?: string };
  const [liveTenants, setLiveTenants] = useState<LiveTenant[]>([]);

  useEffect(() => {
    if (!shared.user || !shared.activeTenant?.id) return;
    let cancelled = false;
    (async () => {
      const token = await getAccessToken();
      if (!token || cancelled) return;
      try {
        const res = await fetch(`${AUTH_URL}/api/session`, {
          credentials: 'include',
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as {
          tenants?: LiveTenant[];
        };
        if (!cancelled && data.tenants) setLiveTenants(data.tenants);
      } catch {
        // ignore
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [shared.user, shared.activeTenant?.id]);

  const activeTenantId = shared.activeTenant?.id;
  const tenantNameOverride =
    liveTenants.find((t) => t.id === activeTenantId)?.name ?? null;

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
  // shape used by BSupervisor components. `tenantName` prefers the live
  // /api/session response so the sidebar shows the real workspace name
  // instead of the offline 'BSVibe' stub.
  const user = shared.user
    ? {
        id: shared.user.id,
        email: shared.user.email,
        tenantId: shared.activeTenant?.id ?? '',
        tenantName: tenantNameOverride ?? shared.activeTenant?.name ?? null,
        role: shared.activeTenant?.role ?? 'member',
      }
    : null;

  return {
    user,
    loading: shared.isLoading,
    login,
    logout,
    // Prefer the live /api/session list (real names) when available;
    // fall back to the shared offline stub.
    tenants: liveTenants.length > 0 ? liveTenants : shared.tenants,
    activeTenant: shared.activeTenant,
    hasPermission: shared.hasPermission,
    switchTenant: shared.switchTenant,
    refresh: shared.refresh,
    error: shared.error,
  };
}
