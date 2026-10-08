"use client";

import AdminS from "@/services/business/AdminS";
import JobS from "@/services/business/JobS";
import type { Report } from "@/services/business/JobS";
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
import { ClipboardList } from "lucide-react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

// ============================================================================
// Private
// ============================================================================

const STATUS_VARIANT: Record<string, "default" | "secondary" | "outline" | "destructive"> = {
  expert_review: "default",
  complete: "secondary",
  processing: "outline",
  pending: "outline",
  failed: "destructive",
};

function ReviewCard({ job, onClick }: { job: Report; onClick: () => void }) {
  const t = UISessionS.useT();
  const statusKey = `report_status_${job.status}` as Parameters<typeof t>[0];
  return (
    <Button
      variant="ghost"
      fill
      onClick={onClick}
      className="h-auto lg:h-auto justify-start gap-3 rounded-none py-3"
    >
      <Thumbnail
        src={job.thumbnail_url ?? undefined}
        alt={job.name ?? job.description ?? "Review"}
        size="md"
      />
      <Col gap="none" grow>
        <Text size="sm" weight="medium" truncate>
          {job.name ?? job.description ?? t("report_processing")}
        </Text>
        <Text size="xs" color="muted">
          {new Date(job.created_at).toLocaleDateString()}
          {job.defect_type ? ` · ${JobS.defectTypeLabel(t, job.defect_type)}` : ""}
        </Text>
      </Col>
      <Col gap="xs" align="end">
        <Badge variant={STATUS_VARIANT[job.status] ?? "outline"}>{t(statusKey)}</Badge>
        {job.severity && <Badge variant="outline">{JobS.severityLabel(t, job.severity)}</Badge>}
      </Col>
    </Button>
  );
}

// ============================================================================
// Public
// ============================================================================

export function ExpertQueuePage() {
  const { status } = useSession();
  const router = useRouter();
  const { token } = AuthS.useAuth();
  const t = UISessionS.useT();
  const nav = RoutingClientS.useNav();

  useEffect(() => {
    if (status === "unauthenticated") router.replace(RoutingS.paths.signIn());
  }, [status, router]);

  const authToken = status === "authenticated" ? token : null;
  const { reviews } = AdminS.useAllReviews(authToken);

  if (status === "loading" || status === "unauthenticated") return null;

  return (
    <Col gap="none" className="min-h-full">
      <Row px="md" py="sm" className="border-b">
        <Text as="h1" size="base" weight="semibold">
          {t("expert_review_queue")}
        </Text>
      </Row>

      {reviews.length === 0 ? (
        <Col align="center" justify="center" gap="md" className="flex-1 py-20 text-center">
          <ClipboardList className="size-12 text-muted-foreground" />
          <Text size="sm" color="muted">
            {t("expert_review_queue_empty")}
          </Text>
        </Col>
      ) : (
        <Col gap="none" divided px="md">
          {reviews.map((review) => (
            <ReviewCard
              key={review.id}
              job={review}
              onClick={() => nav.toExpertReview(review.id)}
            />
          ))}
        </Col>
      )}
    </Col>
  );
}
