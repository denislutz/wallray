# Testing Plan — Closing the Repository/Default Gap

Triggered by a real bug: `customer_language` was silently dropped in
`PostgresJobRepository.save()` — never added to the `INSERT`, so every job
fell back to the ORM column's `server_default="en"`. No test caught it
because every test exercising `customer_language` used `JobRepoFake`
(an in-memory stand-in), and no test exercising the real Postgres repository
ever checked that specific field survived a round-trip. The bug was
invisible: wrong data, no error, no failing test.

---

## Root Cause Pattern

This is a general shape, not a one-off:

1. A domain field has a default (`Job.customer_language: str = "en"`).
2. The default is repeated at the ORM layer (`server_default="en"`).
3. A mapping function (`save()`, `_row_to_job()`, a schema's `_to_report_item()`)
   forgets to wire the field through.
4. Nothing errors — the default silently absorbs the gap at whichever layer
   dropped it, and the result *looks* like valid data.
5. Unit tests built on fakes (`JobRepoFake`, `UserRepoFake`) don't catch it,
   because fakes don't have the ORM's column list to miss a field from.

Any field with a default, on any dataclass that has a matching ORM row, is
at risk of this. Fields without a default are safer here — a missing field
raises immediately (`TypeError` or a DB `NOT NULL` violation) instead of
silently resolving to a plausible-looking value.

---

## Gap 1 — No repository round-trip tests against the real DB

**Problem:** `be/tests/test_report.py`, `test_pipeline.py` etc. construct
`Job`/`User` objects and hand them to `JobRepoFake`/`UserRepoFake` for
*use-case* unit tests. That's correct and should stay — but it means the
real `PostgresJobRepository` / `PostgresUserRepository` mapping code
(`save()`, `get()`, `_row_to_job()`, `upsert()`) has no dedicated test of
its own. It's only incidentally exercised through HTTP tests that don't
assert on most fields.

**Fix:** add one test module per repository that does a real save → real
get round-trip against the test Postgres/SQLite session (the same
`db_engine` fixture `test_upload.py` already uses), constructing a `Job` /
`User` with **every** field set to a non-default, distinguishable value,
then asserting the fetched-back object equals the original field-for-field.

```python
# be/tests/test_job_repo.py (new)
async def test_save_and_get_round_trips_every_field(db_engine: AsyncEngine) -> None:
    session = async_sessionmaker(db_engine, expire_on_commit=False)()
    repo = PostgresJobRepository(session)

    job = Job(
        id="job-rt-1",
        user_id=TEST_USER_ID,
        status=JobStatus.pending,
        photos=[Photo(key="k", content_type="image/jpeg", thumb_key="t")],
        description="desc",
        created_at=datetime.now(UTC),
        thumbnail_key="thumb",
        defect_type="crack",
        severity="high",
        report_key="report.pdf",
        error=None,
        request_expert_review=True,
        expert_notes="notes",
        name="name",
        assigned_expert_id="expert-1",
        customer_language="de",       # <- the field this bug dropped
        expert_language="ru",
        classification_notes="raw notes",
        expert_report_key="expert.pdf",
    )
    await repo.save(job)

    fetched = await repo.get(job.id)
    assert fetched == job  # Job should be a comparable @dataclass
```

This single test would have failed immediately on the bug that motivated
this plan (`fetched.customer_language == "en"`, not `"de"`).

**Applies to:** `PostgresJobRepository`, `PostgresUserRepository`. Extend to
any new repository added later.

**Maintenance rule:** whenever a field is added to `Job`, `User`, or their
ORM rows, this test's constructor call must be updated to set it to a
non-default value. Field lists drifting apart (dataclass has 17 fields,
test only sets 12) is the exact hole this closes — a code reviewer can spot
"field added to `Job` but not to `test_save_and_get_round_trips_every_field`"
as a one-line diff check.

---

## Gap 2 — No end-to-end test for "field chosen at intake survives to output"

**Problem:** Even with Gap 1 closed, there was still no test proving the
*user-facing promise* — "the language I pick at upload is the language I
get back" — end to end through `POST /upload` → `GET /report/{id}`.
Repository-level tests catch storage bugs; they don't catch the case where
the route/use-case layer never reads the right form field, or the response
serializer forgets to map a field (this repo has already had both: this
session also found `report.py`'s `_to_report_item()` omitting
`classification_notes_localized`/`photo_urls`/`photo_thumb_urls` entirely).

**Fix:** for every "user picks X at intake, X shapes what they see later"
feature, add one HTTP-level test through the real app + real DB
(`assess_client`, so the background pipeline runs synchronously) that sets
a non-default value for X and asserts it shows up transformed correctly in
the read path. Added as part of this session:

```python
# be/tests/test_report.py
async def test_upload_persists_customer_language_through_real_repository(
    assess_client: AsyncClient,
) -> None:
    resp = await assess_client.post("/upload", files=[...], data={"language": "de"}, ...)
    job_id = resp.json()["job_id"]
    resp = await assess_client.get(f"/report/{job_id}", ...)
    assert resp.json()["classification_notes_localized"].startswith("[de] ")
```

**Other candidates for this pattern** (fields chosen at intake that must
survive to a later read):

| Field chosen at intake | Where it's set | Where it must show up | Test exists? |
|---|---|---|---|
| `language` (customer) | `POST /upload` | `GET /report/{id}` → `classification_notes_localized` | ✅ added this session |
| `assigned_expert_id` | `POST /upload` | `GET /admin/jobs/{id}` → `assigned_expert_email` on `GET /report/{id}` | ⚠️ indirectly covered, no dedicated test |
| `name` | `POST /upload` | `GET /jobs`, `GET /report/{id}` | ⚠️ indirectly covered |
| expert's `preferred_language` | `PATCH /me/language` | next job assigned to that expert → `expert_language` on the job | ❌ not covered |
| `request_expert_review=false` (no expert requested) | `POST /upload` | job never enters `expert_review`, `report_url` populates without expert step | ❌ not covered |

---

## Gap 3 — Schema/response mapper drift (`_to_report_item`-style functions)

**Problem:** `report.py`'s `_to_report_item()` and `admin.py`'s
`_to_report_item()` are two hand-written functions mapping the same
`ResolvedJob` dataclass to the same `ReportItem` schema, and they'd drifted
— one had 3 fewer fields mapped than the other, silently (no type error,
since all `ReportItem` fields have defaults of `None`/`False`).

**Fix — pick one:**

- **Cheap, immediate:** a test that constructs a `ResolvedJob` with every
  field set to a non-default value, calls both `_to_report_item()`
  functions, and asserts the two `ReportItem` results are equal except for
  fields that are legitimately role-specific (document why each excluded
  field differs, e.g. `request_expert_review` is intentionally not exposed
  on the admin/expert response).
- **Structural, longer-term:** collapse the two `_to_report_item()`
  functions into one shared mapper (`app/api/schemas.py` or a small
  `app/application/report_presenter.py`), since `report.py` and `admin.py`
  are mapping the exact same `ResolvedJob` → `ReportItem` shape today. One
  function can't drift from itself.

---

## Gap 4 — Hardcoded literals duplicating source constants

**Problem:** Tests re-type magic numbers/strings that already exist as a
named constant in the source (e.g. `test_upload.py` seeded
`report_count=3` to simulate "at the free tier limit," duplicating
`upload_job._FREE_TIER_LIMIT` instead of referencing it). When the source
constant changes, the duplicated literal goes stale silently — the test
keeps passing (or starts failing for the wrong reason) because it's
asserting against a copy-pasted number, not the actual rule.

**Fix:** go through the test suite and replace hardcoded literals that
mirror a source-level constant with a reference to that constant, and
prefer property-based assertions over fixed example values wherever the
thing under test is a *rule* ("at the limit → rejected," "over max size →
downscaled") rather than a specific fixture. Concretely:

- Import and use the real constant (`_FREE_TIER_LIMIT`, `_ALLOWED_TYPES`,
  size caps, etc.) instead of re-typing its value in the test.
- Where a test asserts a boundary condition, assert it as a relationship
  to the constant (`report_count == _FREE_TIER_LIMIT`,
  `size == settings.max_upload_bytes + 1`) rather than a bare literal, so
  the test still expresses the right thing if the constant changes.
- Where it's cheap, prefer `hypothesis`-style generated inputs (e.g. any
  `report_count >= _FREE_TIER_LIMIT` should 402, any count below should
  not) over a single hand-picked example, so the test verifies the
  *property* the code is supposed to guarantee, not one point on it.

---

## Why defaults specifically make this worse

A field *without* a default fails loudly the moment it's dropped —
`TypeError: missing required argument` at the dataclass constructor, or a
DB `NOT NULL` violation at insert. A field *with* a default (dataclass
default, ORM `server_default`, or both, as `customer_language` had) fails
silently: the gap resolves to a plausible value and the bug ships.

This doesn't mean "remove all defaults" — `customer_language` needs one,
since older rows and any code path that doesn't set it explicitly must
still work. But it does mean: **the presence of a default is a signal that
a round-trip test is required**, not optional, because a missing-field bug
on a defaulted field will never announce itself any other way.

---

## Action Items

- [ ] Add `be/tests/test_job_repo.py` and `test_user_repo.py` — full-field
      round-trip tests against the real Postgres repository (Gap 1).
- [ ] Fill in the ❌ rows in the Gap 2 table with dedicated intake→output
      tests.
- [ ] Decide on Gap 3's fix (shared mapper preferred — removes the
      drift risk structurally instead of just testing for it) and apply it.
- [ ] When adding a field to `Job`, `User`, or any other aggregate with a
      matching ORM row: update the Gap 1 round-trip test in the same PR.
      Treat "field added to dataclass, not added to round-trip test" as a
      review blocker.
- [ ] Audit `be/tests/` for hardcoded literals duplicating a source
      constant (limits, allowed-type sets, size caps) and replace with a
      reference to the constant; convert boundary-condition tests to
      property-based assertions where feasible (Gap 4).
