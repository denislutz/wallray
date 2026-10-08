"use client";

import AccountS from "@/services/business/AccountS";
import UISessionS from "@/services/business/UISessionS";
import AuthS from "@/services/tech/AuthS";
import { Text } from "@/ui/base/Text";

// ============================================================================
// Component
// ============================================================================

const UserBadge = () => {
  const { token } = AuthS.useAuth();
  const { me } = AccountS.useMe(token);
  const t = UISessionS.useT();

  if (!me) return null;

  const roleLabel = t(`role_${me.role}` as Parameters<typeof t>[0]);

  return (
    <Text size="xs" className="text-muted-foreground">
      {me.email} · {roleLabel}
    </Text>
  );
};

export default UserBadge;
