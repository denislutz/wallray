import type { Report } from "@/services/business/JobS";
import HttpS from "@/services/tech/HttpS";
import ReactQueryS from "@/services/tech/ReactQueryS";

// ============================================================================
// Private
// ============================================================================

const getAdminJob = (jobId: string, token: string): Promise<Report> =>
  HttpS.get<Report>(`/admin/jobs/${jobId}`, token);

const getReviews = (token: string): Promise<Report[]> =>
  HttpS.get<Report[]>("/admin/reviews", token);

const getAllReviews = (token: string): Promise<Report[]> =>
  HttpS.get<Report[]>("/admin/reviews/history", token);

const approve = (
  jobId: string,
  expertNotes: string | null,
  token: string
): Promise<{ ok: boolean }> =>
  HttpS.post<{ ok: boolean }>(`/admin/jobs/${jobId}/approve`, { expert_notes: expertNotes }, token);

// ============================================================================
// Public service API
// ============================================================================

const useJob = (jobId: string, token: string | null): { job: Report | undefined } => {
  const { data } = ReactQueryS.useQuery({
    queryKey: ["adminJob", jobId],
    queryFn: () => getAdminJob(jobId, token ?? ""),
    enabled: !!token,
    refetchInterval: (query) => (query.state.data?.status === "processing" ? 10_000 : false),
  });
  return { job: data };
};

const useReviews = (token: string | null): { reviews: Report[] } => {
  const { data } = ReactQueryS.useQuery({
    queryKey: ["adminReviews"],
    queryFn: () => getReviews(token ?? ""),
    enabled: !!token,
    refetchInterval: 10_000,
  });
  return { reviews: data ?? [] };
};

const useAllReviews = (token: string | null): { reviews: Report[] } => {
  const { data } = ReactQueryS.useQuery({
    queryKey: ["adminAllReviews"],
    queryFn: () => getAllReviews(token ?? ""),
    enabled: !!token,
    refetchInterval: 10_000,
  });
  return { reviews: data ?? [] };
};

const useApprove = (token: string | null) => {
  const queryClient = ReactQueryS.useQueryClient();
  return ReactQueryS.useMutation({
    mutationFn: ({ jobId, expertNotes }: { jobId: string; expertNotes: string | null }) =>
      approve(jobId, expertNotes, token ?? ""),
    onSuccess: (_data, { jobId }) => {
      queryClient.invalidateQueries({ queryKey: ["adminJob", jobId] });
      queryClient.invalidateQueries({ queryKey: ["adminReviews"] });
    },
  });
};

const AdminS = { useJob, useReviews, useAllReviews, useApprove };
export default AdminS;
