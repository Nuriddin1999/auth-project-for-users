import { useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { authErrorMessage } from "./authErrors";
import PasswordInput from "./PasswordInput";
import { isEmail, isFilled } from "../validation";

interface Props {
  prefillEmail?: string;
  /** Put the cursor in the password field (email already known, e.g. right after sign up). */
  focusPassword?: boolean;
  onDone: () => void;
}

/** Email + password sign in, with a "Forgot password?" link. */
export default function SignInForm({ prefillEmail = "", focusPassword = false, onDone }: Props) {
  const { loginWithPassword } = useAuth();
  const [email, setEmail] = useState(prefillEmail);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<ReactNode>("");
  const [busy, setBusy] = useState(false);
  const canSubmit = isEmail(email) && isFilled(password);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await loginWithPassword(email.trim(), password);
      onDone();
    } catch (err) {
      setError(authErrorMessage(err, email.trim()));
      setPassword("");
      setBusy(false);
    }
  };

  return (
    <form className="form" onSubmit={handleSubmit}>
      <label className="field">
        <span>Email</span>
        <input
          className="input"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          placeholder="you@example.com"
          maxLength={254}
          required
        />
      </label>
      <div>
        <PasswordInput
          label="Password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          autoFocus={focusPassword}
          required
        />
        <div className="field-link">
          <Link to="/forgot-password" state={{ email: email.trim() }}>
            Forgot password?
          </Link>
        </div>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <button className="btn btn-primary" type="submit" disabled={busy || !canSubmit}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
