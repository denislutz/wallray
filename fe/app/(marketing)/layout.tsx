import { Logo } from "@/ui/base/Logo";
import { Row } from "@/ui/base/Row";
import { Text } from "@/ui/base/Text";
import { MarketingLangSwitch } from "@/ui/business/MarketingLangSwitch";
import { MarketingLegalLink } from "@/ui/business/MarketingLegalLink";
import Link from "next/link";
import type { ReactNode } from "react";

export default function MarketingLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <>
      <Row as="header" px="md" py="sm" justify="between" align="center" className="border-b">
        <Link href="/">
          <Row gap="sm" align="center">
            <Logo size={28} />
            <Text size="sm" weight="semibold" tracking="tight">
              WallRay
            </Text>
          </Row>
        </Link>
        <MarketingLangSwitch />
      </Row>
      <main>{children}</main>
      <Row as="footer" px="md" py="sm" justify="center" className="border-t">
        <MarketingLegalLink />
      </Row>
    </>
  );
}
