"use client";

import HealthS from "@/services/business/HealthS";
import UISessionS from "@/services/business/UISessionS";
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

const BeVersionLabel = () => {
  const health = HealthS.useHealth();
  const t = UISessionS.useT();

  if (!health?.version) return null;

  return (
    <Text size="xs" className="text-muted-foreground">
      {t("api_version", { time: fmtVersion(health.version) })}
    </Text>
  );
};

export default BeVersionLabel;
