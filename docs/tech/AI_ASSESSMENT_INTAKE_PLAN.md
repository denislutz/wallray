# Structured intake questions extend `context_signals` — Implementation Plan

Execution plan for Amendment 3 tracked in `docs/tech/AI_ASSESSMENT_REWORK_TODO.md`. Full rationale
lives in `docs/tech/AI_ASSESSMENT_REWORK.md` → "Amendment — structured intake questions extend
`context_signals`"; this file is the file-by-file execution plan for that amendment.

## Context

`docs/tech/AI_ASSESSMENT_REWORK.md`'s `context_intake` node was documented as pulling "floor level,
building age, description text" from the intake form — that was aspirational, never actual.
`fe/ui/business/NewReportPage.tsx` collects only free-text `description`, and
`be/app/application/pipeline/nodes/context_intake.py` folds nothing else into `context_signals`.
The first `ai_assessment` call (Fable 5) therefore reasons from photos + prose alone, even though
`CLUSTERS.md`'s cluster set hinges on a few cheap-to-state facts a photo can't reliably reveal:
building age (pre/post-DPC), indoor vs. outdoor, floor level (rules `rising_damp` in/out outright),
and a known moisture source nearby (differentiates `hidden_column_leak` / `ac_condensate_leak` /
`balcony_junction_damp` / `biological_streak`). Today these only surface reactively, as a
`customer_question`-kind `verification_item` the model might ask in the one clarification round —
which doubles report cost (~$0.14 → ~$0.27) and only helps if the customer bothers to reply.

This plan adds four optional, enum-valued questions to the upload form so the **first**
`ai_assessment` call gets this signal, not just a possible second one.

**Key design point discovered during investigation:** no migration needed. `Job.context_signals`
(JSON column, `be/app/domain/job.py:73`) already exists for the clarification loop's own bookkeeping
(`be/app/application/respond_to_job.py:29,131-134`). The only real gap is
`be/app/application/run_assessment.py:51`, which hardcodes `context_signals={}` on the very first
graph invocation — harmless today since nothing populates `Job.context_signals` before upload, but
it would silently discard these four fields the moment they exist. That one-line fix is what makes
this whole feature work.

## Fields (unchanged from the doc amendment)

| Field | Enum values |
|---|---|
| `building_age` | `pre_1980` / `1980_2000` / `2000_2015` / `post_2015` / `unknown` |
| `problem_location` | `indoor` / `outdoor` / `both` / `unknown` |
| `floor_level` | `ground_floor` / `upper_floor` / `basement` / `roof_or_top_floor` / `unknown` |
| `known_moisture_source` | `none_known` / `plumbing_leak` / `roof_or_gutter` / `ac_condensate` / `irrigation_or_garden` / `balcony_drainage` / `other` / `unknown` |

All four default to `unknown` in the UI and are always sent as a real string (never omitted by the
FE) — an explicit "unknown" is a real signal per `CLUSTERS.md`'s "no false precision" rule, not a
placeholder for a skipped question.

## Backend changes

**`be/app/application/upload_job.py`** — `UploadJob.execute()` (currently at lines 130-137) gains
`building_age: str | None = None, problem_location: str | None = None, floor_level: str | None = None, known_moisture_source: str | None = None`.
Build `context_signals = {k: v for k, v in {...}.items() if v is not None}` from the four, pass to
`Job(..., context_signals=context_signals or None)` (the `Job(...)` construction is currently at
lines 175-185).

**`be/app/api/routes/upload.py`** — add four `Annotated[str | None, Form()] = None` params to
`upload()` (currently lines 27-38), pass straight through to `UploadJob(...).execute(...)`
(currently lines 40-46). No `UploadRequest` Pydantic model exists today (it's plain `Form()` params
in `be/app/api/schemas.py`) so no schema class changes — `fe/types/api.ts` picks these up
automatically from FastAPI's generated OpenAPI multipart schema.

**`be/app/application/run_assessment.py`** — line 51: `context_signals={}` →
`context_signals=job.context_signals or {}`, matching the pattern
`be/app/application/respond_to_job.py:29`'s `_base_state` already uses. This is the load-bearing
fix.

**`be/app/adapters/vision_llm/anthropic.py`** — optional, low-risk wording tweak: the
`verification_items` `customer_question` example in `_ASSESS_SYSTEM_PROMPT` (line 104, "e.g.
building age") now describes a pre-answered field rather than one to ask for. Update the example to
something not covered by the four new fields (e.g. "is there a drip irrigation line against this
wall?", already used elsewhere in the docs). Not required for correctness — skip if it risks scope
creep, but cheap to do while touching this file's neighborhood.

**No ORM/migration changes.** `be/app/adapters/persistence/orm_models.py`'s `JobRow.context_signals`
JSON column already exists.

## Frontend changes

**`fe/ui/base/Select.tsx`** — no change, reused as-is (existing `size`/variant API, see current
`language` selector in `NewReportPage.tsx:127-140`).

**`fe/ui/business/NewReportPage.tsx`** — new "Additional details" `Card` between the description
card (currently lines 78-92) and the photo upload row (currently starting line 100), with four
`Select` inputs (labelled, each defaulting to `"unknown"`), matching the existing
`Card`/`CardHeader`/`CardTitle`/`CardContent` pattern already used for name (lines 62-76) and
description. Four new `useState` vars (alongside the existing ones at lines 36-40), all passed into
`upload.mutate(...)` (currently lines 102-109).

**`fe/services/business/JobS.ts`** — `upload()` (currently lines 55-76) takes 5 positional params
(`files, description, token, name?, language?`); adding 4 more positional optional strings makes a
9-arg signature genuinely hard to call correctly. Refactor to bundle the trailing optional fields
into one options object:

```ts
const upload = async (
  files: File[],
  description: string,
  token: string,
  options?: {
    name?: string | null;
    language?: string;
    buildingAge?: string;
    problemLocation?: string;
    floorLevel?: string;
    knownMoistureSource?: string;
  }
): Promise<{ id: string }> => { ... }
```

Append each `options.*` field to `FormData` under its snake_case form-field name
(`building_age`, `problem_location`, `floor_level`, `known_moisture_source`) when present. This is a
call-site-breaking rename local to this file + its one caller (`ReportS.ts`) + `NewReportPage.tsx`
— both already need editing for this feature, so the refactor doesn't touch anything extra.

**`fe/services/business/ReportS.ts`** — `useUpload`'s mutation input type (currently lines 48-66)
gains the four optional fields (flat on the mutation input object, same shape it already has for
`name`/`language`), passed through into
`JobS.upload(files, description, token ?? "", { name, language, buildingAge, ... })`.

**`fe/types/api.ts`** — regenerate via `mise run "schema:sync"` (exports BE OpenAPI →
`be/openapi.json` → runs `openapi-typescript` into this file). Do not hand-edit.

**i18n — `fe/services/tech/i18n/{en,de,ru}.ts`** — add, per field, one label key plus one key per
enum value, following the existing `report_defect_type_<value>` naming convention
(`en.ts:104-109`) and placed near `report_description_label`/`report_description_hint`
(`en.ts:57-58`):

- `report_building_age_label`, `report_building_age_pre_1980`, `report_building_age_1980_2000`,
  `report_building_age_2000_2015`, `report_building_age_post_2015`, `report_building_age_unknown`
- `report_location_label`, `report_location_indoor`, `report_location_outdoor`,
  `report_location_both`, `report_location_unknown`
- `report_floor_level_label`, `report_floor_level_ground_floor`, `report_floor_level_upper_floor`,
  `report_floor_level_basement`, `report_floor_level_roof_or_top_floor`,
  `report_floor_level_unknown`
- `report_moisture_source_label`, `report_moisture_source_none_known`,
  `report_moisture_source_plumbing_leak`, `report_moisture_source_roof_or_gutter`,
  `report_moisture_source_ac_condensate`, `report_moisture_source_irrigation_or_garden`,
  `report_moisture_source_balcony_drainage`, `report_moisture_source_other`,
  `report_moisture_source_unknown`

All three language files need the exact same key set — `fe/services/tech/I18nS.ts`'s
`TranslationKey<T>` type (`keyof T[keyof T]`) means a key missing from even one language file fails
`tsc` wherever `t()` is called with it, so `qa:fe`'s typecheck step is the actual safety net here,
not manual review.

## Tests

**`be/tests/fakes.py`**:

- `make_job()` (currently lines 61-78) gains `context_signals: dict[str, Any] | None = None`,
  passed through to `Job(...)`.
- `VisionLLMStub.assess()` (currently lines 184-onward) records its calls (e.g.
  `self.assess_calls: list[dict] = []`, appended with at least `context_signals` each call) so
  tests can assert what the first `ai_assessment` call actually received — today the stub only
  returns a canned response with no way to inspect inputs.

**`be/tests/test_upload.py`**:

- Extend the `_upload()` helper (currently lines 30-41) with the four new optional kwargs (mirrors
  how `description` is already handled there).
- New test: upload with all four fields set → assert each lands as its exact key in the underlying
  `Job.context_signals`, via the job repo fixture — same access pattern
  `test_upload_with_description` (line 61) uses for `description` (`context_signals` isn't in
  `ReportItem`/exposed over `GET /jobs` today).
- New test: upload with none of the four fields → `job.context_signals` is `None` (no empty-string
  keys injected).

**`be/tests/test_report.py`** (has the exact harness needed — `make_job()` + `RunAssessment(...).run()`
directly, see `test_run_pauses_for_customer_input` at line 79):

- New regression test: `make_job(job_id, keys, context_signals={"building_age": "pre_1980"})`, run
  `RunAssessment(...).run(job_id, ...)` via the `_uc(...)` helper (lines 30-44), then assert the
  `VisionLLMStub`'s recorded first `assess()` call's `context_signals` actually contains
  `"building_age": "pre_1980"` — this is the test that would have caught the
  `run_assessment.py:51` bug before this fix, and pins it going forward.

## Verification

1. `mise run "qa:be"` — mypy strict + pytest, covering all backend changes above.
2. `mise run "qa:fe"` — biome + tsc, covering the i18n key-completeness check and the
   `JobS.upload()` signature refactor across its call sites.
3. Manual: submit a report from `NewReportPage.tsx` with all four fields answered, confirm (via
   `logs/be.log` or a debug breakpoint) that the first `ai_assessment` call's `context_signals`
   includes all four; confirm the resulting `summary` visibly reasons using them (e.g. doesn't
   entertain `rising_damp` when `floor_level=upper_floor` was given).
4. Manual: submit with all four left at "unknown," confirm the job still proceeds normally
   (non-blocking) and `context_signals` shows `"unknown"` string values, not missing keys.
