# AI Assessment Pipeline Rework — Implementation Plan

**For a flat checklist of what's actually left to build** (vs. this doc's full rationale/design),
see `docs/tech/AI_ASSESSMENT_REWORK_TODO.md`.

Replaces `docs/tech/AI_ASSESSMENT_ALGO.md` (deleted — its ClusterRegistry/Cluster-Match/Template-
Instantiation design is not what this rework builds; see "Why not the old design" below). The
ClusterRegistry *concepts* still used by the manual photo-triage workflow (maturity levels,
expert dispositions, no-false-precision) now live in `CLUSTERS.md` instead.

---

## Context — why this rework

Feeding `docs/business/AI_VS_EXPERT_STRATEGY.md` directly to Fable 5 as a one-shot prompt (photos

+ the full causal-reasoning framework, single strong model) produced a structured, specific
inspection-quality result (Befund / Ursache / Schweregrad / Prüfung). The same photo run through
the live app produced generic boilerplate. Tracing the app's pipeline
(`be/app/adapters/vision_llm/anthropic.py`, `be/app/application/pipeline/`) found a **double
information bottleneck**, not one:

1. `classify()` (`anthropic.py:77`) — cheap model (Haiku), a system prompt with **zero domain
   content** (no causal-reasoning framework, no context signals), output capped at a single
   keyword + severity band + "one or two sentences." This compresses the photo into ~20 words.
2. `synthesize()` (`anthropic.py:130`), called from both `report_generator.py` (no-expert path)
   and `generate_report.py` (post-expert path) — runs the strong model (Sonnet 5), but is only
   ever given the ~20-word text output of step 1. **It never receives the photos.** However smart
   the model, it can only polish an already-generic seed.

Neither call site is given any of the causal-reasoning framework that made the direct Fable test
good. This plan fixes both bottlenecks and adds a bounded, one-round customer clarification loop
— without introducing the ClusterRegistry machinery the old design doc assumed.

## Why not the old design (`AI_ASSESSMENT_ALGO.md`)

That doc's shape — Feature Extraction → Cluster Match → Template Instantiation / Fuzzy Estimation
— is built around an expert-curated, versioned ClusterRegistry compounding over time. It's a
legitimate future direction once enough resolved cases exist, but it's a different, bigger bet
than what's needed to close the Fable-quality gap right now. This rework is deliberately simpler:
one rich reasoning call (not a match-then-template pipeline), severity/cost still comes from the
model's own reasoning, not a matched template. Consistency/compounding across cases is a
trade-off knowingly given up here in exchange for per-case reasoning depth today.

---

## Core principles

1. **Images travel with the state through every reasoning call.** No node hands a later node a
   text summary of a photo and expects it to reason as if it had seen the photo. This is the
   single fix that matters most.
2. **The model writes customer/expert-facing prose natively in the target language, in the same
   call** — never draft-in-English-then-translate. Already true of `synthesize()` today
   (`_SYNTHESIS_SYSTEM_PROMPT`'s `CRITICAL LANGUAGE RULE`); carried forward unchanged. System
   prompts/instructions stay in English regardless of output language (see
   `docs/tech/LANGUAGE_PLAN.md` Session 6) — that's the pattern that already works, not a gap to
   fix.
3. **Simple over taxonomy.** No ClusterRegistry, no confidence-floor auto-approval, no template
   instantiation. Severity/cost/reasoning come from one strong model's judgment per case.
4. **The clarification loop is reserved, not built.** `customer_after_questions` exists as a
   config value defaulting to `0` so raising it later doesn't require restructuring the graph.

---

## Node design

Replaces `photo_validator → defect_classifier → [expert_notifier | report_generator]`
(`be/app/application/pipeline/graph.py`) with the following abstract shape — one connected graph,
not the two disjoint fragments this looked like before:

```
intake_gate
   │
   ▼
context_intake
   │
   ▼
ai_assessment ◄────────────────────────────┐
   │                                        │
   ▼                                        │
[branch: loop_count < customer_after_questions?]
   │yes                              │no    │
   ▼                                 │      │
await_customer_answers               │      │
   │                                 │      │
   ├─accept ─────────────────────────┴──────┘
   │      │
   │      ▼
   │  report_generator  (AI-only render, JobStatus.complete) ──► END
   │
   ├─reply ─────────────────────────────────► loop back to ai_assessment
   │        (full call, photos included)
   │
   └─request_expert_review ─────────────────► expert_notifier
                                                     │
                                 (expert submits notes — outside the graph,
                                       see `generate_report.py`)
                                                     ▼
                                              expert_synthesis
                                                     │
                                                     ▼
                                              report_generator  (final render — the
                                                                  only PDF this job
                                                                  gets on this path)
```

Note the shape change from the original version of this diagram: expert review is no longer a
branch *after* `report_generator` — it's a third outcome of `await_customer_answers`, decided
*before* any PDF is rendered. See "Amendment — expert review request moves to
`await_customer_answers`, not upload" near the end of this doc.

### `intake_gate` (replaces `photo_validator`)

+ Keeps today's mechanical checks (magic bytes, min dimension) as a cheap pre-filter.
+ Adds one batched vision call (Haiku) across all photos: (a) **is this a building/defect photo
  at all** — reject junk (selfies, screenshots, unrelated objects) before any expensive reasoning;
  (b) **role tag** per photo — `close_up | context | repeat_location` (the `PhotoRole` enum
  already exists in `be/app/domain/job.py:14` but is unused beyond a filename-heuristic stub in
  today's validator).
+ Output: `validation_passed`, `validation_errors` (unchanged shape), plus new `photo_roles: dict[str, PhotoRole]`.

### `context_intake` (no LLM call — state assembly only)

+ Pulls whatever structured facts the intake form already collects (floor level, building age,
  description text) into `context_signals: dict[str, Any]`. This is the seed the clarification
  loop appends to later.

### `ai_assessment` (replaces `defect_classifier`, absorbs what `synthesize()` did)

+ One call, strong model (Sonnet 5 — `settings.anthropic_assessment_model`), given: **all photos**
  + `context_signals` + a system prompt carrying the causal-reasoning framework (the actual
  content that made the direct Fable test work — Befund → Ursache → Schweregrad →
  Prüfung-scaffold reasoning).
+ Output, structured:
  + `defect_type`, `severity` — unchanged controlled vocab.
  + `reasoning_en` — the structured English writeup (successor to today's `classification_notes`;
    stable internal representation, same role `classify()`'s notes play today — never shown to
    the customer directly, the only thing `translate()` ever runs on).
  + `summary` — customer-facing prose, natively generated in `customer_language` in this same
    call (same contract as today's `synthesize()`).
  + `confidence: float`.
  + `verification_items: list[{text: str, kind: "customer_question" | "photo_request" | "expert_only_check"}]`
    — see "Typed verification items" below. Always populated (cost-free — same call), acted on
    only once the loop is enabled.

### Branch — clarify or proceed

+ `loop_count < settings.customer_after_questions` → `await_customer_answers`. Not gated on
  `verification_items` containing a `customer_question` — the customer always gets the one round,
  whether or not the model flagged anything worth asking. `customer_question`-kind
  `verification_items` are passed through as suggested prompts in the reply UI (see below), not a
  precondition for showing it.
+ Else → `report_generator`.
+ Pure routing, same shape as the existing `request_expert_review?` conditional edge
  (`graph.py:43-46`).

### `await_customer_answers`

With `customer_after_questions = 1` this fires on every job, exactly once.

+ Pauses the job and shows the customer the `summary` `ai_assessment` just produced (already in
  `customer_language`; `report_key` is still null — no PDF has been rendered yet), alongside a
  **free-text reply box** — not a list of questions to answer one by one. Any `customer_question`-
  kind `verification_items` from this round are shown as suggested prompts inside that box (e.g.
  "You could tell us: is there a drip irrigation line against this wall?") to help the customer
  decide what's worth adding. The customer can write anything, or nothing.
+ **This is also where the customer decides whether to request expert review** — not at upload.
  Alongside the reply box, an explicit **"Request expert review"** action with an expert picker
  (the same dropdown `NewReportPage.tsx` shows at upload today) is offered whenever experts exist
  to assign. See "Amendment — expert review request moves to `await_customer_answers`, not
  upload" near the end of this doc for the full rationale and change list.
+ Three outcomes, all terminal for this round:
  + **Accept** (empty reply, or an explicit "use this report" action) → straight to
    `report_generator` with `defect_classification` unchanged. **No LLM call at all** — declining
    costs nothing, which is the point.
  + **Reply** (non-empty free text) → append `{round: loop_count, customer_reply: text}` to
    `qa_history`, fold `text` into `context_signals`, increment `loop_count`, loop back to
    `ai_assessment` for one full re-run — photos included, same as every other call in this
    pipeline, never a text-only rerun. Since `customer_after_questions = 1`, this can only happen
    once per job; after the second `ai_assessment` call the branch routes straight to
    `report_generator` regardless of what `verification_items` come back this time.
  + **Request expert review** (picks an expert, no reply text) → persists
    `request_expert_review=True` + `assigned_expert_id` on the job (no longer set at upload) and
    routes **directly to `expert_notifier`, skipping `report_generator` entirely**. No AI-only PDF
    is ever rendered on this path — the first PDF the job gets is the one `generate_report.py`
    produces after the expert submits notes. No new strong-model call either; the assessment
    already exists from this round's `ai_assessment`.
+ Needs `JobStatus.awaiting_customer_input` (`be/app/domain/job.py`), a
  `POST /jobs/{id}/respond` endpoint (`be/app/api/routes/jobs.py`, body
  `{reply: str | null, request_expert_review: bool = False, assigned_expert_id: str | null = None}`
  — empty `reply` with `request_expert_review=False` triggers accept, non-empty `reply` triggers
  regenerate, `request_expert_review=True` triggers the expert path; the three are mutually
  exclusive and validated server-side), and LangGraph checkpointing to persist state across the
  pause (the customer may take minutes or days to respond).
+ No new model call is introduced by the accept/reply/request-expert choice itself — that's a UI
  decision. The only new call is the optional full `ai_assessment` re-run on reply, already the
  strong-model call in this design. `intake_gate` stays on the cheap model regardless; nothing
  about this loop needs a strong model for anything other than the reasoning re-run itself.

### `report_generator`

+ Renders whatever the latest `ai_assessment` output is — same rendering/upload logic as today
  (`report_generator.py:42-53`), but the `synthesize_report()` call it currently makes is gone;
  `ai_assessment`'s output is already the final AI-only assessment.

### `expert_notifier` / `expert_synthesis` (fixes the second bottleneck)

+ `expert_notifier` unchanged in shape (`expert_notifier.py`), but no longer reached via a graph
  conditional edge — the graph itself never routes to it (see "Amendment" below). It's invoked
  directly, the same way `report_generator` already is in `RespondToJob._accept()`, from a new
  `RespondToJob._request_expert()` path.
+ The expert-review-complete path (`be/app/application/generate_report.py`, invoked outside the
  graph after an expert submits notes) currently calls `synthesize_report()` with **text only**
  (`generate_report.py:45-53` passes `initial_notes`, never photos). Replace with
  `expert_synthesis`: same strong-model call shape as `ai_assessment`, but now also given
  `expert_notes` with explicit priority instruction — **and the photos, every time**. Produces the
  final `DefectClassification` (`summary`, `summary_expert` per existing two-language contract in
  `LANGUAGE_PLAN.md` Session 4 — unchanged).

### Typed verification items

The model's own "what to check further" output (e.g. moisture-meter readings at three heights,
"photograph the wall's interior side," "what year was this built?") mixes three different kinds
of follow-up that must not be conflated:

+ `customer_question` — the customer can answer directly (building age, "is there a drip
  irrigation line against this wall?"). Surfaced to the customer in `await_customer_answers`, but
  as a suggested prompt in a free-text box, not a form field requiring a per-item answer.
+ `photo_request` — needs a new photo, not a text answer (e.g. "photograph the interior wall
  directly behind this location"). Not wired to anything yet; named now so it's never confused
  with a text question later.
+ `expert_only_check` — needs a tool/person on site (moisture meter, opening a section). Never
  shown to the customer. Surfaces in the report's own "further verification" section as-is (this
  is what the direct Fable test's point 4 already did), and is passed into `expert_synthesis` as
  context if expert review is requested.

---

## State changes (`be/app/application/pipeline/state.py`)

Add to `AssessmentState`:

```python
photo_roles: dict[str, str]          # PhotoRole per photo_key
context_signals: dict[str, Any]      # floor_level, building_age, description, + accumulated Q&A
verification_items: list[dict]       # {text, kind} — kind: customer_question | photo_request | expert_only_check
qa_history: list[dict]               # {round, customer_reply} — free-text replies, not per-item answers
loop_count: int                      # derived as len(qa_history) on resume, not stored independently
reasoning_en: str | None             # structured internal writeup, successor to classification_notes
confidence: float | None
api_call_count: int                  # every Anthropic call this job has made, across all nodes — see "Anthropic API call cap" below
```

`classification_notes` stays as the DB column name for backward compatibility (avoids a rename
migration); `reasoning_en` is the in-state/in-model name, mapped to that column on persist —
same pattern `defect_classifier.py:24` already uses.

## Domain model (`be/app/domain/job.py`)

`DefectClassification` gains `reasoning_en: str | None` and `verification_items: list[dict] | None`.
`Job` gains `context_signals: dict[str, Any] | None` and `qa_history: list[dict] | None` (both JSON
columns, mirroring `JobRow.photos` pattern in `orm_models.py:41`) — no separate `loop_count`
column; it's derived as `len(qa_history)` on resume. `JobStatus` gains `awaiting_customer_input`.

## Settings (`be/app/core/config.py`)

```python
customer_after_questions: int = 1     # max clarification-loop rounds; customer gets exactly one reply-or-accept round
anthropic_max_calls_per_job: int = 5  # hard ceiling on Anthropic calls per job — see "Anthropic API call cap" below
```

## ORM / migration (`be/app/adapters/persistence/orm_models.py`)

Add to `JobRow`: `context_signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)` and
`qa_history: Mapped[dict | None] = mapped_column(JSON, nullable=True)`. Run
`alembic revision --autogenerate` per `CLAUDE.md`'s schema-change workflow once the model change
lands.

## Vision LLM port + adapter (`be/app/domain/ports/vision_llm.py`, `anthropic.py`)

Replace `classify()`/`synthesize()` with:

```python
async def assess(
    self, photo_keys: list[str], context_signals: dict[str, Any],
    customer_language: str = "en",
) -> Assessment: ...  # defect_type, severity, reasoning_en, summary, confidence, verification_items

async def expert_synthesize(
    self, photo_keys: list[str], context_signals: dict[str, Any],
    prior_reasoning: str, expert_notes: str,
    customer_language: str = "en", expert_language: str = "en",
) -> DefectClassification: ...  # summary, summary_expert, expert_note_localized — same as today's synthesize()
```

`translate()` is unchanged — still the only place a draft-then-translate pattern is legitimate
(expert email localization, admin GET), per `LANGUAGE_PLAN.md` Session 6.

---

## Model costs (reference)

**Decision:** `ai_assessment` / `expert_synthesize` run on **Fable 5** (this is the model that
produced the good direct-test result — no fallback tier, it *is* `anthropic_assessment_model`
now), `intake_gate` runs on **Haiku 4.5** (decent, cheap — junk-photo/role-tagging is not a task
that needs the strong model), and `customer_after_questions = 1` (the customer gets exactly one
reply-to-a-question round before the loop closes).

| Model | Input | Output | Role here |
|---|---|---|---|
| Claude Haiku 4.5 | $1 / MTok | $5 / MTok | `intake_gate` — validity + role-tagging vision call |
| Claude Fable 5 | $10 / MTok | $50 / MTok | `ai_assessment`, `expert_synthesize` — every reasoning call, including the one clarification re-run |

### Per-report cost estimate

Assumptions (stated because they drive the number directly): **4 photos/report** (close-up +
context, sometimes a repeat-location pair), **~1,500 tokens/photo** (typical phone photo resized
to Claude's ~1568px long-edge cap), **~2,500-token system prompt** for `ai_assessment` (it has to
carry the full causal-reasoning framework — that's the whole point of this rework), no prompt
caching applied (conservative; see note below).

| Scenario | Calls | Est. cost/report |
|---|---|---|
| AI-only, customer doesn't use the question | `intake_gate` + 1× `ai_assessment` | **~$0.14** |
| AI-only, customer uses their one reply | `intake_gate` + 2× `ai_assessment` (loop re-runs the full call, photos included) | **~$0.27** |
| + expert review requested | above + 1× `expert_synthesize` (photos + expert notes, two-language output) | **~$0.31–$0.44** |

Rough breakdown per `ai_assessment`/`expert_synthesize` call: ~8,700 input tokens (photos + system
prompt + context) × $10/MTok ≈ $0.09, plus ~900 output tokens × $50/MTok ≈ $0.045 → **~$0.13-0.17
per call**. `intake_gate` is ~$0.008 and roughly a rounding error next to the Fable 5 calls.

The clarification loop's second `ai_assessment` call repeats the same photos + system prompt as
the first — a real candidate for prompt caching (5-min cache) once the loop is actually built,
which would cut that second call's cost by roughly 80-90% on the cached portion. Not counted above
since caching isn't in this plan's scope yet.

### Anthropic API call cap — manual ceiling as a security/cost safety net

`loop_count < customer_after_questions` is a *design* bound on the clarification loop — it assumes
the branch logic behaves correctly. It is not a defense against a bug in that branch (an
off-by-one, a checkpoint restored to the wrong point, a retry policy re-entering the graph), or
against direct abuse of `POST /jobs/{id}/respond` bypassing whatever the UI intends. Every
Anthropic call costs real money at Fable 5 rates (~$0.13–0.17/call) — a runaway loop or a scripted
flood of replies is a cost-exhaustion vector, not just a correctness bug, so it gets its own,
independent, hard-coded limit rather than relying on the loop's own bookkeeping being correct.

+ `AssessmentState.api_call_count` (added above) increments **once per Anthropic API call**,
  regardless of which node makes it — `intake_gate` (Haiku), `ai_assessment` (Fable 5, every
  invocation including clarification re-runs), `expert_synthesize` (Fable 5). One counter, not
  per-node counters, because the risk being defended against is total spend on this job, not any
  single node's behavior.
+ Checked at the top of every node that's about to make an Anthropic call: if
  `api_call_count >= settings.anthropic_max_calls_per_job`, the node fails the job outright
  (`JobStatus.failed`, a distinct logged reason — e.g. `"api_call_limit_exceeded"`) instead of
  making the call. This is a hard stop, not a retry-with-backoff — the assumption on trip is that
  something is behaving unexpectedly, not that the API is transiently unavailable.
+ Default `5` = the worst-case intended path (`intake_gate` + `ai_assessment` ×2 under
  `customer_after_questions = 1` + `expert_synthesize`) plus one call of headroom — tight enough to
  catch a genuine runaway, loose enough not to false-positive on the documented flow.
+ This is deliberately independent of the free-tier upload limit already enforced client-side
  (`FreeTierError` / 402 in `JobS.ts:44-51`) — that gates *how many jobs* a free user can create;
  `api_call_count` gates *how many model calls a single job* can rack up once it exists, and
  applies regardless of tier.
+ Enforcement lives server-side in the graph, not in the UI or the endpoint layer — a compromised
  or scripted client hitting `/respond` directly still can't push a job past the ceiling.

---

## File-by-file summary

| File | Change |
|---|---|
| `be/app/application/pipeline/nodes/photo_validator.py` | rename/extend → `intake_gate`, add vision call for validity + role tagging |
| `be/app/application/pipeline/nodes/defect_classifier.py` | replace with `ai_assessment` node calling `vision_llm.assess()` |
| `be/app/application/pipeline/nodes/report_synthesizer.py` | delete — `ai_assessment` produces the final AI-only assessment directly |
| `be/app/application/pipeline/nodes/report_generator.py` | drop the `synthesize_report()` call; render `state["defect_classification"]` as-is |
| `be/app/application/pipeline/nodes/expert_notifier.py` | unchanged |
| `be/app/application/pipeline/nodes/await_customer_answers.py` | new — pauses on `JobStatus.awaiting_customer_input`, resumes on accept (→ `report_generator`) or reply (→ `ai_assessment`) |
| `be/app/application/generate_report.py` | replace `synthesize_report()` call with `expert_synthesize()`, now passing photo bytes |
| `be/app/application/pipeline/graph.py` | wire `intake_gate` → `context_intake` → `ai_assessment` → branch (`loop_count < customer_after_questions`) → `await_customer_answers` ↔ `ai_assessment` → `report_generator` |
| `be/app/application/pipeline/state.py` | additions above |
| `be/app/domain/job.py` | `DefectClassification`/`Job` additions above, `JobStatus.awaiting_customer_input` |
| `be/app/api/routes/jobs.py` | new `POST /jobs/{id}/respond` endpoint (`{reply: str \| null}`) |
| `be/app/adapters/persistence/orm_models.py` | `JobRow.context_signals`, `JobRow.qa_history`, migration |
| `be/app/adapters/vision_llm/anthropic.py` | new `_ASSESS_SYSTEM_PROMPT` (carries the causal-reasoning framework), new `_EXPERT_SYNTHESIS_SYSTEM_PROMPT`, implement `assess()`/`expert_synthesize()`, drop `classify()`/`synthesize()` |
| `be/app/core/config.py` | `customer_after_questions: int = 1`, `anthropic_max_calls_per_job: int = 5` |
| every pipeline node that calls `vision_llm` (`intake_gate`, `ai_assessment`) + `generate_report.py` (`expert_synthesize`) | check + increment `state["api_call_count"]` against `settings.anthropic_max_calls_per_job` before calling; fail the job (`JobStatus.failed`, reason `api_call_limit_exceeded`) if at the ceiling |
| `be/tests/fakes.py` | `VisionLLMStub.assess()`/`expert_synthesize()` replacing `classify()`/`synthesize()` |
| `be/tests/test_pipeline.py` | update node-name assertions; add a photo-rejection-at-intake test, a `verification_items` typing test, an accept-vs-reply `await_customer_answers` test, an `api_call_count` ceiling test |

---

## Frontend impact (`fe/ui/business/`) — flagged, not itemized in the table above

The be/-focused file table above doesn't cover it, but this rework changes the shape of the
product flow, not just the backend internals — three FE files assume the old
classify-then-triage pipeline and need to move with it, not just get new copy.

### `NewReportPage.tsx` — expert review moves from upload-time to the `await_customer_answers` screen

Today `requestExpertReview` + the assigned-expert `Select` (`NewReportPage.tsx:115-172`) are
decided **before upload**, and `request_expert_review` rides along in the upload FormData
(`JobS.ts:75,83`) into `Job.request_expert_review`/`assigned_expert_id`, inert until `graph.py`'s
`_expert_branch` or `RespondToJob._accept()` reads it much later — the customer never sees or
confirms this choice at the point their report actually becomes visible. That made sense when
`classify()` produced almost nothing to react to — there was no AI verdict yet to decide against.
Under this rework, `ai_assessment` produces a full causal-reasoning report (`defect_type`,
`severity`, `summary`) before any human is involved; the customer should see *that* first, then
decide whether to escalate — matching `BUSINESS_PLAN.md` Section 5's package structure, where Scan
(AI-only) is the default and Assess (AI + expert) is an upgrade chosen *after* seeing the verdict,
not a checkbox ticked blind at intake.

Move the expert-request UI (`NewReportPage.tsx:115-172`) off the upload form entirely and onto the
`await_customer_answers` screen (`awaiting_customer_input` status), alongside the reply box —
**not** onto the `complete` report view, and **not** via a new endpoint: it's a third action on
the existing `POST /jobs/{id}/respond`. Full details in "Amendment — expert review request moves
to `await_customer_answers`, not upload" below. `assignedExpertId`/`requestExpertReview` are
removed from `JobS.ts`'s `upload()` entirely — the upload form no longer collects them at all.

### `ExpertReviewPage.tsx` — no more triage; the expert reviews an already-good report

`ReportGallery` (shared by both the customer and expert pages via `ReportView`) titles its AI
section `expert_review_ai_section` and shows `defect_type` + `severity` +
`classification_notes_localized` (`ReportView.tsx:61-113`) — triage framing built for the old
`classify()` output (a keyword + one or two sentences the expert had to make sense of cold). Under
this rework there's no separate "raw triage" stage — `ai_assessment`'s `summary` is already the
customer-facing report, and `reasoning_en` (successor to `classification_notes`, see "State
changes" above) is the structured writeup the expert should actually see, not a truncated
classification badge. Adjust `ReportGallery` to show `reasoning_en` as "AI assessment" for the
expert and drop any copy implying first-pass triage — the expert is confirming/refining a complete
assessment, not building one from a keyword.

### `ReportView.tsx` — collapse the two-summary split; add the clarification-loop UI

`ReportGallery` ("AI classification") and `ReportSynthesis` ("Final review", `report.summary`,
`ReportView.tsx:115-129`) exist as two separate cards because today `classify()` and `synthesize()`
are genuinely different-quality outputs. Once `ai_assessment` produces final-quality `summary` on
the very first pass, that split reads as "rough draft vs. polished" when it's really the same
report shown twice. Reframe rather than duplicate: `ReportGallery` → photos + `reasoning_en`
(internal/expert-facing detail), `ReportSynthesis` → `summary` (the customer's actual report) —
not "AI classification" vs "final review."

Also needs the `await_customer_answers` UI from "Node design" above: once `ai_assessment`
finishes and before `complete`, show the free-text reply box + accept/regenerate actions. Requires
a new visual state for `JobStatus.awaiting_customer_input` in `deriveVisualState`
(`ReportView.tsx:22-30`), alongside `uploading | processing | expert_review | complete | failed`.

---

## Amendment — expert review request moves to `await_customer_answers`, not upload

**Status: implemented.** See `docs/tech/AI_ASSESSMENT_REWORK_TODO.md` for the file-by-file
checklist; `qa:be`/`qa:fe` pass. `mise run fe-e2e` (including the rewritten
`expert-review.spec.ts`) and the manual walkthroughs in that TODO's "Verification" section are
still outstanding runtime checks.

### Why

Today `request_expert_review`/`assigned_expert_id` are chosen on the upload form, before a single
photo has been reasoned about, and stored inert on the `Job` row. Two places read them much later
without the customer ever re-confirming: `graph.py`'s `_expert_branch` (only reached on the
resumed-after-reply graph path, i.e. after `RespondToJob._reply()` re-invokes `build_resume`) and
`RespondToJob._accept()`. That's the "hidden trigger" this amendment removes — a checkbox ticked
blind at intake silently deciding, minutes or days later, whether a human gets pulled in, with no
chance for the customer to change their mind once they've actually seen the AI's assessment.

It also wastes a render: `report_generator` always produces and stores an "AI-only" PDF
(`JobStatus.complete`) even when `request_expert_review` is true, immediately followed by
`expert_notifier` overwriting status to `expert_review` — a PDF nobody sees, generated and
discarded on every expert-review job today.

The fix: move the decision to the one moment the customer has actually seen something to decide
against — `await_customer_answers`, right after `ai_assessment` produces `summary` and before
`report_generator` ever runs. `report_key` is still null at this point ("the first report is
visible but not generated in pdf"), consistent with this doc's core principle that no node should
act on a stand-in for something it should reason over directly — here, no *decision* should be
made on a stand-in (a pre-assessment checkbox) for something the customer should actually see
first. The customer picks one of three explicit actions there: accept, reply, or request expert
review — never a flag set before any evidence existed.

### Node design change

`await_customer_answers` gains a third outgoing edge (see the updated diagram in "Node design"
above). `report_generator`'s conditional edge to `expert_notifier` (the old `_expert_branch`) is
deleted — `report_generator` is now reached only via **accept**, and is terminal (→ END).
`expert_notifier` is reached only via **request expert review**, directly, skipping
`report_generator`.

### UI interaction (`RespondPanel`)

Checking "Request expert review" **swaps the textarea out entirely** rather than leaving it
visible alongside the picker — reply and expert-request are mutually exclusive actions on the same
endpoint (see "Out of scope" below), and hiding the textarea makes that obvious instead of leaving
the customer to guess whether a typed comment is still going to be sent.

+ **Default mode**: `Textarea` (existing, `report_respond_placeholder`) + suggested prompts
  (existing) + `[Accept report]` / `[Send comment]` buttons (existing, unchanged), plus a new
  `[ ] Request expert review instead` checkbox beneath those.
+ **Checked mode**: checking it replaces the textarea and the accept/send buttons with an expert
  `Select` (same options `NewReportPage.tsx` fetches today via `ExpertS.useExperts()`) + a price
  disclosure (**€49**) + a `[Request expert review →]` submit button, disabled until an expert is
  chosen (mirrors the `expertRequiredError` validation removed from `NewReportPage.tsx`), plus the
  checkbox itself (now checked) to uncheck and return to default mode.
  **Pricing note:** €49 matches `BUSINESS_PLAN.md:254`'s Assess (AI + expert review) price —
  updated there to launch pricing set at Billy's per-case cost (see that doc's Section 5 pricing
  note). No divergence to reconcile: the in-app price and the published price are the same figure.
+ New local state in `RespondPanel` (`ReportView.tsx`): `requestingExpert: boolean` (the
  checkbox), `assignedExpertId: string` (the picker selection), `expertRequiredError: boolean`
  (validation) — the same three pieces of state `NewReportPage.tsx` already had, just relocated.
  The existing `reply` state is only read/sent when `requestingExpert` is `false`.
+ Submit dispatches exactly one of three payload shapes to `ReportS.useRespond()` depending on
  mode: `{ reply: null }` (accept), `{ reply: text }` (send comment), or
  `{ requestExpertReview: true, assignedExpertId }` (request expert) — never a combination.

### API / state changes

+ `POST /jobs/{id}/respond` body becomes
  `{reply: str | null, request_expert_review: bool = False, assigned_expert_id: str | null = None}`
  — the three fields form one mutually-exclusive action, not independent flags; validated
  server-side (mirrors the `request_expert_review and not assigned_expert_id` check
  `upload_job.py:124` already does at upload — that check moves here, since upload no longer takes
  these params).
+ `RespondToJob.run()` dispatches three ways instead of two: `request_expert_review=True` →
  `_request_expert()` (new); non-empty `reply` → `_reply()` (unchanged); else → `_accept()`
  (unchanged shape, but loses the `if job.request_expert_review: notify(...)` block at
  `respond_to_job.py:96` — accept never triggers expert now, that's a separate action).
+ New `RespondToJob._request_expert(job, assigned_expert_id)`: persists
  `request_expert_review=True, assigned_expert_id=...` via `job_repo.update_status`, builds state,
  calls `expert_notifier` directly (imported and invoked the same way `report_generator` already
  is in `_accept()` — not through the graph), then `increment_count` — this is the terminal
  free-tier-counted action on this path, since no AI-only render precedes it (mirrors the comment
  already in `generate_report.py:104-105` about not double-counting).
+ `AssessmentState.request_expert_review`/`assigned_expert_id` (`state.py:11-12`) stay in the
  state shape — `expert_notifier` still reads them — they're just never populated from the graph's
  own entry state anymore (`run_assessment.py` drops that seeding), only set explicitly by
  `RespondToJob._request_expert()` before calling `expert_notifier`.
+ No new `Job`/ORM fields — `request_expert_review`/`assigned_expert_id` already exist
  (`orm_models.py:49,52`); they're populated later instead of at job creation.

### File-by-file changes

| File | Change |
|---|---|
| `be/app/api/schemas.py` | `RespondRequest` gains `request_expert_review: bool = False`, `assigned_expert_id: str \| None = None` |
| `be/app/api/routes/jobs.py` | pass the two new fields through to `RespondToJob.run()` |
| `be/app/application/respond_to_job.py` | three-way dispatch in `run()`; new `_request_expert()`; drop the expert check from `_accept()` |
| `be/app/application/pipeline/graph.py` | delete `_expert_branch`; `report_generator`'s conditional edge becomes `g.add_edge("report_generator", END)`; drop `expert_notifier`'s node registration from `_wire_downstream_of_assessment` (no longer graph-reachable — called directly instead, like `report_generator` is in `respond_to_job.py`) |
| `be/app/application/upload_job.py` | drop `request_expert_review`/`assigned_expert_id` params and the `upload_job.py:124` validation (moves to `respond_to_job.py`) — `Job` created with defaults |
| `be/app/api/routes/upload.py` | drop the two form fields |
| `be/app/application/run_assessment.py` | drop the now-dead `request_expert_review=job.request_expert_review, assigned_expert_id=job.assigned_expert_id` seeding into the initial graph state |
| `fe/ui/business/NewReportPage.tsx` | delete the expert checkbox/select block (`115-172`), its three state vars (`requestExpertReview`, `assignedExpertId`, `expertRequiredError`), the `experts`/`ExpertS.useExperts()` import, and the two args passed to `upload.mutate` |
| `fe/ui/business/ReportView.tsx` | `RespondPanel` gains `requestingExpert`/`assignedExpertId`/`expertRequiredError` local state, imports `ExpertS` and calls `useExperts()`, renders the default-vs-checked mode split from "UI interaction" above, gated on `experts.length > 0` same as `NewReportPage.tsx` did |
| `fe/services/business/JobS.ts` | `upload()` drops `assignedExpertId`/`requestExpertReview` params and the two `formData.append` calls; `respond()` signature changes from `(id, reply, token)` to `(id, body: { reply: string \| null } \| { requestExpertReview: true; assignedExpertId: string }, token)` |
| `fe/services/business/ReportS.ts` | `useUpload`'s mutation input type drops the two fields; `useRespond`'s mutation input type changes from `reply: string \| null` to the new union type, passed through to `JobS.respond()` |
| `fe/types/api.ts` | regenerate from the updated OpenAPI schema (`RespondRequest` gains the two fields) — auto-generated, do not hand-edit |
| `fe/services/tech/i18n/en.ts` | reuse `report_request_expert`, `report_request_expert_hint`, `report_select_expert`, `report_expert_required` (relocated, not new copy); add `report_request_expert_action` ("Request expert review") and `report_request_expert_price` ("€49") |
| `fe/services/tech/i18n/de.ts` | same key changes, German copy |
| `fe/services/tech/i18n/ru.ts` | same key changes, Russian copy |
| `be/app/domain/job.py` | no field changes — `request_expert_review`/`assigned_expert_id` already exist on `Job`; confirm nothing else in this file assumes they're set at creation time |
| `be/tests/test_upload.py` | drop `test_upload_rejects_expert_review_without_assigned_expert` (moves to a respond-path test in `test_report.py`) |
| `be/tests/test_report.py` | add a `request_expert_review` respond-path test: skips `report_generator`, job goes straight to `expert_review` status with `report_key` still null; add a validation test for `request_expert_review=True` with no `assigned_expert_id` |
| `be/tests/test_pipeline.py` | drop `_expert_branch`/graph-reaches-`expert_notifier` assertions; drop `expert_notifier` from the list of registered graph nodes if asserted anywhere |
| `be/tests/fakes.py` | check `JobRepository`/`UserRepository` fakes used by `test_report.py`'s new respond-path test support an expert-bearing `User` fixture (mirrors whatever `test_upload.py`'s dropped test used) |
| `fe/e2e/PageObjectS.ts` | `submitNewReport()` drops the `expertEmail` option and its upload-time checkbox/select interaction entirely; add a new helper (e.g. `requestExpertReview()`) that drives the expert picker at the `await_customer_answers` screen instead |
| `fe/e2e/specs/expert-review.spec.ts` | rewrite: no `expertEmail` on `submitNewReport()`; call the new `requestExpertReview()` helper directly instead of `answerClarification()` (the two are mutually exclusive now — see "Out of scope" below); assert `report_key` stays null through the request-expert transition |
| `docs/tech/E2E_TESTING_PLAN.md:222` | update the `expert_review` path description — it's no longer "requested in the form," it's `POST /jobs/{id}/respond` with `request_expert_review: true` at `await_customer_answers` |

### Out of scope for this amendment

+ Combining "reply" and "request expert review" in one action (e.g. leaving a comment *and*
  escalating in the same submission) — the three actions stay mutually exclusive, matching the
  "one round, one decision" shape the rest of this loop already uses.
+ Offering "request expert review" again after a reply — `customer_after_questions = 1` still caps
  the loop at one `await_customer_answers` screen total; the second `ai_assessment` call (after a
  reply) routes straight to `report_generator`, same as before this amendment.

---

## Amendment — AI model selection explicit and configurable via env vars

**Status: implemented.** All four env files (`.env.local.example`, `.env.local`, `be/.env.prod`,
`be/.env.test`) carry explicit `ANTHROPIC_CLASSIFICATION_MODEL`/`ANTHROPIC_ASSESSMENT_MODEL`
lines; `config.py`'s defaults were already correct and needed no change.

### Why

`anthropic_classification_model` / `anthropic_assessment_model` (`be/app/core/config.py:26-27`)
are already `pydantic_settings.BaseSettings` fields, which means they're technically already
overridable by an env var (`ANTHROPIC_CLASSIFICATION_MODEL` / `ANTHROPIC_ASSESSMENT_MODEL` —
pydantic-settings' default uppercased-field-name alias, no `validation_alias` needed) — but
nothing in any `.env*` file actually sets them, so this capability is invisible: nobody looking at
`.env.local.example` would know the model is swappable without reading `config.py`. Make it
explicit at both levels: the Python default stays the safety net, but the env files declare the
current model outright, plus commented alternatives ready to uncomment.

This is also a real cost lever worth surfacing, not just a config nicety: per current Anthropic
pricing, **Claude Sonnet 5 is exactly 1/3 of Claude Fable 5** on both input ($3 vs $10/MTok) and
output ($15 vs $50/MTok) — cheaper still during Sonnet 5's introductory window ($2/$10, i.e. 1/5).
`ai_assessment`/`expert_synthesize` run on Fable 5 today (`config.py:27`, "Model costs (reference)"
above) because it's the model that produced the good direct-test result this whole rework is
chasing — that choice doesn't change by default. But being able to flip one env var to Sonnet 5
for a cost/quality comparison run, without a code change or redeploy of anything but config, is
worth having ready rather than rediscovered later.

### Change

+ **Code-level default stays exactly as-is** — `anthropic_classification_model: str =
  "claude-haiku-4-5-20251001"` and `anthropic_assessment_model: str = "claude-fable-5"`
  (`config.py:26-27`) are unchanged. This remains the fallback if an env file omits the vars
  entirely (e.g. a fresh clone before `.env.local` is populated from the example).
+ **Env files gain explicit, uncommented lines matching the current code default** — not a
  behavior change, just making the already-active default visible and editable in the one place a
  developer would actually look to change it.
+ **`.env.local.example` additionally gains commented-out alternative values** — a ready-to-uncomment
  `ANTHROPIC_ASSESSMENT_MODEL=claude-sonnet-5` line with a one-line cost comment, so switching for
  a comparison run is an uncomment, not a documentation lookup.

### File-by-file changes

| File | Change |
|---|---|
| `be/app/core/config.py` | no field changes — `anthropic_classification_model`/`anthropic_assessment_model` are already `BaseSettings` fields with the correct defaults; this amendment is env-file-only |
| `.env.local.example` | add explicit `ANTHROPIC_CLASSIFICATION_MODEL=claude-haiku-4-5-20251001` and `ANTHROPIC_ASSESSMENT_MODEL=claude-fable-5` lines under the existing `# ── LLM ──` section (alongside `ANTHROPIC_API_KEY`); add commented alternatives below each, e.g. `# ANTHROPIC_ASSESSMENT_MODEL=claude-sonnet-5  # ~1/3 the cost of claude-fable-5 — see "Model costs" above` and `# ANTHROPIC_ASSESSMENT_MODEL=claude-opus-4-8` |
| `.env.local` | mirror the same two explicit lines (this file is gitignored — update the developer's actual local copy, not just the example) |
| `be/.env.prod` | add the same two explicit lines pinned to the current production models (`claude-haiku-4-5-20251001` / `claude-fable-5`) — makes the deployed model choice a reviewable line in a diff instead of an implicit code default |
| `be/.env.test` | add the same two explicit lines — low-stakes for correctness since e2e tests send `X-E2E-Fake-Ai: 1` and never hit the real model (`be/app/api/deps.py::get_vision_llm`), but keeps all four env files consistent so there's one pattern to learn, not three |

### Out of scope for this amendment

+ Actually switching the production default to Sonnet 5 or any other model — this only makes the
  switch a one-line env edit; the model choice itself (`claude-fable-5`, "Model costs (reference)"
  above) is unchanged.
+ Per-node model overrides beyond the two that already exist (`intake_gate` on Haiku,
  `ai_assessment`/`expert_synthesize` on Fable 5) — no new settings fields, no per-request model
  selection.

---

## Amendment — structured intake questions extend `context_signals`

**Status: not yet implemented.**

### Why

`context_intake`'s own section above already claimed it "pulls whatever structured facts the
intake form already collects (floor level, building age, description text)" — that was aspirational
when written, not actual: `NewReportPage.tsx` collects only a free-text `description`, and
`context_intake.py:8` folds nothing but that description into `context_signals`. Meanwhile
`_ASSESS_SYSTEM_PROMPT`'s `verification_items` doc (`anthropic.py:104`) lists "building age" as an
example of a `customer_question` the model asks *reactively*, after already seeing the photos —
which only pays off if the customer uses their one `customer_after_questions` round to answer it.
The rework's own cost table shows that round doubling the price of the report (~$0.14 → ~$0.27).

`CLUSTERS.md`'s ten-plus-two clusters turn out to hinge on a small number of facts that are cheap
for a customer to state up front and expensive for a model to guess from pixels alone:

+ **Building age** — pre-DPC (damp-proof-course) construction stock is far more exposed to
  `rising_damp`; newer stock shifts the prior toward penetrating damp, condensation, or workmanship
  defects (`efflorescence_crack`, `facade_delamination`). The rising/penetrating/condensation
  three-way (`DOMAIN_EXPERT_FEEDBACK.md` §16, "Why Moisture Measurement Is Recommended") is exactly
  the ambiguity a photo alone cannot resolve, and building age is one of the strongest priors on it.
+ **Indoor vs. outdoor** — separates the interior clusters (`interior_compound_damp`,
  `ac_condensate_leak`, `hidden_column_leak`) from the facade/exterior clusters (`rising_damp`'s
  exterior face, `concrete_spalling`, `paint_blistering`, `boundary_wall_crack`,
  `facade_delamination`, `biological_streak`) before the model has to infer it from framing.
+ **Floor level** — `rising_damp` is only physically plausible at ground floor or basement; this
  one fact alone rules an entire cluster in or out. `balcony_junction_damp` and `ac_condensate_leak`
  skew upper floors; `boundary_wall_crack`/`facade_delamination` near the parapet line skew top
  floor/roof.
+ **Known moisture source nearby** — this is close to the literal differentiator between
  `hidden_column_leak`, `ac_condensate_leak`, `balcony_junction_damp`, and `biological_streak`: each
  of those cluster definitions in `CLUSTERS.md` is essentially "which source is implicated,"
  something the customer standing in the room usually already knows and the model has to infer from
  a stain shape.

Asking these four up front, once, at upload — rather than leaving them to a maybe-used reactive
`customer_question` — means the **first** `ai_assessment` call gets the same differentiating signal
the direct Fable-5 test benefited from, instead of only the second call (if the customer bothers to
reply). This is squarely the gap `verification_items`' own `customer_question` kind names
(`anthropic.py:104`) — this amendment moves the highest-value instances of it from reactive to
proactive, it doesn't add a new mechanism.

Kept deliberately small: four fields, all optional, all with an explicit "not sure" value — per
`CLUSTERS.md`'s "no false precision" principle, an explicit "unknown" is a real, useful signal (it
tells the model nothing is known, rather than silently omitting a key the model can't distinguish
from "wasn't asked"). Exact construction year, precise moisture readings, and anything requiring a
tool are out of scope here — those stay as `expert_only_check`/`photo_request` verification items,
unchanged.

### Fields

Four new optional selections on the upload form, alongside the existing free-text `description`
(which stays exactly as-is for open narrative):

| Field | Options | Cluster signal it resolves |
|---|---|---|
| `building_age` | `pre_1980` / `1980_2000` / `2000_2015` / `post_2015` / `unknown` | rising damp vs. penetrating/condensation prior |
| `problem_location` | `indoor` / `outdoor` / `both` / `unknown` | interior clusters vs. facade/exterior clusters |
| `floor_level` | `ground_floor` / `upper_floor` / `basement` / `roof_or_top_floor` / `unknown` | rules `rising_damp` in/out outright; skews balcony/AC/parapet clusters |
| `known_moisture_source` | `none_known` / `plumbing_leak` / `roof_or_gutter` / `ac_condensate` / `irrigation_or_garden` / `balcony_drainage` / `other` / `unknown` | differentiates `hidden_column_leak` / `ac_condensate_leak` / `balcony_junction_damp` / `biological_streak` |

Single-select (not multi-select) for `known_moisture_source` — deliberately simple over building a
new checkbox-group primitive (`fe/ui/base/` has no `Checkbox` today) for a field where the single
most-likely source is what actually shifts the model's reasoning; `description` remains the place
to mention a second contributing factor in prose.

### Wiring — reuses `context_signals`, no migration

`Job.context_signals: dict[str, Any] | None` (`job.py:73`) and its JSON `JobRow` column already
exist for the clarification loop's own use (`respond_to_job.py:29` seeds `_base_state` from it,
`:131-134` appends `customer_reply_round_N` keys to it on reply). This amendment populates the same
column at upload time instead of leaving it empty until the first `context_intake`/reply round —
**no new column, no new migration.**

The one real gap this closes: `run_assessment.py:51` currently hardcodes
`context_signals={}` on the very first graph invocation — dead code today since nothing populates
`Job.context_signals` before the graph runs, but it would silently discard these four fields the
moment they exist. Fix: `context_signals=job.context_signals or {}`, matching the pattern
`respond_to_job.py:29`'s `_base_state` already uses for every later round. `context_intake.py:8`
needs no change — it already folds `description` on top of whatever `context_signals` it's handed,
which is now the four intake fields instead of `{}`.

No system-prompt change is required either — `_ASSESS_SYSTEM_PROMPT`'s existing "CONTEXT SIGNALS...
structured facts for this case — intake-form fields and any customer replies" line (`anthropic.py:63`)
already describes exactly this, and the fields are just new keys in the same
`json.dumps(context_signals)` blob (`anthropic.py:228`) the model already reads. Worth a small
follow-up wording pass on the `verification_items` `customer_question` example (`anthropic.py:104`,
currently "e.g. building age") since that example is now pre-answered rather than something the
model should expect to ask for — not required for correctness, since an already-populated
`context_signals["building_age"]` naturally gives the model no reason to ask again.

### File-by-file changes

| File | Change |
|---|---|
| `be/app/application/upload_job.py` | `execute()` gains `building_age`, `problem_location`, `floor_level`, `known_moisture_source: str \| None = None` params; builds a `context_signals` dict from whichever are non-null and passes it to `Job(...)` |
| `be/app/api/routes/upload.py` | four new `Annotated[str \| None, Form()]` params, passed through to `UploadJob.execute()` |
| `be/app/application/run_assessment.py` | line 51: `context_signals={}` → `context_signals=job.context_signals or {}` |
| `be/app/adapters/vision_llm/anthropic.py` | optional wording tweak to the `customer_question` example in `_ASSESS_SYSTEM_PROMPT` (no functional change) |
| `fe/ui/business/NewReportPage.tsx` | new "Additional details" card: four `Select` inputs (all default to an "unknown"/unanswered option), new local state, four new fields passed to `upload.mutate(...)` |
| `fe/services/business/JobS.ts` | `upload()` gains the four optional params, appended to `FormData` when non-null |
| `fe/services/business/ReportS.ts` | `useUpload`'s mutation input type gains the four optional fields |
| `fe/types/api.ts` | regenerate from updated OpenAPI schema (auto-generated, do not hand-edit) |
| `fe/services/tech/i18n/en.ts` | new keys: `report_building_age_label` + one per option, `report_location_label` + options, `report_floor_level_label` + options, `report_moisture_source_label` + options |
| `fe/services/tech/i18n/de.ts` | same keys, German copy |
| `fe/services/tech/i18n/ru.ts` | same keys, Russian copy |
| `be/tests/test_upload.py` | assert the four fields land as keys in `job.context_signals` when provided, and are simply absent when omitted |
| `be/tests/test_pipeline.py` or a new assessment test | regression test for the `run_assessment.py:51` fix — a job created with `context_signals` pre-populated actually reaches `ai_assessment` with those keys present, not `{}` |

### Out of scope for this amendment

+ Exact construction year, precise moisture readings, or anything needing a tool on-site — those
  stay `expert_only_check`/`photo_request` verification items, unchanged.
+ Multi-select moisture sources (a `Checkbox` group primitive) — single-select is the bet for now;
  revisit if case data shows customers frequently have two co-located sources worth distinguishing.
+ Making any of the four fields required — free-tier upload must not gain a new blocking step;
  "unknown" is always available and is itself a real signal, not a placeholder for a skipped
  question.
+ Showing these four fields anywhere in the rendered report or `ReportItem` — they're reasoning
  input for `ai_assessment`, not customer-facing report content.

---

## What stays exactly as-is

+ Two-PDF customer/expert language contract (`LANGUAGE_PLAN.md` Sessions 1–5) — unchanged, just
  fed by `expert_synthesize()` instead of `synthesize()`.
+ `translate()` and its narrow uses (expert email, admin GET localization).
+ Storage/renderer ports, email adapter, auth, upload flow.

## Out of scope for this pass

+ Per-item Q&A (customer answering each `verification_item` individually) — the loop is one
  free-text reply, not a form.
+ Raising `customer_after_questions` above `1` — nothing in the design prevents it later, but one
  round is the bet for now.
+ `photo_request`-kind verification items acting on anything (no "ask for one more photo" flow
  yet).
+ Any ClusterRegistry/taxonomy automation — that's the old design doc's bet, not this one's.

---

## Verification

1. `mise run "qa:be"` — mypy strict + pytest, after the node/port renames.
2. Manual: submit a real defect photo set and accept the report at `await_customer_answers`
   without replying; confirm the report reads closer to the direct Fable-5 output in specificity
   (causal reasoning present, not generic boilerplate) — the actual regression test for the
   problem this plan fixes — and confirm no second `ai_assessment` call was made (check logs/spend).
3. Manual: submit the same photo set and reply with free text at `await_customer_answers`; confirm
   `ai_assessment` re-runs with photos + the reply folded into `context_signals`, and the second
   report reflects the added information.
4. Confirm a junk photo (non-building image) is rejected at `intake_gate` before any strong-model
   call runs (cost check).
5. Confirm expert-reviewed reports show evidence the final synthesis saw the photos (e.g. ask it
   to reference something only visible in the image, not in the expert's text notes).
