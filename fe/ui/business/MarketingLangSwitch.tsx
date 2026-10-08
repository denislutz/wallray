"use client";

import { cn } from "@/services/tech/TailwindS";
import { Row } from "@/ui/base/Row";
import { buttonVariants } from "@/ui/base/buttonVariants";
import Link from "next/link";
import { usePathname } from "next/navigation";

// ============================================================================
// Private
// ============================================================================

const LANGS = [
  { label: "EN", href: "/" },
  { label: "DE", href: "/de" },
  { label: "RU", href: "/ru" },
  { label: "EL", href: "/el" },
] as const;

// ============================================================================
// Public
// ============================================================================

export function MarketingLangSwitch() {
  const pathname = usePathname();

  return (
    <Row gap="xs">
      {LANGS.map(({ label, href }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(buttonVariants({ size: "sm", variant: active ? "default" : "outline" }))}
          >
            {label}
          </Link>
        );
      })}
    </Row>
  );
}
