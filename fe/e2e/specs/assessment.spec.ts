import { expect, test } from "@playwright/test";

import PageObjectS from "../PageObjectS";

// Drives the real clarification-loop state machine end to end, but with the fake vision_llm port
// (X-E2E-Fake-Ai header, set at the project level in playwright.config.ts) standing in for the
// real Anthropic call — see be/app/adapters/vision_llm/fake.py. Its first assess() always raises
// one customer question, so this test always hits `awaiting_customer_input` once before
// completing — real UI, real DB, real background-task orchestration, fixed/instant model output.
test.setTimeout(120_000);

test("assessment reaches a clarification, then completes", async ({ page }) => {
  await page.goto("/reports/new");
  await PageObjectS.submitNewReport(page, { title: "E2E assessment flow" });

  await PageObjectS.answerClarification(page, "Building is about 15 years old.");

  await expect(page.getByText("Report ready")).toBeVisible({ timeout: 40_000 });
  await expect(page.getByRole("link", { name: "Download report" })).toBeVisible();
});
