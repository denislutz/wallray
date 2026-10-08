# AI Assessment — Unified Single-Report Model

Follow-up to `AI_ASSESSMENT_REWORK.md` (implemented). That rework fixed the "model never sees the
photos" bottleneck but left a new one behind: every pass produces **two** overlapping narrations of
the same finding — `reasoning_en` (deep, structured, English) and `summary` (a shorter paraphrase
"written from reasoning_en... in plain language"). Production output showed both to the customer,
and the downloadable PDF kept only the shorter one, dropping the depth entirely. This plan collapses
the two back into one, and unifies the two model-call sites (`assess()` / `expert_synthesize()`)
into one method so there is only one prompt's depth-preservation behavior to get right, not two.

---

## Node diagram

Graph topology (`be/app/application/pipeline/graph.py`) is **unchanged** — this plan does not touch
edges or branching. What changes is that both external call sites now invoke the same
`vision_llm.assess()` method, just with different arguments:

```
intake_gate → context_intake → ai_assessment (A)
                                    │
                                    ▼
                    [loop_count < customer_after_questions?]
                       │yes                  │no
                       ▼                     │
             await_customer_answers          │
                │accept      │reply (B) ─────┘ (loop back to ai_assessment)
                │             (loop back)
                ▼
          report_generator
                │
                ▼
    [request_expert_review?]
       │no                 │yes
       │                   ▼
       │             expert_notifier
       │                   │
       │       [expert reviews, submits expert_notes — outside the graph]
       │                   ▼
       │             GenerateReport.run() (C)
       │                   │
       ▼                   ▼
      END             report_generator (final render)
```

Every one of (A)/(B)/(C) is the same `vision_llm.assess()` call, just with different arguments —
see the table below.

**The one `assess()` call — three invocations, one prompt:**

| Trigger | `prior_summary` | `expert_notes` | `context_signals` |
|---|---|---|---|
| (A) First pass, in-graph | `None` | `None` | intake form fields + description |
| (B) Customer replied, in-graph loop | last round's `summary` | `None` | + `customer_reply_round_N` |
| (C) Expert reviewed, post-graph (`generate_report.py`) | last round's `summary` | expert's text | unchanged from (B) |

Every call sees the photos fresh. Priority rule baked into the single prompt: photos are always
the primary evidence; `context_signals` (whether an intake-form field or a customer reply, doesn't
matter which) is supporting evidence to weigh, never authoritative; `expert_notes`, when present,
**overrides** the AI's own prior visual conclusions on conflict. `prior_summary`, when present, is
the depth/structure baseline to **preserve and extend — never compress**.

---

## Why the old two-field/two-method design caused the bug

1. `_ASSESS_SYSTEM_PROMPT` (`anthropic.py:83-86`) told the model to write `summary` "from
   `reasoning_en`... in plain language" — a deliberate re-derivation of the same content, on every
   call, including pass 1 where nothing had been synthesized yet.
2. `ReportView.tsx` (`fe/ui/business/ReportView.tsx:72-142`) rendered both `ReportGallery`
   (`reasoning_en`, translated) and `ReportSynthesis` (`summary`) unconditionally, to every viewer —
   the rework doc's own intent ("`reasoning_en` never shown to the customer directly") was never
   implemented.
3. `xhtml2pdf.py:26` only ever used `summary` in the PDF (falling back to `reasoning_en` only if
   `summary` was empty) — so the one persisted artifact lost the depth entirely.
4. The same dual-narration problem exists a second time on the **expert** side:
   `admin.py::get_job_for_review` shows both `classification_notes_localized` (translated
   `reasoning_en`) *and* `summary`/`summary_expert` — same bug, different audience.

Simply hiding `reasoning_en` from the customer (the rework doc's original intent) isn't the fix, since it would throw away the depth the direct-Fable-5 test was actually valued for. The fix is to
stop generating two versions of the same content at all: one field, always at full depth, refined
in place across rounds.

**A second risk, caught before implementation:** naively keeping `expert_synthesize()` as a
separate method/prompt would just move the compression bug one step later — its current prompt
says `summary` should be **"a professional, concise final assessment"**, which is the same
shrink-it-down instinct that caused the original bug, except now with no second detail field left
to catch the loss. Merging `assess()`/`expert_synthesize()` into one method with one prompt removes
this risk structurally: there's only one depth-preservation instruction to write correctly, and it
applies identically whether the trigger was a customer reply or an expert review.

---

## Domain model (`be/app/domain/job.py`)

- `DefectClassification`: remove `reasoning_en`. Update docstring: *"Output of every `assess()`
  call — the same method whether this is the first pass, a customer-reply rerun, or a
  post-expert-review regeneration."* Keeps `summary`, `summary_expert`, `expert_note_localized`,
  `confidence`, `verification_items`.
- `Job`: remove `classification_notes` field.

## Vision LLM port (`be/app/domain/ports/vision_llm.py`)

Replace `assess()` + `expert_synthesize()` with one method:

```python
async def assess(
    self,
    photo_keys: list[str],
    context_signals: dict[str, Any],
    prior_summary: str | None = None,
    expert_notes: str | None = None,
    customer_language: str = "en",
    expert_language: str | None = None,
) -> DefectClassification: ...
```

## Adapter (`be/app/adapters/vision_llm/anthropic.py`)

Delete `_EXPERT_SYNTHESIZE_SYSTEM_PROMPT` and `expert_synthesize()`. Replace `_ASSESS_SYSTEM_PROMPT`
with the single unified prompt below — no `reasoning_en` in the output schema, `summary` is the
sole narrative field at full causal-reasoning depth every round; explicit depth-preservation,
evidence-priority, and attribution instructions (the two risks caught above); the
`summary_expert`/`expert_note_localized` two-language contract carried over unchanged.

```python
_ASSESS_SYSTEM_PROMPT = """\
You are an experienced building surveyor analysing photos of a possible building defect. You will \
be shown all photos submitted for this case together — treat close-up photos as detail evidence \
and context/wide photos as the structural evidence for WHY the defect sits where it does.

Do not stop at a superficial label like "this is a crack" or "this is peeling paint" — that alone \
is worthless, it's visible in the photo itself. Your real job is to use the context photos to \
reason through WHY this defect is occurring at this exact location:

- Where exactly does this sit in the building (foundation, window corner, balcony junction, roof \
  edge, interior, weather-facing side)?
- What water paths, load paths, or building-component junctions visible in the context photos \
  explain the damage pattern in the close-up?
- Are there visible clues to the cause in the context photos (missing/damaged sealant, junction \
  gap, drainage, orientation to weather, crack path relative to openings or component edges)?
- If a wet room (bathroom, kitchen, WC) could plausibly sit behind this facade location, consider \
  whether the cause is more likely interior condensation/humidity pushing outward through the \
  window/wall than external causes (rain, windowsill leak). State both possibilities if the photos \
  don't clearly settle it.

PRIOR ASSESSMENT (if provided below): your own previous round's `summary` for this case. Treat it \
as the depth/structure baseline — preserve and extend it, never shrink it to a shorter paraphrase. \
Re-examine the photos yourself rather than just repeating it. The never-shrink rule applies to the \
depth of reasoning, not to open questions: when a customer reply or expert note resolves an item \
from the prior round's Further checks, fold the answer into the finding/cause narrative and drop \
it from the open checks — don't keep answered items listed as open.

CONTEXT SIGNALS (may be empty): structured facts for this case — intake-form fields and any \
customer replies, labeled by round. Supporting evidence to weigh alongside the photos, never more \
authoritative than what you can see yourself.

EXPERT NOTES (if provided below): a certified expert has physically reviewed this case; their \
findings take priority over your own prior reasoning on conflict — defer to them, but still use \
the photos yourself to explain how their finding relates to what's visible.

ATTRIBUTION: whenever you incorporate a customer reply or expert note into the reasoning, say so \
explicitly in the narrative (e.g. "Per your reply, ...", "Per the reviewing expert's on-site \
finding, ...") rather than blending it in silently — the reader should be able to tell what came \
from where.

CRITICAL LANGUAGE RULE: You MUST write `summary` in {customer_language} (ISO 639-1 code) — a hard \
requirement regardless of what language the context signals, prior assessment, or expert notes are \
in. See `summary_expert` / `expert_note_localized` / `verification_items` below for their own \
language conditions.

FORMATTING: `summary` and `summary_expert` are rendered through a markdown viewer, not shown as raw \
text — use markdown to make them scannable the way a well-formatted report reads: a bold label per \
section (e.g. `**Finding:**`), short paragraphs, and a bullet list (`- item`) wherever you're \
listing more than one thing. This is about structure, not decoration — no headings, no tables, no \
code blocks, and don't force a bullet list where a single sentence reads better. The JSON string \
value itself is unaffected — write the markdown source with literal `\n` line breaks inside the \
string, exactly like any other multi-line JSON string value.

Return ONLY valid JSON (no markdown fences, no extra text) with exactly these keys:
- defect_type: short identifier, e.g. "crack", "water_damage", "mould", "spalling", "none"
- severity: one of "low", "medium", "high", "critical"
- summary: the full assessment in markdown, in {customer_language}, covering, in order: (1) \
  **Finding** — what is visible, (2) **Probable cause** — your reasoned derivation, not just the \
  symptom, (3) **Severity reasoning**, (4) **Further checks** — what else should be checked to \
  confirm the cause, as a bullet list if there's more than one. Same depth every round.
- summary_expert: the same assessment, same depth, in {expert_language}, or null if it matches \
  {customer_language}
- expert_note_localized: the expert's note translated into {customer_language} verbatim (not \
  paraphrased), or null if no expert notes were provided
- confidence: a float from 0.0 to 1.0 reflecting how confident you are in this assessment given \
  the photos and context available
- verification_items: an array of objects, each {{"text": "...", "kind": "..."}}, for anything \
  from point (4) above worth flagging — kind is one of:
  - "customer_question": the customer could answer this directly in text (e.g. building age, \
    "is there a drip irrigation line against this wall?") — write `text` in {customer_language}
  - "photo_request": this needs a new photo, not a text answer (e.g. "photograph the interior \
    wall directly behind this location") — write `text` in English
  - "expert_only_check": this needs a tool or person on site (e.g. moisture meter reading, \
    opening a section) — never phrase these as something the customer can just answer; write \
    `text` in English
  When expert notes are provided, include only items still open after the expert's on-site \
  findings — often none. May be an empty array if there's nothing further worth flagging."""
```

Rewrite `assess()`: same photo-loading, but the trailing text block now conditionally includes a
labeled `Prior assessment:\n{prior_summary}` section and a labeled
`Expert notes:\n{expert_notes}` section, only when each is given.
`.format(customer_language=..., expert_language=expert_language or customer_language)`.

**Raise `max_tokens` from 4096 to 8192.** The (C) call now demands the full-depth assessment
*twice* — `summary` plus `summary_expert` at the same depth — plus `expert_note_localized` and
`verification_items`, in one response. The old expert prompt fit in 4096 only because it demanded
"concise"; a truncated response fails `_parse_json` and `GenerateReport` marks the job failed.

## Other `VisionLLMPort` implementations (same port change, easy to miss)

- **`be/app/adapters/vision_llm/fake.py`** — the E2E fake (`X-E2E-Fake-Ai`, wired in
  `core/container.py`, served by `deps.py::get_vision_llm`). Merge its `assess()`/
  `expert_synthesize()` into one `assess()` matching the new signature; drop `reasoning_en`.
  Branch on `expert_notes` presence to produce `summary_expert`/`expert_note_localized` (today's
  `expert_synthesize()` behavior) — **not** on the per-photo-set call counter, since the (C) call
  now arrives through the same method and must not be mistaken for another clarification round.
  Keep the counter only for the existing first-call-raises-a-customer-question behavior. Without
  this file, mypy fails and the fake-AI E2E suite (test-sequence step 1 below) breaks.
- **`be/app/adapters/vision_llm/openai.py`** — drop `reasoning_en=...` (line 75) and match the new
  `assess()` signature — same dead-adapter/mypy-consistency treatment as `weasyprint.py`.

## State (`be/app/application/pipeline/state.py`)

Remove `classification_notes` and `reasoning_en` keys from `AssessmentState`. No new key needed for
`prior_summary` — the `ai_assessment` node derives it inline from
`state.get("defect_classification")`.

**But note:** that derivation only works if `_base_state()` reconstructs the prior classification
from the Job row (see `respond_to_job.py` below). `ai_assessment` is never entered with a populated
`defect_classification` today: `build()` runs it once per invocation before any loop can occur, and
the (B) "loop back" is really a fresh `build_resume()` invocation — possibly in another process —
whose state comes from `_base_state()`, which currently sets `defect_classification=None`. Without
the reconstruction, `prior_summary` would be `None` on every call and the depth-preservation
contract would silently never engage.

## Pipeline nodes

- **`ai_assessment.py`** — derive `prior = state.get("defect_classification")`, call
  `vision_llm.assess(state["photo_keys"], state["context_signals"], prior_summary=prior.summary if
  prior else None, customer_language=state["customer_language"])`. Drop `classification_notes`/
  `reasoning_en` from the `update_status` call and the returned dict.
- **`expert_notifier.py`** — `notes_for_expert` currently reads `state.get("classification_notes")`;
  change to `state["defect_classification"].summary if state.get("defect_classification") else ""`.
  Also fix the pre-existing `expert_lang != "en"` comparison to `expert_lang !=
  state["customer_language"]` (translate whenever it actually differs from the *customer's*
  language, not hardcoded English) while touching this line.

## Use cases

- **`generate_report.py`** — replace the `expert_synthesize()` call with
  `vision_llm.assess(photo_keys, job.context_signals or {}, prior_summary=job.summary,
  expert_notes=job.expert_notes, customer_language=customer_language,
  expert_language=expert_language)`. Rest of the method (PDF render, `summary_expert` branch,
  `update_status`) is unchanged — `DefectClassification`'s shape didn't change on this side.
- **`respond_to_job.py`** — `_base_state()`: drop `classification_notes=job.classification_notes`
  and `reasoning_en=job.classification_notes`; replace `defect_classification=None` with a
  reconstruction of the prior round's classification from the Job row:

  ```python
  defect_classification=DefectClassification(
      defect_type=job.defect_type or "unknown",
      severity=job.severity or "unknown",
      summary=job.summary,
      verification_items=job.verification_items,
  )
  if job.defect_type
  else None,
  ```

  This is what makes `prior_summary` non-`None` on the (B) rerun: `ai_assessment` persists
  `summary` to the Job row every round, and `_base_state()` reads it back. `_accept()`: delete its
  own hand-built `DefectClassification(...)` block entirely — `_base_state()` now provides the same
  object (no LLM call on accept — unchanged). `run_assessment.py`'s initial state stays
  `defect_classification=None`, so pass (A) correctly gets no prior.
- **`run_assessment.py`** — drop `classification_notes=None, reasoning_en=None,` from the initial
  `AssessmentState`.
- **`get_report.py`** — `job.summary` is already customer-language-native now; delete the
  `notes_localized`/`translate()` block entirely (it was translating `reasoning_en`, which no longer
  exists) and the `classification_notes_localized=notes_localized` field from the returned
  `ResolvedJob`.
- **`list_jobs.py`** — remove the unused `classification_notes_localized` field from `ResolvedJob`.

## API layer

- **`schemas.py`** — remove `classification_notes_localized` from `ReportItem`. `summary` is now
  the single narrative field for both customer and expert views.
- **`report.py`** (`_to_report_item`) — drop the `classification_notes_localized=...` line.
- **`admin.py`**:
  - `_to_report_item` — drop `classification_notes_localized=...`.
  - `get_job_for_review` (pre-approval expert view) — replace the `notes_localized` translate block
    with: `summary_for_expert = job.summary_expert or job.summary`, then if `not job.summary_expert
    and job.summary and job.expert_language and job.expert_language != job.customer_language:
    summary_for_expert = await vision_llm.translate(job.summary, job.expert_language)`. Pass
    `summary=summary_for_expert` into `ResolvedJob`, drop `classification_notes_localized`. This is
    the one legitimate use of `translate()` here — a stopgap for the expert reading *before* they've
    submitted notes (no `summary_expert` exists yet); once they approve, `generate_report.py`
    produces a properly natively-generated `summary_expert` and this codepath stops mattering for
    that job.

After `schemas.py` changes: run `mise run schema:sync` to regenerate `be/openapi.json` and
`fe/types/api.ts` — never hand-edit `fe/types/api.ts`.

## Email (expert-review-request notification)

`classification_notes` as a param name is misleading once it's carrying the full assessment, not
"notes" — rename to `assessment_summary` for clarity while touching these files:

- `be/app/domain/ports/email.py` — `send_expert_review_request(..., classification_notes: str |
  None = None, ...)` → `assessment_summary`.
- `be/app/adapters/email/resend.py` — param + template variable rename.
- `be/app/adapters/email/templates/expert_review.html` — `{{ classification_notes }}` →
  `{{ assessment_summary }}`.
- `expert_notifier.py`'s call site — pass the renamed kwarg.

## Renderer / PDF

- **`xhtml2pdf.py`** — `summary = summary_override or classification.summary or
  classification.reasoning_en or ""` → drop the `reasoning_en` fallback (field is gone):
  `summary = summary_override or classification.summary or ""`.
- **Markdown rendering gap** — `report.html` currently does `{{ summary }}` with no
  markdown-to-HTML conversion, so `**bold**`/`- bullets` render as literal characters in the PDF.
  Now that `summary` carries the full structured depth, this needs fixing or the depth won't
  actually display correctly in the one artifact that persists. `markdown>=3.10.2` is already in
  `be/pyproject.toml` — no new dependency. Two traps in the conversion step:
  1. **Autoescape** — the Jinja env (`xhtml2pdf.py:14`) has `autoescape=True`, so passing the
     converted HTML as a plain string through `{{ summary }}` re-escapes it and the PDF shows
     literal `<strong>` tags. Wrap the converted output in `markupsafe.Markup` before putting it
     in the template context.
  2. **HTML injection** — python-markdown passes raw HTML through by default, `summary` is LLM
     output downstream of customer free text (a prompt-injection surface), and
     `expert_note_localized` carries expert free text. HTML-escape the source text
     (`markupsafe.escape`) *before* the markdown conversion, then convert, then `Markup`-wrap —
     markdown syntax survives escaping; raw HTML doesn't.
- **`report.html`** — move the `expert_note_localized` block ("Expert Note" section) to after
  "Submitted Photos", right before the footer — a true reference/citation at the bottom, not a
  second section competing with the main assessment for attention. Also delete the dead
  `{% elif notes %}` branch — the renderer never passes `notes` into the context.
- **`weasyprint.py`** (disabled reference adapter, kept for future high-fidelity rendering) —
  `notes=classification.reasoning_en` → `notes=classification.summary`, so mypy strict doesn't
  choke on a removed field even though this adapter isn't wired up.

## Migration

`be/app/adapters/persistence/orm_models.py` — remove `JobRow.classification_notes` column.
`be/app/adapters/persistence/pg_job_repo.py` — drop `classification_notes=row.classification_notes`
from `_row_to_job`. Then:

```bash
cd be && mise exec -- uv run alembic revision --autogenerate -m "drop classification_notes column"
```

Review the generated migration file before committing (per `CLAUDE.md`'s schema-change workflow).

Dropping the column discards existing rows' `classification_notes` (the only full-depth text for
jobs created before this change, whose `summary` is the short paraphrase). Accepted — not live yet,
no data worth backfilling.

## Frontend

- **`fe/ui/business/ReportView.tsx`** — collapse `ReportGallery` + `ReportSynthesis` into one card:
  photos + defect_type/severity badges + the single `summary` narrative (rendered via `Markdown`).
  Delete all `classification_notes_localized` references. One consistent title instead of
  "AI Assessment" vs "Final review".
- **`fe/ui/business/ExpertReviewPage.tsx`** — no change needed; it already renders the shared
  `ReportView`, so the expert sees the exact same single card, just backed by whatever `summary`
  the API resolved for them (translated pre-approval, natively `summary_expert` post-approval, per
  the `admin.py` change above).
- **i18n** (`fe/services/tech/i18n/{en,de,ru}.ts`) — remove `report_final_review_label`; repurpose
  `expert_review_ai_section` as the single card's title across all three locale files (or introduce
  one new shared key — pick whichever reads better once the card is drafted).
- Run `mise run schema:sync` (see API layer section) before touching `ReportView.tsx`'s types, so
  `Report.classification_notes_localized` is already gone from `fe/types/api.ts`.

## Tests

- **`be/tests/fakes.py`** — `VisionLLMStub`: merge `assess()`/`expert_synthesize()` stub logic into
  one `assess()` matching the new signature (`prior_summary`, `expert_notes`, `expert_language`);
  when `expert_notes` is given, behave like today's `expert_synthesize()` stub (produce
  `summary_expert`/`expert_note_localized`); when `prior_summary` is given but no `expert_notes`,
  reflect that the summary was extended, not replaced. Delete the stub's separate
  `expert_synthesize()` method. Update/remove the `reasoning_en` comment and field.
- **`be/tests/test_pipeline.py`** — update assertions referencing `reasoning_en`/
  `classification_notes`/`expert_synthesize`; add assertions that `prior_summary` is passed on the
  loop-rerun path and that `expert_notes` is passed (and `prior_summary` still populated) on the
  post-expert-review path.
- **`be/tests/test_report.py`** — update the 8 references to removed symbols:
  `classification_notes=` fixtures (lines 396, 455, 668), `classification_notes_localized`
  assertions (lines 408, 464, 594–595), and the `expert_synthesize` comment (line 253).
- **`be/tests/test_e2e_integration.py`** — replace `assert result.reasoning_en` (line 87) with an
  assertion on `summary`.

## File-by-file summary

| File | Change |
|---|---|
| `be/app/domain/job.py` | `DefectClassification.reasoning_en` removed; `Job.classification_notes` removed |
| `be/app/domain/ports/vision_llm.py` | `assess()`/`expert_synthesize()` → one `assess()` |
| `be/app/adapters/vision_llm/anthropic.py` | one merged system prompt + method, depth-preservation + priority rules; `max_tokens` 4096 → 8192 |
| `be/app/adapters/vision_llm/fake.py` | unify E2E fake's `assess()`, branch on `expert_notes` presence, drop `reasoning_en` |
| `be/app/adapters/vision_llm/openai.py` | drop `reasoning_en`, match new signature (dead code, mypy consistency) |
| `be/app/application/pipeline/state.py` | drop `classification_notes`, `reasoning_en` |
| `be/app/application/pipeline/nodes/ai_assessment.py` | derive `prior_summary`, drop removed fields |
| `be/app/application/pipeline/nodes/expert_notifier.py` | read `summary` instead of `classification_notes`; fix `expert_lang` comparison |
| `be/app/application/generate_report.py` | call unified `assess()` instead of `expert_synthesize()` |
| `be/app/application/respond_to_job.py` | drop removed fields; `_base_state` reconstructs prior `DefectClassification` from Job row; `_accept` loses its duplicate construction |
| `be/app/application/run_assessment.py` | drop removed fields from initial state |
| `be/app/application/get_report.py` | drop `translate()`-on-read block + `classification_notes_localized` |
| `be/app/application/list_jobs.py` | drop unused `classification_notes_localized` field |
| `be/app/api/schemas.py` | drop `classification_notes_localized` from `ReportItem` |
| `be/app/api/routes/report.py` | drop `classification_notes_localized=...` |
| `be/app/api/routes/admin.py` | drop `classification_notes_localized`; new `summary_for_expert` translate-fallback logic |
| `be/app/domain/ports/email.py`, `adapters/email/resend.py`, `adapters/email/templates/expert_review.html` | rename `classification_notes` → `assessment_summary` |
| `be/app/adapters/renderer/xhtml2pdf.py` | drop `reasoning_en` fallback; add escape→markdown→`Markup` rendering (autoescape-safe, injection-safe) |
| `be/app/adapters/renderer/templates/report.html` | reposition Expert Note block to the bottom; delete dead `{% elif notes %}` branch |
| `be/app/adapters/renderer/weasyprint.py` | `notes=classification.summary` (dead code, mypy consistency) |
| `be/app/adapters/persistence/orm_models.py` | drop `classification_notes` column + migration |
| `be/app/adapters/persistence/pg_job_repo.py` | drop `classification_notes` from `_row_to_job` |
| `be/tests/fakes.py` | unify `VisionLLMStub.assess()`, drop `expert_synthesize()` |
| `be/tests/test_pipeline.py` | update assertions for the unified call |
| `be/tests/test_report.py` | update `classification_notes`/`classification_notes_localized` fixtures + assertions |
| `be/tests/test_e2e_integration.py` | `assert result.reasoning_en` → assert on `summary` |
| `fe/ui/business/ReportView.tsx` | collapse two cards into one |
| `fe/services/tech/i18n/{en,de,ru}.ts` | drop/repurpose title keys |
| `fe/types/api.ts` | regenerated via `mise run schema:sync`, not hand-edited |

---

## Verification

1. `mise run "qa:be"` after the renames/removals.
2. `mise run schema:sync` after `schemas.py` changes; confirm `fe/types/api.ts` diff only removes
   `classification_notes_localized` and nothing else shifts unexpectedly.
3. Manual, pass 1: submit a defect photo set, accept without replying — confirm the single
   displayed card and the downloaded PDF both show full causal-reasoning depth (Finding/Probable
   cause/Severity reasoning/Further checks), not a shortened paraphrase, and that there is only one
   text section, not two.
4. Manual, customer-reply rerun: reply with free text — confirm the regenerated `summary` is
   visibly extended (references the new information) rather than shorter or reset to a generic
   paraphrase.
5. Manual, expert-review path: submit expert notes that contradict the AI's initial read on one
   point — confirm the final `summary` defers to the expert on that point, still shows the full
   depth (not compressed to "professional, concise"), and that `expert_note_localized` appears as a
   verbatim citation at the bottom of the PDF, not paraphrased into the main narrative.
6. Confirm the expert-facing view (`ExpertReviewPage`) and customer-facing view render identically
   in shape (same single card), differing only in which language `summary` happens to be in.

---

## Test sequence once implemented

Two passes, both targeting `localhost`, fake before real:

1. `E2E_ENV=local mise run fe-e2e` — the regular Playwright suite against the local stack, fake AI
   (`X-E2E-Fake-Ai: 1`, canned vision/LLM response). Exercises upload, DB, background jobs, the
   clarification loop, PDF, email with a fixed response, catching wiring/regression breaks
   (removed-field references, broken routes, the collapsed `ReportView` card, `schema:sync` drift)
   without spending on or waiting for the real model. Must be green first.
2. Only once (1) is green: `E2E_ENV=local mise run fe-e2e-real-ai` — the same flows against the
   real Anthropic pipeline, still on `localhost`. This is the actual test of the unified prompt
   itself: full depth preserved on the first pass, extended (not reset) after a customer reply,
   expert notes overriding the AI's own prior reasoning with visible attribution, and
   `expert_note_localized` showing up as a verbatim citation — the qualitative checks from the
   Verification section above, exercised through the real UI rather than by hand.
