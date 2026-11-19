import type { ReactNode } from "react";
import { useLocation, useNavigate, type Location } from "react-router-dom";
import { config } from "../config";
import type { Provider, ProviderButtonProps } from "../types";

interface Props extends Pick<ProviderButtonProps, "onError"> {
  provider: Provider;
  name: string;
  env: string;
  className: string;
  icon: ReactNode;
}

/**
 * Button for a provider whose keys are missing.
 * Test mode: opens /connect/<provider>, which asks for an email / Telegram username and a code.
 * Otherwise: explains what to configure.
 */
export default function UnconfiguredButton({ provider, name, env, onError, className, icon }: Props) {
  const navigate = useNavigate();
  const location = useLocation();

  const handleClick = () => {
    if (!config.mockAuth) {
      onError(`${name} is not configured: set ${env} in frontend/.env and restart "npm run dev"`);
      return;
    }
    // Come back to where the user wanted to go (from sign in / sign up) or to this page (profile).
    const onAuthPage = ["/login", "/signup"].includes(location.pathname);
    const from = onAuthPage ? (location.state as { from?: Location } | null)?.from : location;
    navigate(`/connect/${provider}`, { state: { from } });
  };

  return (
    <button type="button" className={`btn ${className}`} onClick={handleClick}>
      {icon}
      Continue with {name}
    </button>
  );
}
