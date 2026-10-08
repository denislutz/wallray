import path from "node:path";
import { defineConfig, devices } from "@playwright/test";
import dotenv from "dotenv";

import { APP_BASE_URL, CUSTOMER_STORAGE_STATE, E2E_ENV } from "./e2e/env";

dotenv.config({
  path: path.resolve(process.cwd(), E2E_ENV === "local" ? ".env.local" : ".env.test"),
});

// Default project (`chromium`) sends X-E2E-Fake-Ai on every request — the vision/LLM port is
// swapped for a fixed, canned response server-side (be/app/api/deps.py::get_vision_llm), only
// when settings.debug is true, so this is a no-op in prod regardless. Keeps this suite fast, free,
// and deterministic. `real-ai` is a separate, explicit-only project — never run by bare
// `playwright test`, only via `playwright test --project=real-ai`.
export default defineConfig({
  globalSetup: "./e2e/global-setup.ts",
  reporter: [["html", { open: "never" }], ["list"]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  // The test environment's VPS is small and shared with prod's full stack — real photo uploads
  // run memory-heavy PIL decode/resize/thumbnail work server-side, and running several of those
  // concurrently has been confirmed (dmesg) to OOM-kill uvicorn mid-request (see
  // docs/tech/DEVOPS.md). Run fully sequentially against the real deployed environment.
  workers: E2E_ENV === "local" ? undefined : 1,
  use: {
    baseURL: APP_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // The deployed test environment sits behind Traefik Basic Auth (docs/tech/DEVOPS.md — "Test
    // Environment Access Protection"); local dev has no such gate. httpCredentials is a no-op
    // against localhost.
    httpCredentials:
      E2E_ENV === "local"
        ? undefined
        : {
            username: process.env.TEST_BASIC_AUTH_USER ?? "",
            password: process.env.TEST_BASIC_AUTH_PASS ?? "",
          },
  },
  projects: [
    {
      name: "chromium",
      testDir: "./e2e/specs",
      use: {
        ...devices["Desktop Chrome"],
        storageState: CUSTOMER_STORAGE_STATE,
        extraHTTPHeaders: { "X-E2E-Fake-Ai": "1" },
      },
    },
    {
      name: "real-ai",
      testDir: "./e2e/specs-real-ai",
      use: {
        ...devices["Desktop Chrome"],
        storageState: CUSTOMER_STORAGE_STATE,
      },
    },
  ],
});
