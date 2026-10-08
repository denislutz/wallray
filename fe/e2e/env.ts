export const E2E_ENV: "local" | "test" = process.env.E2E_ENV === "local" ? "local" : "test";

export const APP_BASE_URL =
  E2E_ENV === "local" ? "http://localhost:3000" : "https://test.app.wallray.app";
export const MARKETING_BASE_URL =
  E2E_ENV === "local" ? "http://localhost:3000" : "https://test.wallray.app";
export const API_BASE_URL =
  E2E_ENV === "local" ? "http://localhost:8000" : "https://test.api.wallray.app";

export const SESSION_COOKIE_NAME =
  E2E_ENV === "local" ? "authjs.session-token" : "__Secure-authjs.session-token";
export const SESSION_COOKIE_SECURE = E2E_ENV !== "local";

export const CUSTOMER_STORAGE_STATE = "e2e/.auth/customer.json";
export const EXPERT_STORAGE_STATE = "e2e/.auth/expert.json";
