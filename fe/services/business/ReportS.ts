import JobS from "@/services/business/JobS";
import type { Report, RespondBody } from "@/services/business/JobS";
import ReactQueryS from "@/services/tech/ReactQueryS";

export { FreeTierError } from "@/services/business/JobS";
export type { Report } from "@/services/business/JobS";

// ============================================================================
// Public service API
// ============================================================================

const useReports = (
  token: string | null
): { reports: Report[] | undefined; isLoading: boolean } => {
  const { data, isLoading } = ReactQueryS.useQuery({
    queryKey: ["reports"],
    queryFn: () => JobS.listReports(token ?? ""),
    enabled: !!token,
  });
  return { reports: data, isLoading };
};

const useReport = (id: string, token: string | null): { report: Report | undefined } => {
  const { data: report } = ReactQueryS.useQuery({
    queryKey: ["report", id],
    queryFn: () => JobS.getReport(id, token ?? ""),
    enabled: !!token,
    refetchInterval: (query) => {
      const d = query.state.data;
      const settled =
        !d ||
        d.status === "complete" ||
        d.status === "failed" ||
        d.status === "awaiting_customer_input";
      return settled ? false : 10_000;
    },
  });
  return { report };
};

const useRespond = (id: string, token: string | null) => {
  const queryClient = ReactQueryS.useQueryClient();
  return ReactQueryS.useMutation({
    mutationFn: (body: RespondBody) => JobS.respond(id, body, token ?? ""),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["report", id] });
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
  });
};

const useUpload = (token: string | null) => {
  const queryClient = ReactQueryS.useQueryClient();
  return ReactQueryS.useMutation({
    mutationFn: ({
      files,
      description,
      name,
      language,
    }: {
      files: File[];
      description: string;
      name?: string | null;
      language?: string;
    }) => JobS.upload(files, description, token ?? "", name, language),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
  });
};

const ReportS = {
  useReports,
  useReport,
  useUpload,
  useRespond,
  defectTypeLabel: JobS.defectTypeLabel,
};
export default ReportS;
