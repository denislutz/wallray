# Playwright E2E UI Test Suite

## Context

Cypress/Playwright research led to picking Playwright, kept code-first (no hosted AI-native
platform). The gap today: `fe/` has no test framework at all, and CI (`ci.yml`) only runs
lint/typecheck/unit-tests + build before auto-deploying to the test environment — there is no
real browser-driven check of the actual UI. The goal is a full-scale Playwright suite that
exercises the real deployed test environment (`test.wallray.app` / `test.app.wallray.app` /
`test.api.wallray.app`) after every push to `main`, plus on demand for ad-hoc runs. This
specifically matters because two real production bugs (`docs/tech/DEVOPS.md` — the `host` vs
`hostname` port bug and NextAuth's `trustHost` origin rewrite) only manifested with two real,
distinct domains and could not have been caught locally or by unit tests — the test environment
is the only place that class of bug is visible.

Decisions already made with the user:

- **Auth**: most specs log in via direct NextAuth session-cookie injection (fast, deterministic);
  one dedicated spec still drives the real OTP UI end-to-end.
- **Trigger — regular (fake-AI) suite**: runs automatically in CI, as a new job appended to
  `.github/workflows/ci.yml` after `deploy-test` — see §9. A Claude-Code trigger phrase in
  `.claude/project-specifics.md` also exists for ad-hoc local/on-demand runs.
- **Trigger — full-scale real-AI suite**: **not** in CI. Claude-Code-triggered convention only,
  explicit and separate from the regular trigger, since it costs real Anthropic API calls and is
  slower/nondeterministic — never something that should fire on every push.
- **Default target**: the test environment (not local), because that's where the domain-routing
  bug class actually lives; local stays available as a fast-iteration opt-in.
- **AI calls**: the regular/default suite must never call the real Anthropic API — it should be
  fast, free, and deterministic by substituting canned responses for the vision/LLM port only,
  while every other layer (upload, DB writes, background-task orchestration, the clarification-loop
  state machine, PDF rendering, email dispatch) stays 100% real. The separate real-AI trigger
  (built after the fast path lands) runs the same journeys against the real Anthropic pipeline for
  true full-scale AI verification.

---

## 1. Package + config

Install from `fe/` (standalone pnpm project, not a workspace-filtered install):

```bash
mise exec -- pnpm add -D @playwright/test
mise exec -- pnpm exec playwright install --with-deps chromium
```

New `fe/playwright.config.ts`:

- Reads `E2E_ENV` (`local` | `test`, **default `test`**).
- Base URLs: `test` → `https://test.app.wallray.app` (app), `https://test.wallray.app`
  (marketing), `https://test.api.wallray.app` (api). `local` → all `http://localhost:3000` /
  `http://localhost:8000` (matches DEVOPS.md's note that marketing+app share one host locally).
- `globalSetup: "./e2e/global-setup.ts"`, `testDir: "./e2e/specs"`,
  `use: { storageState: "e2e/.auth/user.json" }` as the suite-wide default.
- `reporter: [["html", { open: "never" }], ["list"]]`.
- Single `chromium` project to start — no cross-browser matrix yet, this is about coverage depth
  not browser matrix.
- `use.extraHTTPHeaders: { "X-E2E-Fake-Ai": "1" }` at the top-level `use` block — the default
  project sends this on every request, which is what keeps the regular suite off the real
  Anthropic API (see §5a). A second `projects` entry, `real-ai`, points at `./e2e/specs-real-ai`
  and does **not** set this header — excluded from the default `playwright test` run, only
  invoked explicitly (see §9).

## 2. Directory structure

```
fe/e2e/
  global-setup.ts
  fixtures/
    testUser.ts           # fixed E2E test user id/email
  specs/                   # default project — fake vision_llm, always run
    marketing.spec.ts      # landing + /de + /ru render, links to sign-in
    domain-routing.spec.ts # logged-out: marketing-path→marketing-host, app-path→app-host redirects
    auth.spec.ts           # real OTP UI flow (send code → enter code → verify)
    reports-new.spec.ts    # NewReportPage: fill form, upload photos, submit
    assessment.spec.ts     # poll job to terminal status, clarification loop, PDF availability
    expert-review.spec.ts  # expert/review/[jobId] approve flow
    account.spec.ts        # account page smoke
  specs-real-ai/           # `real-ai` project — real Anthropic calls, not part of default run
    assessment.spec.ts     # same journey as specs/assessment.spec.ts, no fake-AI header
  .auth/                   # storageState output — gitignored
```

Lives outside `ui/`, `services/`, `types/` — E2E specs aren't part of the 4-layer app
architecture (`.claude/fe-domain-rules.md` governs application code, not test harnesses).

## 3. Session-cookie global setup (`fe/e2e/global-setup.ts`)

1. `dotenv.config({ path: process.env.E2E_ENV === "local" ? "../.env.local" : "../.env.test" })`
   — picks up the already-present `AUTH_SECRET` for the target env (confirmed present in
   `fe/.env.test`, gitignored, no new secret storage needed).
2. Drive the **real** backend once against the target API base URL:
   - `POST /auth/otp/send { email: TEST_USER_EMAIL }`
   - `GET /auth/otp/debug?email=...` → plaintext code (new endpoint, §5)
   - `POST /auth/otp/verify { email, code }` → `{ id, email, name }`. This call is also the seed
     step: `verify_otp` in `be/app/api/routes/auth.py` already auto-creates the `UserRow` if one
     doesn't exist for that email — so no separate seed script is needed, and re-running is safe
     (idempotent: existing user is just returned).
3. Mint the session token with `encode` from `next-auth/jwt`:
   `encode({ token: { sub: id, email }, secret: process.env.AUTH_SECRET, salt: <cookie name> })`.
   NextAuth auto-fills `iat`/`exp`/`jti`. The `session()` callback in `AuthS.ts` re-derives
   `apiToken` fresh on every request from `sub`/`email`, so nothing else needs to be replicated.
4. `context.addCookies([...])` with cookie name `__Secure-authjs.session-token` (test env, HTTPS)
   or `authjs.session-token` (local), domain = the **app** host only (`test.app.wallray.app` /
   `localhost`) — marketing pages are public and need no cookie.
5. `context.storageState({ path: "e2e/e2e/.auth/user.json" })`, reused by every spec via
   `playwright.config.ts`'s default `use.storageState`.
6. `domain-routing.spec.ts` explicitly overrides with `test.use({ storageState: { cookies: [],
   origins: [] } })` to test logged-out redirect behavior specifically.

## 4. `GET /auth/otp/debug` — `be/app/api/routes/auth.py`

The stored code is bcrypt-hashed only (`code_hash`), never persisted in plaintext — a debug
endpoint needs a transient plaintext capture:

```python
_last_otp_codes: dict[str, str] = {}  # module-level, in-memory, test/local only

# inside send_otp, after computing `code`:
if settings.debug:
    _last_otp_codes[str(body.email)] = code

@router.get("/otp/debug")
async def debug_otp(email: str) -> dict[str, str]:
    if not settings.debug:
        raise HTTPException(status_code=404)
    code = _last_otp_codes.get(email)
    if code is None:
        raise HTTPException(status_code=404, detail="No OTP sent for this email")
    return {"code": code}
```

`settings.debug` is `False` in prod, `True` in test/local (`be/app/core/config.py`) — this route
is a 404 no-op in prod regardless of who calls it. No ORM change → no Alembic migration.

`auth.spec.ts` calls this endpoint directly (`page.request.get`) to read the code, then types it
into the real sign-in UI (`fe/app/(app)/auth/signin/`), exercising `AuthS.sendOtp` →
`signInWithOtp` → the `credentials` NextAuth provider for real — independent of the cookie
shortcut everything else uses.

## 5. Faking the vision/LLM port — the seam that makes the regular suite fast + free

Found the exact injection point: `be/app/api/deps.py` already resolves the real adapter through a
per-request FastAPI dependency, not a hardcoded import:

```python
def get_vision_llm(
    container: Annotated[Container, Depends(get_container)],
) -> VisionLLMPort:
    return container.vision_llm
```

And `container.vision_llm` is a single `AnthropicAdapter` instance built once in
`be/app/core/container.py::build()`. `AnthropicAdapter` implements `VisionLLMPort`
(`validate_intake`, `translate`, `assess`, `expert_synthesize` — `be/app/domain/ports/vision_llm.py`),
consumed only by the LangGraph pipeline nodes (`be/app/application/pipeline/`,
`be/app/application/run_assessment.py`) — the orchestration/state-machine logic (including the
`awaiting_customer_input` pause in `nodes/await_customer_answers.py`) is separate from the port and
stays real either way.

**Changes**:

1. New `be/app/adapters/vision_llm/fake.py` — `FakeVisionLLMAdapter` implementing the same port,
   instant/deterministic, no network call:
   - `validate_intake`: always `accepted=True`, assigns roles round-robin
     (`close_up`, `context`, `repeat_location`) across the given photo keys.
   - `assess`: **first call for a given job returns one `customer_question` verification item**
     (e.g. "How old is the building?") alongside a fixed `defect_type`/`severity`/`summary` —
     this is what drives the real `await_customer_answers` node to pause at
     `awaiting_customer_input`, so the clarification-loop UI/state machine still gets genuinely
     exercised, not skipped. A second call (after `POST /jobs/{id}/respond`) returns the same fixed
     classification with an empty `verification_items` list, letting the graph proceed to
     `complete`. (Call count keyed by job's photo-keys tuple, held in a small in-memory dict —
     mirrors the real "first assess, then re-assess after answer" shape without needing job state.)
   - `translate`: identity (returns input unchanged) — fine since assertions never check exact
     AI-authored text (see §6).
   - `expert_synthesize`: fixed canned `DefectClassification`, same idea.
2. `Container` (`be/app/core/container.py`) gains a second field, `fake_vision_llm:
   FakeVisionLLMAdapter`, constructed unconditionally in `build()` (cheap — no API key, no network).
3. `get_vision_llm` in `be/app/api/deps.py` becomes header-gated, debug-only:

   ```python
   def get_vision_llm(
       request: Request,
       container: Annotated[Container, Depends(get_container)],
   ) -> VisionLLMPort:
       if settings.debug and request.headers.get("x-e2e-fake-ai") == "1":
           return container.fake_vision_llm
       return container.vision_llm
   ```

   `settings.debug` is `False` in prod (`be/app/core/config.py`) — this header has zero effect in
   prod no matter who sends it. In test/local, the header is only ever sent by Playwright's
   default project (`use.extraHTTPHeaders`, §1), so a human manually using `test.wallray.app` for
   normal QA still gets the real Anthropic pipeline; only Playwright-originated requests get the
   fake. Since `upload.py`'s route handler resolves `vision_llm` via `Depends(get_vision_llm)`
   before scheduling the background assessment task, the selection made at request time is what
   the background task actually runs with — no extra plumbing needed for `BackgroundTasks`.
4. No ORM/schema change → no Alembic migration.

This is what makes the *default* run "pretty realistic and fast": real upload, real multipart
handling, real DB persistence, real background-task scheduling, real clarification-loop state
transitions, real PDF rendering (`Xhtml2pdfAdapter`, untouched), real email dispatch (Resend,
already isolated to the test env's `noreply+test@example.com`) — only the actual model call is
swapped for a fixed, known response.

## 6. Core assessment flow (`fe/e2e/specs/assessment.spec.ts`)

Journey: `NewReportPage.tsx` (fill name/description/language, upload photos) → `POST /upload` →
poll `GET /report/{job_id}` → `ReportPage.tsx`. With the fake port (§5) active by default, this
resolves in a few seconds (dominated by DB writes/background-task scheduling, not model latency),
so a short poll timeout is enough — no need for the 60–120s budget a real call would require.

- `expect.poll(...)` the job status (`JobStatus` enum: `pending → processing →
  awaiting_customer_input | expert_review | complete | failed`) with a short timeout
  (a few seconds) until it reaches `awaiting_customer_input` (expected, given the fake's first
  response — see §5).
- Answer the clarifying question via the real UI (`POST /jobs/{id}/respond`), poll again to
  `complete`.
- Assert `defect_type`, `severity`, and the `report_key`-backed PDF link are populated — since the
  fake returns fixed values, these can be asserted **exactly**, not just non-null, which is a
  strictly stronger check than a real-AI run could ever give the default suite.
- `expert_review` path: covered separately by `expert-review.spec.ts`. The request itself happens
  at `await_customer_answers`, not on the upload form — `POST /jobs/{id}/respond` with
  `request_expert_review: true` and `assigned_expert_id` set, mutually exclusive with replying —
  and routes straight to `expert_review` with `report_key` still null (no AI-only PDF rendered).
  The expert's own approval step is unchanged: `POST /jobs/{id}/approve`, also instant via the
  fake `expert_synthesize`.

## 7. Full-scale real-AI run (follow-up, not part of the regular trigger)

Structurally slotted in now so it drops in cleanly later, built out after the fast path above is
working:

- `fe/e2e/specs-real-ai/assessment.spec.ts` — same journey as §6, but run under the `real-ai`
  Playwright project (§1), which has no `X-E2E-Fake-Ai` header — every request hits the real
  Anthropic pipeline. Assertions here can't rely on fixed values: assert non-null/populated
  `defect_type`/`severity`/PDF link (as originally planned before this adjustment), with a
  generous timeout (`test.setTimeout(120_000)`+) to absorb real model latency.
- New mise task, `fe-e2e-real-ai` → `pnpm exec playwright test --project=real-ai`.
- A distinct, separate trigger phrase in `.claude/project-specifics.md` (e.g. "run full AI e2e" /
  "test with real AI") — never folded into the "test the UI" default trigger, so routine
  post-rework runs never incur LLM cost/latency/nondeterminism by accident.

## 8. mise tasks (`mise.toml`)

```toml
[tasks.fe-e2e-install]
description = "Install Playwright browsers (one-time)"
dir = "fe"
run = "pnpm exec playwright install --with-deps chromium"

[tasks.fe-e2e]
description = "Run Playwright E2E suite (default: test env, fake AI; E2E_ENV=local for localhost)"
dir = "fe"
run = "pnpm exec playwright test"

[tasks.fe-e2e-real-ai]
description = "Run the real-AI E2E project — actual Anthropic calls, not part of the default suite"
dir = "fe"
run = "pnpm exec playwright test --project=real-ai"
```

`E2E_ENV` defaults to `test` inside `playwright.config.ts` itself, so `mise run fe-e2e` targets
the test environment out of the box; `E2E_ENV=local mise run fe-e2e` for fast local iteration.

## 9. CI workflow — new `e2e` job in `.github/workflows/ci.yml`

Runs the regular (fake-AI) suite automatically after every push to `main`, once the test
environment has redeployed — appended after the existing `deploy-test` job:

```yaml
  e2e:
    runs-on: ubuntu-latest
    needs: [deploy-test]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    env:
      AUTH_SECRET: ${{ secrets.AUTH_SECRET_TEST }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Enable pnpm
        run: corepack enable && corepack prepare pnpm@11.8.0 --activate

      - name: Install dependencies
        working-directory: fe
        run: pnpm install --frozen-lockfile

      - name: Install Playwright browsers
        working-directory: fe
        run: pnpm exec playwright install --with-deps chromium

      - name: Wait for test environment to redeploy
        run: |
          # Phase 1: /health's `version` field is the backend's start timestamp — poll until it's
          # newer than a reference time captured before polling, proving the *new* build is live
          # (a bare reachability check can't tell old vs. new code apart, see below).
          REFERENCE_TIME=$(date -u +%s)
          for i in $(seq 1 30); do
            RESPONSE=$(curl -fsS https://test.api.wallray.app/health || true)
            VERSION=$(echo "$RESPONSE" | jq -r '.version // empty')
            if [[ -n "$VERSION" ]]; then
              VERSION_EPOCH=$(date -u -d "$VERSION" +%s 2>/dev/null || echo 0)
              if [[ "$VERSION_EPOCH" -ge "$REFERENCE_TIME" ]]; then
                echo "new build is live (version=$VERSION)"
                break
              fi
              echo "still old build (version=$VERSION) — waiting... ($i/30)"
            else
              echo "backend not reachable yet — waiting... ($i/30)"
            fi
            sleep 10
            if [[ "$i" -eq 30 ]]; then
              echo "test backend never redeployed with the new build" >&2
              exit 1
            fi
          done

          # Phase 2: /health needs no DB and answers instantly even mid-startup, so it passing
          # doesn't prove the app is actually ready — a fresh container can still be finishing
          # Alembic migrations or warming up its DB connection pool. Confirm a real, DB-touching
          # request also succeeds before handing off to the suite.
          echo "confirming a DB-touching endpoint is responsive..."
          for i in $(seq 1 12); do
            STATUS=$(curl -s -o /dev/null -m 15 -w "%{http_code}" -X POST \
              -H "Content-Type: application/json" \
              -d '{"email":"e2e-warmup@wallray.app"}' \
              https://test.api.wallray.app/auth/otp/send || echo "000")
            if [[ "$STATUS" == "200" ]]; then
              echo "backend is warmed up (otp/send responded 200)"
              exit 0
            fi
            echo "otp/send returned $STATUS — waiting for DB warmup... ($i/12)"
            sleep 5
          done
          echo "backend never warmed up (otp/send never returned 200)" >&2
          exit 1

      - name: Run E2E suite (fake AI)
        working-directory: fe
        run: pnpm exec playwright test --project=chromium

      - name: Upload Playwright report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: |
            fe/playwright-report/
            fe/test-results/
          retention-days: 14
```

Notes:

- **New GitHub Actions secret required**: `AUTH_SECRET_TEST`, same value as `fe/.env.test`'s
  `AUTH_SECRET` — needed so `global-setup.ts` can mint the session cookie in CI, where there's no
  local `.env.test` to read from. `playwright.config.ts`'s dotenv loading must prefer an
  already-set `process.env.AUTH_SECRET` (CI) over reading a `.env.*` file (local), so the same
  global-setup code works in both places without branching.
- The wait step checks `/health`'s `version` field (the backend process's start timestamp) against
  a reference time captured before polling begins, not just "does `/health` respond" — a bare
  reachability check can't distinguish the old container (still up while Coolify builds the new
  one) from the new one, since `/health` existed before this change too. First discovered the hard
  way: the very first CI run after this feature merged raced ahead on a 200 from the still-old
  container and hit a since-fixed 404/502 on the new-only `/auth/otp/debug` route.
- This job runs **after** `deploy-test` but doesn't gate it — the test environment already
  auto-deploys on every green push regardless of E2E outcome (unchanged from today). It **does**
  gate prod (as of 2026-07-08, see DEVOPS.md's Deploy Workflow section): a separate `deploy-prod`
  job runs only if `e2e` succeeds, so this suite is the actual promotion gate, not just a signal.
- The wait step also confirms the **frontend** has redeployed, not just the backend — the two are
  separate Coolify services that don't necessarily finish at the same time (FE's `next build` is
  often slower). Found the hard way: a run passed locally but failed against test with an
  untranslated label, because the FE container was still serving the previous build while the
  backend had already redeployed. **Updated 2026-07-09**: originally this polled the
  server-rendered "Version: ..." string (`fe/services/tech/BuildTimeS.ts`, a git-commit-time
  stamp regenerated by `code:clean:fe`) and waited for it to change from a pre-deploy value — but
  that string only changes when a commit actually touches `fe/` source, so any commit that didn't
  (a docs change, a `be/`-only fix, a workflow tweak) made this loop the full 3 minutes and fail
  e2e every time, even though the container had genuinely redeployed. Replaced with a real FE
  equivalent of `/health` — `fe/app/api/health/route.ts` returns `StartTimeS.time`
  (`fe/services/tech/StartTimeS.ts`), a timestamp captured once when the Node process starts, not
  tied to git content — and the wait step now uses the exact same reference-time comparison as the
  backend check above it. `BuildTimeS.ts`/`FeVersionLabel.tsx` are unchanged and still drive the
  human-visible "Version: ..." label on `/auth/signin`; they're just no longer load-bearing for
  this check.
- The `real-ai` project is deliberately never invoked from this workflow — see §7/§10.

## 10. `.claude/project-specifics.md` — trigger section

Add, matching the existing "New Cluster Photos" / "Server Logs" section style. Covers the
on-demand/local case — CI (§9) already covers the automatic post-push case for the regular suite:

```markdown
## End-to-End UI Tests (Playwright)

Playwright specs live in `fe/e2e/`, targeting the deployed test environment
(`test.wallray.app` / `test.app.wallray.app` / `test.api.wallray.app`) by default — this is the
only place the real Traefik/SSL/domain-routing layer can be exercised (see DEVOPS.md's domain
routing history). `E2E_ENV=local` is available for fast iteration against `localhost:3000`.

The regular suite runs automatically in CI after every push to `main` (`.github/workflows/ci.yml`
→ `e2e` job) and never calls the real Anthropic API — it sends `X-E2E-Fake-Ai: 1`, which
`be/app/api/deps.py::get_vision_llm` honors only when `settings.debug` is true, substituting a
fixed canned response for the vision/LLM port so the run stays fast, free, and deterministic while
every other layer (upload, DB, background jobs, clarification loop, PDF, email) stays real.

### Auto-trigger — regular suite (fake AI, on-demand)

When the user says **"test the UI"**, **"run e2e"**, **"full UI test"**, or similar — especially
to check something locally before pushing, since CI already runs this automatically after every
push to `main` — run this without asking for more detail:

1. `mise run fe-e2e-install` if Playwright browsers aren't already installed.
2. `mise run fe-e2e` (defaults to the test environment, fake AI).
3. Report pass/fail per spec.
4. On any failure, surface `fe/playwright-report/index.html` and the relevant trace(s) from
   `fe/test-results/` so the user can inspect without re-running.

### Auto-trigger — full-scale real-AI suite (explicit only, never automatic, never in CI)

When the user says **"run full AI e2e"** / **"test with real AI"** — run `mise run
fe-e2e-real-ai` instead. This drives the real Anthropic pipeline (real latency/cost,
nondeterministic content) and must never be substituted for the regular trigger above, and must
never be added to the CI workflow.

Never target prod. Never flip `NEXT_PUBLIC_DEV_AUTH` to `"true"` on test/prod to make this easier
— the cookie-injection approach in `fe/e2e/global-setup.ts` exists specifically so that flag stays
off everywhere except local dev.
```

## 11. `.gitignore`

Add a `# Playwright` block (root `.gitignore` or new `fe/.gitignore`):

```
fe/test-results/
fe/playwright-report/
fe/playwright/.cache/
fe/e2e/.auth/
```

---

## Verification

1. `mise run fe-e2e-install` once, then `E2E_ENV=local mise run fe-e2e` against a locally running
   stack (`mise run start-dev`) — fast loop while building the suite itself.
2. `mise run fe-e2e` (no env override) against the real test environment — confirms cookie
   injection, the debug OTP endpoint, the fake-AI header round-trip, and the domain-routing spec
   all work against real Traefik/SSL, which is the actual point of this suite.
3. Deliberately break `fe/proxy.ts`'s `hostname` check (revert to `.host`) locally against test
   env once, confirm `domain-routing.spec.ts` catches the regression, then revert — proves the
   suite would have caught the two historical bugs DEVOPS.md documents.
4. Manually hit `test.api.wallray.app` (or the local backend) **without** the `X-E2E-Fake-Ai`
   header and confirm a real assessment still runs — proves the fake seam only activates for
   Playwright-originated requests, not for ordinary QA traffic on the same environment.
5. Run `mise run "code:clean:fe"` and `mise run "code:clean:be"` to confirm the new `fe/e2e/**`
   and `be/app/adapters/vision_llm/fake.py`/`deps.py` changes satisfy Biome/tsc and ruff/mypy
   (adjust `fe/tsconfig.json`/`fe/biome.json` includes only if the check fails on the new e2e
   directory).
6. Add the `AUTH_SECRET_TEST` GitHub Actions secret, push a small commit to `main`, and confirm the
   new `e2e` CI job runs after `deploy-test`, passes, and (if deliberately broken once) uploads the
   Playwright report artifact on failure.
