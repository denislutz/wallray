"use client";

import { Text } from "@/ui/base/Text";
import Link from "next/link";
import { usePathname } from "next/navigation";

// ============================================================================
// Public
// ============================================================================

export function MarketingLegalLink() {
  const pathname = usePathname();
  const isGreek = pathname.startsWith("/el");

  return (
    <Link href={isGreek ? "/el/legal" : "/legal"}>
      <Text size="xs" color="muted">
        {isGreek ? "Απόρρητο & Αποποίηση Ευθύνης" : "Privacy & Disclaimer"}
      </Text>
    </Link>
  );
}
