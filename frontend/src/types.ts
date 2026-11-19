export type Provider = "google" | "facebook" | "telegram";

export interface SocialAccount {
  provider: Provider;
  uid: string;
  avatar_url: string;
  created_at: string;
}

export interface User {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  avatar_url: string;
  social_accounts: SocialAccount[];
  date_joined: string;
}

/** The refresh token is never in a response body - only in an httpOnly cookie. */
export interface AccessToken {
  access: string;
}

export interface AuthResponse extends AccessToken {
  user: User;
  created: boolean;
}

/** Data returned by the Telegram Login Widget. */
export interface TelegramUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

export type MockPayload = { mock: true };

export type LoginPayload = { credential: string } | { access_token: string } | TelegramUser | MockPayload;

export interface ProviderButtonProps {
  onSuccess: (payload: LoginPayload) => void;
  onError: (message: string) => void;
  /** Google button text variant. */
  text?: "signin_with" | "signup_with" | "continue_with" | "signin";
  /** Facebook button label. */
  label?: string;
}
