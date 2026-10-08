"use client";

import { useState } from "react";

import UISessionS from "@/services/business/UISessionS";
import AuthS from "@/services/tech/AuthS";
import ReactQueryS from "@/services/tech/ReactQueryS";
import RoutingClientS from "@/services/tech/RoutingClientS";
import ToastS from "@/services/tech/ToastS";
import { Checkbox } from "@/ui/base/Checkbox";
import { Col } from "@/ui/base/Col";
import { Input } from "@/ui/base/Input";
import { Text } from "@/ui/base/Text";
import { Turnstile } from "@/ui/base/Turnstile";
import { Button } from "@/ui/base/button";
import { Card, CardContent } from "@/ui/base/card";
import { LangSwitcher } from "@/ui/business/LangSwitcher";

type Step = "email" | "code";

export function SignInPage() {
  const { signInDev } = AuthS.useAuth();
  const t = UISessionS.useT();
  const { lang } = UISessionS.useUISession();
  const nav = RoutingClientS.useNav();
  const legalHref = lang === "EL" ? "/el/legal" : "/legal";

  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);

  const sendCode = ReactQueryS.useMutation({
    mutationFn: () => AuthS.sendOtp(email, termsAccepted, turnstileToken ?? ""),
    onSuccess: () => setStep("code"),
    onError: () => ToastS.error(t("auth_send_code_error")),
  });

  const verify = ReactQueryS.useMutation({
    mutationFn: () => AuthS.signInWithOtp(email, code),
    onSuccess: (result) => {
      if (result?.error) {
        ToastS.error(t("auth_code_error"));
      } else {
        ToastS.success(t("auth_signin_success"));
        nav.toReports();
      }
    },
    onError: () => ToastS.error(t("auth_code_error")),
  });

  const handleSendCode = () => {
    if (!AuthS.isValidEmail(email)) {
      ToastS.error(t("auth_email_invalid"));
      return;
    }
    sendCode.mutate();
  };

  return (
    <Col as="main" fill gap="xl" align="center" justify="center" py="xl" px="md">
      <Col gap="xs" align="center" textAlign="center">
        <Text as="h1" size="2xl" weight="semibold" tracking="tight">
          {t("appName")}
        </Text>
        <Text size="sm" color="muted">
          {t("auth_signin_body")}
        </Text>
        <LangSwitcher />
      </Col>

      <Card width="sm">
        <CardContent>
          {step === "email" ? (
            <Col gap="md">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("auth_email_placeholder")}
                onKeyDown={(e) =>
                  e.key === "Enter" && !sendCode.isPending && email && handleSendCode()
                }
              />
              <label htmlFor="terms-accepted" className="flex items-start gap-2">
                <Checkbox
                  id="terms-accepted"
                  className="mt-0.5"
                  checked={termsAccepted}
                  onChange={(e) => setTermsAccepted(e.target.checked)}
                />
                <Text size="xs" color="muted">
                  {t("auth_terms_prefix")}{" "}
                  <a href={legalHref} target="_blank" rel="noreferrer" className="underline">
                    {t("auth_terms_link")}
                  </a>
                </Text>
              </label>
              <Turnstile onVerify={setTurnstileToken} onExpire={() => setTurnstileToken(null)} />
              <Button
                onClick={handleSendCode}
                disabled={!email || !termsAccepted || !turnstileToken || sendCode.isPending}
                fill
              >
                {sendCode.isPending ? "…" : t("auth_send_code")}
              </Button>
              {signInDev && (
                <Button id="dev-login-btn" variant="outline" onClick={signInDev} fill>
                  Dev login
                </Button>
              )}
            </Col>
          ) : (
            <Col gap="md">
              <Col gap="xs">
                <Text size="base" weight="semibold">
                  {email}
                </Text>
                <Text size="sm" color="muted">
                  {t("auth_code_sent")}
                </Text>
              </Col>
              <Input
                type="text"
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder={t("auth_code_placeholder")}
                maxLength={6}
                onKeyDown={(e) => e.key === "Enter" && !verify.isPending && code && verify.mutate()}
              />
              <Button
                onClick={() => verify.mutate()}
                disabled={code.length !== 6 || verify.isPending}
                fill
              >
                {verify.isPending ? "…" : t("auth_sign_in")}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setStep("email");
                  setCode("");
                  verify.reset();
                }}
                fill
              >
                {t("auth_back")}
              </Button>
            </Col>
          )}
        </CardContent>
      </Card>
    </Col>
  );
}
