"use client";

import UISessionS from "@/services/business/UISessionS";
import I18nS, { type Lang } from "@/services/tech/I18nS";
import { Row } from "@/ui/base/Row";
import { Text } from "@/ui/base/Text";
import { Button } from "@/ui/base/button";

// ============================================================================
// Private
// ============================================================================

const LANG_LABELS: Record<Lang, string> = {
  EN: "English",
  DE: "Deutsch",
  RU: "Русский",
  EL: "Ελληνικά",
};

// ============================================================================
// Public
// ============================================================================

export function LangSwitcher() {
  const { lang, setLang } = UISessionS.useUISession();

  return (
    <Row gap="xs">
      {I18nS.langs.map((l) => (
        <Button
          key={l}
          type="button"
          size="sm"
          variant={l === lang ? "default" : "outline"}
          aria-label={LANG_LABELS[l]}
          onClick={() => setLang(l)}
        >
          <span
            aria-hidden="true"
            className="inline-flex size-5 items-center justify-center rounded-full bg-current/15 text-[0.65rem] font-semibold"
          >
            {l}
          </span>
          <Text as="span" size="sm" className="hidden sm:inline">
            {LANG_LABELS[l]}
          </Text>
        </Button>
      ))}
    </Row>
  );
}
