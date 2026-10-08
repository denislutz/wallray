"use client";

import AdminS from "@/services/business/AdminS";
import UISessionS from "@/services/business/UISessionS";
import AuthS from "@/services/tech/AuthS";
import RoutingS from "@/services/tech/RoutingS";
import ToastS from "@/services/tech/ToastS";
import { Col } from "@/ui/base/Col";
import { Text } from "@/ui/base/Text";
import { Textarea } from "@/ui/base/Textarea";
import { Button } from "@/ui/base/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/ui/base/card";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ReportView } from "./ReportView";

// ============================================================================
// Public
// ============================================================================

export function ExpertReviewPage({ jobId }: { jobId: string }) {
  const { status } = useSession();
  const router = useRouter();
  const { token } = AuthS.useAuth();
  const t = UISessionS.useT();

  const [expertNotes, setExpertNotes] = useState("");
  const notesInitialized = useRef(false);

  useEffect(() => {
    if (status === "unauthenticated") router.replace(RoutingS.paths.signIn());
  }, [status, router]);

  const authToken = status === "authenticated" ? token : null;
  const { job } = AdminS.useJob(jobId, authToken);
  const approve = AdminS.useApprove(authToken);

  useEffect(() => {
    if (!notesInitialized.current && job?.expert_notes != null) {
      setExpertNotes(job.expert_notes);
      notesInitialized.current = true;
    }
  }, [job?.expert_notes]);

  if (status === "loading" || status === "unauthenticated") return null;

  const canApprove = job?.status === "expert_review";

  const handleSubmit = () => {
    approve.mutate(
      { jobId, expertNotes: expertNotes.trim() || null },
      {
        onSuccess: () => {
          ToastS.info(t("report_submitted"));
        },
        onError: () => {
          ToastS.error(t("report_failed"));
        },
      }
    );
  };

  return (
    <Col gap="md" px="md" py="md" data-testid="expert-review-page">
      <Text as="h1" size="base" weight="semibold">
        {t("expert_review_title")}
      </Text>

      <ReportView
        report={job}
        jobId={jobId}
        canRespond={false}
        extra={
          <>
            <Card>
              <CardHeader>
                <CardTitle>{t("expert_review_notes_label")}</CardTitle>
              </CardHeader>
              <CardContent>
                <Textarea
                  rows={5}
                  value={expertNotes}
                  onChange={(e) => setExpertNotes(e.target.value)}
                  placeholder={t("expert_review_notes_hint")}
                  maxLength={2000}
                  disabled={approve.isPending || !canApprove}
                />
              </CardContent>
            </Card>

            <Button onClick={handleSubmit} disabled={approve.isPending || !canApprove}>
              {approve.isPending ? t("action_uploading") : t("expert_review_submit")}
            </Button>
          </>
        }
      />
    </Col>
  );
}
