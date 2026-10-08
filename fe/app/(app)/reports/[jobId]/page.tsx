import { ReportPage } from "@/ui/business/ReportPage";

export default async function ReportRoute({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  return <ReportPage jobId={jobId} />;
}
