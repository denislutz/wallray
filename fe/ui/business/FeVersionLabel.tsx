"use client";

import UISessionS from "@/services/business/UISessionS";
import BuildTimeS from "@/services/tech/BuildTimeS";
import { Text } from "@/ui/base/Text";

// ============================================================================
// Private
// ============================================================================

const fmtVersion = (iso: string): string => {
  const d = new Date(iso);
  const month = d.toLocaleString("en", { month: "short" });
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${month} ${d.getDate()} · ${hh}:${mm}`;
};

// ============================================================================
// Component
// ============================================================================

const FeVersionLabel = () => {
  const t = UISessionS.useT();
  return (
    <Text size="xs" className="text-muted-foreground">
      {t("deploy_version", { time: fmtVersion(BuildTimeS.time) })}
    </Text>
  );
};

export default FeVersionLabel;
