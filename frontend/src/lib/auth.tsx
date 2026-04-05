import { createContext, useContext, useState, useEffect, useCallback } from "react";
import type { ReactNode } from "react";
import { BSVibeAuth } from "./bsvibe-auth";

const AUTH_URL = "https://auth.bsvibe.dev";

const auth = new BSVibeAuth({
  authUrl: AUTH_URL,
  callbackPath: "/auth/callback",
});

interface AuthState {
  token: string | null;
  user: { email: string; name?: string } | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: () => void;
  signup: () => void;
  logout: () => void;
  handleCallback: () => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    user: null,
    isLoading: true,
  });

  // Initialize: check local session, then try silent SSO
  useEffect(() => {
    const localUser = auth.getUser();
    if (localUser) {
      setState({
        token: localUser.accessToken,
        user: { email: localUser.email },
        isLoading: false,
      });
      return;
    }

    // Silent SSO check (redirect-based)
    const result = auth.checkSession();
    if (result === 'redirect') return; // page is navigating away
    if (result) {
      setState({
        token: result.accessToken,
        user: { email: result.email },
        isLoading: false,
      });
    } else {
      setState({ token: null, user: null, isLoading: false });
    }
  }, []);

  const login = useCallback(() => {
    auth.redirectToLogin();
  }, []);

  const signup = useCallback(() => {
    auth.redirectToSignup();
  }, []);

  const logout = useCallback(() => {
    setState({ token: null, user: null, isLoading: false });
    auth.logout();
  }, []);

  const handleCallback = useCallback((): boolean => {
    const bsUser = auth.handleCallback();
    if (!bsUser) return false;
    setState({
      token: bsUser.accessToken,
      user: { email: bsUser.email },
      isLoading: false,
    });
    return true;
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, signup, logout, handleCallback }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

/** Get current access token for API interceptors (can be called outside React) */
export function getToken(): string | null {
  return auth.getToken();
}
