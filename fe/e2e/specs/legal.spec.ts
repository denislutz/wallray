import { expect, test } from "@playwright/test";

import { MARKETING_BASE_URL } from "../env";

test.describe("legal page", () => {
  test("loads with privacy policy and disclaimer sections", async ({ page }) => {
    await page.goto(`${MARKETING_BASE_URL}/legal`);
    await expect(page).toHaveTitle(/Privacy Policy/);

    await expect(page.locator("#privacy")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Privacy Policy" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Controller" })).toBeVisible();

    await expect(page.locator("#disclaimer")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Disclaimer & Acceptable Use" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Report Disclaimer" })).toBeVisible();
  });

  test("is linked from the marketing footer", async ({ page }) => {
    await page.goto(`${MARKETING_BASE_URL}/`);
    await page.getByRole("link", { name: "Privacy & Disclaimer" }).click();
    await expect(page).toHaveURL(/\/legal$/);
  });

  test("Greek locale loads with translated privacy policy and disclaimer sections", async ({
    page,
  }) => {
    await page.goto(`${MARKETING_BASE_URL}/el/legal`);
    await expect(page).toHaveTitle(/Απορρήτου/);

    await expect(page.locator("#privacy")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Πολιτική Απορρήτου" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ελεγκτής" })).toBeVisible();

    await expect(page.locator("#disclaimer")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Αποποίηση Ευθύνης & Αποδεκτή Χρήση" })
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Αποποίηση Ευθύνης Αναφοράς" })).toBeVisible();
  });

  test("is linked from the Greek marketing footer", async ({ page }) => {
    await page.goto(`${MARKETING_BASE_URL}/el`);
    await page.getByRole("link", { name: "Απόρρητο & Αποποίηση Ευθύνης" }).click();
    await expect(page).toHaveURL(/\/el\/legal$/);
  });
});
