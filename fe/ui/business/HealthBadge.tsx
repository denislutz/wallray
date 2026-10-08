"use client";

import HealthS from "@/services/business/HealthS";
import UISessionS from "@/services/business/UISessionS";
import type { DotVariant } from "@/ui/base/StatusDot";
import { StatusDot } from "@/ui/base/StatusDot";

// ============================================================================
// Private
// ============================================================================

const variantMap: Record<"ok" | "degraded" | "error", DotVariant> = {
  ok: "ok",
  degraded: "warning",
  error: "error",
};

type T = ReturnType<typeof UISessionS.useT>;

const buildLabel = (t: T, status: "ok" | "degraded" | "error", latencyMs?: number): string => {
  if (status === "ok") {
    return latencyMs !== undefined
      ? t("health_ok_latency", { latency: latencyMs.toString() })
      : t("health_ok");
  }
  if (status === "degraded") return t("health_degraded");
  return t("health_error");
};

// ============================================================================
// Component
// ============================================================================

const HealthBadge = () => {
  const health = HealthS.useHealth();
  const t = UISessionS.useT();

  if (!health) return <StatusDot variant="idle" label={t("health_checking")} showLabel={false} />;

  return (
    <StatusDot
      variant={variantMap[health.status]}
      label={buildLabel(t, health.status, health.latencyMs)}
      showLabel={false}
    />
  );
};

export default HealthBadge;
