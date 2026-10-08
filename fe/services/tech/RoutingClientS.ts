import { useRouter } from "next/navigation";

import RoutingS from "./RoutingS";

// ============================================================================
// Public service API
// ============================================================================

const useNav = () => {
  const router = useRouter();
  return {
    toReports: () => router.push(RoutingS.paths.reports()),
    toNewReport: (prefill?: { name?: string | null; description?: string | null }) =>
      router.push(RoutingS.paths.newReport(prefill)),
    toReportDetail: (jobId: string) => router.push(RoutingS.paths.reportDetail(jobId)),
    toAccount: () => router.push(RoutingS.paths.account()),
    toExpertReviews: () => router.push(RoutingS.paths.expertReviews()),
    toExpertReview: (jobId: string) => router.push(RoutingS.paths.expertReview(jobId)),
    toSignIn: () => router.push(RoutingS.paths.signIn()),
    back: () => router.back(),
  };
};

const RoutingClientS = { useNav };
export default RoutingClientS;
