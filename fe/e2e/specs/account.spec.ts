import { expect, test } from "@playwright/test";

import { CUSTOMER_EMAIL } from "../fixtures/testUser";

test("account page shows the signed-in user's email", async ({ page }) => {
  await page.goto("/account");
  // exact: true — the app-shell header also shows a compact "{email} · {role}" badge
  // (UserBadge.tsx) on every authenticated page, which would otherwise match this substring too.
  await expect(page.getByText(CUSTOMER_EMAIL, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});
