import { test } from "@playwright/test";

import PageObjectS from "../PageObjectS";

test("customer can submit a new report", async ({ page }) => {
  await page.goto("/reports/new");
  await PageObjectS.submitNewReport(page, {
    title: "E2E test crack",
    description: "Hairline crack near the window, noticed last week.",
  });
});
