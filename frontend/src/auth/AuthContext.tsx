import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, refreshAccessToken, setOnAuthLost } from "../api/client";
import type { AuthResponse, LoginPayload, Provider, User } from "../types";
import { tokens } from "./tokens";

interface IAuthContextValue {
  user: User | null;
  loading: boolean;
  /** When already logged in, the backend links the provider to the current user. */
  loginWith: (provider: Provider, payload: LoginPayload) => Promise<AuthResponse>;
  disconnect: (provider: Provider) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<IAuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore the session after a page reload: refresh cookie -> access token -> profile.
  useEffect(() => {
    setOnAuthLost(() => setUser(null));
    refreshAccessToken()
      .then(() => api.get<User>("/auth/me/"))
      .then(({ data }) => setUser(data))
      .catch(() => tokens.clear()) // no cookie / expired session: just show the login page
      .finally(() => setLoading(false));
  }, []);

  const loginWith = useCallback(async (provider: Provider, payload: LoginPayload) => {
    const { data } = await api.post<AuthResponse>(`/auth/${provider}/`, payload);
    tokens.access = data.access;
    setUser(data.user);
    return data;
  }, []);

  const disconnect = useCallback(async (provider: Provider) => {
    const { data } = await api.delete<User>(`/auth/social/${provider}/`);
    setUser(data);
  }, []);

  const logout = useCallback(async () => {
    await api.post("/auth/logout/").catch(() => {}); // blacklists the token and clears the cookie
    tokens.clear();
    setUser(null);
    window.FB?.logout?.();
  }, []);

  const value = useMemo(() => ({ user, loading, loginWith, disconnect, logout }), [user, loading, loginWith, disconnect, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): IAuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
