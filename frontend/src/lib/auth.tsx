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
  setAuth: (token: string, user: { email: string; name?: string }) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const AUTH_BASE = "https://auth.bsvibe.dev";
const TOKEN_KEY = "bsupervisor_token";
const USER_KEY = "bsupervisor_user";

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
    localStorage.removeItem(USER_KEY);
    setState({ token: null, user: null, isLoading: false });
  }, []);

  const setAuth = useCallback(
    (token: string, user: { email: string; name?: string }) => {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
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
