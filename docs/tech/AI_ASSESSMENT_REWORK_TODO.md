# AI Assessment Rework — Delta TODO

Companion to `docs/tech/AI_ASSESSMENT_REWORK.md`, which holds the full rationale and design for
everything below. This file is the flat checklist: what's actually built vs. what's still just
plan. Update the checkboxes as work lands — don't let this file drift from reality the way the
main doc's narrative sections can.

## Status at a glance

| Piece | Status |
|---|---|
| Base rework — `intake_gate` → `context_intake` → `ai_assessment` → `await_customer_answers` ↔ `ai_assessment` → `report_generator` graph, state/domain/ORM fields, `POST /jobs/{id}/respond` (accept/reply only), `api_call_count` ceiling | ✅ Implemented |
| Amendment 1 — expert review moves from upload to `await_customer_answers` | ✅ Implemented |
| Amendment 2 — AI model configurable via env vars | ✅ Implemented |
| Amendment 3 — structured intake questions extend `context_signals` | ⬜ Not started |
| `docs/business/BUSINESS_PLAN.md` — Assess price €69 → €49 (launch/Billy-cost pricing) | ✅ Done (doc edit only, already applied) |

---

## Amendment 1 — Expert review moves to `await_customer_answers`

Full rationale: `AI_ASSESSMENT_REWORK.md` → "Amendment — expert review request moves to
`await_customer_answers`, not upload".

### Backend

- [x] `be/app/api/schemas.py` — `RespondRequest` gains `request_expert_review: bool = False`,
      `assigned_expert_id: str | None = None`
- [x] `be/app/api/routes/jobs.py` — pass the two new fields through to `RespondToJob.run()`
- [x] `be/app/application/respond_to_job.py` — three-way dispatch in `run()`; new
      `_request_expert(job, assigned_expert_id)`; drop the expert check from `_accept()`
- [x] `be/app/application/pipeline/graph.py` — delete `_expert_branch`; `report_generator`'s
      conditional edge becomes `g.add_edge("report_generator", END)`; drop `expert_notifier`'s
      node registration from `_wire_downstream_of_assessment`
- [x] `be/app/application/upload_job.py` — drop `request_expert_review`/`assigned_expert_id`
      params and the line-124 validation (moves to `respond_to_job.py`)
- [x] `be/app/api/routes/upload.py` — drop the two form fields
- [x] `be/app/application/run_assessment.py` — drop the dead
      `request_expert_review=job.request_expert_review, assigned_expert_id=job.assigned_expert_id`
      seeding into the initial graph state

### Frontend

- [x] `fe/ui/business/NewReportPage.tsx` — delete the expert checkbox/select block (`115-172`),
      its three state vars (`requestExpertReview`, `assignedExpertId`, `expertRequiredError`), the
      `ExpertS`/`useExperts()` import, and the two args passed to `upload.mutate`
- [x] `fe/ui/business/ReportView.tsx` — `RespondPanel` gains `requestingExpert`/`assignedExpertId`/
      `expertRequiredError` local state, imports `ExpertS`, renders default-vs-checked mode split
      (textarea+accept/send **or** expert picker+price+submit, never both)
- [x] `fe/services/business/JobS.ts` — `upload()` drops `assignedExpertId`/`requestExpertReview`;
      `respond()` signature changes to `(id, body: { reply } | { requestExpertReview, assignedExpertId }, token)`
- [x] `fe/services/business/ReportS.ts` — `useUpload`/`useRespond` mutation input types updated to
      match
- [x] `fe/types/api.ts` — regenerate from updated OpenAPI schema (auto-generated, don't hand-edit)
- [x] `fe/services/tech/i18n/en.ts` — add `report_request_expert_action`, `report_request_expert_price`
- [x] `fe/services/tech/i18n/de.ts` — same two keys, German copy
- [x] `fe/services/tech/i18n/ru.ts` — same two keys, Russian copy

### Tests

- [x] `be/tests/test_upload.py` — drop `test_upload_rejects_expert_review_without_assigned_expert`
- [x] `be/tests/test_report.py` — add a `request_expert_review` respond-path test (skips
      `report_generator`, job → `expert_review` with `report_key` still null); add a
      no-`assigned_expert_id` validation test
- [x] `be/tests/test_pipeline.py` — drop `_expert_branch`/graph-reaches-`expert_notifier` assertions
- [x] `be/tests/fakes.py` — confirm fixtures support an expert-bearing `User` for the new test

### E2E tests (Playwright, `fe/e2e/`)

The current e2e expert-review flow is built entirely around the upload-time checkbox this
amendment removes — `PageObjectS.submitNewReport()` checks "Request expert review" and picks the
expert **before** upload, then `expert-review.spec.ts` *also* answers the clarification question
afterward. Under this amendment that's not just stale, it's an invalid sequence: reply and
request-expert become mutually exclusive actions at `await_customer_answers` (see "Out of scope"
above), so a test can no longer do both in one job the way it does today.

- [x] `fe/e2e/PageObjectS.ts` — `submitNewReport()` (`~L49-99`) drops the `expertEmail` option
      entirely: no more `page.getByLabel("Request expert review").check()` /
      `getByTestId("expert-select")` at upload, no more `request_expert_review`/
      `assigned_expert_id` in the upload `FormData`. Add a new page-object helper, e.g.
      `requestExpertReview(page, expertEmail)`, that drives the **new** `await_customer_answers`
      UI instead: check the "Request expert review instead" checkbox in `RespondPanel`, select the
      expert from `getByTestId("expert-select")` (now rendered there, not on the upload form),
      click the submit button — mirroring the shape of the existing `answerClarification()`
      helper but as the mutually-exclusive alternative to it, not a compatible-with-reply step.
- [x] `fe/e2e/specs/expert-review.spec.ts` — rewrite the test body: `submitNewReport()` no longer
      takes `expertEmail`; after upload, call the new `requestExpertReview()` helper directly at
      the `awaiting_customer_input` state (skip `answerClarification()` — the two are no longer
      combinable in one job). Confirm the job goes straight to `expert_review` status with
      `report_key` still null (no AI-only PDF render) before `approveAsExpert()` runs.
- [x] `docs/tech/E2E_TESTING_PLAN.md:222` — "`expert_review` path (if requested in the form)" is
      now wrong on two counts: the request no longer happens "in the form" (it's at
      `await_customer_answers`), and it's `POST /jobs/{id}/respond` with
      `request_expert_review: true`, not a separate `/approve` endpoint for the *request* leg
      (`/approve` is still correct for the expert's own approval step, unchanged). Update the
      paragraph to describe the new flow and its expected state transition
      (`awaiting_customer_input → expert_review`, `report_key` staying null, verified via
      `expect.poll`).
- [x] `fe/e2e/specs/reports-new.spec.ts`, `fe/e2e/specs/localization.spec.ts`,
      `fe/e2e/specs/assessment.spec.ts`, `fe/e2e/specs-real-ai/assessment.spec.ts` — no change
      expected; none of these pass `expertEmail` to `submitNewReport()`, so removing that option
      doesn't affect them. Re-run after the `PageObjectS.ts` edit to confirm — a signature change
      to a shared helper is worth a full-suite pass, not just the directly-touched spec.

---

## Amendment 2 — AI model configurable via env vars

Full rationale: `AI_ASSESSMENT_REWORK.md` → "Amendment — AI model selection explicit and
configurable via env vars".

- [x] `.env.local.example` — add explicit `ANTHROPIC_CLASSIFICATION_MODEL=claude-haiku-4-5-20251001`
      and `ANTHROPIC_ASSESSMENT_MODEL=claude-fable-5`; add commented alternatives
      (`# ANTHROPIC_ASSESSMENT_MODEL=claude-sonnet-5  # ~1/3 the cost of claude-fable-5`, `#
      ANTHROPIC_ASSESSMENT_MODEL=claude-opus-4-8`)
- [x] `.env.local` — mirror the same two explicit lines (gitignored, edit the real dev file)
- [x] `be/.env.prod` — add the same two explicit lines pinned to current production models
- [x] `be/.env.test` — add the same two lines for consistency (low-stakes — e2e uses
      `X-E2E-Fake-Ai: 1` and never hits the real model)
- [x] `be/app/core/config.py` — no change needed; confirm only (fields already exist with correct
      defaults)

---

## Amendment 3 — Structured intake questions extend `context_signals`

Full rationale: `AI_ASSESSMENT_REWORK.md` → "Amendment — structured intake questions extend
`context_signals`".

### Backend

- [ ] `be/app/application/upload_job.py` — `execute()` gains `building_age`, `problem_location`,
      `floor_level`, `known_moisture_source: str | None = None`; builds a `context_signals` dict
      from whichever are non-null, passed to `Job(...)`
- [ ] `be/app/api/routes/upload.py` — four new `Annotated[str | None, Form()]` params passed
      through to `UploadJob.execute()`
- [ ] `be/app/application/run_assessment.py` — line 51 fix: `context_signals={}` →
      `context_signals=job.context_signals or {}` (the actual bug this amendment depends on)
- [ ] `be/app/adapters/vision_llm/anthropic.py` — optional wording tweak to the `customer_question`
      example in `_ASSESS_SYSTEM_PROMPT` (no functional change)

### Frontend

- [ ] `fe/ui/business/NewReportPage.tsx` — new "Additional details" card: four `Select` inputs
      (each defaulting to an "unknown" option), new local state, four fields passed to
      `upload.mutate(...)`
- [ ] `fe/services/business/JobS.ts` — `upload()` gains the four optional params, appended to
      `FormData` when non-null
- [ ] `fe/services/business/ReportS.ts` — `useUpload`'s mutation input type gains the four fields
- [ ] `fe/types/api.ts` — regenerate from updated OpenAPI schema (auto-generated, don't hand-edit)
- [ ] `fe/services/tech/i18n/en.ts` — new label + per-option keys for all four fields
- [ ] `fe/services/tech/i18n/de.ts` — same keys, German copy
- [ ] `fe/services/tech/i18n/ru.ts` — same keys, Russian copy

### Tests

- [ ] `be/tests/test_upload.py` — the four fields land as keys in `job.context_signals` when
      provided, absent when omitted
- [ ] `be/tests/test_pipeline.py` (or a new assessment test) — regression test for the
      `run_assessment.py:51` fix: a job with `context_signals` pre-populated actually reaches
      `ai_assessment` with those keys present, not `{}`

---

## Verification once both amendments land

1. `mise run "qa:be"` + `mise run "qa:fe"`.
2. Manual: at `await_customer_answers`, check "Request expert review," pick an expert, submit —
   confirm job goes straight to `expert_review` status with `report_key` still null (no wasted
   AI-only PDF), and the price shown matches `BUSINESS_PLAN.md`'s current Assess price.
3. Manual: accept and reply paths at `await_customer_answers` still work unchanged (regression
   check on the base rework).
4. Manual: set `ANTHROPIC_ASSESSMENT_MODEL=claude-sonnet-5` in `.env.local`, restart the backend,
   confirm `ai_assessment` actually calls Sonnet 5 (check `logs/be.log` or the Anthropic request
   for the model string), then revert.
5. `mise run fe-e2e` (or `E2E_ENV=local mise run fe-e2e` for a fast local pass) — the regular
   fake-AI suite, including the rewritten `expert-review.spec.ts`. This is the actual regression
   test for "expert request no longer wastes an AI-only PDF render" — the fake vision port makes
   the wasted-render bug (or its absence) deterministic and fast to check via `expect.poll` on job
   status, rather than needing a manual walkthrough each time.

**Status:** #1 (`qa:be` + `qa:fe`) passed clean. #2–#5 are manual/e2e runtime checks not yet
executed in this pass — servers weren't started per this project's "never start servers
automatically" rule, and e2e wasn't triggered since the user didn't ask to run/test the UI. Run
`mise run fe-e2e` (and the two manual walkthroughs) before considering this shippable.
