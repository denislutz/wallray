import AccountS from "@/services/business/AccountS";
import AuthS from "@/services/tech/AuthS";
import type { Lang } from "@/services/tech/I18nS";
import I18nS from "@/services/tech/I18nS";
import ToastS from "@/services/tech/ToastS";
import {
  type ReactNode,
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

// ============================================================================
// Private
// ============================================================================

interface UISession {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

const UISessionContext = createContext<UISession>({
  lang: "EN",
  setLang: () => {},
});

const STORAGE_KEY = "bs_lang";

const isValidLang = (value: string | null | undefined): value is Lang =>
  value != null && (I18nS.langs as string[]).includes(value);

const detectBrowserLang = (): Lang => {
  const candidates = navigator.languages?.length ? navigator.languages : [navigator.language];
  for (const candidate of candidates) {
    const primary = candidate.split("-")[0]?.toUpperCase();
    if (isValidLang(primary)) return primary;
  }
  return "EN";
};

// ============================================================================
// Public service API
// ============================================================================

function UISessionProvider({ children }: { children: ReactNode }) {
  const { token } = AuthS.useAuth();
  const { me } = AccountS.useMe(token);
  const updateLanguage = AccountS.useUpdateLanguage(token);

  // Guest/pre-auth fallback only — read once on mount (client-only, avoids SSR
  // access to localStorage). Falls back to the browser's own locale when
  // nothing was stored yet. Never re-read after this; the DB is what decides
  // once an account is known, so this must not be able to clobber it later.
  const [storedLang, setStoredLang] = useState<Lang | null>(null);
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    setStoredLang(isValidLang(stored) ? stored : detectBrowserLang());
  }, []);

  // Explicit in-session pick, held until the DB confirms it (see below). Needed
  // because `me.preferred_language` only updates after the PATCH round-trips —
  // without this, picking a language would flash to the old one until then.
  const [override, setOverride] = useState<Lang | null>(null);

  // A pick made while still a guest (no token) — the account doesn't exist
  // yet to persist it against, so it's held here until login and pushed to
  // the DB then. Without this, the DB's default (English) wins over the
  // language the user actually chose on the sign-in page.
  const guestPickRef = useRef<Lang | null>(null);

  const accountLangRaw = me?.preferred_language.toUpperCase();
  const accountLang = isValidLang(accountLangRaw) ? accountLangRaw : null;

  // Single deterministic precedence, computed fresh every render — no dueling
  // setState calls racing to decide `lang`, which is what let a stale write
  // clobber the correct value across reloads. DB always wins once known; an
  // explicit pick wins until the DB confirms it; localStorage is only the
  // pre-auth guess.
  const lang: Lang = override ?? accountLang ?? storedLang ?? "EN";

  // Once the DB reflects the override, drop it — the DB goes back to being
  // authoritative (e.g. if changed from another device/tab).
  useEffect(() => {
    if (override && accountLang === override) setOverride(null);
  }, [override, accountLang]);

  useEffect(() => {
    I18nS.setLanguage(lang);
    localStorage.setItem(STORAGE_KEY, lang);
  }, [lang]);

  const setLang = useCallback(
    (l: Lang) => {
      setOverride(l);
      if (token) {
        updateLanguage.mutate(l.toLowerCase(), {
          onError: () => ToastS.error(I18nS.t("account_language_update_error")),
        });
      } else {
        guestPickRef.current = l;
      }
    },
    [token, updateLanguage]
  );

  // Once login completes, push a guest-era pick to the DB — it never had a
  // chance to persist before an account existed.
  useEffect(() => {
    if (token && guestPickRef.current) {
      const pick = guestPickRef.current;
      guestPickRef.current = null;
      updateLanguage.mutate(pick.toLowerCase(), {
        onError: () => ToastS.error(I18nS.t("account_language_update_error")),
      });
    }
  }, [token, updateLanguage]);

  return createElement(UISessionContext.Provider, { value: { lang, setLang } }, children);
}

const useUISession = (): UISession => useContext(UISessionContext);

const useT = (): typeof I18nS.t => {
  const { lang } = useUISession();
  I18nS.setLanguage(lang);
  return I18nS.t;
};

const UISessionS = { UISessionProvider, useUISession, useT };
export default UISessionS;
