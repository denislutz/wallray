import { test } from "@playwright/test";

import PageObjectS from "../PageObjectS";

// Runs only via `pnpm e2e:real-ai` / `mise run fe-e2e-real-ai` (playwright test
// --project=real-ai) — never part of the default suite, never in CI (see
// docs/tech/E2E_TESTING_PLAN.md §9-10). Drives the real Anthropic pipeline: real latency, real
// cost, nondeterministic content. Contrast with e2e/specs/assessment.spec.ts, which asserts fixed
// values from the fake vision_llm port — here we can only assert a terminal state was reached.
test.setTimeout(180_000);

test("real AI: assessment reaches a terminal state", async ({ page }) => {
  await page.goto("/reports/new");
  await PageObjectS.submitNewReport(page, { title: "Real-AI E2E flow" });
  await PageObjectS.answerClarificationIfAsked(page, "Building is about 15 years old.");
});
