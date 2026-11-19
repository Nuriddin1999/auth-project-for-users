import { useEffect, useRef } from "react";
import { config } from "../config";
import type { ProviderButtonProps, TelegramUser } from "../types";
import UnconfiguredButton from "./UnconfiguredButton";

let counter = 0;

/**
 * Embeds the official Telegram Login Widget.
 * The widget only works on the domain registered for the bot via /setdomain
 * in @BotFather (localhost is not accepted - use a tunnel like ngrok in dev).
 */
export default function TelegramButton({ onSuccess, onError }: ProviderButtonProps) {
  const container = useRef<HTMLDivElement>(null);
  const callbackRef = useRef(onSuccess);

  useEffect(() => {
    callbackRef.current = onSuccess;
  }, [onSuccess]);

  useEffect(() => {
    const node = container.current;
    if (!config.telegramBotName || !node) return;

    const callbackName = `__onTelegramAuth${++counter}` as const;
    window[callbackName] = (user: TelegramUser) => callbackRef.current(user);

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", config.telegramBotName);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "8");
    script.setAttribute("data-request-access", "write");
    script.setAttribute("data-onauth", `${callbackName}(user)`);
    node.appendChild(script);

    return () => {
      delete window[callbackName];
      node.innerHTML = "";
    };
  }, []);

  if (!config.telegramBotName) {
    return (
      <UnconfiguredButton
        name="Telegram"
        env="VITE_TELEGRAM_BOT_NAME"
        onSuccess={onSuccess}
        onError={onError}
        className="btn-telegram"
        icon={<TelegramIcon />}
      />
    );
  }
  return <div className="provider-slot" ref={container} />;
}

function TelegramIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        fill="currentColor"
        d="M9.78 18.65l.28-4.23 7.68-6.92c.34-.31-.07-.46-.52-.19L7.74 13.3 3.64 12c-.88-.25-.89-.86.2-1.3l15.97-6.16c.73-.33 1.43.18 1.15 1.3l-2.72 12.81c-.19.91-.74 1.13-1.5.71l-4.14-3.06-1.99 1.93c-.23.23-.42.42-.83.42z"
      />
    </svg>
  );
}
