"use client";

import ReportS, { FreeTierError } from "@/services/business/ReportS";
import UISessionS from "@/services/business/UISessionS";
import AuthS from "@/services/tech/AuthS";
import RoutingClientS from "@/services/tech/RoutingClientS";
import RoutingS from "@/services/tech/RoutingS";
import ToastS from "@/services/tech/ToastS";
import { Col } from "@/ui/base/Col";
import { Input } from "@/ui/base/Input";
import { Row } from "@/ui/base/Row";
import { Select } from "@/ui/base/Select";
import { Text } from "@/ui/base/Text";
import { Textarea } from "@/ui/base/Textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/ui/base/card";
import { useSession } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { PhotoUpload } from "./PhotoUpload";

// ============================================================================
// Public
// ============================================================================

export function NewReportPage() {
  const { status } = useSession();
  const router = useRouter();
  const { token } = AuthS.useAuth();
  const t = UISessionS.useT();
  const { lang } = UISessionS.useUISession();
  const nav = RoutingClientS.useNav();
  const searchParams = useSearchParams();

  // Restarting a failed report (ReportView.tsx's "Start over" link) prefills these from the
  // query string instead of losing what the customer already typed.
  const [name, setName] = useState(() => searchParams.get("name") ?? "");
  const [description, setDescription] = useState(() => searchParams.get("description") ?? "");
  const [language, setLanguage] = useState(() => lang.toLowerCase());
  const [freeTierLimit, setFreeTierLimit] = useState<number | null>(null);
  const languageTouched = useRef(false);

  useEffect(() => {
    if (status === "unauthenticated") router.replace(RoutingS.paths.signIn());
  }, [status, router]);

  // Default the report language to the user's active UI language, but stop
  // following it once they've explicitly picked one themselves.
  useEffect(() => {
    if (!languageTouched.current) setLanguage(lang.toLowerCase());
  }, [lang]);

  const upload = ReportS.useUpload(status === "authenticated" ? token : null);

  if (status === "loading" || status === "unauthenticated") return null;

  return (
    <Col gap="md" px="md" py="md" data-testid="new-report-page">
      <Text as="h1" size="base" weight="semibold">
        {t("report_new")}
      </Text>

      <Card>
        <CardHeader>
          <CardTitle>{t("report_name_label")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("report_name_hint")}
            maxLength={100}
            disabled={upload.isPending}
            data-testid="report-name-input"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("report_description_label")}</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t("report_description_hint")}
            maxLength={500}
            disabled={upload.isPending}
          />
        </CardContent>
      </Card>

      {freeTierLimit !== null && (
        <Text size="sm" color="destructive">
          {t("report_free_tier_limit", { limit: String(freeTierLimit) })}
        </Text>
      )}

      <Row justify="center">
        <PhotoUpload
          onSubmit={(files) => {
            upload.mutate(
              {
                files,
                description,
                name: name || null,
                language,
              },
              {
                onSuccess: (res) => {
                  ToastS.info(t("report_submitted"));
                  nav.toReportDetail(res.id);
                },
                onError: (err) => {
                  if (err instanceof FreeTierError) {
                    setFreeTierLimit(err.limit);
                  } else {
                    ToastS.error(t("report_failed"));
                  }
                },
              }
            );
          }}
          isSubmitting={upload.isPending}
          beforeSubmit={
            <Select
              size="sm"
              value={language}
              onChange={(e) => {
                languageTouched.current = true;
                setLanguage(e.target.value);
              }}
              disabled={upload.isPending}
              aria-label={t("report_language_label")}
            >
              <option value="en">{t("language_en")}</option>
              <option value="de">{t("language_de")}</option>
              <option value="ru">{t("language_ru")}</option>
              <option value="el">{t("language_el")}</option>
            </Select>
          }
        />
      </Row>
    </Col>
  );
}
