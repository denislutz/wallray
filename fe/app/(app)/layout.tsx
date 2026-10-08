import { Col } from "@/ui/base/Col";
import { Logo } from "@/ui/base/Logo";
import { Row } from "@/ui/base/Row";
import { Text } from "@/ui/base/Text";
import BeVersionLabel from "@/ui/business/BeVersionLabel";
import { BottomNav } from "@/ui/business/BottomNav";
import FeVersionLabel from "@/ui/business/FeVersionLabel";
import HealthBadge from "@/ui/business/HealthBadge";
import LangBadge from "@/ui/business/LangBadge";
import UserBadge from "@/ui/business/UserBadge";
import Link from "next/link";
import type { ReactNode } from "react";
import { Providers } from "./providers";

export default function AppLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <Providers>
      <Row as="header" px="md" py="sm" justify="between" align="center" className="border-b">
        <Link href="/">
          <Row gap="sm" align="center">
            <Logo size={28} />
            <Text size="sm" weight="semibold" tracking="tight" className="hidden sm:inline">
              WallRay
            </Text>
          </Row>
        </Link>
        <Row gap="sm" align="center">
          <UserBadge />
          <LangBadge />
          <Row gap="sm" align="center" className="hidden sm:flex">
            <FeVersionLabel />
            <BeVersionLabel />
          </Row>
          <HealthBadge />
        </Row>
      </Row>
      <Col fill className="pb-20">
        {children}
      </Col>
      <BottomNav />
    </Providers>
  );
}
