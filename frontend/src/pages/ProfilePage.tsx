import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ProviderButton from "../components/ProviderButton";
import { PROVIDERS } from "../components/providers";
import type { LoginPayload, Provider, SocialAccount } from "../types";

export default function ProfilePage() {
  const { user, loginWith, disconnect, logout } = useAuth();
  const [error, setError] = useState("");

  const run = useCallback(async (fn: () => Promise<unknown>) => {
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  const connect = useCallback((provider: Provider) => (payload: LoginPayload) => run(() => loginWith(provider, payload)), [loginWith, run]);
  const onError = useCallback((msg: string) => setError(msg), []);

  // Rendered only inside <RequireAuth>, so the user is always present here.
  if (!user) return null;

  const linked: Partial<Record<Provider, SocialAccount>> = Object.fromEntries(user.social_accounts.map((a) => [a.provider, a]));
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;

  return (
    <main className="card">
      <div className="profile-head">
        {user.avatar_url ? (
          <img className="avatar" src={user.avatar_url} alt="" referrerPolicy="no-referrer" />
        ) : (
          <div className="avatar avatar-placeholder">{fullName[0]?.toUpperCase()}</div>
        )}
        <div>
          <h1>{fullName}</h1>
          <p className="muted">
            @{user.username}
            {user.email && ` · ${user.email}`}
          </p>
        </div>
      </div>

      <h2>Sign-in methods</h2>
      <ul className="accounts">
        {user.email && (
          <li>
            <span className="account-name">Password</span>
            <span className={user.has_password ? "badge" : "badge badge-muted"}>{user.has_password ? "Set" : "Not set"}</span>
            <Link className="btn-link" to="/forgot-password" state={{ email: user.email, from: { pathname: "/" } }}>
              {user.has_password ? "Change" : "Set password"}
            </Link>
          </li>
        )}
        {PROVIDERS.map((p) => (
          <li key={p.id}>
            <span className="account-name">{p.name}</span>
            {linked[p.id] ? (
              <>
                <span className="badge">Connected</span>
                <button className="btn btn-link" onClick={() => run(() => disconnect(p.id))}>
                  Disconnect
                </button>
              </>
            ) : (
              <ProviderButton provider={p.id} onSuccess={connect(p.id)} onError={onError} text="continue_with" label="Connect Facebook" />
            )}
          </li>
        ))}
      </ul>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <button className="btn btn-outline" onClick={logout}>
        Log out
      </button>
    </main>
  );
}
