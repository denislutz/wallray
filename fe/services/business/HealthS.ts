import HttpS from "@/services/tech/HttpS";
import ReactQueryS from "@/services/tech/ReactQueryS";
import type { HealthStatus } from "@/types/api";

// ============================================================================
// Private
// ============================================================================

const normalize = (raw: string): HealthStatus["status"] =>
  raw === "ok" || raw === "degraded" ? raw : "error";

const fetch = async (): Promise<HealthStatus> => {
  const t0 = performance.now();
  const data = await HttpS.get<{ status: string; version?: string }>("/health");
  return {
    status: normalize(data.status),
    latencyMs: Math.round(performance.now() - t0),
    version: data.version,
  };
};

// ============================================================================
// Public service API
// ============================================================================

const useHealth = (): HealthStatus | null => {
  const { data, isError } = ReactQueryS.useQuery({
    queryKey: ["health"],
    queryFn: fetch,
    refetchInterval: 30_000,
  });

  if (isError) return { status: "error" };
  return data ?? null;
};

const HealthS = { useHealth };
export default HealthS;
