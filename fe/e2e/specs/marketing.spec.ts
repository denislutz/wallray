import { expect, test } from "@playwright/test";

import { MARKETING_BASE_URL } from "../env";

test.describe("marketing pages", () => {
  test("landing page loads", async ({ page }) => {
    await page.goto(`${MARKETING_BASE_URL}/`);
    await expect(page).toHaveTitle(/WallRay/);
  });

  test("German locale loads", async ({ page }) => {
    await page.goto(`${MARKETING_BASE_URL}/de`);
    await expect(page).toHaveTitle(/WallRay/);
  });

  test("Russian locale loads", async ({ page }) => {
    await page.goto(`${MARKETING_BASE_URL}/ru`);
    await expect(page).toHaveTitle(/WallRay/);
  });

  test("Greek locale loads", async ({ page }) => {
    await page.goto(`${MARKETING_BASE_URL}/el`);
    await expect(page).toHaveTitle(/WallRay/);
  });
});
