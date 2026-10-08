import { expect, test } from "@playwright/test";

import PageObjectS from "../PageObjectS";
import { APP_BASE_URL } from "../env";

// Regression coverage for the JobS.ts defect_type/severity i18n gap: the AI assessment badges
// must render as translated labels ("Mängeltyp", "Riss", "Mittel") once the UI language is
// switched to German, not fall back to the raw English identifiers the fake vision_llm returns
// (be/app/adapters/vision_llm/fake.py: defect_type="crack", severity="medium").
//
// Uses its own throwaway account (like auth.spec.ts) rather than the shared customer fixture —
// switching the UI language persists to the account (PATCH /me/language), which would otherwise
// leak into every other spec sharing CUSTOMER_EMAIL and break their English-placeholder selectors.
const LOCALIZATION_EMAIL = "e2e-localization@wallray.app";
// Separate throwaway account from the German test above — same file, same defensive-reset
// reasoning (PATCH /me/language persists server-side), kept distinct so the two tests can't
// clobber each other's language state if execution order ever changes.
const LOCALIZATION_EMAIL_EL = "e2e-localization-el@wallray.app";

test.use({ storageState: { cookies: [], origins: [] } });
test.setTimeout(60_000);

test("report view shows AI assessment labels in German", async ({ page }) => {
  await page.goto(`${APP_BASE_URL}/auth/signin`);
  await PageObjectS.signInViaOtpUi(page, LOCALIZATION_EMAIL);
  await expect(page.getByTestId("reports-page")).toBeVisible();

  // Defensive reset: the language switch below persists server-side to this account
  // (PATCH /me/language), so a prior run that failed after switching to German would otherwise
  // leave this fixture user permanently in German — breaking submitNewReport's English-only
  // selectors on every subsequent run. setLang always fires the mutation even when already on
  // the target language (fe/services/business/UISessionS.ts), so this is safe to run unconditionally.
  await page.goto("/account");
  const resetToEnglish = page.waitForResponse(
    (res) => res.url().includes("/me/language") && res.ok()
  );
  await page.getByRole("button", { name: "English" }).click();
  await resetToEnglish;

  await page.goto("/reports/new");
  const jobId = await PageObjectS.submitNewReport(page, { title: "E2E German labels" });

  // Switch UI language after submitting — submitNewReport's placeholder-based selectors are
  // English-only, so the language switch happens after the form step rather than before it.
  await page.goto("/account");
  const patched = page.waitForResponse((res) => res.url().includes("/me/language") && res.ok());
  await page.getByRole("button", { name: "Deutsch" }).click();
  await patched;

  await page.goto(`/reports/${jobId}`);
  // exact: true — the await_customer_answers panel's "Request expert review" hint also mentions
  // "KI-Einschätzung" in a longer sentence, so a substring match is ambiguous here.
  await expect(page.getByText("KI-Einschätzung", { exact: true })).toBeVisible({
    timeout: 40_000,
  });
  await expect(page.getByText("Mängeltyp")).toBeVisible();
  // "Riss" appears twice — once in the Mängeltyp field, once in the AI assessment badge.
  await expect(page.getByText("Riss").first()).toBeVisible();
  await expect(page.getByText("Mittel")).toBeVisible();
});

test("report view shows AI assessment labels in Greek", async ({ page }) => {
  await page.goto(`${APP_BASE_URL}/auth/signin`);
  await PageObjectS.signInViaOtpUi(page, LOCALIZATION_EMAIL_EL);
  await expect(page.getByTestId("reports-page")).toBeVisible();

  // Defensive reset — see the German test above for why this runs unconditionally.
  await page.goto("/account");
  const resetToEnglish = page.waitForResponse(
    (res) => res.url().includes("/me/language") && res.ok()
  );
  await page.getByRole("button", { name: "English" }).click();
  await resetToEnglish;

  await page.goto("/reports/new");
  const jobId = await PageObjectS.submitNewReport(page, { title: "E2E Greek labels" });

  // Switch UI language after submitting — submitNewReport's placeholder-based selectors are
  // English-only, so the language switch happens after the form step rather than before it.
  await page.goto("/account");
  const patched = page.waitForResponse((res) => res.url().includes("/me/language") && res.ok());
  await page.getByRole("button", { name: "Ελληνικά" }).click();
  await patched;

  await page.goto(`/reports/${jobId}`);
  // exact: true for consistency with the German test above — no actual ambiguity here since the
  // Greek hint text inflects "αξιολόγηση" differently ("...επαληθεύσει την αξιολόγηση της ΤΝ."),
  // so it isn't a substring match of the heading regardless.
  await expect(page.getByText("Αξιολόγηση ΤΝ", { exact: true })).toBeVisible({
    timeout: 40_000,
  });
  await expect(page.getByText("Τύπος βλάβης")).toBeVisible();
  // "Ρωγμή" appears twice — once in the Τύπος βλάβης field, once in the AI assessment badge.
  await expect(page.getByText("Ρωγμή").first()).toBeVisible();
  await expect(page.getByText("Μέτρια")).toBeVisible();
});
