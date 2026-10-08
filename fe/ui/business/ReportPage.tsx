"use client";

import ReportS from "@/services/business/ReportS";
import UISessionS from "@/services/business/UISessionS";
import AuthS from "@/services/tech/AuthS";
import RoutingS from "@/services/tech/RoutingS";
import { Col } from "@/ui/base/Col";
import { Text } from "@/ui/base/Text";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ReportView } from "./ReportView";

// ============================================================================
// Public
// ============================================================================

export function ReportPage({ jobId }: { jobId: string }) {
  const { status } = useSession();
  const router = useRouter();
  const { token } = AuthS.useAuth();
  const t = UISessionS.useT();

  useEffect(() => {
    if (status === "unauthenticated") router.replace(RoutingS.paths.signIn());
  }, [status, router]);

  const authToken = status === "authenticated" ? token : null;
  const { report } = ReportS.useReport(jobId, authToken);

  if (status === "loading" || status === "unauthenticated") return null;

  return (
    <Col gap="md" px="md" py="md">
      <ReportView
        report={report}
        jobId={jobId}
        extra={
          report?.expert_notes ? (
            <Col gap="xs">
              <Text size="xs" color="muted" weight="medium">
                {t("report_expert_notes_label")}
              </Text>
              <Text size="sm">{report.expert_notes}</Text>
            </Col>
          ) : undefined
        }
      />
    </Col>
  );
}
