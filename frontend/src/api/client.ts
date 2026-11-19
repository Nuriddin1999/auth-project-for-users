import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { tokens } from "../auth/tokens";
import { config } from "../config";
import type { AccessToken } from "../types";

// withCredentials: send/receive the httpOnly refresh cookie on cross-origin calls.
export const api = axios.create({ baseURL: config.apiUrl, withCredentials: true });

// Plain instance without interceptors, used for the refresh call itself.
const bare = axios.create({ baseURL: config.apiUrl, withCredentials: true });

api.interceptors.request.use((req) => {
  const access = tokens.access;
  if (access) req.headers.Authorization = `Bearer ${access}`;
  return req;
});

let refreshing: Promise<string> | null = null;
let onAuthLost: () => void = () => {};

export function setOnAuthLost(fn: () => void): void {
  onAuthLost = fn;
}

/** Get a new access token using the refresh cookie. One request is shared by all callers. */
export function refreshAccessToken(): Promise<string> {
  refreshing ??= bare
    .post<AccessToken>("/auth/token/refresh/")
    .then(({ data }) => {
      tokens.access = data.access;
      return data.access;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    // Only retry requests that were sent with an (expired) access token.
    if (!original || error.response?.status !== 401 || original._retried || !tokens.access) {
      throw error;
    }
    original._retried = true;
    try {
      const access = await refreshAccessToken();
      original.headers.Authorization = `Bearer ${access}`;
      return api(original);
    } catch {
      tokens.clear();
      onAuthLost();
      throw error;
    }
  },
);

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError<{ detail?: string }>(error)) {
    return error.response?.data?.detail || error.message;
  }
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}
