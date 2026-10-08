# WallRay — Phase 3 Plan

Three goals: fix a silent bug that breaks expert review, add richer metadata to the report detail page, and upgrade the report-ready email with direct download + app deep link.

---

## Bug: expert review never triggered

### Root cause

`NewReportPage.tsx` calls `upload.mutate()` without `requestExpertReview` in the payload:

```ts
upload.mutate({ files, description, name, assignedExpertId, language })
// requestExpertReview is local state — never sent
```

`ReportS.useUpload` mutationFn type has no `requestExpertReview` field, and `JobS.upload()` has no matching param — so it never appends `request_expert_review` to the FormData. The backend default is `False`, so the expert path is never entered regardless of what the user selects in the UI.

---

## Missing data on report detail page

`ResolvedJob` / `ReportItem` currently expose: `id`, `status`, `created_at`, `description`, `name`, `thumbnail_url`, `defect_type`, `report_url`, `severity`, `expert_notes`.

Missing:

| Field | Source | Why needed |
|---|---|---|
| `request_expert_review` | `job.request_expert_review` | Show "Expert review requested" row |
| `assigned_expert_email` | resolve `job.assigned_expert_id` → `user_repo.get()` → `.email` | Show which expert is reviewing |

`created_at` is already in the schema but never rendered in the UI.

---

## Session plan

### Session 0 — Fix `request_expert_review` wiring ❌

**`fe/services/business/JobS.ts`**

Add `requestExpertReview?: boolean` before `language` in `upload()`, append to FormData:

```ts
const upload = async (
  files: File[],
  description: string,
  token: string,
  name?: string | null,
  assignedExpertId?: string | null,
  language = "en",
  requestExpertReview = false,
): Promise<{ id: string }> => {
  ...
  formData.append("request_expert_review", String(requestExpertReview));
  ...
};
```

**`fe/services/business/ReportS.ts`**

Add `requestExpertReview?: boolean` to the `useUpload` mutationFn payload type and pass it through to `JobS.upload()`:

```ts
mutationFn: ({
  files, description, name, assignedExpertId, language, requestExpertReview,
}: {
  files: File[];
  description: string;
  name?: string | null;
  assignedExpertId?: string | null;
  language?: string;
  requestExpertReview?: boolean;
}) => JobS.upload(files, description, token ?? "", name, assignedExpertId, language, requestExpertReview),
```

**`fe/ui/business/NewReportPage.tsx`**

Add `requestExpertReview` to the `upload.mutate()` call:

```ts
upload.mutate({
  files,
  description,
  name: name || null,
  assignedExpertId: requestExpertReview && assignedExpertId ? assignedExpertId : null,
  language,
  requestExpertReview,
})
```

---

### Session 1 — Wire `assigned_expert_id` as a real FK + expose expert metadata ❌

#### ORM fix (`be/app/adapters/persistence/orm_models.py`)

Currently `assigned_expert_id` on `JobRow` is a plain `String` with no referential integrity:

```python
# current — no FK
assigned_expert_id: Mapped[str | None] = mapped_column(String, nullable=True)
```

Change to a proper FK to `users.id`:

```python
from sqlalchemy import ForeignKey
assigned_expert_id: Mapped[str | None] = mapped_column(
    UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
)
```

`ondelete="SET NULL"` — if an expert user row is ever removed the job is not orphaned, it just loses its assignment. Requires `db:reset`.

**`be/app/application/list_jobs.py`**

- Add `request_expert_review: bool = False` and `assigned_expert_email: str | None = None` to `ResolvedJob`
- `ListJobs` constructor accepts `user_repo: UserRepository`
- In `execute()`, after building each job: if `job.assigned_expert_id`, call `await self._user_repo.get(job.assigned_expert_id)` and use `.email`
- Pass both new fields when constructing `ResolvedJob`

**`be/app/application/get_report.py`**

- `GetReport` constructor accepts `user_repo: UserRepository`
- Same expert email lookup in `execute()`
- Pass `request_expert_review` and `assigned_expert_email` to `ResolvedJob`

**`be/app/api/schemas.py`**

Add to `ReportItem`:

```python
request_expert_review: bool = False
assigned_expert_email: str | None = None
```

**`be/app/api/routes/report.py`**

- Inject `user_repo` dependency into both `get_jobs` and `get_report` handlers
- Pass `user_repo` to `ListJobs(...)` and `GetReport(...)`
- Forward `request_expert_review` and `assigned_expert_email` in `_to_report_item()`

**`be/app/api/routes/upload.py`** — no change needed

---

### Session 2 — Report detail page UI ❌

**`fe/services/business/JobS.ts`**

Add new fields to `Report` interface:

```ts
request_expert_review: boolean;
assigned_expert_email: string | null;
```

**`fe/ui/business/ReportPage.tsx`**

Below the header row (thumbnail + name + job ID), add a metadata section visible in all states:

```tsx
<Col gap="xs" className="border rounded-lg px-4 py-3 bg-muted/30">
  <Row justify="between">
    <Text size="xs" color="muted">{t("report_submitted_label")}</Text>
    <Text size="xs">{formatDate(report.created_at)}</Text>
  </Row>
  <Row justify="between">
    <Text size="xs" color="muted">{t("report_status_label")}</Text>
    <Badge variant="outline">{t(`report_status_${report.status}`)}</Badge>
  </Row>
  {report.request_expert_review && (
    <Row justify="between">
      <Text size="xs" color="muted">{t("report_expert_label")}</Text>
      <Text size="xs">{report.assigned_expert_email ?? "—"}</Text>
    </Row>
  )}
  {report.defect_type && (
    <Row justify="between">
      <Text size="xs" color="muted">{t("report_defect_type_label")}</Text>
      <Text size="xs">{report.defect_type}</Text>
    </Row>
  )}
</Col>
```

`formatDate` — inline helper, e.g. `new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(created_at))`.

The existing state blocks (uploading / processing / expert_review / complete / failed) stay below and are unchanged, except:

- `expert_review` block: remove the generic detail lines — they're now in the metadata card above, supplemented by the expert email row.
- `complete` block: `severity` badge and download button stay; `expert_notes` block stays.

**`fe/services/tech/i18n/en.ts`** — add:

```ts
report_submitted_label:        "Submitted",
report_status_label:           "Status",
report_expert_label:           "Assigned expert",
report_defect_type_label:      "Defect type",
report_status_pending:         "Pending",
report_status_processing:      "Processing",
report_status_expert_review:   "With expert",
report_status_complete:        "Complete",
report_status_failed:          "Failed",
```

**`fe/services/tech/i18n/de.ts`** — matching German keys.

**`fe/services/tech/i18n/ru.ts`** — matching Russian keys.

---

### Session 3 — Report-ready email: download + deep link ❌

Currently `send_report(to, job_id, report_url)` sends a single "View Report" button pointing at the S3 signed URL. The customer has no direct download link and no link back into the app.

**`be/app/domain/ports/email.py`**

Add `app_report_url: str` param to `send_report`:

```python
async def send_report(self, to: str, job_id: str, report_url: str, app_report_url: str) -> None: ...
```

**`be/app/adapters/email/resend.py`**

Update `_REPORT_HTML` to include two calls-to-action:

```html
<a href="{app_report_url}" ...>Open in WallRay</a>
<a href="{report_url}" ...>Download PDF</a>
```

- "Open in WallRay" — primary button (blue), links to `{fe_base_url}/reports/{job_id}`
- "Download PDF" — secondary/outline button, links directly to the signed S3 URL
- Both open in new tab (`target="_blank"`)
- Note below: "The PDF link expires in 1 hour."

Update `send_report()` signature to accept `app_report_url: str` and format it into the template.

**`be/app/application/generate_report.py`**

`GenerateReport.run()` already calls `self._email.send_report(user.email, job_id, report_url)`. Change to:

```python
app_report_url = f"{self._fe_base_url}/reports/{job.id}"
await self._email.send_report(user.email, job_id, report_url, app_report_url)
```

`GenerateReport` already holds `self._fe_base_url` (injected alongside other deps).

**`be/app/api/routes/upload.py` / `be/app/application/run_assessment.py`**

`RunAssessment` also calls `send_report` on the non-expert path. Same change: pass `app_report_url`.

**`be/tests/fakes.py`**

`EmailFake.send_report` gains `app_report_url: str` — stored in the `sent` dict.

Any test asserting on `EmailFake.sent` entries is unaffected unless it checks the dict keys directly — update those assertions if needed.

---

## Cross-session rules (Phase 3)

- `request_expert_review` must reach the FormData — `String(false)` is a valid form value; the backend already handles it correctly once received
- `GetReport` and `ListJobs` both take `user_repo` — expert email lookup is one extra `get()` call per job; acceptable at this scale
- If `assigned_expert_id` is set but the user row is gone, return `None` for `assigned_expert_email` — don't error
- Metadata card renders regardless of job state — customer always sees submitted date and status
- `formatDate` is an inline function in `ReportPage.tsx`, not a service — it's a one-liner with no shared callers
- Status badge labels use `t(\`report_status_\${status}\`)` — consistent with the role label pattern already in use
- `app_report_url` in the email is always the public FE URL (`fe_base_url/reports/{job_id}`) — requires the customer to be signed in to view it, which is correct
- Both email buttons open in a new tab — PDF link is the signed S3 URL (1h expiry noted in email); app link is permanent
- The `EmailPort.send_report` signature change propagates to `EmailFake` and any test that instantiates `ResendAdapter` directly — update all callers in the same session
