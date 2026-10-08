import { expect, test } from "@playwright/test";

import { APP_BASE_URL, E2E_ENV, MARKETING_BASE_URL } from "../env";

// Regression coverage for the two historical bugs in fe/proxy.ts (docs/tech/DEVOPS.md) — both
// only manifested with two real, distinct domains, so this only means anything against the test
// environment. Locally, marketing and app share one host and the routing check is always a no-op.
test.skip(E2E_ENV === "local", "marketing and app share one host locally — nothing to redirect");

test.use({ storageState: { cookies: [], origins: [] } });

test.describe("cross-domain routing (fe/proxy.ts)", () => {
  test("marketing path on the app host redirects to the marketing host", async ({ page }) => {
    await page.goto(`${APP_BASE_URL}/`);
    await expect(page).toHaveURL(new RegExp(`^${MARKETING_BASE_URL}/`));
  });

  test("app path on the marketing host redirects to the app host", async ({ page }) => {
    await page.goto(`${MARKETING_BASE_URL}/reports`);
    await expect(page).toHaveURL(new RegExp(`^${APP_BASE_URL}/`));
  });

  test("marketing host serves marketing paths without redirecting", async ({ page }) => {
    await page.goto(`${MARKETING_BASE_URL}/`);
    await expect(page).toHaveURL(`${MARKETING_BASE_URL}/`);
  });
});
