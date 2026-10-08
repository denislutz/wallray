"use client";

import UISessionS from "@/services/business/UISessionS";
import { Text } from "@/ui/base/Text";

// ============================================================================
// Component
// ============================================================================

const LangBadge = () => {
  const { lang } = UISessionS.useUISession();

  return (
    <Text size="xs" className="text-muted-foreground" mono>
      {lang}
    </Text>
  );
};

export default LangBadge;
