# Auth Integration Plan

> ✅ **Complete** — all steps implemented and shipped.

**Library:** Auth.js (next-auth v5)
**Strategy:** JWT issued by Next.js, verified locally by FastAPI using a shared `AUTH_SECRET`. No network call between the two services.

---

## Step 1 — Install & configure Auth.js ✅

Config lives in `fe/services/tech/AuthS.ts`. Route handler at `fe/app/api/auth/[...nextauth]/route.ts` re-exports `AuthS.handlers`.

- Session strategy: `jwt` — no database adapter needed
- In the `session` callback, mint `apiToken` (HS256, 7d) so FastAPI can verify it

### Providers

| Provider  | Status          | Notes                                                                                      |
| --------- | --------------- | ------------------------------------------------------------------------------------------ |
| Email OTP | ✅ active        | Primary. FastAPI sends code via Resend, Auth.js Credentials verifies. No passwords stored. |
| Dev       | ✅ local only    | `NEXT_PUBLIC_DEV_AUTH=true` — instant bypass, never in prod                                |
| Google    | 💤 commented out | Uncomment + add `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET` to activate                        |
| Twitter/X | 💤 commented out | Uncomment + add `AUTH_TWITTER_ID` / `AUTH_TWITTER_SECRET` to activate                      |

Providers are built dynamically from env — commented-out ones cost nothing at runtime.

---

## Step 2 — Env vars ✅

`.env.local.example`:

```
AUTH_SECRET=          # openssl rand -base64 32 — same value used by FastAPI
JWT_SECRET=           # same value as AUTH_SECRET

# OAuth — uncomment provider block in AuthS.ts to activate
# AUTH_GOOGLE_ID=
# AUTH_GOOGLE_SECRET=
# AUTH_TWITTER_ID=
# AUTH_TWITTER_SECRET=
```

`AUTH_SECRET` matches `jwt_secret` in `be/app/core/config.py`.

---

## Step 3 — Wrap the app in SessionProvider ✅

`fe/app/providers.tsx` wraps children with `SessionProvider` (and `UISessionProvider`).
`fe/app/layout.tsx` uses `<Providers>`.

---

## Step 4 — Protect routes with proxy ✅

`fe/proxy.ts` uses `AuthS.auth` to protect all routes except `/auth/*` and `/api/auth/*`.
Unauthenticated users redirect to `/auth/signin`.

---

## Step 5 — AuthS tech service ✅

`fe/services/tech/AuthS.ts` — single auth file. Combines NextAuth config (private) with `useAuth()` (public). Exposes `handlers` and `auth` for the route handler and proxy.

---

## Step 6 — `HttpS` token support ✅

`HttpS.get()` and `HttpS.post()` accept an optional `token` parameter.
`withAuth()` adds `Authorization: Bearer <token>` when present.

---

## Step 7 — FastAPI auth dependency ✅

`be/app/api/deps.py` — `current_user` decodes the JWT, raises `401` on failure.
`GET /users/me` is the first protected route. `/health` stays open.

---

## Step 8 — Sign-in UI ✅

`fe/ui/business/UserMenu.tsx` — signed-out: sign-in button. Signed-in: avatar + name + sign-out.
`fe/ui/business/SignInPage.tsx` — two-step OTP form: enter email → enter code.
`UserMenu` lives in the layout header.

---

## Step 9 — Email OTP: FastAPI endpoints + user table ✅

### DB schema (SQLAlchemy async)

```
users       — id (uuid pk), email (unique), name, created_at
otp_tokens  — id, email, code_hash (bcrypt), expires_at
              deleted on first successful use
```

### Endpoints

`POST /auth/otp/send` — public

- Generates 6-digit code, bcrypt-hashes, upserts into `otp_tokens` (replaces any prior code for that email)
- Sends email via Resend
- Always returns `200` — no email enumeration

`POST /auth/otp/verify` — public

- Accepts `{email, code}`, checks hash + expiry (5 min), deletes row
- Upserts user into `users` (first verify = register, repeat = login)
- Returns `{id, email, name}` — Auth.js Credentials `authorize()` issues session

### FE changes (Auth.ts + SignInPage)

- Replace hardcoded `signIn("google")` with `signIn(provider)` — caller-supplied
- Add Credentials provider: `authorize({email, code})` calls `POST /auth/otp/verify`
- Google + Twitter blocks present but commented out in `AuthS.ts`
- `SignInPage` becomes two-step: email input → code input

---

## Architecture

### Email OTP sign-in flow

```
Browser              Next.js (fe/)         FastAPI (be/)        Resend
───────              ─────────────         ─────────────        ──────
│                │   │           │         │           │         │    │
│ enter email    │   │           │         │           │         │    │
│ POST /auth/otp/send ──────────────────▶ │           │         │    │
│                │   │           │         │ gen code  │         │    │
│                │   │           │         │ hash+store│         │    │
│                │   │           │         │ ──────────┼────────▶│    │
│                │   │           │         │  200 OK   │  email  │    │
│◀───────────────────────────────────────  │           │         │    │
│                │   │           │         │           │         │    │
│ enter code     │   │           │         │           │         │    │
│ signIn("credentials", {email,code})      │           │         │    │
│ ─────────────▶ │   │           │         │           │         │    │
│                │ Credentials authorize() │           │         │    │
│                │ POST /auth/otp/verify ─────────────▶│         │    │
│                │   │           │         │ verify    │         │    │
│                │   │           │         │ delete row│         │    │
│                │   │           │         │ upsert    │         │    │
│                │   │           │         │ user      │         │    │
│                │   │           │         │ {id,email}│         │    │
│                │ mint apiToken │◀─────────           │         │    │
│                │ (HS256, 7d)   │         │           │         │    │
│◀───────────────│ session cookie│         │           │         │    │
```

### Authenticated API call flow

```
Browser                          FastAPI (be/)
───────                          ─────────────────────────
│  AuthS.useAuth() → token   │   │                        │
│  HttpS.get("/users/me",    │   │ HTTPBearer             │
│    token)                  │──▶│ current_user()         │
│                            │   │ jwt.decode(token,      │
│                            │   │   jwt_secret)          │
│◀───────────────────────────│───│ route handler runs     │
```

### Shared secret

```
AUTH_SECRET (env)
      ├─▶ Next.js — signs apiToken (HS256)
      └─▶ FastAPI jwt_secret — verifies apiToken
```

---

## Email Provider — Resend

All transactional email (OTP codes, report delivery, future notifications) goes through **Resend**.

- SDK: `resend` Python package, called from FastAPI
- Free tier: 3,000 emails/month, 100/day — sufficient through Phase 1–2
- Paid: $20/mo for 50k emails/month (upgrade when live)
- Templates: React Email (co-developed by Resend team) — write templates as TSX, render server-side
- Why not alternatives: Postmark (transactional-only, no marketing path), SendGrid (heavier, enterprise-y), Mailgun (Sinch-owned, dated DX), AWS SES (cheap at scale but no DX)

```python
import resend

resend.api_key = "re_xxxxxxxxxx_xxxxxxxxxxxxxxxxxxxx"

r = resend.Emails.send({
  "from": "onboarding@resend.dev",
  "to": "owner@example.com",
  "subject": "Hello World",
  "html": "<p>Congrats on sending your <strong>first email</strong>!</p>"
})

```

```js
import { Resend } from 'resend';

const resend = new Resend('re_xxxxxxxxxx_xxxxxxxxxxxxxxxxxxxx');

resend.emails.send({
  from: 'onboarding@resend.dev',
  to: 'owner@example.com',
  subject: 'Hello World',
  html: '<p>Congrats on sending your <strong>first email</strong>!</p>'
});
```

---

## Step 10 — Auth UX Polish ✅

### User-facing states

| State                       | What the user sees                                                                                                           |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Unauthenticated, visits `/` | Proxy redirects to `/auth/signin`                                                                                            |
| Sign-in page — email step   | "Enter your email to sign in or create your account." + email input + Send code                                              |
| Sign-in page — code step    | "Check your inbox at {email} for a 6-digit code. Also check your spam folder." + code input                                  |
| Wrong code entered          | Inline error: "That code didn't match. Check your inbox and spam folder, or go back to request a new one." — **no redirect** |
| Correct code                | Session created → redirect to `/`                                                                                            |
| Authenticated, visits `/`   | Upload page directly — no sign-in prompt                                                                                     |
| Header (always)             | LangSwitcher + UserMenu (email + Sign out when logged in; Sign in button when not)                                           |

### First-time vs returning user

The UI uses neutral copy ("sign in or create your account") — both paths are identical. The backend upserts on first verify (register) and returns the existing user on subsequent verifies (login). No separate registration screen.

### Error handling

- **Wrong code**: `signIn("credentials", { redirect: false })` returns `{ ok: false }` — shown inline, no page navigation.
- **Resend failure**: caught, logged to backend stdout with `[auth] Resend error: ...`, OTP token still saved — user can retry. Returns 200 to avoid email enumeration.

### Email delivery (Resend free tier)

- Sender: `onboarding@resend.dev`
- Free tier: can only deliver to the email address registered on the Resend account until a custom domain is verified
- Upgrade path: verify a domain in Resend dashboard, update `from` in `be/app/api/routes/auth.py`

---

## What stays out for now

- Rate limiting (`slowapi`) — add when approaching production
- Private networking (FastAPI off the public internet) — add on Azure with VPC support

Next.js API routes are auth-only (`/api/auth/*`). All other browser → FastAPI calls are direct.
