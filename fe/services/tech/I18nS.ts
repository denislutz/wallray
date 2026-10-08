// ============================================================================
// Private — translation builder (EN is the default language)
// ============================================================================

import { Fragment, type ReactNode, createElement } from "react";
import DE from "./i18n/de";
import EL from "./i18n/el";
import EN from "./i18n/en";
import RU from "./i18n/ru";

type Translation = Record<string, string>;
type Translations<T> = Record<keyof T, Translation>;
type TranslationKey<T> = keyof T[keyof T] & string;
type LanguageKey<T> = keyof T;

const buildService = <T extends Translations<T>>(translations: T) => {
  let currentLanguage: LanguageKey<T> = Object.keys(translations)[0] as LanguageKey<T>;

  const setLanguage = (language: LanguageKey<T>): void => {
    if (translations[language]) currentLanguage = language;
  };

  const translateKey = (key: TranslationKey<T>): string | undefined =>
    translations[currentLanguage][key];

  function t(key: TranslationKey<T>, params?: Record<string, string>): string;
  function t(key: TranslationKey<T>, params?: Record<string, string | ReactNode>): ReactNode;
  function t(
    key: TranslationKey<T>,
    params?: Record<string, string | ReactNode>
  ): string | ReactNode {
    const template = translateKey(key);
    if (!template) return "";
    if (!params) return template;

    const anyReactComponent = Object.values(params).some((param) => typeof param !== "string");

    if (!anyReactComponent) {
      return Object.keys(params).reduce(
        (result, attr) => result.replace(`{${attr}}`, params[attr] as string),
        template
      );
    }

    const elements = template.split(/(\{[^}]+\})/g).map((part, index) => {
      const placeholder = /\{([^}]+)\}/.exec(part);
      if (placeholder) {
        const value = params[placeholder[1]];
        return value !== undefined ? createElement(Fragment, { key: index }, value) : part;
      }
      return part;
    });

    return createElement(Fragment, {}, ...elements);
  }

  const langs = Object.keys(translations) as LanguageKey<T>[];

  return { setLanguage, t, langs };
};

const CURRENCY_LOCALE_BY_LANG: Record<string, string> = {
  EN: "en-US",
  DE: "de-DE",
  RU: "ru-RU",
  EL: "el-GR",
};

const formatEurPrice = (amount: number, lang: string): string =>
  new Intl.NumberFormat(CURRENCY_LOCALE_BY_LANG[lang] ?? "en-US", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(amount);

const I18nS = { ...buildService({ EN, DE, RU, EL }), formatEurPrice };
export type Lang = Parameters<typeof I18nS.setLanguage>[0];
export type TFn = typeof I18nS.t;
export default I18nS;
