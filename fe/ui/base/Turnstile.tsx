"use client";

import { useEffect, useRef } from "react";

import TurnstileS from "@/services/tech/TurnstileS";

type Props = {
  onVerify: (token: string) => void;
  onExpire?: () => void;
};

function Turnstile({ onVerify, onExpire }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Widget is rendered once, on mount — callbacks are read through refs so the widget doesn't
  // get torn down and re-rendered on every parent re-render just because an inline callback prop
  // got a new identity.
  const onVerifyRef = useRef(onVerify);
  const onExpireRef = useRef(onExpire);
  onVerifyRef.current = onVerify;
  onExpireRef.current = onExpire;

  useEffect(() => {
    let cancelled = false;
    let widgetId: string | null = null;

    TurnstileS.loadScript().then(() => {
      if (cancelled || !containerRef.current || !window.turnstile) return;
      widgetId = window.turnstile.render(containerRef.current, {
        sitekey: TurnstileS.siteKey(),
        callback: (token) => onVerifyRef.current(token),
        "expired-callback": () => onExpireRef.current?.(),
      });
    });

    return () => {
      cancelled = true;
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
    };
  }, []);

  return <div ref={containerRef} data-testid="turnstile-widget" />;
}

export { Turnstile };
