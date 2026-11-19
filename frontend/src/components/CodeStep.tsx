import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { errorBody, errorMessage } from "../api/client";

const RESEND_COOLDOWN = 60;

interface Props {
  email: string;
  /** Text above the input; defaults to "We sent a N-digit code to <email>". */
  message?: ReactNode;
  codeLength: number;
  /** Seconds the current code stays valid. */
  expiresIn: number;
  onVerify: (code: string) => Promise<unknown>;
  onResend: () => Promise<{ expires_in: number; code_length: number }>;
  onBack: () => void;
  backLabel?: string;
}

/** Second step of email auth: enter the code sent to the email before it expires. */
export default function CodeStep({
  email,
  message,
  codeLength,
  expiresIn,
  onVerify,
  onResend,
  onBack,
  backLabel = "Use a different email",
}: Props) {
  const [length, setLength] = useState(codeLength);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [expiresAt, setExpiresAt] = useState(() => Date.now() + expiresIn * 1000);
  const [resendAt, setResendAt] = useState(() => Date.now() + RESEND_COOLDOWN * 1000);
  const [now, setNow] = useState(() => Date.now());
  const input = useRef<HTMLInputElement>(null);

  // One ticking clock drives both countdowns.
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, []);

  const secondsLeft = Math.max(0, Math.ceil((expiresAt - now) / 1000));
  const resendIn = Math.max(0, Math.ceil((resendAt - now) / 1000));
  const expired = secondsLeft === 0;

  const verify = async (value: string) => {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await onVerify(value);
    } catch (e) {
      setError(errorMessage(e));
      setCode("");
      setBusy(false);
      setTimeout(() => input.current?.focus());
    }
  };

  const handleChange = (value: string) => {
    const digits = value.replace(/\D/g, "").slice(0, length);
    setCode(digits);
    if (digits.length === length && !busy && !expired) void verify(digits); // auto-submit, incl. paste
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (code.length === length && !expired) void verify(code);
  };

  const resend = async () => {
    setError("");
    setNotice("");
    try {
      const sent = await onResend();
      setLength(sent.code_length);
      setCode("");
      setExpiresAt(Date.now() + sent.expires_in * 1000);
      setResendAt(Date.now() + RESEND_COOLDOWN * 1000);
      setNotice("A new code has been sent");
      setTimeout(() => input.current?.focus());
    } catch (e) {
      setError(errorMessage(e));
      const retryAfter = errorBody(e)?.retry_after;
      if (retryAfter) setResendAt(Date.now() + retryAfter * 1000);
    }
  };

  return (
    <form className="form" onSubmit={handleSubmit}>
      <p className="muted">
        {message ?? (
          <>
            We sent a {length}-digit code to <strong className="text">{email}</strong>. Enter it below to continue.
          </>
        )}
      </p>

      <label className="field">
        <span>Verification code</span>
        <input
          ref={input}
          className="input code-input"
          value={code}
          onChange={(e) => handleChange(e.target.value)}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder={"0".repeat(length)}
          maxLength={length}
          autoFocus
          disabled={busy || expired}
          aria-invalid={Boolean(error)}
        />
      </label>

      <p className={`timer ${expired ? "timer-expired" : secondsLeft <= 10 ? "timer-warn" : ""}`} aria-live="polite">
        {expired ? "The code has expired. Request a new one." : `Code expires in ${formatTime(secondsLeft)}`}
      </p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && <p className="success">{notice}</p>}

      <button className="btn btn-primary" type="submit" disabled={busy || expired || code.length !== length}>
        {busy ? "Checking…" : "Continue"}
      </button>

      <div className="form-row">
        <button type="button" className="btn-link" onClick={onBack}>
          {backLabel}
        </button>
        <button type="button" className="btn-link" onClick={resend} disabled={resendIn > 0}>
          {resendIn > 0 ? `Resend code in ${resendIn}s` : "Resend code"}
        </button>
      </div>
    </form>
  );
}

function formatTime(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
