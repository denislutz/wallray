"use client";

import AccountS from "@/services/business/AccountS";
import UISessionS from "@/services/business/UISessionS";
import AuthS from "@/services/tech/AuthS";
import RoutingS from "@/services/tech/RoutingS";
import { Col } from "@/ui/base/Col";
import { Row } from "@/ui/base/Row";
import { Text } from "@/ui/base/Text";
import { Button } from "@/ui/base/button";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LangSwitcher } from "./LangSwitcher";

// ============================================================================
// Public
// ============================================================================

export function AccountPage() {
  const { status } = useSession();
  const router = useRouter();
  const { user, token, signOut } = AuthS.useAuth();
  const t = UISessionS.useT();
  const { me } = AccountS.useMe(token);

  useEffect(() => {
    if (status === "unauthenticated") router.replace(RoutingS.paths.signIn());
  }, [status, router]);

  if (status === "loading" || status === "unauthenticated") return null;

  return (
    <Col gap="none" className="min-h-full">
      <Row px="md" py="sm" className="border-b">
        <Text as="h1" size="base" weight="semibold">
          {t("nav_account")}
        </Text>
      </Row>

      <Col gap="none" divided px="md">
        <Row justify="between" align="center" py="sm">
          <Text size="sm" color="muted">
            {t("account_email")}
          </Text>
          <Text size="sm">{user?.email ?? "—"}</Text>
        </Row>

        <Row justify="between" align="center" py="sm">
          <Text size="sm" color="muted">
            {t("account_role")}
          </Text>
          <Text size="sm">{me ? t(`role_${me.role}` as Parameters<typeof t>[0]) : "—"}</Text>
        </Row>

        <Row justify="between" align="center" py="sm">
          <Text size="sm" color="muted">
            {t("account_language")}
          </Text>
          <LangSwitcher />
        </Row>
      </Col>

      <Col px="md" py="md">
        <Button variant="outline" onClick={signOut}>
          {t("auth_sign_out")}
        </Button>
      </Col>
    </Col>
  );
}
