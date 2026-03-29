import { createContext, useContext, useState, useEffect, useCallback } from "react";
import type { ReactNode } from "react";

interface AuthState {
  token: string | null;
  user: { email: string; name?: string } | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: () => void;
  logout: () => void;
  setAuth: (token: string, user: { email: string; name?: string }, refreshToken?: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const AUTH_BASE = "https://auth.bsvibe.dev";
const TOKEN_KEY = "bsupervisor_token";
const REFRESH_TOKEN_KEY = "bsupervisor_refresh_token";
const USER_KEY = "bsupervisor_user";

/** Decode JWT payload without verification (browser-side, for display only). */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

/**
 * Extract access_token and refresh_token from the URL hash fragment.
 * Returns null if no access_token is found.
 * Cleans the hash from the URL after extraction.
 */
export function consumeHashTokens(): {
  accessToken: string;
  refreshToken: string | null;
} | null {
  const hash = window.location.hash.substring(1);
  if (!hash) return null;

  const params = new URLSearchParams(hash);
  const accessToken = params.get("access_token");
  if (!accessToken) return null;

  const refreshToken = params.get("refresh_token");

  // Clean hash from URL
  window.history.replaceState(null, "", window.location.pathname + window.location.search);

  return { accessToken, refreshToken };
}

/** Extract user info from a JWT access token. */
export function userFromToken(token: string): { email: string; name?: string } | null {
  const payload = decodeJwtPayload(token);
  if (!payload) return null;

  const email = (payload.email ?? payload.sub ?? "") as string;
  if (!email) return null;

  const name = (payload.name ?? payload.user_name ?? undefined) as string | undefined;
  return { email, name };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    user: null,
    isLoading: true,
  });

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    const userStr = localStorage.getItem(USER_KEY);
    if (token && userStr) {
      try {
        const user = JSON.parse(userStr);
        setState({ token, user, isLoading: false });
      } catch {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        setState({ token: null, user: null, isLoading: false });
      }
    } else {
      setState({ token: null, user: null, isLoading: false });
    }
  }, []);

  const login = useCallback(() => {
    const callbackUrl = `${window.location.origin}/auth/callback`;
    window.location.href = `${AUTH_BASE}/login?redirect_uri=${encodeURIComponent(callbackUrl)}`;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setState({ token: null, user: null, isLoading: false });
  }, []);

  const setAuth = useCallback(
    (token: string, user: { email: string; name?: string }, refreshToken?: string) => {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
      if (refreshToken) {
        localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
      }
      setState({ token, user, isLoading: false });
    },
    [],
  );

  return (
    <AuthContext.Provider value={{ ...state, login, logout, setAuth }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
