import { useEffect } from "react";
import AuthCard from "./AuthCard";

const REDIRECT_DELAY = 1500;

interface Props {
  title?: string;
  message?: string;
  continueLabel?: string;
  onContinue: () => void;
}

/** Success screen (e.g. "Authentication successful") that redirects after a short delay. */
export default function AuthSuccess({
  title = "Authentication successful",
  message = "You're all set.",
  continueLabel = "Continue",
  onContinue,
}: Props) {
  useEffect(() => {
    const timer = setTimeout(onContinue, REDIRECT_DELAY);
    return () => clearTimeout(timer);
  }, [onContinue]);

  return (
    <AuthCard title={title}>
      <div className="success-screen" role="status">
        <svg className="success-icon" viewBox="0 0 52 52" aria-hidden="true">
          <circle cx="26" cy="26" r="24" />
          <path d="M15 27l7 7 15-15" />
        </svg>
        <p>{message}</p>
        <p className="muted">Redirecting…</p>
        <button type="button" className="btn btn-primary" onClick={onContinue}>
          {continueLabel}
        </button>
      </div>
    </AuthCard>
  );
}
