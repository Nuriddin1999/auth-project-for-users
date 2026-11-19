import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, refreshAccessToken, setOnAuthLost } from "../api/client";
import type {
  AuthResponse,
  CodeSent,
  EmailPurpose,
  LoginPayload,
  MockCodeSent,
  Provider,
  SignUpConfirmed,
  SignUpData,
  User,
} from "../types";
import { tokens } from "./tokens";

interface IAuthContextValue {
  user: User | null;
  loading: boolean;
  /** Social login. When already logged in, the backend links the provider to the current user. */
  loginWith: (provider: Provider, payload: LoginPayload) => Promise<AuthResponse>;
  /** Email + password sign in. */
  loginWithPassword: (email: string, password: string) => Promise<AuthResponse>;
  /** Sign up, step 1: sends a code to the email. The account is created after the code is confirmed. */
  signUp: (data: SignUpData) => Promise<CodeSent>;
  /** Sign up, step 2: confirm the code -> account created. Does not sign in: the user signs in afterwards. */
  confirmSignUp: (email: string, code: string) => Promise<SignUpConfirmed>;
  /** Forgot password, step 1: sends a code to the email. */
  requestPasswordReset: (email: string) => Promise<CodeSent>;
  /** Forgot password, step 2: confirm the code -> token for choosing a new password. */
  verifyPasswordReset: (email: string, code: string) => Promise<string>;
  /** Forgot password, step 3: set the new password -> signed in. */
  resetPassword: (token: string, password: string, passwordConfirm: string) => Promise<AuthResponse>;
  /** Send a new code for a pending sign up / password reset. */
  resendCode: (purpose: EmailPurpose, email: string) => Promise<CodeSent>;
  /** Test mode: "send" a code for a provider without keys (email or Telegram username). */
  startMockLogin: (provider: Provider, identity: string) => Promise<MockCodeSent>;
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

  const startSession = useCallback((data: AuthResponse) => {
    tokens.access = data.access;
    setUser(data.user);
    return data;
  }, []);

  /** POST that returns a session. */
  const postSession = useCallback(
    async (url: string, body: object) => startSession((await api.post<AuthResponse>(url, body)).data),
    [startSession],
  );

  const value = useMemo<IAuthContextValue>(() => {
    const post = async <T,>(url: string, body: object) => (await api.post<T>(url, body)).data;
    return {
      user,
      loading,
      loginWith: (provider, payload) => postSession(`/auth/${provider}/`, payload),
      loginWithPassword: (email, password) => postSession("/auth/login/", { email, password }),
      signUp: (data) => post<CodeSent>("/auth/email/signup/", data),
      confirmSignUp: (email, code) => post<SignUpConfirmed>("/auth/email/verify/", { email, code }),
      requestPasswordReset: (email) => post<CodeSent>("/auth/password/reset/", { email }),
      verifyPasswordReset: async (email, code) =>
        (await post<{ reset_token: string }>("/auth/password/reset/verify/", { email, code })).reset_token,
      resetPassword: (token, password, passwordConfirm) =>
        postSession("/auth/password/reset/confirm/", { token, password, password_confirm: passwordConfirm }),
      resendCode: (purpose, email) => post<CodeSent>("/auth/email/resend/", { purpose, email }),
      startMockLogin: (provider, identity) => post<MockCodeSent>(`/auth/${provider}/`, { mock: true, identity }),
      disconnect: async (provider) => setUser((await api.delete<User>(`/auth/social/${provider}/`)).data),
      logout: async () => {
        await api.post("/auth/logout/").catch(() => {}); // blacklists the token and clears the cookie
        tokens.clear();
        setUser(null);
        window.FB?.logout?.();
      },
    };
  }, [user, loading, postSession]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): IAuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
