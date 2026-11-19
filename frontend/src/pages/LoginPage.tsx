import { useCallback, useState } from "react";
import { Navigate, useLocation, useNavigate, type Location } from "react-router-dom";
import { errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import ProviderButton from "../components/ProviderButton";
import { PROVIDERS } from "../components/providers";
import type { LoginPayload, Provider } from "../types";

export default function LoginPage() {
  const { user, loginWith } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const next = (location.state as { from?: Location } | null)?.from?.pathname || "/";

  const handle = useCallback(
    (provider: Provider) => async (payload: LoginPayload) => {
      setError("");
      setBusy(true);
      try {
        await loginWith(provider, payload);
        navigate(next, { replace: true });
      } catch (e) {
        setError(errorMessage(e));
      } finally {
        setBusy(false);
      }
    },
    [loginWith, navigate, next],
  );

  const onError = useCallback((msg: string) => setError(msg), []);

  if (user) return <Navigate to={next} replace />;

  return (
    <main className="card">
      <h1>Sign in</h1>
      <p className="muted">Choose how you want to continue</p>

      <div className={`providers ${busy ? "is-busy" : ""}`}>
        {PROVIDERS.map((p) => (
          <ProviderButton key={p.id} provider={p.id} onSuccess={handle(p.id)} onError={onError} />
        ))}
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </main>
  );
}
