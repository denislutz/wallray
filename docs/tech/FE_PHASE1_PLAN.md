# fe — Phase 1 Implementation Plan

Phase 1 goal: user signs in, uploads photos with a description, watches live pipeline progress, downloads a PDF report.
No payments, no expert gate. Free tier capped at 3 reports per account.

Parent plan: `docs/TECH_PLAN.md` § Phase 1.

---

## Architecture — Layer Flow

```
app/pages          Route shells — layout, auth guard, navigation only
     ↓
ui/business/       Domain components — consume business services + base UI
     ↓
services/business/ Domain hooks — HTTP calls, SSE, state machine
     ↓
services/tech/     Infrastructure — HttpS, EnvS, I18nS
```

Dependency rule: every arrow points downward. `app/` never calls services directly.
`ui/business/` never imports from other `ui/business/` files.

---

## Navigation — Mobile-First Layout

Bottom tab bar, fixed. Two tabs: **Reports** and **Account**. Only rendered when authenticated.

```
┌─────────────────────┐
│ WallRay             │  ← top bar: wordmark only
├─────────────────────┤
│                     │
│   [page content]    │  ← scrollable, pb-20
│                     │
├─────────────────────┤
│  Reports  │ Account │  ← BottomNav, fixed bottom
└─────────────────────┘
```

### Routes

```
/                        redirect → /reports
/auth/signin             sign-in flow
/reports                 list of all user reports
/reports/new             photo upload + description
/reports/[jobId]         report lifecycle (processing → complete → download)
/account                 email, language switch, sign out
```

---

## Status

**Phase 1 is complete.** All routes, services, and components are implemented.

---

## Types

All domain types live in `fe/services/business/`:

| Type | File | Description |
|---|---|---|
| `Report` | `JobS.ts` | Single type for a report at any lifecycle stage |
| `ReportStatus` | `JobS.ts` | `pending \| processing \| expert_review \| complete \| failed` |
| `FreeTierError` | `JobS.ts` | Thrown by `upload()` on HTTP 402 |
| `AssessmentPhase` | `AssessmentS.ts` | `photo_validation \| defect_classification \| report_generation` |
| `AssessmentState` | `AssessmentS.ts` | Live SSE stream state (`phase`, `progress`, `done`, `reportUrl`, `error`) |

`Report` covers all fields at all lifecycle stages — `report_url` and `severity` are `null` until complete.

---

## Services

### Tech services (`services/tech/`)

| Service | Responsibility |
|---|---|
| `AuthS` | `useAuth()` — user, token, signIn, signOut; OTP + dev provider |
| `EnvS` | `NEXT_PUBLIC_API_URL`, devAuth flag |
| `HttpS` | axios client — `get()`, `post()`, `postForm()` with auth header |
| `I18nS` | EN/DE string resolution, `setLanguage()` |
| `ReactQueryS` | TanStack Query wrapper — Provider, `useQuery`, `useMutation` |
| `RoutingS` | Server-safe path constants |
| `RoutingClientS` | `useNav()` client hook |
| `TailwindS` | `cn()` styling utility |
| `ToastS` | Sonner wrapper — `success()`, `error()`, `info()` |

### Business services (`services/business/`)

| Service | Responsibility |
|---|---|
| `HealthS` | `useHealth()` — API health polling |
| `UISessionS` | Language state, `useT()` translation hook |
| `JobS` | `listReports()`, `upload()`, `getReport()` — HTTP calls to BE |
| `AssessmentS` | `useAssessment()` — SSE stream for pipeline progress |
| `ReportS` | Domain-facing API for UI: `useReports()`, `useReport()` (includes assessment), `useUpload()` |

`ReportS` is the only service `ui/business/` components import for report operations.
`useReport()` returns both the REST snapshot and live `AssessmentState` as `{ report, assessment }`.

---

## Free-tier limit

`JobS.upload()` throws `FreeTierError` on HTTP 402. `NewReportPage` catches it and shows an inline notice. No count fetched from API — limit revealed only when hit.

---

## i18n

All user-facing strings live in `services/tech/i18n/en.ts` and `de.ts`. EN is the type source. DE keys are always "Bewertung" terminology (never "Report"). Supported languages: EN, DE.
