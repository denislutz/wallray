# be — Phase 2 Implementation Plan (revised)

Phase 2 goal: pipeline runs as a true background task decoupled from HTTP; optional human expert review gate with expert submission UI; role-based access control; FE relies on pure polling (no SSE).

Parent plan: `docs/TECH_PLAN.md` § Phase 2.

---

## Implementation Status

### Done ✅

| Area | What |
|---|---|
| `domain/user.py` | `UserRole(StrEnum)` + `role` field on `User` |
| `domain/job.py` | `request_expert_review: bool`, `expert_notes: str \| None` |
| `adapters/persistence/orm_models.py` | `role` on `UserRow`; `request_expert_review`, `expert_notes` on `JobRow` |
| `core/config.py` | `expert_review_emails`, `admin_emails`, `admin_email`, `app_url`, `expert_review_emails_set` |
| `api/deps.py` | `derive_role()`, `require_role()`, role upserted on every auth |
| `application/pipeline/state.py` | `request_expert_review: bool` |
| `application/pipeline/nodes/expert_notifier.py` | Sets status → `expert_review`, sends review email |
| `application/pipeline/graph.py` | Conditional edge wired (wrong position — see below) |
| `application/run_assessment.py` | Background runner, no SSE |
| `api/routes/upload.py` | Accepts `request_expert_review`, triggers `BackgroundTasks` |
| `api/routes/admin.py` | `GET /admin/jobs/{id}` + `POST /admin/jobs/{id}/approve` |
| `api/schemas.py` | `ApproveRequest`, `expert_notes` in `ReportItem` |
| `adapters/email/resend.py` | `send_expert_review_request` + `send_report` |
| `domain/ports/email.py` | `send_expert_review_request` in protocol |
| `fe/ui/business/ReportPage.tsx` | `expert_review` visual state (Clock icon) |
| `fe/services/business/ReportS.ts` | Polling in `useReport`; `useUpload` |

### Remaining ❌

See **File-level changes** below.

---

## Revised Architecture

### Key change: report is generated AFTER expert review, with AI re-synthesis

The original plan generated the PDF first, then had the expert review it.
The revised flow: AI runs initial analysis → expert reviews and adds notes → AI re-synthesizes a final classification giving priority to expert input → PDF is generated from the merged result.

```
[non-expert path]
photo_validator → defect_classifier → report_generator → complete

[expert path]
photo_validator → defect_classifier → expert_notifier → expert_review (waiting)
                                                            ↓
                                             Expert opens deep link from email
                                             Expert adds notes and submits
                                                            ↓
                                             POST /admin/jobs/{id}/approve
                                               → expert_notes written to DB
                                               → status → processing
                                               → GenerateReport background task
                                                     → LLM re-synthesis
                                                           inputs:  initial defect_type, severity,
                                                                    classification_notes + expert_notes
                                                           output:  final_defect_type, final_severity,
                                                                    final_summary (expert input has priority)
                                                     → renderer.render(final_classification, expert_notes)
                                                           PDF section 1: AI final assessment (synthesis)
                                                           PDF section 2: raw expert note (blockquote)
                                                     → status → complete
                                                     → customer email sent
```

`report_generator` is never reached in the expert path during the graph run. After approval, `GenerateReport` calls the LLM directly (not via LangGraph) for synthesis, then renders the PDF.

### Expert selection and assignment

Instead of always assigning the first expert, the customer picks from a dropdown shown on the upload form when "Request expert review" is checked.

- `config.py` exposes `expert_review_emails_list: list[str]` — ordered as entered in `EXPERT_REVIEW_EMAILS`, not sorted
- At app **startup**, each email in that list is upserted as a `User` with `role=expert_review` — giving each expert a stable UUID in the DB
- `GET /experts` returns `[{id, email}]` in config-list order — any authenticated user can call it
- The selected expert's user ID is sent with the upload form as `assigned_expert_id`
- `Job.assigned_expert_id` links to `users.id` — a real FK reference, not a dangling email string
- `expert_notifier` reads `state["assigned_expert_id"]`, looks up the expert's email from `user_repo`, sends the deep link email
- `GET /admin/jobs/{id}` and `POST /admin/jobs/{id}/approve` both verify `job.assigned_expert_id == str(current_user["sub"])`

### Expert review page (what the expert sees)

Expert sees: AI defect_type, severity, classification notes — **no PDF yet** (hasn't been generated). After the expert adds notes and approves, the PDF is generated incorporating both AI analysis and expert notes.

### FE polling states

```
pending       → "Sending your photos…"
processing    → "Analysing…"  (also covers GenerateReport phase post-approve)
expert_review → "With our expert · up to 48 h"
complete      → "Report ready" + download + expert_notes (if present)
failed        → "Something went wrong"
```

---

## File-level changes

### Backend

#### `core/config.py` ❌

- Add `expert_review_emails_list` computed property — preserves config order:

  ```python
  @computed_field
  @property
  def expert_review_emails_list(self) -> list[str]:
      return [e.strip().lower() for e in self.expert_review_emails.split(",") if e.strip()]
  ```

- Remove `admin_email` field — replaced by per-job assigned expert email (already in config but no longer used as notification target)

#### `adapters/persistence/orm_models.py` ❌ (`db:reset` required)

New columns:

| Table | Column | Type | Notes |
|---|---|---|---|
| `users` | `email` | `String, unique=True` | Change `index=True` → `unique=True` (enables upsert-by-email) |
| `jobs` | `name` | `String, nullable` | User-given report name |
| `jobs` | `assigned_expert_id` | `String(UUID), nullable` | FK to `users.id` |

#### `domain/job.py` ❌

- Add `name: str | None = None`
- Add `assigned_expert_id: str | None = None`

#### `adapters/persistence/pg_user_repo.py` ❌

- Add `get_or_create_by_email(email: str, role: UserRole) -> User`:
  - Queries by email; if not found, inserts with a new `uuid4()` id and given role
  - If found, updates `role` on the row (handles role changes via re-seeding)
  - Commits and returns the `User` domain object
- Add `get_by_emails(emails: list[str]) -> list[User]`:
  - `SELECT * FROM users WHERE email IN (...)` — returns unordered; caller sorts by config position

#### `adapters/persistence/pg_job_repo.py` ❌

- `get()`: map `row.name`, `row.assigned_expert_id` → domain `Job`
- `update_status()` already uses `**fields` — new fields pass through once ORM columns exist

#### `main.py` ❌

Add expert seeding to `_lifespan` after `create_all`:

```python
from app.adapters.persistence.pg_user_repo import PostgresUserRepository
from app.domain.user import UserRole

async with SessionLocal() as session:
    repo = PostgresUserRepository(session)
    for email in settings.expert_review_emails_list:
        await repo.get_or_create_by_email(email, UserRole.expert_review)
```

This runs every startup — safe to re-run because `get_or_create_by_email` is idempotent.

#### `application/pipeline/state.py` ❌

- Add `expert_notes: str | None`
- Add `assigned_expert_id: str | None`

#### `application/pipeline/nodes/expert_notifier.py` ❌

Remove `admin_email` / `first_expert_email` param; receive `user_repo` and `app_url`:

```python
def expert_notifier(job_repo, user_repo, email, app_url):
    async def _node(state):
        assigned_id = state["assigned_expert_id"]
        expert = await user_repo.get(assigned_id) if assigned_id else None
        expert_email = expert.email if expert else ""

        await job_repo.update_status(state["job_id"], JobStatus.expert_review)
        review_url = f"{app_url}/expert/review/{state['job_id']}"
        classification = state["defect_classification"]
        await email.send_expert_review_request(
            to=expert_email,
            job_id=state["job_id"],
            review_url=review_url,
            defect_type=classification.defect_type if classification else "unknown",
            severity=classification.severity if classification else "unknown",
        )
        return {}
    return _node
```

#### `application/pipeline/graph.py` ❌

Two changes:

1. Move conditional edge from after `report_generator` to after `defect_classifier`:

```python
g.add_conditional_edges(
    "defect_classifier",
    lambda state: "expert_notifier" if state["request_expert_review"] else "report_generator",
)
g.add_edge("report_generator", END)
g.add_node("expert_notifier", expert_notifier(job_repo, user_repo, email, app_url))
g.add_edge("expert_notifier", END)
```

1. `build()` signature: replace `admin_email: str` with `user_repo: UserRepository`

#### `application/run_assessment.py` ❌

- Add `user_repo` to `graph.build()` call (replacing `admin_email`)
- Fix the `report_key` check to not mark expert-review jobs as failed:

  ```python
  # Only treat missing report_key as failure on the non-expert path
  if not final_state["report_key"] and not job.request_expert_review:
      await self._job_repo.update_status(job_id, JobStatus.failed, ...)
      return
  ```

- Expert path returns early — no `increment_count`, no customer email (both happen in `GenerateReport`)

#### `application/pipeline/nodes/report_synthesizer.py` (new) ❌

Standalone async function — not a LangGraph node, but follows the same VisionLLM call pattern as `defect_classifier`. Called from `GenerateReport` after expert approval.

```python
async def synthesize_report(
    vision_llm: VisionLLMPort,
    initial_defect_type: str,
    initial_severity: str,
    initial_notes: str | None,
    expert_notes: str,
) -> DefectClassification:
    """Re-runs classification with expert input having priority."""
    ...
```

**Prompt** (system):
> You are a structural defect assessment AI. You made an initial assessment of a defect. A certified expert has now reviewed your assessment and provided their own notes. Your task is to produce a final, merged assessment. The expert's input takes priority — if the expert disagrees with your classification, defer to them. Integrate both perspectives into one coherent conclusion.

**Prompt** (user):
> Initial AI assessment:
>
> - Defect type: {initial_defect_type}
> - Severity: {initial_severity}
> - Notes: {initial_notes}
>
> Expert review notes:
> {expert_notes}
>
> Return a JSON object: { "defect_type": str, "severity": str, "summary": str }
> Where `summary` is a professional, concise merged assessment paragraph for the customer report.

Output is a `DefectClassification` with `defect_type`, `severity`, and `summary` (merged narrative).

#### `application/generate_report.py` (new) ❌

Application service — called after expert approval. Runs LLM re-synthesis then renders the PDF:

```python
class GenerateReport:
    def __init__(self, storage, job_repo, user_repo, renderer, email, vision_llm): ...

    async def run(self, job_id: str) -> None:
        job = await self._job_repo.get(job_id)
        # job.expert_notes already written by the approve endpoint

        # Re-synthesize: AI merges its initial classification with expert input
        final_classification = await synthesize_report(
            self._vision_llm,
            initial_defect_type=job.defect_type or "unknown",
            initial_severity=job.severity or "unknown",
            initial_notes=job.classification_notes,
            expert_notes=job.expert_notes or "",
        )

        photo_data = []
        for photo in job.photos:
            with contextlib.suppress(Exception):
                photo_data.append(await self._storage.download(photo.key))

        # Pass final_classification (synthesized) + raw expert_notes (for blockquote)
        pdf_bytes = await self._renderer.render(
            job, final_classification, photo_data, expert_notes=job.expert_notes
        )
        report_key = f"jobs/{job.id}/report.pdf"
        await self._storage.upload(report_key, pdf_bytes, "application/pdf")
        report_url = await self._storage.signed_url(report_key)
        await self._job_repo.update_status(job.id, JobStatus.complete, report_key=report_key)
        await self._user_repo.increment_count(job.user_id)
        user = await self._user_repo.get(job.user_id)
        if user and user.email:
            with contextlib.suppress(Exception):
                await self._email.send_report(user.email, job_id, report_url)
```

`vision_llm` is injected alongside the existing dependencies. `synthesize_report` is imported from `nodes/report_synthesizer.py`.

#### `api/routes/experts.py` (new) ❌

```
GET /experts
  Auth: JWT Bearer (any role)
  Returns: [{ id: str, email: str }]  ordered by EXPERT_REVIEW_EMAILS config position
```

Implementation:

```python
experts = await user_repo.get_by_emails(settings.expert_review_emails_list)
email_map = {u.email: u for u in experts}
return [
    ExpertItem(id=email_map[e].id, email=email_map[e].email)
    for e in settings.expert_review_emails_list
    if e in email_map
]
```

#### `api/routes/me.py` (new) ❌

```
GET /me
  Auth: JWT Bearer
  Returns: { role: str, email: str }
```

Reads the user row from DB (kept current by `current_user` upsert), returns role and email for the FE account page.

#### `api/routes/admin.py` ❌

- `GET /admin/jobs/{id}`: add `job.assigned_expert_id == str(current_user["sub"])` check → 403
- `POST /admin/jobs/{id}/approve`:
  1. Check `job.assigned_expert_id == str(current_user["sub"])` → 403
  2. Write `expert_notes` to DB
  3. Set status → `processing`
  4. `background_tasks.add_task(GenerateReport(...).run, job_id)`
  5. Remove old `user_repo.increment_count` and `email.send_report` — moved into `GenerateReport`
- New: `GET /admin/reviews` — returns all `expert_review` jobs where `assigned_expert_id = str(current_user["sub"])`

Inject `BackgroundTasks` into the approve handler.

#### `application/upload_job.py` ❌

- Accept `name: str | None = None` and `assigned_expert_id: str | None = None` in `execute()`
- Pass both to `Job` construction

#### `api/routes/upload.py` ❌

- Accept `name: Annotated[str | None, Form()] = None`
- Accept `assigned_expert_id: Annotated[str | None, Form()] = None`
- Pass both to `UploadJob.execute()`

#### `api/schemas.py` ❌

- Add `name: str | None = None` to `ReportItem`
- Add `ExpertItem(BaseModel)`: `id: str`, `email: str`

#### `adapters/renderer/xhtml2pdf.py` ❌

- `render()` signature gains `expert_notes: str | None = None` param (only set on expert path)
- Pass `name=job.name`, `expert_notes=expert_notes`, and all fields of `final_classification` (including `summary`) to template context

#### `adapters/renderer/templates/report.html` ❌

- Use `name` (if present) as page title subtitle
- Assessment Summary section uses `classification.summary` (merged narrative on expert path; AI-only on non-expert path)
- After Assessment Summary, add expert note as blockquote (only on expert path):

```html
{% if expert_notes %}
<div class="section">
  <div class="section-title">Expert Note</div>
  <blockquote class="expert-note">{{ expert_notes }}</blockquote>
</div>
{% endif %}
```

On non-expert path, `expert_notes` is `None` — block is skipped.

---

### Frontend

#### `fe/services/business/AssessmentS.ts` ❌

**Delete** — SSE hook no longer needed.

#### `fe/services/business/JobS.ts` ❌

- Add `name: string | null` to `Report` interface
- Add `assigned_expert_id: string | null` to `Report` interface
- Update `upload()`:
  - Add `name?: string` param → `formData.append("name", name ?? "")`
  - Add `requestExpertReview?: boolean` param → `formData.append("request_expert_review", ...)`
  - Add `assignedExpertId?: string` param → `formData.append("assigned_expert_id", assignedExpertId ?? "")`
- Add `getExperts(token: string): Promise<Expert[]>` → calls `GET /experts`
- Add `getReviewJob(id: string, token: string): Promise<Report>` → calls `GET /admin/jobs/{id}`
- Add `approveJob(jobId: string, expertNotes: string | null, token: string): Promise<void>` → `POST /admin/jobs/{id}/approve`

New type:

```ts
export interface Expert {
  id: string;
  email: string;
}
```

#### `fe/services/business/ReportS.ts` ❌

- `useUpload` payload: `{ files, name, description, requestExpertReview, assignedExpertId }`
- Pass all new fields to `JobS.upload()`
- Add `useExperts(token)` → wraps `JobS.getExperts(token)` with `useQuery` (stale-time: long — rarely changes)
- Add `useApprove(token)` mutation → `JobS.approveJob()`, invalidates `["report", jobId]`

#### `fe/services/business/AccountS.ts` (new) ❌

```ts
// Private
const getMe = (token: string): Promise<{ role: string; email: string }> =>
  HttpS.get("/me", token);

// Public
const useMe = (token: string | null) => {
  const { data } = ReactQueryS.useQuery({
    queryKey: ["me"],
    queryFn: () => getMe(token ?? ""),
    enabled: !!token,
  });
  return { me: data ?? null };
};

const AccountS = { useMe };
export default AccountS;
```

#### `fe/ui/business/NewReportPage.tsx` ❌

- Add `name: string` state (default `""`)
- Add `requestExpertReview: boolean` state (default `false`)
- Add `assignedExpertId: string` state (default `""`)
- Layout:
  1. `<Input>` for name (above description card, no card wrapper)
  2. Description `<Card>` (existing)
  3. Expert review section (below description):
     - `<Checkbox>` + label `{t("report_request_expert")}` + hint text
     - When checked: `<Select>` dropdown listing `{expert.email}` for each expert from `ReportS.useExperts(token)`; default to first expert
  4. `<PhotoUpload>` (existing)
- Pass `{ files, name, description, requestExpertReview, assignedExpertId }` to `upload.mutate()`
- Disable dropdown when `!requestExpertReview`

#### `fe/ui/business/ReportsPage.tsx` ❌

- `JobCard`: primary text shows `job.name` if set, falls back to `job.description`, then `t("report_processing")`

#### `fe/ui/business/ReportPage.tsx` ❌

- `complete` block: render `expert_notes` paragraph if non-null
- `expert_review` block: add detail lines `t("report_expert_review_detail")` and `t("report_expert_review_time")`

#### `fe/ui/business/AccountPage.tsx` ❌

- Import `AccountS`
- Call `AccountS.useMe(token)` → `me.role`
- Add role row between email and language:

  ```tsx
  <Row justify="between" align="center" py="sm">
    <Text size="sm" color="muted">{t("account_role")}</Text>
    <Text size="sm">{me ? t(`role_${me.role}`) : "—"}</Text>
  </Row>
  ```

#### `fe/app/expert/review/[jobId]/page.tsx` (new) ❌

```tsx
import { ExpertReviewPage } from "@/ui/business/ExpertReviewPage";
export default function ExpertReviewRoute({ params }: { params: { jobId: string } }) {
  return <ExpertReviewPage jobId={params.jobId} />;
}
```

#### `fe/ui/business/ExpertReviewPage.tsx` (new) ❌

`'use client'` — Expert-only page:

- Auth gate: redirect to sign-in if unauthenticated
- Loads job via `JobS.getReviewJob(jobId, token)` → `GET /admin/jobs/{id}`
- Shows: defect_type, severity badge, classification notes (AI output)
- **No PDF link** — PDF not generated yet
- `<Textarea>` for expert notes, label `t("expert_review_notes_label")`, hint `t("expert_review_notes_hint")`
- Submit button → `ReportS.useApprove(token).mutate({ jobId, expertNotes })`
- On success: navigate to `/reports/${jobId}` (shows `processing` then `complete`)
- On 403: render "Access denied" text
- `JobS.getReviewJob()` calls `GET /admin/jobs/{id}` (expert route, not customer `/report/{id}`)

#### `fe/services/tech/RoutingS.ts` ❌

- Add `expertReview: (jobId: string) => \`/expert/review/${jobId}\``
- Add to `paths` export

#### `fe/services/tech/i18n/en.ts` + `de.ts` ❌

New keys:

```ts
// Reports
report_name_label:             "Report name",
report_name_hint:              "Give this report a short title",
report_request_expert:         "Request expert review",
report_request_expert_hint:    "A certified engineer will verify the AI assessment.",
report_select_expert:          "Select expert",
report_expert_review_detail:   "A certified engineer is reviewing your report.",
report_expert_review_time:     "This can take up to 48 hours.",
report_expert_notes_label:     "Expert note",

// Expert review page
expert_review_title:           "Expert Review",
expert_review_ai_section:      "AI Assessment",
expert_review_notes_label:     "Your assessment",
expert_review_notes_hint:      "Add your expert observations — visible to the customer.",
expert_review_submit:          "Approve & complete",

// Account
account_role:                  "Role",

// Role labels — used via t(`role_${role}`)
role_customer:                 "Customer",
role_expert_review:            "Expert",
role_admin:                    "Admin",
```

German (`de.ts`) — add matching keys in German.

> Role labels are translated via the standard `t(\`role_\${role}\`)` pattern — no special helper in `I18nS.ts`.

---

## Base URL standardisation ❌

Two canonical variables replace all ad-hoc URL strings:

| Variable | What it is | Who reads it |
|---|---|---|
| `FE_BASE_URL` | Frontend origin | BE config → building deep links in emails |
| `BE_BASE_URL` | Backend origin | FE server-side (Next-Auth OTP call) |
| `NEXT_PUBLIC_BE_BASE_URL` | Backend origin (public) | FE client-side → `EnvS.apiUrl()` |

`NEXT_PUBLIC_API_URL`, `INTERNAL_API_URL`, and `APP_URL` are all retired and removed.

### BE `core/config.py` ❌

- Replace `app_url`/`APP_URL` with `fe_base_url: str = Field(default="http://localhost:3000", validation_alias="FE_BASE_URL")`
- Add `be_base_url: str = Field(default="http://localhost:8000", validation_alias="BE_BASE_URL")`
- Every occurrence of `settings.app_url` in existing code → `settings.fe_base_url`

### FE `services/tech/EnvS.ts` ❌

- `apiUrl()` reads `NEXT_PUBLIC_BE_BASE_URL` (fallback `http://localhost:8000`) — replaces `NEXT_PUBLIC_API_URL`
- Add `feBaseUrl()` reads `NEXT_PUBLIC_FE_BASE_URL` (fallback `http://localhost:3000`) — for any FE self-reference

All URL derivation in FE services goes through `EnvS` — no raw `process.env` for URLs outside this file.

### FE `services/tech/AuthS.ts` ❌

Server-side OTP call: replace

```ts
process.env.INTERNAL_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
```

with

```ts
process.env.BE_BASE_URL ?? process.env.NEXT_PUBLIC_BE_BASE_URL ?? "http://localhost:8000"
```

`BE_BASE_URL` (no `NEXT_PUBLIC_`) allows Docker-internal routing (different from the public URL) while `NEXT_PUBLIC_BE_BASE_URL` is the client-side fallback.

---

## Environment additions

### `.env.local`

```
# Base URLs
FE_BASE_URL=http://localhost:3000
BE_BASE_URL=http://localhost:8000
NEXT_PUBLIC_BE_BASE_URL=http://localhost:8000
NEXT_PUBLIC_FE_BASE_URL=http://localhost:3000

# Expert review
EXPERT_REVIEW_EMAILS=owner@example.com,reviewer1@example.com,reviewer2@example.com
ADMIN_EMAILS=
```

### `.env.prod`

```
# Base URLs
FE_BASE_URL=http://m44jmxufqxwowgkwjyq1qzft.167.235.74.32.sslip.io
BE_BASE_URL=http://jp71snbdqmuqdquutbcda8vy.167.235.74.32.sslip.io
NEXT_PUBLIC_BE_BASE_URL=http://jp71snbdqmuqdquutbcda8vy.167.235.74.32.sslip.io
NEXT_PUBLIC_FE_BASE_URL=http://m44jmxufqxwowgkwjyq1qzft.167.235.74.32.sslip.io

# Expert review
EXPERT_REVIEW_EMAILS=owner@example.com,reviewer1@example.com,reviewer2@example.com
ADMIN_EMAILS=
```

Retired vars — remove from all env files: `APP_URL`, `ADMIN_EMAIL`, `NEXT_PUBLIC_API_URL`, `INTERNAL_API_URL`.

---

## Remaining session plan

| # | Focus | Done when |
|---|---|---|
| 0 | Base URL standardisation ✅ | `FE_BASE_URL`/`BE_BASE_URL` in BE config; `EnvS.apiUrl()` reads `NEXT_PUBLIC_BE_BASE_URL`; `EnvS.feBaseUrl()` added; `AuthS` server-side uses `BE_BASE_URL`; all old URL vars retired |
| 1 | Graph restructure ✅ | `defect_classifier` → conditional → `expert_notifier` or `report_generator`; `run_assessment` doesn't fail expert-review jobs; `expert_notifier` receives `user_repo`, looks up expert email |
| 2 | Expert seeding + assignment columns ✅ | `expert_review_emails_list` in config; `UserRow.email` unique; `get_or_create_by_email`; startup seeds experts; `Job.assigned_expert_id` + `Job.name` on domain + ORM |
| 3 | `GET /experts` endpoint ✅ | Returns `[{id, email}]` in config order; any authenticated user |
| 4 | Upload form accepts `name` + `assigned_expert_id` ✅ | Route + `UploadJob.execute()` + `pg_job_repo` map both fields |
| 5 | `GenerateReport` service + approve refactor ✅ | `approve` writes expert_notes, sets `processing`, triggers background; `GenerateReport.run` calls `synthesize_report` (LLM re-synthesis with expert priority) then renders PDF, sets `complete`, emails customer |
| 6 | Expert notes + name in PDF ✅ | `report_synthesizer.py` prompt written; renderer accepts `expert_notes` param; template: Assessment Summary uses merged `summary`, Expert Note blockquote below |
| 7 | `GET /me` + `AccountS` + role in AccountPage ✅ | `GET /me`; `AccountS.useMe`; `AccountPage` shows translated role; all role + account i18n keys |
| 8 | Expert review checkbox + dropdown in `NewReportPage` ✅ | `requestExpertReview` checkbox; expert dropdown; `assignedExpertId` flows to upload call |
| 9 | `ExpertReviewPage` + routing ✅ | New page; loads via `GET /admin/jobs/{id}`; shows AI classification; textarea; submit → `useApprove`; redirect on success |
| 10 | `GET /admin/reviews` endpoint (FE: expert queue) ✅ | Lists expert's pending jobs; optional in Phase 2 — skip if email deep link is sufficient |
| 11 | `ReportPage` polish + all i18n + cleanup ✅ | `expert_notes` shown after complete; expert_review detail strings; all new i18n keys en + de; `AssessmentS.ts` deleted |
| 12 | QA ✅ | `mise run "qa:all"` passes; manual end-to-end: upload with name + expert → expert gets deep link email → opens review page → approves → LLM re-synthesizes → PDF Assessment Summary reflects merged conclusion → Expert Note blockquote shows raw expert input → customer email received |

---

## Cross-session rules (Phase 2)

- Graph conditional lives after `defect_classifier` — `report_generator` is never reached when `request_expert_review=True`
- `expert_notifier` looks up expert email via `user_repo.get(assigned_expert_id)` — no hardcoded email in graph
- `GenerateReport.run()` is the only path to PDF generation for expert-review jobs — reads `job.expert_notes` from DB (written by approve endpoint before triggering background)
- `GenerateReport` calls `synthesize_report()` before rendering — this is a direct `vision_llm` call (not a LangGraph node) that re-derives `defect_type`, `severity`, and `summary` giving expert input priority
- `synthesize_report` lives in `application/pipeline/nodes/report_synthesizer.py` — same file pattern as other nodes but called imperatively, not via the graph
- PDF on expert path: Assessment Summary uses the LLM-merged `summary`; Expert Note section renders `expert_notes` as a blockquote beneath it
- PDF on non-expert path: Assessment Summary uses `defect_classifier` output; no Expert Note section (expert_notes is None)
- `render()` signature accepts `expert_notes: str | None = None` — None on non-expert path, value on expert path
- Approve sets status → `processing` before triggering `GenerateReport` — keeps customer polling consistent
- `assigned_expert_id` is the access key: only the assigned expert (matching `current_user["sub"]`) can GET or approve a job — 403 otherwise
- Expert ordering comes from `EXPERT_REVIEW_EMAILS` config order, never alphabetical — `expert_review_emails_list` preserves it
- `expert_review_emails_set` (frozenset) stays for O(1) `derive_role` checks; `expert_review_emails_list` (list) is the ordered source for seeding and `GET /experts`
- Expert users are seeded at startup via `get_or_create_by_email` — idempotent, safe to re-run
- `user_repo.increment_count()` is called only inside `GenerateReport.run()` for expert-review jobs, and inside `RunAssessment.run()` for auto-complete jobs
- `expert_notes` is submitted once at approve time — no edit endpoint
- `expert_notes` is exposed in `ReportItem` — customer sees it after completion
- `name` is shown as primary title in `ReportsPage` — falls back to `description` then processing placeholder
- Role is never embedded in the JWT or Next-Auth session — always fetched from `GET /me`
- Role labels translated via `t(\`role_\${role}\`)` — no special helper in `I18nS.ts`
- `ADMIN_EMAIL` env var is retired — notifications go to assigned expert's DB email, not a global inbox
- All FE URL derivation goes through `EnvS.ts` — no raw `process.env` for URLs anywhere else in FE code
- BE uses `settings.fe_base_url` for FE deep links (emails) and `settings.be_base_url` for self-reference — never a hardcoded hostname
- `NEXT_PUBLIC_BE_BASE_URL` is the single client-side env var for the API base URL — `NEXT_PUBLIC_API_URL` and `INTERNAL_API_URL` are retired
- `BE_BASE_URL` (server-only, no `NEXT_PUBLIC_`) allows Docker-internal routing in `AuthS.ts`; falls back to `NEXT_PUBLIC_BE_BASE_URL`
