import path from "node:path";
import { chromium } from "@playwright/test";
import dotenv from "dotenv";
import { encode } from "next-auth/jwt";

import {
  API_BASE_URL,
  APP_BASE_URL,
  E2E_ENV,
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_SECURE,
} from "./env";
import { CUSTOMER_EMAIL, EXPERT_EMAIL } from "./fixtures/testUser";

// Doesn't override already-set env vars (e.g. AUTH_SECRET injected directly in CI) — only fills
// gaps from the local, gitignored .env file for on-machine runs.
dotenv.config({
  path: path.resolve(process.cwd(), E2E_ENV === "local" ? ".env.local" : ".env.test"),
});

// ============================================================================
// Private
// ============================================================================

async function loginViaOtp(email: string): Promise<{ id: string; email: string }> {
  const send = await fetch(`${API_BASE_URL}/auth/otp/send`, {
    method: "POST",
    // Raw fetch, no browser — can never produce a real Turnstile token. Honored by the BE only
    // when settings.debug is true (never prod), same as X-E2E-Fake-Ai.
    headers: { "Content-Type": "application/json", "X-E2E-Skip-Turnstile": "1" },
    body: JSON.stringify({ email, terms_accepted: true }),
  });
  if (!send.ok) throw new Error(`auth/otp/send failed for ${email}: ${send.status}`);

  const debug = await fetch(`${API_BASE_URL}/auth/otp/debug?email=${encodeURIComponent(email)}`);
  if (!debug.ok) {
    throw new Error(
      `auth/otp/debug failed for ${email}: ${debug.status} — is settings.debug true on this env?`
    );
  }
  const { code } = (await debug.json()) as { code: string };

  const verify = await fetch(`${API_BASE_URL}/auth/otp/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  });
  if (!verify.ok) throw new Error(`auth/otp/verify failed for ${email}: ${verify.status}`);
  return (await verify.json()) as { id: string; email: string };
}

async function mintStorageState(email: string, outputFile: string): Promise<void> {
  const { id } = await loginViaOtp(email);

  const secret = process.env.AUTH_SECRET;
  if (!secret) throw new Error("AUTH_SECRET is not set — cannot mint the E2E session cookie");

  const sessionToken = await encode({
    token: { sub: id, email },
    secret,
    salt: SESSION_COOKIE_NAME,
  });

  const browser = await chromium.launch();
  const context = await browser.newContext();
  await context.addCookies([
    {
      name: SESSION_COOKIE_NAME,
      value: sessionToken,
      domain: new URL(APP_BASE_URL).hostname,
      path: "/",
      httpOnly: true,
      secure: SESSION_COOKIE_SECURE,
      sameSite: "Lax",
    },
  ]);
  await context.storageState({ path: outputFile });
  await browser.close();
}

// ============================================================================
// Entry point
// ============================================================================

export default async function globalSetup(): Promise<void> {
  await mintStorageState(CUSTOMER_EMAIL, "e2e/.auth/customer.json");
  await mintStorageState(EXPERT_EMAIL, "e2e/.auth/expert.json");
}
