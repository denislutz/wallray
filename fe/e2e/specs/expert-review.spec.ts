import { expect, test } from "@playwright/test";

import PageObjectS from "../PageObjectS";
import { EXPERT_EMAIL } from "../fixtures/testUser";

// Full expert-review journey: the customer uploads, then at await_customer_answers requests
// expert review + picks the fixed E2E expert (instead of replying) — skipping straight to
// expert_review with no AI-only PDF ever rendered — and a second, expert-authenticated browser
// context approves it to completion.
//
// Requires EXPERT_EMAIL (fixtures/testUser.ts) to be listed in the target environment's
// EXPERT_REVIEW_EMAILS backend setting, so it gets the expert_review role on first login and
// shows up in the expert picker — see docs/tech/E2E_TESTING_PLAN.md.
test.setTimeout(120_000);

// Expert-review checkbox is disabled in the UI for now (only AI assessment is available) — this
// spec is skipped, not deleted, so it can be re-enabled once expert review comes back.
test.skip("expert review: request, respond, approve", async ({ page, browser }) => {
  await page.goto("/reports/new");
  const jobId = await PageObjectS.submitNewReport(page, {
    title: "E2E expert review flow",
  });

  // request-expert and reply are mutually exclusive at await_customer_answers — this path never
  // calls answerClarification().
  await PageObjectS.requestExpertReview(page, EXPERT_EMAIL);
  await expect(page.getByText("With our expert")).toBeVisible({ timeout: 40_000 });
  // report_key must still be null here — no AI-only PDF is rendered on the request-expert path.
  await expect(page.getByRole("link", { name: "Open report" })).not.toBeVisible();

  await PageObjectS.approveAsExpert(
    browser,
    jobId,
    "Confirmed hairline crack, consistent with thermal movement."
  );
});
