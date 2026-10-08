# Backend Architecture — Hexagonal (Ports & Adapters)

The backend follows **Hexagonal Architecture**. Code is organised into three zones; dependencies always point inward toward the Domain Core.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            OUTSIDE WORLD                                │
│        HTTP clients · PostgreSQL · S3/Minio · Anthropic · Resend        │
├────────────────────────────────┬────────────────────────────────────────┤
│        DRIVING (inbound) ▼     │              ▼ DRIVEN (outbound)       │
│                                │                                         │
│  Adapters — left               │   Adapters — right                      │
│  api/routes/                   │   adapters/persistence/  (Postgres)     │
│    GET  /jobs                  │   adapters/storage/      (S3 / R2)      │
│    POST /upload                │   adapters/vision_llm/   (Anthropic)    │
│    POST /assess/{id}/stream    │   adapters/renderer/     (WeasyPrint)   │
│    GET  /report/{id}           │   adapters/email/        (Resend)       │
│              │                 │                   │                     │
│              │ calls           │                   │ implements          │
│              ▼                 │                   ▲                     │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                         DOMAIN CORE                               │  │
│  │                                                                   │  │
│  │   Domain Models      Use Cases (application/)    Ports            │  │
│  │   ─────────────      ──────────────────────────  ──────────────   │  │
│  │   Job                UploadJob                   StoragePort      │  │
│  │   User               ListJobs                    VisionLLMPort    │  │
│  │   Photo              RunAssessment               RendererPort     │  │
│  │   DefectClass.         pipeline/graph.py         EmailPort        │  │
│  │                         pipeline/nodes/          JobRepository    │  │
│  │                       GetReport                  UserRepository   │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Three zones

### Domain Core — `app/domain/` + `app/application/`

The center of the hexagon. Zero dependencies on frameworks, cloud SDKs, or infrastructure.

| Concept | Location | Examples |
|---|---|---|
| Domain Models | `app/domain/` | `Job`, `User`, `Photo`, `DefectClassification` |
| Use Cases | `app/application/` | `UploadJob`, `ListJobs`, `RunAssessment`, `GetReport` |
| Ports (interfaces) | `app/domain/ports/` | `StoragePort`, `JobRepository`, `VisionLLMPort` |

Ports are `typing.Protocol` definitions — they describe what the domain *needs* without knowing how it is provided. The dependency rule: **domain code never imports adapters**.

### Driving Adapters (inbound) — `app/api/`

Translate external triggers (HTTP requests) into domain calls. They are thin: parse input → call use case → return response. No business logic lives here.

| Adapter | Path | Calls |
|---|---|---|
| HTTP Controller | `api/routes/jobs.py` | `ListJobs` |
| HTTP Controller | `api/routes/upload.py` | `UploadJob` |
| HTTP Controller | `api/routes/assess.py` | `RunAssessment` |
| HTTP Controller | `api/routes/report.py` | `GetReport` |

### Driven Adapters (outbound) — `app/adapters/`

Implement the ports. They own all external SDK imports (boto3, SQLAlchemy, anthropic, weasyprint, resend). The domain core never sees these classes directly.

| Adapter | Port it implements | Notes |
|---|---|---|
| `adapters/storage/s3.py` | `StoragePort` | Works with S3, R2, minio |
| `adapters/storage/azure_blob.py` | `StoragePort` | Swap via `STORAGE_PROVIDER` env var |
| `adapters/persistence/pg_job_repo.py` | `JobRepository` | SQLAlchemy ORM lives here only |
| `adapters/persistence/pg_user_repo.py` | `UserRepository` | |
| `adapters/vision_llm/anthropic.py` | `VisionLLMPort` | Injection defense lives here |
| `adapters/renderer/weasyprint.py` | `RendererPort` | Jinja2 → WeasyPrint → PDF bytes |
| `adapters/email/resend.py` | `EmailPort` | |

---

## Wiring — `app/core/container.py`

`container.py` is the single file that knows which concrete adapter is selected. It reads env vars and constructs the right adapter instances at startup. Use cases never do this — they receive ports through dependency injection.

```
STORAGE_PROVIDER=s3     → container wires S3StorageAdapter
STORAGE_PROVIDER=azure  → container wires AzureBlobStorageAdapter
```

---

## Call chains — current implementation

### POST /upload

```
DRIVING ADAPTER
  api/routes/upload.py
    async def upload(files, description, user, ...)
      │  parses multipart, reads user["sub"]
      │
      ├─ raises HTTP 402  ←──────────────────────── FreeTierLimitError
      ├─ raises HTTP 422  ←──────────────────────── ValidationError
      └─ returns UploadResponse(job_id)
              │
              ▼
APPLICATION
  application/upload_job.py
    class UploadJob
      async def execute(user_id, files, description) -> str
        │
        ├─1  UserRepository.get(user_id)          ← port call
        │      raises FreeTierLimitError if count ≥ 3
        │
        ├─2  _check_magic_bytes(data, filename)   ← pure function
        │      raises ValidationError on bad content
        │
        ├─3  StoragePort.upload(key, data, ct)    ← port call  (per file)
        │
        └─4  JobRepository.save(job)              ← port call
              │                    │
              ▼                    ▼
DOMAIN CORE
  domain/job.py
    class Job           (dataclass)
    class JobStatus     (StrEnum)
    class Photo         (dataclass, frozen)

  domain/ports/storage.py       domain/ports/job_repo.py      domain/ports/user_repo.py
    class StoragePort (Protocol)  class JobRepository (Protocol)  class UserRepository (Protocol)
      upload                        save                             get
      download                      get                              upsert
      signed_url                    list_by_user                     increment_count
                                    update_status
              │                    │                    │
              ▼                    ▼                    ▼
DRIVEN ADAPTERS
  adapters/storage/s3.py          adapters/persistence/pg_job_repo.py   adapters/persistence/pg_user_repo.py
    class S3StorageAdapter          class PostgresJobRepository            class PostgresUserRepository
      async def upload(...)           async def save(job)                    async def get(user_id)
        asyncio.to_thread               session.add(JobRow(...))               select(UserRow).where(...)
        → boto3 put_object              → commit                             async def increment_count(user_id)
      async def signed_url(...)       async def list_by_user(user_id)         row.report_count += 1 → commit
        asyncio.to_thread               select(JobRow).where(...)
        → boto3 presigned_url           → [_row_to_job(row), ...]

  adapters/persistence/orm_models.py   ← SQLAlchemy ORM lives here only
    class UserRow  (Base)
    class JobRow   (Base)
    class OtpTokenRow (Base)
```

---

### GET /jobs

```
DRIVING ADAPTER
  api/routes/jobs.py
    async def list_jobs(user, job_repo, storage)
      │
      ├─ ListJobs(storage, job_repo).execute(user["sub"])
      └─ [_to_report_item(r) for r in resolved] → list[ReportItem]
              │
              ▼
APPLICATION
  application/list_jobs.py
    class ListJobs
      async def execute(user_id) -> list[ResolvedJob]
        │
        ├─1  JobRepository.list_by_user(user_id)       ← port call
        ├─2  StoragePort.signed_url(thumbnail_key)      ← port call (if set)
        └─3  StoragePort.signed_url(report_key)         ← port call (if complete)

    class ResolvedJob (dataclass)   ← application-layer output type; no API imports
      id · status · created_at · description
      thumbnail_url · defect_type · report_url · severity
              │
              ▼
DOMAIN CORE / DRIVEN ADAPTERS
  (same as POST /upload above)
```

---

### Startup wiring

```
core/container.py
  def build() -> Container
    └─ Container(storage=S3StorageAdapter(...))
         stored in app.state at lifespan

api/deps.py
  get_container(request)  → app.state.container
  get_storage(container)  → container.storage           (S3StorageAdapter)
  get_job_repo(session)   → PostgresJobRepository(session)
  get_user_repo(session)  → PostgresUserRepository(session)
```

---

## Dependency rule (summary)

```
api/routes/    →  application/  →  domain/ports/
                                        ▲
adapters/      ─────────────────────────┘  (implements)
core/          imported by all layers for Settings + db session
```

No arrow ever points outward. `domain/` imports nothing. `application/` imports `domain/` only. `adapters/` imports `domain/ports/` to implement them. `api/` imports `application/` and `domain/` — never `adapters/` directly.
