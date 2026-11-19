import type { ReactNode } from "react";
import { config } from "../config";
import type { ProviderButtonProps } from "../types";

interface Props extends Pick<ProviderButtonProps, "onSuccess" | "onError"> {
  name: string;
  env: string;
  className: string;
  icon: ReactNode;
}

/**
 * Button for a provider whose keys are missing.
 * Test mode: signs in a fake user. Otherwise: explains what to configure.
 */
export default function UnconfiguredButton({ name, env, onSuccess, onError, className, icon }: Props) {
  const handleClick = () => {
    if (config.mockAuth) onSuccess({ mock: true });
    else onError(`${name} is not configured: set ${env} in frontend/.env and restart "npm run dev"`);
  };
  return (
    <button className={`btn ${className}`} onClick={handleClick}>
      {icon}
      Continue with {name}
    </button>
  );
}
