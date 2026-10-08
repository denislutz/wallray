import { LinkButton } from "@/ui/base/LinkButton";
import { Row } from "@/ui/base/Row";
import type { LandingCopy } from "./landing/types";

// ============================================================================
// Private
// ============================================================================

const NAV_ITEMS = [
  { key: "what", href: "#what" },
  { key: "why", href: "#why" },
  { key: "how", href: "#how" },
  { key: "who", href: "#who" },
  { key: "howMuch", href: "#how-much" },
] as const satisfies { key: keyof LandingCopy["nav"]; href: string }[];

// ============================================================================
// Public
// ============================================================================

export function LandingNav({ nav }: { nav: LandingCopy["nav"] }) {
  return (
    <nav
      aria-label="Section navigation"
      className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur"
    >
      <Row gap="sm" px="md" py="sm" justify="evenly" wrap className="mx-auto max-w-2xl">
        {NAV_ITEMS.map(({ key, href }) => (
          <LinkButton key={key} href={href} variant="ghost" size="sm">
            {nav[key]}
          </LinkButton>
        ))}
      </Row>
    </nav>
  );
}
