"use client";

import ExpertS from "@/services/business/ExpertS";
import JobS from "@/services/business/JobS";
import type { Report } from "@/services/business/JobS";
import ReportS from "@/services/business/ReportS";
import UISessionS from "@/services/business/UISessionS";
import AuthS from "@/services/tech/AuthS";
import EnvS from "@/services/tech/EnvS";
import I18nS from "@/services/tech/I18nS";
import RoutingS from "@/services/tech/RoutingS";
import { Col } from "@/ui/base/Col";
import { Markdown } from "@/ui/base/Markdown";
import { Row } from "@/ui/base/Row";
import { Select } from "@/ui/base/Select";
import { Text } from "@/ui/base/Text";
import { Textarea } from "@/ui/base/Textarea";
import { Thumbnail } from "@/ui/base/Thumbnail";
import { Badge } from "@/ui/base/badge";
import { Button, buttonVariants } from "@/ui/base/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/ui/base/card";
import { AlertCircle, CheckCircle, Clock, Download, Loader2 } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useRef, useState } from "react";

// ============================================================================
// Private
// ============================================================================

type VisualState =
  | "uploading"
  | "processing"
  | "awaiting_customer_input"
  | "expert_review"
  | "complete"
  | "failed";

function deriveVisualState(report: Report | undefined): VisualState {
  if (report?.status === "failed") return "failed";
  if (report?.status === "complete") return "complete";
  if (report?.status === "expert_review") return "expert_review";
  if (report?.status === "awaiting_customer_input") return "awaiting_customer_input";
  if (report?.status === "processing") return "processing";
  return "uploading";
}

const formatDate = (iso: string) =>
  new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(iso)
  );

// Retries a failed image load with exponential backoff (handles S3 503 SlowDown).
// Uses a ref + direct DOM reset instead of state/key to avoid SSR hydration mismatch.
function RetryImg({ src, alt, className }: { src: string; alt: string; className: string }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const retries = useRef(0);

  const handleError = () => {
    if (retries.current < 3) {
      const delay = 1_000 * 2 ** retries.current; // 1 s, 2 s, 4 s
      retries.current += 1;
      setTimeout(() => {
        const img = imgRef.current;
        if (img) {
          img.src = "";
          img.src = src;
        }
      }, delay);
    }
  };

  // eslint-disable-next-line @next/next/no-img-element
  return <img ref={imgRef} src={src} alt={alt} className={className} onError={handleError} />;
}

function ReportAssessment({ report }: { report: Report }) {
  const t = UISessionS.useT();
  const hasContent =
    (report.photo_urls && report.photo_urls.length > 0) ||
    report.defect_type ||
    report.summary ||
    report.description;
  if (!hasContent) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("expert_review_ai_section")}</CardTitle>
      </CardHeader>
      <CardContent>
        <Col gap="sm">
          {report.photo_urls && report.photo_urls.length > 0 && (
            <div className="grid grid-cols-3 gap-2">
              {report.photo_urls.map((url, i) => {
                const thumbUrl = report.photo_thumb_urls?.[i] ?? url;
                return (
                  <a key={url} href={url} target="_blank" rel="noreferrer">
                    <RetryImg
                      src={thumbUrl}
                      alt=""
                      className="w-full rounded object-cover aspect-square"
                    />
                  </a>
                );
              })}
            </div>
          )}
          {(report.defect_type || report.severity) && (
            <Row gap="sm" align="center">
              {report.defect_type && (
                <Badge variant="secondary">{JobS.defectTypeLabel(t, report.defect_type)}</Badge>
              )}
              {report.severity && (
                <Badge variant="outline">{JobS.severityLabel(t, report.severity)}</Badge>
              )}
            </Row>
          )}
          {report.summary && <Markdown>{report.summary}</Markdown>}
          {report.description && (
            <Text size="sm" color="muted">
              {report.description}
            </Text>
          )}
        </Col>
      </CardContent>
    </Card>
  );
}

function RespondPanel({ report, jobId }: { report: Report; jobId: string }) {
  const t = UISessionS.useT();
  const { lang } = UISessionS.useUISession();
  const { token } = AuthS.useAuth();
  const respond = ReportS.useRespond(jobId, token);
  const { experts } = ExpertS.useExperts(token);
  const [reply, setReply] = useState("");
  const [requestingExpert, setRequestingExpert] = useState(false);
  const [assignedExpertId, setAssignedExpertId] = useState("");
  const [expertRequiredError, setExpertRequiredError] = useState(false);

  const suggestedPrompts = (report.verification_items ?? []).filter(
    (item) => item.kind === "customer_question"
  );

  const formattedPrice = I18nS.formatEurPrice(EnvS.expertReviewPriceEur(), lang);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("report_respond_title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <Col gap="sm">
          {requestingExpert ? (
            <Col gap="xs">
              <Text size="sm" weight="bold" className="text-center">
                {t("report_request_expert_intro", {
                  price: (
                    <Text as="span" size="sm" weight="bold" color="destructive">
                      {formattedPrice}
                    </Text>
                  ),
                })}
              </Text>
              <Text size="xs" color="muted">
                {t("report_request_expert_explanation")}
              </Text>
              <Select
                value={assignedExpertId}
                onChange={(e) => {
                  setAssignedExpertId(e.target.value);
                  if (e.target.value) setExpertRequiredError(false);
                }}
                disabled={respond.isPending}
                data-testid="expert-select"
              >
                <option value="">{t("report_select_expert")}</option>
                {experts.map((expert) => (
                  <option key={expert.id} value={expert.id}>
                    {expert.email}
                  </option>
                ))}
              </Select>
              {expertRequiredError && (
                <Text size="xs" color="destructive">
                  {t("report_expert_required")}
                </Text>
              )}
            </Col>
          ) : (
            <>
              {suggestedPrompts.length > 0 && (
                <Col gap="xs">
                  <Text size="xs" color="muted">
                    {t("report_respond_suggestions_label")}
                  </Text>
                  {suggestedPrompts.map((item) => (
                    <Text key={item.text} size="xs" color="muted">
                      {item.text}
                    </Text>
                  ))}
                </Col>
              )}
              <Textarea
                rows={3}
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder={t("report_respond_placeholder")}
                maxLength={1000}
                disabled={respond.isPending}
              />
            </>
          )}

          <Row gap="sm">
            {requestingExpert ? (
              <Button
                onClick={() => {
                  if (!assignedExpertId) {
                    setExpertRequiredError(true);
                    return;
                  }
                  respond.mutate({ requestExpertReview: true, assignedExpertId });
                }}
                disabled={respond.isPending}
              >
                {respond.isPending ? t("action_uploading") : t("report_request_expert_action")}
              </Button>
            ) : (
              <Button
                onClick={() => respond.mutate({ reply: reply.trim() || null })}
                disabled={respond.isPending}
              >
                {respond.isPending
                  ? t("action_uploading")
                  : reply.trim()
                    ? t("report_respond_send")
                    : t("report_respond_accept")}
              </Button>
            )}
          </Row>

          {experts.length > 0 && (
            <Row gap="sm" align="center">
              <input
                type="checkbox"
                id="request-expert"
                checked={requestingExpert}
                onChange={(e) => {
                  setRequestingExpert(e.target.checked);
                  if (!e.target.checked) {
                    setAssignedExpertId("");
                    setExpertRequiredError(false);
                  }
                }}
                // Only AI assessment is available for now — expert review request is disabled.
                disabled
                className="size-4 accent-primary"
              />
              <label htmlFor="request-expert" className="cursor-pointer">
                <Text size="sm" weight="medium">
                  {t("report_request_expert")}
                </Text>
              </label>
            </Row>
          )}
          {experts.length > 0 && !requestingExpert && (
            <Text size="xs" color="muted">
              {t("report_request_expert_hint")}
            </Text>
          )}
        </Col>
      </CardContent>
    </Card>
  );
}

function ReportFinalDocument({ report }: { report: Report }) {
  const t = UISessionS.useT();

  if (!report.report_url) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("expert_review_report")}</CardTitle>
      </CardHeader>
      <CardContent>
        <Row gap="sm">
          <a
            href={report.report_url}
            target="_blank"
            rel="noopener noreferrer"
            className={buttonVariants({ variant: "default" })}
          >
            {t("expert_review_report_open")}
          </a>
          <a
            href={report.report_url}
            target="_blank"
            rel="noopener noreferrer"
            download={JobS.reportFilename(t, report)}
            className={buttonVariants({ variant: "outline" })}
          >
            <Download className="size-4" />
            {t("report_download")}
          </a>
        </Row>
      </CardContent>
    </Card>
  );
}

// ============================================================================
// Public
// ============================================================================

// Shared report body for both the customer report page and the expert review
// page. Role-specific content (e.g. the expert's editable assessment form, or
// a read-only expert note) is injected via `extra`, rendered between the
// "with expert" state and the completion banner.
export function ReportView({
  report,
  jobId,
  extra,
  canRespond = true,
}: {
  report: Report | undefined;
  jobId: string;
  extra?: ReactNode;
  canRespond?: boolean;
}) {
  const t = UISessionS.useT();
  const visualState = deriveVisualState(report);

  return (
    <Col gap="md" data-testid="report-view">
      <Row gap="sm" align="center">
        <Thumbnail src={report?.thumbnail_url ?? undefined} alt="Report photo" size="lg" />
        <Col gap="xs" grow>
          <Text size="sm" weight="medium">
            {report?.name ?? report?.description ?? t("report_processing")}
          </Text>
          <Text size="xs" color="muted" mono data-testid="job-id">
            {jobId}
          </Text>
        </Col>
      </Row>

      {report && (
        <Col gap="xs" className="border rounded-lg px-4 py-3 bg-muted/30">
          <Row justify="between" align="center">
            <Text size="xs" color="muted">
              {t("report_submitted_label")}
            </Text>
            <Text size="xs">{formatDate(report.created_at)}</Text>
          </Row>
          <Row justify="between" align="center">
            <Text size="xs" color="muted">
              {t("report_status_label")}
            </Text>
            <Badge variant="outline">{t(`report_status_${report.status}`)}</Badge>
          </Row>
          {report.request_expert_review && (
            <Row justify="between" align="center">
              <Text size="xs" color="muted">
                {t("report_expert_label")}
              </Text>
              <Text size="xs">{report.assigned_expert_email ?? "—"}</Text>
            </Row>
          )}
          {report.defect_type && (
            <Row justify="between" align="center">
              <Text size="xs" color="muted">
                {t("report_defect_type_label")}
              </Text>
              <Text size="xs">{JobS.defectTypeLabel(t, report.defect_type)}</Text>
            </Row>
          )}
        </Col>
      )}

      {visualState === "uploading" && (
        <Col gap="sm" align="center" className="py-8 text-center">
          <Loader2 className="size-8 animate-spin text-primary" />
          <Text size="sm" color="muted">
            {t("report_uploading")}
          </Text>
        </Col>
      )}

      {visualState === "processing" && (
        <Col gap="sm" align="center" className="py-8 text-center">
          <Loader2 className="size-8 animate-spin text-primary" />
          <Text size="sm" color="muted">
            {t("report_processing")}
          </Text>
        </Col>
      )}

      {report && <ReportAssessment report={report} />}

      {visualState === "awaiting_customer_input" &&
        (canRespond ? (
          report && <RespondPanel report={report} jobId={jobId} />
        ) : (
          <Col gap="sm" align="center" className="py-4 text-center">
            <Clock className="size-8 text-warning" />
            <Text size="sm" color="muted">
              {t("report_awaiting_customer_input")}
            </Text>
          </Col>
        ))}

      {visualState === "expert_review" && (
        <Col gap="sm" align="center" className="py-4 text-center">
          <Clock className="size-8 text-warning" />
          <Text size="sm" weight="medium">
            {t("report_expert_review")}
          </Text>
          <Text size="xs" color="muted">
            {t("report_expert_review_time")}
          </Text>
        </Col>
      )}

      {extra}

      {visualState === "complete" && (
        <Row gap="sm" align="center">
          <CheckCircle className="size-5 text-success" />
          <Text size="sm" weight="medium">
            {t("report_complete")}
          </Text>
          {report?.severity && (
            <Badge variant="secondary">{JobS.severityLabel(t, report.severity)}</Badge>
          )}
        </Row>
      )}

      {report && <ReportFinalDocument report={report} />}

      {visualState === "failed" && (
        <Col gap="md" align="center" className="py-8 text-center">
          <AlertCircle className="size-8 text-destructive" />
          <Text size="sm" color="destructive">
            {t("report_failed")}
          </Text>
          <Link
            href={RoutingS.paths.newReport({
              name: report?.name,
              description: report?.description,
            })}
            className={buttonVariants({ variant: "outline" })}
          >
            {t("report_start_over")}
          </Link>
        </Col>
      )}
    </Col>
  );
}
