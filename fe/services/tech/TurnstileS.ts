import EnvS from "@/services/tech/EnvS";

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement,
        options: {
          sitekey: string;
          callback: (token: string) => void;
          "expired-callback"?: () => void;
        }
      ) => string;
      remove: (widgetId: string) => void;
    };
  }
}

// ============================================================================
// Private
// ============================================================================

const SCRIPT_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js";

let scriptPromise: Promise<void> | null = null;

// ============================================================================
// Public service API
// ============================================================================

const loadScript = (): Promise<void> => {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.turnstile) return Promise.resolve();
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load the Turnstile script"));
      document.head.appendChild(script);
    });
  }
  return scriptPromise;
};

const TurnstileS = { loadScript, siteKey: EnvS.turnstileSiteKey };
export default TurnstileS;
