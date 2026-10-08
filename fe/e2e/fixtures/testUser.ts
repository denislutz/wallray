// Fixed E2E identities. Both are auto-created on first OTP verify (be/app/api/routes/auth.py)
// — no separate seed script needed. EXPERT_EMAIL must be listed in the target environment's
// EXPERT_REVIEW_EMAILS backend setting so it gets the expert_review role on first login.

export const CUSTOMER_EMAIL = "e2e-customer@wallray.app";
export const EXPERT_EMAIL = "e2e-expert@wallray.app";
