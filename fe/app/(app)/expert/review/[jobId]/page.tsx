import { ExpertReviewPage } from "@/ui/business/ExpertReviewPage";

export default async function ExpertReviewRoute({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <ExpertReviewPage jobId={jobId} />;
}
