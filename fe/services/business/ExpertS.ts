import HttpS from "@/services/tech/HttpS";
import ReactQueryS from "@/services/tech/ReactQueryS";

// ============================================================================
// Private
// ============================================================================

export interface Expert {
  id: string;
  email: string;
}

const getExperts = (token: string): Promise<Expert[]> => HttpS.get<Expert[]>("/experts", token);

// ============================================================================
// Public service API
// ============================================================================

const useExperts = (token: string | null): { experts: Expert[] } => {
  const { data } = ReactQueryS.useQuery({
    queryKey: ["experts"],
    queryFn: () => getExperts(token ?? ""),
    enabled: !!token,
  });
  return { experts: data ?? [] };
};

const ExpertS = { useExperts };
export default ExpertS;
