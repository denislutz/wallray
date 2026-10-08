"use client";

import ReportS from "@/services/business/ReportS";
import type { Report } from "@/services/business/ReportS";
import UISessionS from "@/services/business/UISessionS";
import AuthS from "@/services/tech/AuthS";
import RoutingClientS from "@/services/tech/RoutingClientS";
import RoutingS from "@/services/tech/RoutingS";
import { Col } from "@/ui/base/Col";
import { Row } from "@/ui/base/Row";
import { Text } from "@/ui/base/Text";
import { Thumbnail } from "@/ui/base/Thumbnail";
import { Badge } from "@/ui/base/badge";
import { Button } from "@/ui/base/button";
import { ClipboardList, Plus } from "lucide-react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

// ============================================================================
// Private
// ============================================================================

const STATUS_VARIANT: Record<
  Report["status"],
  "default" | "secondary" | "outline" | "destructive"
> = {
  pending: "outline",
  processing: "secondary",
  awaiting_customer_input: "secondary",
  expert_review: "secondary",
  complete: "default",
  failed: "destructive",
};

function JobCard({ job, onClick }: { job: Report; onClick: () => void }) {
  const t = UISessionS.useT();
  return (
    <Button
      variant="ghost"
      fill
      onClick={onClick}
      className="h-auto lg:h-auto justify-start gap-3 rounded-none py-3"
    >
      <Thumbnail src={job.thumbnail_url ?? undefined} alt={job.description ?? "Report"} size="md" />
      <Col gap="none" grow>
        <Text size="sm" weight="medium" truncate>
          {job.name ?? job.description ?? t("report_processing")}
        </Text>
        <Text size="xs" color="muted">
          {new Date(job.created_at).toLocaleDateString()}
          {job.defect_type ? ` · ${ReportS.defectTypeLabel(t, job.defect_type)}` : ""}
        </Text>
      </Col>
      <Badge variant={STATUS_VARIANT[job.status]}>{job.status.replace("_", " ")}</Badge>
    </Button>
  );
}

function EmptyState({ onNew }: { onNew: () => void }) {
  const t = UISessionS.useT();
  return (
    <Col align="center" justify="center" gap="md" className="flex-1 py-20 text-center">
      <ClipboardList className="size-12 text-muted-foreground" />
      <Col gap="xs" align="center">
        <Text as="h2" size="base" weight="semibold">
          {t("report_empty_title")}
        </Text>
        <Text size="sm" color="muted">
          {t("report_empty_body")}
        </Text>
      </Col>
      <Button onClick={onNew}>
        <Plus className="size-4" />
        {t("report_new")}
      </Button>
    </Col>
  );
}

// ============================================================================
// Public
// ============================================================================

export function ReportsPage() {
  const { status } = useSession();
  const router = useRouter();
  const { token } = AuthS.useAuth();
  const t = UISessionS.useT();
  const nav = RoutingClientS.useNav();

  useEffect(() => {
    if (status === "unauthenticated") router.replace(RoutingS.paths.signIn());
  }, [status, router]);

  const { reports, isLoading } = ReportS.useReports(status === "authenticated" ? token : null);

  if (status === "loading" || status === "unauthenticated") return null;

  return (
    <Col gap="none" className="min-h-full" data-testid="reports-page">
      <Row justify="between" align="center" px="md" py="sm" className="border-b">
        <Text as="h1" size="base" weight="semibold">
          {t("nav_reports")}
        </Text>
        <Button size="sm" onClick={() => nav.toNewReport()}>
          <Plus className="size-4" />
          {t("report_new")}
        </Button>
      </Row>

      {isLoading ? (
        <Col align="center" justify="center" className="flex-1 py-20">
          <Text size="sm" color="muted">
            …
          </Text>
        </Col>
      ) : !reports || reports.length === 0 ? (
        <EmptyState onNew={() => nav.toNewReport()} />
      ) : (
        <Col gap="none" divided px="md">
          {reports.map((report) => (
            <JobCard key={report.id} job={report} onClick={() => nav.toReportDetail(report.id)} />
          ))}
        </Col>
      )}
    </Col>
  );
}
