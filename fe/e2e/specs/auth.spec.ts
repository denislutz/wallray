import { expect, test } from "@playwright/test";

import PageObjectS from "../PageObjectS";
import { APP_BASE_URL } from "../env";

// The one spec that drives the REAL sign-in UI (send code → enter code → verify) end-to-end,
// instead of the session-cookie shortcut every other spec uses (see global-setup.ts). Uses its
// own throwaway email so it never races the shared customer/expert fixture users.
const AUTH_FLOW_EMAIL = "e2e-auth-flow@wallray.app";

test.use({ storageState: { cookies: [], origins: [] } });

test("real OTP sign-in flow", async ({ page }) => {
  await page.goto(`${APP_BASE_URL}/auth/signin`);
  await PageObjectS.signInViaOtpUi(page, AUTH_FLOW_EMAIL);

  await expect(page.getByTestId("reports-page")).toBeVisible();
});
