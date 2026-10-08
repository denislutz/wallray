# be — Phase 1 Implementation Plan

Phase 1 goal: fe sends photos, be runs the LangGraph pipeline, user receives a PDF report.
No payments, no human gate, no RAG. Free tier capped at 3 reports per account.

Parent plan: `docs/TECH_PLAN.md` § Phase 1.

---

## Architecture

See `docs/ARCHITECTURE.md` — Hexagonal (Ports & Adapters).

---

## Target file structure

```
be/
├── docker-compose.yml
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py          (Settings — env vars only)
│   │   ├── db.py              (async SQLAlchemy engine + session factory)
│   │   └── container.py       (wire ports → adapters at startup)
│   │
│   ├── domain/
│   │   ├── job.py             (Job aggregate, JobStatus, Photo value object)
│   │   ├── user.py            (User aggregate)
│   │   └── ports/
│   │       ├── storage.py     (StoragePort protocol)
│   │       ├── vision_llm.py  (VisionLLMPort protocol)
│   │       ├── renderer.py    (ReportRendererPort protocol)
│   │       ├── email.py       (EmailPort protocol)
│   │       ├── job_repo.py    (JobRepository protocol)
│   │       └── user_repo.py   (UserRepository protocol)
│   │
│   ├── application/
│   │   ├── upload_job.py      (UploadJob use case — validates, stores, checks free tier)
│   │   ├── list_jobs.py       (ListJobs use case)
│   │   ├── run_assessment.py  (RunAssessment use case — triggers pipeline)
│   │   ├── get_report.py      (GetReport use case)
│   │   └── pipeline/
│   │       ├── state.py       (AssessmentState TypedDict)
│   │       ├── graph.py       (StateGraph wiring)
│   │       └── nodes/
│   │           ├── photo_validator.py
│   │           ├── defect_classifier.py
│   │           └── report_generator.py
│   │
│   ├── adapters/
│   │   ├── storage/
│   │   │   ├── s3.py          (S3StorageAdapter — covers R2, minio, AWS S3)
│   │   │   └── azure_blob.py  (AzureBlobStorageAdapter)
│   │   ├── vision_llm/
│   │   │   ├── anthropic.py   (AnthropicAdapter)
│   │   │   ├── openai.py      (OpenAIAdapter — Phase 5)
│   │   │   └── qwen.py        (QwenAdapter — Phase 5)
│   │   ├── renderer/
│   │   │   └── weasyprint.py  (WeasyPrintAdapter)
│   │   ├── email/
│   │   │   └── resend.py      (ResendAdapter)
│   │   └── persistence/
│   │       ├── pg_job_repo.py   (PostgresJobRepository)
│   │       └── pg_user_repo.py  (PostgresUserRepository)
│   │
│   └── api/
│       ├── deps.py            (FastAPI deps — auth, db session, container)
│       ├── schemas.py         (Pydantic response models — OpenAPI contract)
│       └── routes/
│           ├── jobs.py        (GET /jobs)
│           ├── upload.py      (POST /upload)
│           ├── assess.py      (POST /assess/{job_id}/stream)
│           └── report.py      (GET /report/{job_id})
│
├── openapi.json               (committed; regenerated via `mise run schema:export`)
│
└── tests/
    ├── conftest.py
    ├── test_upload.py
    ├── test_jobs.py
    ├── test_pipeline.py
    └── test_report.py
```

---

## Domain layer

### `domain/job.py`

- `JobStatus` enum: `pending | processing | expert_review | complete | failed`
- `Photo` value object: `key: str, content_type: str`
- `Job` dataclass (aggregate root):

  ```python
  id: str
  user_id: str
  status: JobStatus
  photos: list[Photo]
  description: str | None      # user-submitted text from upload form
  created_at: datetime
  thumbnail_key: str | None    # key of first photo; signed URL in list responses
  defect_type: str | None      # set by defect_classifier node
  severity: str | None         # set by report_generator node; None until complete
  report_key: str | None       # S3 key of generated PDF; None until complete
  error: str | None
  ```

- No ORM imports, no framework imports

### `domain/user.py`

- `User` dataclass: `id, email, report_count: int`

### `domain/ports/` — protocols (structural typing via `typing.Protocol`)

```
StoragePort
  upload(key, data, content_type) -> str
  download(key) -> bytes
  signed_url(key, expires) -> str

VisionLLMPort
  classify(photo_keys: list[str]) -> DefectClassification

ReportRendererPort
  render(job: Job, classification: DefectClassification) -> bytes

EmailPort
  send_report(to, job_id, report_url) -> None

JobRepository
  save(job: Job) -> None
  get(job_id: str) -> Job | None
  list_by_user(user_id: str) -> list[Job]
  update_status(job_id, status, **fields) -> None

UserRepository
  upsert(user: User) -> None
  get(user_id: str) -> User | None
  increment_count(user_id: str) -> None
```

All ports are pure Python protocols — zero dependencies on frameworks or cloud SDKs.

---

## Application layer

### Use cases

**`UploadJob`** — called by `POST /upload`

1. Check user free-tier limit via `UserRepository` — raise `FreeTierLimitError` (→ HTTP 402) if hit
2. Validate files (MIME allowlist, magic bytes, size, count) — OWASP rules here, not in the route
3. Store each photo via `StoragePort.upload()`
4. Create `Job` domain object with `description`, `created_at=now()`, `thumbnail_key=photos[0].key`
5. Persist via `JobRepository.save()`
6. Return `job_id`

Free-tier check is the first step so no photos are stored for rejected submissions.

**`ListJobs`** — called by `GET /jobs`

1. Call `JobRepository.list_by_user(user_id)`
2. For each job with a `thumbnail_key`: generate `StoragePort.signed_url(thumbnail_key)`
3. For each complete job with a `report_key`: generate `StoragePort.signed_url(report_key)`
4. Return `list[ResolvedJob]` — application-layer output type; route converts to `list[ReportItem]`

**`RunAssessment`** — called by `POST /assess/{job_id}/stream`

1. Receive ports (`StoragePort`, `JobRepository`, `UserRepository`, `VisionLLMPort`, `ReportRendererPort`, `EmailPort`) via constructor — injected by the route through `deps.py`
2. Load `Job` via `JobRepository`
3. Call `pipeline.graph.build(storage, job_repo, vision_llm, renderer)` — passes ports into graph via closure; returns a compiled graph with all node dependencies pre-bound
4. Invoke `graph.astream_events()` — yields SSE-ready dicts
5. On completion: `JobRepository.update_status(...)`, `UserRepository.increment_count(...)`, `EmailPort.send_report(...)`

Free-tier check is intentionally absent here — enforced at upload time.

**`GetReport`** — called by `GET /report/{job_id}`

1. Load `Job` via `JobRepository`
2. Generate signed URLs for thumbnail and report if present via `StoragePort.signed_url()`
3. Return `ResolvedJob` — application-layer output type; route converts to `ReportItem`

### Pipeline nodes (in `application/pipeline/nodes/`)

Nodes never import adapters. Each node is a factory function that closes over the ports it needs and returns the actual node function:

```python
def photo_validator(storage: StoragePort, job_repo: JobRepository):
    async def _node(state: AssessmentState) -> AssessmentState:
        ...
    return _node
```

`graph.py` calls these factories at build time, binding ports via closure:

```python
def build(storage: StoragePort, job_repo: JobRepository, vision_llm: VisionLLMPort, ...) -> CompiledGraph:
    g = StateGraph(AssessmentState)
    g.add_node("photo_validator",    photo_validator(storage, job_repo))
    g.add_node("defect_classifier",  defect_classifier(vision_llm, job_repo))
    g.add_node("report_generator",   report_generator(storage, renderer, job_repo))
    ...
    return g.compile()
```

`RunAssessment` calls `graph.build(...)` with the ports it received from the DI layer. No node or graph file ever imports a concrete adapter.

**`photo_validator`**

- Downloads each photo via `StoragePort`
- Checks count (3–10), magic bytes re-validation, dimensions ≥ 400 px via Pillow
- Sets `state.validation_passed` and `state.validation_errors`
- Updates job status → `processing` via `JobRepository.update_status`

**`defect_classifier`**

- Calls `VisionLLMPort.classify(state.photo_keys)`
- Sets `state.defect_classification` (includes `defect_type` string)
- Persists `defect_type` back to `Job` via `JobRepository.update_status`
- Injection defense: no user text reaches the LLM prompt (handled inside the adapter)

**`report_generator`**

- Calls `ReportRendererPort.render()`
- Uploads PDF via `StoragePort.upload()`
- Sets `state.report_key`, `state.report_url`, `state.severity`
- Persists `severity` and `report_key` to `Job` via `JobRepository.update_status`

### `AssessmentState` (TypedDict)

```python
job_id, user_id, photo_keys,
description,
validation_passed, validation_errors,
defect_classification,
severity,
report_key, report_url
```

---

## Adapters layer

### `adapters/storage/s3.py` — `S3StorageAdapter`

Implements `StoragePort`. Uses boto3.

- `endpoint_url` empty → AWS S3 / Cloudflare R2
- `endpoint_url = http://localhost:9000` → minio (local dev)

### `adapters/storage/azure_blob.py` — `AzureBlobStorageAdapter`

Implements same `StoragePort`. Switched in via `container.py`.

### `adapters/vision_llm/anthropic.py` — `AnthropicAdapter`

Implements `VisionLLMPort`.

- Static system prompt prefix — user `description` never reaches the LLM
- Parses JSON response → `DefectClassification` (includes `defect_type: str`, `severity: str`)

### `adapters/renderer/weasyprint.py` — `WeasyPrintAdapter`

Implements `ReportRendererPort`. Jinja2 template → WeasyPrint → PDF bytes.

### `adapters/persistence/`

`PostgresJobRepository` and `PostgresUserRepository` implement the domain repo protocols.
ORM models (SQLAlchemy) live here only.

---

## API layer — contract with FE

Routes are thin: parse request → call use case → return response. No business logic.

```
GET  /jobs                  → ListJobs(user_id)              → list[ReportItem]
POST /upload                → UploadJob(files, description)  → UploadResponse  [402 if free tier]
GET  /assess/{id}/stream    → RunAssessment(job_id, user_id) → StreamingResponse (SSE)
GET  /report/{id}           → GetReport(job_id, user_id)     → ReportItem
```

Auth on `GET /assess/{id}/stream` uses `current_user_from_query` — reads JWT from `?token=` query param because `EventSource` cannot set `Authorization` headers.

Auth (`deps.py`): JWT decode + user upsert (calls `UserRepository.upsert`).

### `api/schemas.py` — Pydantic response models

These are the wire types the FE consumes. They must match `fe/services/business/JobS.ts` exactly.

```python
class ReportStatus(str, Enum):
    pending       = "pending"
    processing    = "processing"
    expert_review = "expert_review"
    complete      = "complete"
    failed        = "failed"

class AssessmentPhase(str, Enum):
    photo_validation      = "photo_validation"
    defect_classification = "defect_classification"
    report_generation     = "report_generation"

class ReportItem(BaseModel):
    """Single shape for both GET /jobs (list) and GET /report/{id} (detail)."""
    id:            str
    status:        ReportStatus
    created_at:    datetime
    description:   str | None = None
    thumbnail_url: str | None = None   # signed URL; None while uploading
    defect_type:   str | None = None   # None until defect_classifier completes
    report_url:    str | None = None   # signed URL; None until complete
    severity:      str | None = None   # None until complete

class UploadResponse(BaseModel):
    job_id: str                        # FE normalises job_id → id on receipt

class AssessmentEventType(str, Enum):
    progress = "progress"
    complete = "complete"
    error    = "error"

class AssessmentEvent(BaseModel):
    type:       AssessmentEventType
    phase:      AssessmentPhase | None = None
    message:    str | None = None
    report_url: str | None = None      # present when type == "complete"
```

Every route must declare `response_model=<SchemaClass>` for OpenAPI spec generation.

---

## OpenAPI schema export

`be/openapi.json` is a committed static export. Regenerate after any schema change:

```bash
mise run schema:export   # regenerate
mise run schema:check    # CI gate — fails if FE types are out of sync
```

---

## Infrastructure

### `docker-compose.yml` services

```
be        — FastAPI (port 8000)
postgres  — Postgres 16 (port 5432)
minio     — S3-compatible local storage (ports 9000, 9001)
```

### `.env.local` additions

```
DATABASE_URL=postgresql+asyncpg://wallray:wallray@localhost:5432/wallray
STORAGE_PROVIDER=s3
STORAGE_ENDPOINT_URL=http://localhost:9000
STORAGE_ACCESS_KEY_ID=minioadmin
STORAGE_SECRET_ACCESS_KEY=minioadmin
STORAGE_BUCKET=wallray

# Vision LLM — set VISION_LLM_PROVIDER=deepseek for dev, anthropic for live
VISION_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=<your-deepseek-key>
```

---

## Session plan

| # | Focus | Done when |
|---|---|---|
| ~~1~~ | ~~Docker Compose + DB (ORM models, engine, startup `create_all`)~~ | ✅ `docker compose up` works; tables exist |
| ~~2~~ | ~~Ports + container + S3 adapter + `UploadJob` + `ListJobs` + `GET /jobs` + `POST /upload` + schemas~~ | ✅ `POST /upload` stores photos, returns `job_id`; `GET /jobs` returns list; 402 on 4th upload |
| ~~3~~ | ~~Pipeline scaffold + `photo_validator` node~~ | ✅ `graph.ainvoke()` runs with stubs; validator tests pass |
| ~~4~~ | ~~`AnthropicAdapter` + `defect_classifier` node (sets `defect_type` on Job)~~ | ✅ Node returns classification; `defect_type` persisted to DB |
| ~~5~~ | ~~`WeasyPrintAdapter` + `report_generator` node (sets `severity` + `report_key`)~~ | ✅ PDF in minio, signed URL in state, severity persisted |
| ~~6~~ | ~~`RunAssessment` use case + SSE stream route + `GetReport`~~ | ✅ Full SSE flow; `GET /report/{id}` returns signed PDF URL and severity on completion |
| ~~7~~ | ~~User upsert in auth dep + `ResendAdapter` + email on completion~~ | ✅ Email sent; user row auto-created on first request |
| ~~8~~ | ~~Migrate `WeasyPrintAdapter` → `Xhtml2pdfAdapter` (xhtml2pdf, pure-Python, no system deps)~~ | ✅ `Xhtml2pdfAdapter` wired in `container.py` + `deps.py`; `weasyprint.py` kept as disabled reference |
| ~~9~~ | ~~`DeepSeekAdapter` for dev (cheaper vision LLM) + `VISION_LLM_PROVIDER` env switch~~ | ✅ `adapters/vision_llm/deepseek.py` (OpenAI-compat client); `container.py` selects adapter via `VISION_LLM_PROVIDER=anthropic\|deepseek`; `DEEPSEEK_API_KEY` added to `config.py` |
| ~~10a~~ | ~~Upload + jobs test gaps~~ | ✅ `test_upload_rejects_oversized_file`, `test_upload_rejects_too_many_files`, `test_upload_accepts_webp`, `test_upload_accepts_multiple_files`, `test_jobs_requires_auth`, `test_jobs_complete_job_shows_all_fields` all green |
| ~~10b~~ | ~~Assess stream + report + auth + sync gap test gaps~~ | ✅ `test_assess_stream_wrong_user_emits_error`, `test_get_report_wrong_user_returns_404`, `test_expired_bearer_jwt_rejected`, `test_assess_stream_photo_count_exceeds_pipeline_max` all green |
| ~~11~~ | ~~Real-AI e2e integration test — full path with live DeepSeek + real renderer~~ | ✅ `pytest -m integration` passes; `test_deepseek_classifies_real_photo` + `test_full_e2e_real_ai` green; PDF in StorageFake, SSE emits `complete`, `/report/{id}` fully populated |

---

## Test coverage audit

### Covered ✅

| Area | Tests |
|---|---|
| `POST /auth/otp/send` | valid email, invalid email, replaces existing token |
| `POST /auth/otp/verify` | correct code, creates user, wrong code, expired code, no token, consumed after use |
| `GET /me` | returns sub, requires auth, user-scoped |
| `POST /upload` | job_id returned, with description, wrong mime, bad magic bytes, free tier 402, requires auth |
| `GET /jobs` | empty list, full fields, multiple uploads, user-scoped |
| `GET /assess/{id}/stream` | 200, complete event, all progress phases, requires auth, unknown job error, complete → `/report` shows done |
| `GET /report/{id}` | pending, complete with all fields, 404 unknown, requires auth |
| Pipeline nodes | end-to-end, processing status, PNG accepted, too few/many, small dimensions, bad magic bytes, classifier, report generator |
| `RunAssessment` use case | progress+complete events, user count incremented, email sent/skipped, wrong user, validation fail |
| `GetReport` use case | resolved fields, unknown job, wrong user, no URL when pending |

### Covered ✅ — Session 10a (`test_upload.py`)

| Test | Covers |
|---|---|
| `test_upload_rejects_oversized_file` | 10 MB+ file → 422 (`NEXT_PUBLIC_PHOTO_MAX_SIZE_MB`, logic in `upload_job.py`) |
| `test_upload_rejects_too_many_files` | >10 files in one upload → 422 (`upload_job.py:63`) |
| `test_upload_accepts_webp` | valid WEBP magic bytes → 201 (JPEG + PNG tested, WEBP not) |
| `test_upload_accepts_multiple_files` | 3 photos → job appears in `/jobs` with thumbnail |
| `test_jobs_requires_auth` | `GET /jobs` without token → 401 |
| `test_jobs_complete_job_shows_all_fields` | after assess (with fakes): `/jobs` returns `report_url`, `defect_type`, `severity` all populated |

### Covered ✅ — Session 10b (`test_report.py`, `test_auth.py`)

| File | Test | Covers |
|---|---|---|
| `test_report.py` | `test_assess_stream_wrong_user_emits_error` | upload as user A, assess as user B → error SSE event (HTTP integration) |
| `test_report.py` | `test_get_report_wrong_user_returns_404` | upload as A, `GET /report` as B → 404 (HTTP integration) |
| `test_auth.py` | `test_expired_bearer_jwt_rejected` | JWT with past `exp` on `/jobs` → 401 |
| `test_report.py` | `test_assess_stream_photo_count_exceeds_pipeline_max` | upload 6 photos (> env max 5, ≤ upload max 10) → assess stream emits error event; tests the upload-vs-pipeline sync gap |

### Session 11 — Real-AI e2e integration test

New file: `be/tests/test_e2e_integration.py`

- Mark all tests `@pytest.mark.integration` — excluded from normal `qa:be`, run with `pytest -m integration`
- Uses a new `e2e_client` fixture: real `DeepSeekAdapter` (reads `DEEPSEEK_API_KEY` from env), real `Xhtml2pdfAdapter`, `StorageFake`, SQLite in-memory DB
- Loads a real photo from `docs/clusterindex/pics/` (committed test asset)

**`test_deepseek_classifies_real_photo`** (unit, no HTTP)

- Instantiate `DeepSeekAdapter` directly with real key + `StorageFake`
- Upload a real JPEG, call `classify()`
- Assert: `defect_type` is non-empty string, `severity` in `{"low","medium","high","critical"}`

**`test_full_e2e_real_ai`** (HTTP integration)

1. `POST /upload` — real wall photo
2. `GET /assess/{id}/stream?token=<jwt>` — real DeepSeek + real renderer
3. Assert SSE emits `progress` events then `complete` with a non-null `report_url`
4. `GET /report/{id}` — assert `status=complete`, `defect_type` and `severity` populated, `report_url` non-null
5. Assert the report PDF bytes are stored in `StorageFake` (non-empty, starts with `%PDF`)

---

## Cross-session rules

- `VISION_LLM_PROVIDER=anthropic` (live) / `deepseek` (dev) — switched in `container.py`; both implement `VisionLLMPort`; `Container.vision_llm` is typed as the protocol, not a concrete class
- Nodes never import adapters — they receive ports via closure bound at `graph.build()` time
- `graph.build(storage, job_repo, vision_llm, renderer)` is the only place ports enter the pipeline; `RunAssessment` calls it with ports from DI
- All OWASP file validation lives in `UploadJob`, not in the route
- Free-tier check is enforced in `UploadJob` (step 1, before any storage) — HTTP 402 raised in the route
- Every node error is stored in `Job.error`; the stream emits an `error` event before closing
- `description` is stored on `Job` and passed through `AssessmentState`; it never reaches the LLM
- Use cases (`ListJobs`, `GetReport`) return `ResolvedJob` / `list[ResolvedJob]` — application-layer types; routes convert to `ReportItem` for the HTTP response
- `ReportItem` (api schema) is the single wire shape for both list and detail responses
- `severity` is produced by the LLM/renderer and stored on `Job`; exposed in `ReportItem`
- Auth dep (`deps.py`) calls `UserRepository.upsert()` directly on each authenticated request — no separate use case needed since there is no business logic beyond the upsert itself

### End-to-end local smoke test

```bash
docker compose up postgres minio -d
mise run be-api
# create bucket: open localhost:9001, login minioadmin/minioadmin, create "wallray"
curl localhost:8000/jobs -H "Authorization: Bearer <token>"
curl -X POST localhost:8000/upload -H "Authorization: Bearer <token>" -F "files=@docs/clusterindex/pics/2.jpg" -F "description=Crack in wall"
curl -N "localhost:8000/assess/<job_id>/stream?token=<token>"
curl localhost:8000/report/<job_id> -H "Authorization: Bearer <token>"
```
