import fs from "node:fs";
import path from "node:path";
import { type Browser, type Page, expect } from "@playwright/test";

import { API_BASE_URL, APP_BASE_URL, EXPERT_STORAGE_STATE } from "./env";
import { REPORT_PHOTOS } from "./fixtures/photos";

// ============================================================================
// Private
// ============================================================================

// After submitting a report, wait for the report detail view (data-testid="report-view",
// ReportView.tsx) rather than asserting on the URL — the URL alone doesn't distinguish "still on
// the form because submission failed" from "navigated to a genuinely different page", and a bare
// regex on /reports/:id previously also matched the literal /reports/new form route itself.
//
// On timeout, check for non-empty toast text (e.g. free-tier limit, a failed upload) as a
// diagnostic fallback so a CI failure shows the actual reason instead of a blind timeout. This is
// deliberately NOT a race against getByRole("alert") — Sonner keeps an empty live-announcer region
// with that role mounted at all times, so racing against it resolves immediately on nothing.
const expectReportView = async (page: Page): Promise<void> => {
  try {
    await expect(page.getByTestId("report-view")).toBeVisible({ timeout: 15_000 });
  } catch (err) {
    const toastTexts = (await page.getByRole("alert").allTextContents())
      .map((t) => t.trim())
      .filter(Boolean);
    if (toastTexts.length > 0) {
      throw new Error(
        `Expected the report view, but got a toast instead: ${toastTexts.join(" | ")}`
      );
    }
    throw err;
  }
};

// ============================================================================
// Public service API
// ============================================================================

// Fills the new-report form (fe/ui/business/NewReportPage.tsx), still real UI interaction for
// title/description/file-selection — but submits via Playwright's `request` context (Node's own
// HTTP client, sharing the page's session cookies) instead of clicking the button. Clicking
// triggers the browser's own XHR for this multipart POST, which has been observed to consistently
// fail at the network/HTTP layer in CI against the deployed test environment (HTTP/1.1 downgrade,
// connection reset) — a plain curl multipart upload from the same environment works fine, so the
// server/proxy side is healthy; this is specific to how Chrome negotiates this exact request under
// Playwright's CDP-injected headers.
//
// Expert review is no longer chosen here — it moved to await_customer_answers, see
// requestExpertReview() below.
const submitNewReport = async (
  page: Page,
  opts: { title: string; description?: string }
): Promise<string> => {
  await page.getByTestId("report-name-input").fill(opts.title);
  if (opts.description) {
    await page
      .getByPlaceholder("Describe what you see — location, when you noticed it…")
      .fill(opts.description);
  }
  await page.getByTestId("dropzone-file-input").setInputFiles(REPORT_PHOTOS);
  await expect(page.getByText("Ready").first()).toBeVisible();

  const session = await page.request.get("/api/auth/session");
  const { apiToken } = (await session.json()) as { apiToken: string };

  const form = new FormData();
  form.set("name", opts.title);
  form.set("description", opts.description ?? "");
  form.set("language", "en");
  for (const filePath of REPORT_PHOTOS) {
    const buffer = fs.readFileSync(filePath);
    form.append("files", new Blob([buffer], { type: "image/jpeg" }), path.basename(filePath));
  }

  const response = await page.request.post(`${API_BASE_URL}/upload`, {
    headers: { Authorization: `Bearer ${apiToken}` },
    multipart: form,
  });
  if (!response.ok()) {
    throw new Error(`/upload responded ${response.status()}: ${await response.text()}`);
  }
  const { job_id: jobId } = (await response.json()) as { job_id: string };

  await page.goto(`/reports/${jobId}`);
  await expectReportView(page);
  return jobId;
};

// The fake vision_llm's first assess() call always raises exactly one clarification question
// (be/app/adapters/vision_llm/fake.py) — use this when the caller knows one is guaranteed.
const answerClarification = async (page: Page, reply: string): Promise<void> => {
  await expect(page.getByText("One more thing?")).toBeVisible({ timeout: 40_000 });
  await page.getByPlaceholder("Add anything that might help, or leave this blank.").fill(reply);
  await page.getByRole("button", { name: "Send and refine" }).click();
};

// Drives the "Request expert review" checkbox in RespondPanel (ReportView.tsx) at
// await_customer_answers — checking it swaps the reply textarea for an expert picker. Mutually
// exclusive with answerClarification() on the same round: the customer picks one action, not
// both (see AI_ASSESSMENT_REWORK.md's "expert review request moves to await_customer_answers"
// amendment).
const requestExpertReview = async (page: Page, expertEmail: string): Promise<void> => {
  await expect(page.getByText("One more thing?")).toBeVisible({ timeout: 40_000 });
  await page.getByLabel("Request expert review").check();
  const expertSelect = page.getByTestId("expert-select");
  // Short explicit timeout: if this email isn't in the target env's EXPERT_REVIEW_EMAILS, this
  // option never appears — fail fast with a clear reason instead of silently retrying.
  await expertSelect.selectOption({ label: expertEmail }, { timeout: 10_000 });
  await page.getByRole("button", { name: "Request expert review" }).click();
};

// Real AI may or may not ask a clarifying question — handles both branches, waiting for a
// terminal state either way. Only used by the real-AI project (specs-real-ai/).
const answerClarificationIfAsked = async (page: Page, reply: string): Promise<void> => {
  const clarification = page.getByText("One more thing?");
  const terminal = page.getByText(/Report ready|Something went wrong/);
  await expect(clarification.or(terminal)).toBeVisible({ timeout: 120_000 });
  if (await clarification.isVisible()) {
    await page.getByPlaceholder("Add anything that might help, or leave this blank.").fill(reply);
    await page.getByRole("button", { name: "Send and refine" }).click();
    await expect(terminal).toBeVisible({ timeout: 120_000 });
  }
};

// Opens a second, expert-authenticated browser context and approves the given job to completion.
const approveAsExpert = async (browser: Browser, jobId: string, notes: string): Promise<void> => {
  const expertContext = await browser.newContext({
    storageState: EXPERT_STORAGE_STATE,
    baseURL: APP_BASE_URL,
    extraHTTPHeaders: { "X-E2E-Fake-Ai": "1" },
  });
  const expertPage = await expertContext.newPage();
  await expertPage.goto(`/expert/review/${jobId}`);
  await expect(expertPage.getByTestId("expert-review-page")).toBeVisible();

  await expertPage
    .getByPlaceholder("Add your expert observations — visible to the customer.")
    .fill(notes);
  await expertPage.getByRole("button", { name: "Approve & complete" }).click();
  await expect(expertPage.getByText("Report ready")).toBeVisible({ timeout: 40_000 });
  await expertContext.close();
};

// Drives the real sign-in UI (send code → enter code → verify) end to end, using the debug OTP
// endpoint to read the code instead of an email inbox. Contrast with global-setup.ts's
// loginViaOtp, which does the same round trip via raw fetch to mint a session cookie directly.
const signInViaOtpUi = async (page: Page, email: string): Promise<void> => {
  await page.getByPlaceholder("your@email.com").fill(email);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Send code" }).click();
  await expect(page.getByText("Check your inbox")).toBeVisible();

  const debugRes = await page.request.get(
    `${API_BASE_URL}/auth/otp/debug?email=${encodeURIComponent(email)}`
  );
  expect(debugRes.ok()).toBe(true);
  const { code } = (await debugRes.json()) as { code: string };

  await page.getByPlaceholder("6-digit code").fill(code);
  await page.getByRole("button", { name: "Sign in" }).click();
};

const PageObjectS = {
  submitNewReport,
  answerClarification,
  answerClarificationIfAsked,
  requestExpertReview,
  approveAsExpert,
  signInViaOtpUi,
};
export default PageObjectS;
