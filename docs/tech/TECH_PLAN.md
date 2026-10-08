# Technical Plan

> This project is designed to be production-grade from day one. It is not a toy demo.
> Primary customer: anyone who encounters one ambiguous building problem (mold, crack, damp) and needs an expert verdict before acting — renter, buyer, owner, or remote investor. The remote investor is the high-ticket tier; the uncertain local resident is the volume tier.
>
> Portfolio positioning and DACH skill gap rationale live in `docs/SKILL_DEV_PLAN.md`.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Component Breakdown](#2-component-breakdown)
3. [Build Sequence](#3-build-sequence)
4. [Technology Decisions](#4-technology-decisions)
5. [Framework & Tool Reference](#5-framework--tool-reference)
6. [Implementation Status](#6-implementation-status)

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                             │
│  fe (Next.js)  ·  DE landing page  ·  RU landing page  ·  EN    │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS / REST
┌────────────────────────────▼────────────────────────────────────┐
│                      FastAPI Gateway                            │
│  /upload  ·  /assess  ·  /report  ·  /webhook (expert review)  │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                  LangGraph Agent Pipeline                       │
│                                                                 │
│  Node 1: PhotoValidator                                         │
│    – Check photo count, quality score, required angles          │
│    – If insufficient: return guided re-upload instructions      │
│                                                                 │
│  Node 2: DefectClassifier (Vision LLM)                         │
│    – Call vision model with structured prompt                   │
│    – Output: defect_type, severity, confidence, affected_areas  │
│                                                                 │
│  Node 3: CostEstimator (RAG)                                    │
│    – Embed defect description → query Qdrant price DB           │
│    – Retrieve: labour rates, material costs, regional factors   │
│    – LLM synthesises cost range                                 │
│                                                                 │
│  Node 4: HumanGate (conditional)                               │
│    – If confidence < threshold OR severity == "urgent":         │
│      route to expert review queue                               │
│    – Else: auto-approve for Tier 1 free report                  │
│                                                                 │
│  Node 5: ReportGenerator                                        │
│    – Assemble structured JSON → PDF via WeasyPrint              │
│    – Store in R2, send signed URL to user                       │
│                                                                 │
│  Node 6: ContractorMatcher (optional, Tier 3)                  │
│    – Query contractor DB by location + defect type              │
│    – Generate referral link with tracking                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼──────────────────────┐
        ▼                    ▼                       ▼
  ┌──────────┐        ┌──────────────┐        ┌──────────────┐
  │  Qdrant  │        │  Vision LLM  │        │ Expert Queue │
  │  Vector  │        │  Qwen2-VL    │        │  (Postgres + │
  │  DB      │        │  via Ollama  │        │   webhook)   │
  │          │        │  or GPT-4o   │        │              │
  └──────────┘        └──────────────┘        └──────────────┘
```

**Code architecture:** the backend follows Hexagonal Architecture (Ports & Adapters). See `docs/ARCHITECTURE.md`.

---

## 2. Component Breakdown

### 2.1 FastAPI Gateway

Entry point for all client requests. Handles file upload, authentication (JWT), payment status check, and routing to the LangGraph pipeline.

**Key endpoints:**

```python
POST /upload          # Receive photos, validate MIME, store to R2, return job_id
POST /assess/{job_id} # Trigger LangGraph pipeline for a job
GET  /report/{job_id} # Poll for status, return signed PDF URL when ready
POST /webhook/expert  # Expert submits their review JSON → resume LangGraph
POST /pay/{job_id}    # Stripe checkout session creation
```

---

### 2.2 LangGraph Agent Pipeline

Orchestrates the multi-step assessment as a stateful directed graph. Each node is a discrete Python function. The graph persists state between nodes — critical for the human-in-the-loop gate.

**Why LangGraph and not a simple pipeline:**

A simple `step1() → step2() → step3()` function chain cannot handle:

- Branching logic (confidence below threshold → route to expert)
- Human-in-the-loop interrupts (expert reviews then resumes)
- Retry logic with state memory (re-run classifier with additional context)
- Streaming intermediate results to fe

**Graph definition:**

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict

class AssessmentState(TypedDict):
    job_id: str
    photos: list[str]          # R2 URLs
    property_metadata: dict
    defect_classification: dict
    cost_estimate: dict
    confidence: float
    requires_expert: bool
    expert_review: dict | None
    report_url: str | None

graph = StateGraph(AssessmentState)
graph.add_node("validate_photos", validate_photos)
graph.add_node("classify_defects", classify_defects)
graph.add_node("estimate_cost", estimate_cost)
graph.add_node("human_gate", human_gate)
graph.add_node("generate_report", generate_report)
graph.add_node("match_contractors", match_contractors)

graph.add_edge("validate_photos", "classify_defects")
graph.add_edge("classify_defects", "estimate_cost")
graph.add_conditional_edges(
    "estimate_cost",
    route_by_confidence,
    {"auto": "generate_report", "expert": "human_gate"}
)
graph.add_edge("human_gate", "generate_report")   # resumes after webhook
graph.add_edge("generate_report", "match_contractors")
graph.add_edge("match_contractors", END)
```

---

### 2.3 Vision LLM — Defect Classifier

Takes an array of base64-encoded photos + property metadata, returns structured JSON classifying defect type, severity, affected surface area estimate, and confidence score.

**Model routing — three providers:**

```python
def classify_defects(state: AssessmentState) -> AssessmentState:
    tier = get_user_tier(state["job_id"])
    if tier == "paid" and anthropic_available():
        result = anthropic_classify(...)   # Anthropic SDK
    elif openai_available():
        result = openai_classify(...)      # OpenAI SDK — cloud fallback
    else:
        result = qwen_classify(...)        # Ollama/HuggingFace Hub — GDPR tier
    ...
```

**Structured output prompt:**

```
You are a structural defect assessment assistant. Analyse the provided photos
of a building and return ONLY valid JSON matching this schema:

{
  "defect_type": "rising_damp" | "penetrating_damp" | "condensation_mold" |
                 "structural_crack" | "spalling_concrete" | "efflorescence" | "unknown",
  "severity": "cosmetic" | "moderate" | "urgent",
  "affected_surfaces": ["exterior_wall", "ceiling", "floor", ...],
  "confidence": 0.0–1.0,
  "visible_extent_sqm": <estimated affected area in m²>,
  "reasoning": "<one sentence>"
}

Do not include any text outside the JSON object.
```

---

### 2.4 Cost Estimator — RAG over Price Database

Given a classified defect + severity + location, retrieves relevant contractor price data from Qdrant and synthesises a cost range.

**Data source:**

- Cypriot construction price guides (architectcyprus.com publishes unit rates)
- Greek building cost databases (ergatika.gr unit cost tables)
- Manually curated from contractor quotes received via the service over time
- Each entry: `{defect_type, region, material, labour_rate_per_sqm, source, date}`

**RAG query pattern:**

```python
from langchain_qdrant import QdrantVectorStore
from langchain_core.prompts import ChatPromptTemplate

def estimate_cost(state: AssessmentState) -> AssessmentState:
    query = f"{state['defect_classification']['defect_type']} repair cost \
              {state['property_metadata']['region']} \
              {state['defect_classification']['severity']}"

    docs = vectorstore.similarity_search(query, k=5)

    prompt = ChatPromptTemplate.from_template("""
    Based on these contractor price references:
    {context}

    For a {severity} case of {defect_type} affecting ~{extent}m²
    in {region}, estimate the total repair cost range.
    Return JSON: {{"low": int, "high": int, "currency": "EUR", "basis": str}}
    """)
    ...
```

---

### 2.5 Human-in-the-Loop Gate (Expert Review)

When the AI confidence is below threshold or severity is urgent, the pipeline pauses and sends the job to the expert review queue. The expert logs into a minimal admin dashboard, sees photos + AI classification + cost estimate, adds their comments, and submits. A webhook resumes the LangGraph graph from the `human_gate` node.

**LangGraph interrupt pattern:**

```python
from langgraph.checkpoint.postgres import PostgresSaver

# Persist state to Postgres so interrupt survives server restarts
checkpointer = PostgresSaver.from_conn_string(settings.DATABASE_URL)

def human_gate(state: AssessmentState) -> AssessmentState:
    if not state.get("expert_review"):
        notify_expert(state["job_id"])
        raise NodeInterrupt("Awaiting expert review")
    return state  # Expert review is present — continue

@router.post("/webhook/expert")
async def expert_review_webhook(job_id: str, review: ExpertReview):
    graph.update_state(
        config={"configurable": {"thread_id": job_id}},
        values={"expert_review": review.dict()}
    )
    await graph.ainvoke(None, config={"configurable": {"thread_id": job_id}})
```

---

### 2.6 LLM Evaluation Layer

Automatically scores the quality of defect classifications against a ground-truth test set using DeepEval. Runs in CI on every model prompt change.

```python
from deepeval import evaluate
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase

correctness_metric = GEval(
    name="Defect Classification Accuracy",
    criteria="The predicted defect_type and severity match the ground truth \
              for the given building photos.",
    evaluation_params=["actual_output", "expected_output"],
    threshold=0.8
)

# Ground truth: 50 manually labelled photo sets
test_cases = load_ground_truth_dataset()
evaluate(test_cases, [correctness_metric])
```

---

### 2.7 Infrastructure & DevOps

All services run as containers. Local dev via Docker Compose; production on Azure Container Apps.

**docker-compose.yml services:**

```yaml
services:
  api:        # FastAPI app (REST + SSE streaming)
  worker:     # LangGraph pipeline (async task queue)
  frontend:   # Next.js
  qdrant:     # Vector DB (LangChain + LlamaIndex paths)
  ollama:     # Local LLM serving (Qwen2-VL — GDPR tier)
  postgres:   # LangGraph checkpoint store + main DB
  redis:      # Task queue broker
  mlflow:     # Experiment tracking — prompt versioning + metric logging
  caddy:      # Reverse proxy + HTTPS
```

**CI/CD (GitHub Actions):**

- On PR: run DeepEval test suite + RAGAS eval + MLflow regression check, pytest, type-check
- On merge to main: build Docker images → push to **Azure Container Registry** → deploy to **Azure Container Apps**
- Secrets: Stripe key, R2 + Azure Blob credentials, Anthropic key, OpenAI key (fallback)

---

## 3. Build Sequence

> **Principle:** Ship a working product at the end of every phase. Each phase adds one meaningful capability. Heavy frameworks (MLflow, LlamaIndex, RAG pricing, human gate) are deferred until the product earns them — they are not removed from the plan, just sequenced after real users exist.

---

### Phase 1 — MVP: Classify + Report, Free Tier (Weeks 1–3)

**Goal:** A real user can register, upload photos, and receive a defect classification report. No payments, no human gate. Limited free assessments per account to control cost and create scarcity.

**Pipeline:** `PhotoValidator → DefectClassifier → ReportGenerator`

**What's in:**

1. FastAPI project + Docker Compose (Postgres, Cloudflare R2, Caddy)
2. `PhotoValidator` node — MIME check, minimum count, **OWASP file upload validation**
3. `DefectClassifier` node — single provider to start (Anthropic Claude Vision); structured prompt with **injection defense prefix**; output: defect type, severity, confidence, affected area
4. `ReportGenerator` node — JSON → HTML → PDF via WeasyPrint; stored in R2; signed URL returned
5. SSE streaming endpoint (`POST /assess/{id}/stream`) — LangGraph `.astream_events()`; frontend shows live node progress
6. fe (Next.js) — photo upload wizard + live progress bar via `EventSource`; results page with PDF download
7. Auth — Google OAuth + JWT; registration required to submit
8. Free tier limit — 3 assessments per account; enforced in FastAPI before pipeline starts; count stored in Postgres
9. DE + RU + EN i18n — strings wired, lang switcher in UI
10. Email delivery of report (Resend) on completion
11. Deploy to VPS (not Azure yet — simpler, faster)

**What's deliberately out:**

- Cost estimation / RAG / Qdrant — report says "cost estimate: contact a contractor" as placeholder
- Human-in-the-loop gate — all assessments auto-complete
- Payments
- MLflow, DeepEval, LlamaIndex

**Deliverable:** Live URL. A stranger can register, upload 3 photos, and receive a PDF defect report within 30 seconds. Free, capped at 3 uses.

---

### Phase 2 — Cost Estimation via RAG (Weeks 4–5)

**Goal:** Reports include a repair cost range, not just a classification.

**Adds:** `CostEstimator` node between `DefectClassifier` and `ReportGenerator`

1. Seed Qdrant with 50 contractor price entries (Cyprus + Greece) — `{defect_type, region, material, labour_rate_per_sqm, source, date}`
2. Implement `CostEstimator` node — LangChain + Qdrant path (production); embed defect description → retrieve 5 price docs → LLM synthesises cost range as JSON `{low, high, currency, basis}`
3. Wire into the existing LangGraph graph; SSE events updated to include `cost_estimate` node
4. Report template updated to render cost range section

**What's deliberately out:** LlamaIndex parallel path — deferred to Phase 5

**Deliverable:** PDF reports now include a localised cost range.

---

### Phase 3 — Payments + Azure (Weeks 6–7)

**Goal:** Monetise. Users who want more than 3 free assessments pay. Deploy to Azure.

1. Stripe integration — free tier (3 uses), Scan €29 (unlimited basic), Assess €69 (cost range + priority), Verify €229 (expert sign-off — not yet implemented, sold as "coming soon")
2. `POST /pay/{job_id}` — Stripe checkout session; webhook updates job tier in Postgres
3. Free tier limit lifted for paying users; Anthropic tier unlocked (paying) vs. OpenAI fallback (free)
4. **Push Docker images to Azure Container Registry (ACR)**; deploy API to **Azure Container Apps**
5. CI/CD: GitHub Actions → ACR push → Container Apps rolling deploy

**Deliverable:** Live on Azure. Real payments accepted. First revenue.

---

### Phase 4 — Human Gate + Expert Verify Tier (Weeks 8–9)

**Goal:** Unlock the €229 Verify tier. High-severity or low-confidence cases routed to a human expert.

1. Add LangGraph Postgres checkpointer — state survives server restarts
2. Implement `human_gate` node — `NodeInterrupt` when confidence < threshold or severity == "urgent"
3. Minimal expert admin UI (Next.js, simple auth) — photo viewer + AI classification + cost estimate + comment form
4. Webhook endpoint to resume graph — **schema-validate all expert JSON before any LLM call**
5. Enable Verify tier in Stripe — €229 routes all jobs through expert gate regardless of confidence
6. Write `SECURITY.md` — attack surfaces, injection defense choices, EU AI Act risk class

**Deliverable:** End-to-end Verify flow working. Expert signs off, user gets countersigned PDF.

---

### Phase 5 — MLOps, Evaluation, LlamaIndex (Weeks 10–11)

**Goal:** Harden the AI layer. Use real submission data as ground truth.

1. Add MLflow to Docker Compose; wire into `classify_defects()` — log prompt version, model, confidence, eval score per run
2. Write first 20 ground-truth test cases from real Phase 1–3 submissions; run DeepEval baseline
3. Integrate DeepEval into GitHub Actions CI — fail build on accuracy < 80%
4. **MLflow CI check** — compare mean accuracy across last 10 runs; block merge on regression
5. Implement LlamaIndex path in `CostEstimator` — same Qdrant backend, same ground-truth queries
6. Add RAGAS evaluation on both RAG paths — faithfulness + answer relevance
7. Write `RAG_COMPARISON.md` — quality delta between LangChain and LlamaIndex paths
8. Add Braintrust experiment logging (third eval tool)
9. Add OpenAI SDK fallback + Qwen2-VL local path to `DefectClassifier` — completes the 3-SDK routing

**Deliverable:** Full MLOps loop. `RAG_COMPARISON.md` published. All three LLM SDKs active. CI-gated quality.

---

### Phase 6 — Contractor Network + Referral (Week 12+)

**Goal:** Tier 3 revenue stream. Contractor DB, referral tracking, on-site visit booking.

1. Contractor onboarding form + DB (region, speciality, contact)
2. `ContractorMatcher` LangGraph node — embed defect type, query contractor DB by location
3. Referral link generation with UTM + commission tracking
4. On-site visit booking flow (Verify tier upsell)

---

## 4. Technology Decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Orchestration | LangGraph | Handles interrupt/resume natively; explicit state graph is auditable |
| Vision LLM | Anthropic Claude Vision → GPT-4o → Qwen2-VL | 3-tier routing covers 3 major SDKs |
| RAG | LangChain+Qdrant (primary) + LlamaIndex (parallel) | Comparison is a standalone portfolio artifact |
| Multi-agent | LangGraph with conditional routing + human-in-the-loop | Covers the agentic orchestration pattern |
| Vector DB | Qdrant | Works with both LangChain and LlamaIndex paths |
| LLM Evaluation | DeepEval (CI gate) + RAGAS (retrieval quality) + Braintrust (experiment logging) | Full eval tooling spectrum |
| Experiment tracking | MLflow | LLMOps prompt versioning; CI regression gate |
| API protocols | FastAPI REST + SSE streaming | REST for users; SSE for real-time pipeline progress |
| Deployment | Azure Container Apps + ACR | Serverless Docker, no K8s overhead |
| be | FastAPI | Async-native; SSE streaming built-in. Django considered: its ORM/admin batteries don't help here — we need async SSE streaming, LangGraph async interrupt/resume, and direct asyncpg for the Postgres checkpointer. Django forces sync-to-async adapters for all three. |
| fe | Next.js | i18n built-in; SSR for multilingual SEO landing pages |
| PDF | WeasyPrint | Pure Python, no headless Chrome, GDPR-safe |
| Payments | Stripe | Stripe.js handles PCI compliance |
| Storage | Cloudflare R2 (primary) + Azure Blob (secondary) | R2 for cost; both S3-compatible |
| Checkpointing | Postgres | LangGraph's recommended persistent checkpointer; survives server restarts |
| Security | Prompt injection defense + OWASP file upload | Documented in SECURITY.md |

---

## 5. Framework & Tool Reference

| Tool | Category | One-line role in WallRay |
| --- | --- | --- |
| **LangGraph** | Orchestration | Stateful directed graph — handles conditional routing, human-in-the-loop interrupt, Postgres-persisted state |
| **LangChain** | Toolkit | Components used inside LangGraph nodes: prompts, vector store clients, embeddings |
| **LlamaIndex** | RAG framework | Parallel `CostEstimator` path via `VectorStoreIndex`; compared against LangChain path in `RAG_COMPARISON.md` |
| **FastAPI** | API layer | REST endpoints + SSE streaming (`/assess/{id}/stream`) |
| **Next.js** | fe | Consumer UI, expert dashboard, DE/RU/EN landing pages with SSR |
| **Qdrant** | Vector DB | Stores contractor price embeddings; used by both LangChain and LlamaIndex paths |
| **Ollama** | Local LLM serving | Runs Qwen2-VL on-prem for GDPR tier (zero API cost) |
| **Qwen2-VL** | Vision LLM | Local fallback model loaded via HuggingFace Hub / Ollama |
| **Anthropic SDK** | LLM provider | Paid-tier vision classification; best structured output |
| **OpenAI SDK** | LLM provider | Cloud fallback when local model unavailable |
| **HuggingFace Transformers** | Model loading | Loads Qwen2-VL weights from HF Hub |
| **MLflow** | LLMOps | Logs prompt version + model + confidence + eval score per run; CI regression gate |
| **DeepEval** | LLM evaluation | CI gate — fails build if classification accuracy drops below 80% |
| **RAGAS** | Retrieval evaluation | Scores `CostEstimator` RAG quality: faithfulness + answer relevance |
| **Braintrust** | Eval logging | Experiment logging alongside MLflow |
| **WeasyPrint** | PDF generation | Converts report JSON → HTML → PDF; pure Python, no headless Chrome |
| **Stripe** | Payments | Checkout session creation; Stripe.js handles PCI compliance |
| **Postgres** | Database | LangGraph checkpoint store + main application DB |
| **Redis** | Task queue | Broker for async pipeline jobs |
| **Docker** | Containerisation | All services run as containers; local dev via Docker Compose |
| **Azure Container Apps** | Deployment | Serverless Docker hosting for be |
| **Azure Container Registry** | Image registry | CI/CD pushes built images here before deploy |
| **Azure Blob Storage** | Object storage | Secondary storage; documents Azure SDK integration |
| **Cloudflare R2** | Object storage | Primary photo + report storage (S3-compatible, low cost) |
| **Caddy** | Reverse proxy | HTTPS termination for local and production |

---

## 6. Implementation Status

### Phase 1 — MVP: Classify + Report, Free Tier

- [x] FastAPI project scaffolded (app, config, CORS, `/health`)
- [x] JWT auth dependency (`deps.py`)
- [x] All Phase 1 dependencies declared (`pyproject.toml` — langgraph, anthropic, weasyprint, resend, stripe, boto3…)
- [x] Auth — Google OAuth + JWT minting to API token (`auth.ts`, `AuthS.ts`)
- [x] fe (Next.js) — photo upload wizard with drag-and-drop, file validation, thumbnails, remove (`PhotoUpload.tsx`)
- [x] i18n — EN / DE / RU strings wired (`I18nS.ts`) with lang switcher UI
- [x] Base UI system (Button, Card, Badge, DropZone, Progress, Stack, Row, Text, Thumbnail, StatusDot)
- [ ] Docker Compose (Postgres, R2, Caddy)
- [ ] `POST /upload` endpoint — file receive, MIME/OWASP validation, R2 storage, return `job_id`
- [ ] `POST /assess/{job_id}` — trigger LangGraph pipeline
- [ ] `GET /report/{job_id}` — poll status, return signed PDF URL
- [ ] `PhotoValidator` LangGraph node
- [ ] `DefectClassifier` LangGraph node (Anthropic Vision, structured prompt, injection defense)
- [ ] `ReportGenerator` LangGraph node (JSON → PDF via WeasyPrint, R2 store)
- [ ] SSE streaming endpoint (`/assess/{id}/stream`) + `EventSource` in fe
- [ ] Live progress bar in UI (currently `onSubmit` just `console.log`)
- [ ] Free tier limit (3 assessments per account, Postgres counter)
- [ ] Email delivery on completion (Resend)
- [ ] Deploy to VPS

### Phase 2 — Cost Estimation via RAG

- [ ] Qdrant seeded with 50 contractor price entries
- [ ] `CostEstimator` LangGraph node (LangChain + Qdrant)
- [ ] Cost range in SSE events + report template

### Phase 3 — Payments + Azure

- [ ] Stripe integration (checkout session, webhook, tier update)
- [ ] `POST /pay/{job_id}` endpoint
- [ ] Free tier lift for paying users / model routing by tier
- [ ] Azure Container Registry + Azure Container Apps deploy
- [ ] GitHub Actions CI/CD → ACR → Container Apps

### Phase 4 — Human Gate + Expert Verify Tier

- [ ] Postgres LangGraph checkpointer
- [ ] `human_gate` node with `NodeInterrupt`
- [ ] Expert admin UI (photo viewer + comment form)
- [ ] `POST /webhook/expert` endpoint (schema-validated, resume graph)
- [ ] Verify tier in Stripe (€229)
- [ ] `SECURITY.md`

### Phase 5 — MLOps, Evaluation, LlamaIndex

- [ ] MLflow in Docker Compose + wired into `classify_defects()`
- [ ] DeepEval ground-truth test cases + CI gate
- [ ] MLflow CI regression check
- [ ] LlamaIndex path in `CostEstimator`
- [ ] RAGAS evaluation on both RAG paths
- [ ] `RAG_COMPARISON.md`
- [ ] Braintrust logging
- [ ] OpenAI + Qwen2-VL fallback paths in `DefectClassifier`

### Phase 6 — Contractor Network

- [ ] Contractor onboarding + DB
- [ ] `ContractorMatcher` LangGraph node
- [ ] Referral link + UTM tracking
- [ ] On-site visit booking flow
