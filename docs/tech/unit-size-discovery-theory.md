# Unit Size Discovery: Infrastructure vs. Feature Code

> Separate your code into infrastructure and feature code — infra code is a better candidate for unit testing.

## Summary Table

| Type                        | Infrastructure Code                                                                                                        | Feature Code                                                                                                                                                   |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Example**                 | Central string formatting, neutral HTTP and REST logic, i18n-logic (Technical Domain)                                      | Special feature code like calculation of persons tax amounts for specific constellations and showing it on the screen (Business Domain)                        |
| **Codebase usages**         | All feature services and potentially components are using it all the time → high usage                                     | Low usage, once per feature, inside a feature stack                                                                                                            |
| **Testability**             | Simpler — high amount of usages enforces a simpler and more stable API; can be functional, resulting in better testability | Rather complicated — requires a surrounding feature context; not used by code from other features                                                              |
| **Refactoring probability** | Low — used by many clients; if a refactoring happens it is a really big one                                                | Higher — can be moved when a feature changes internally (e.g. moving a method to higher or lower stack levels makes existing functional mocks obsolete)        |
| **Unit test friendliness**  | Well suited for isolated tests — many clients, lower chance of refactoring → testing effort of smaller units makes sense   | Only testable as a whole feature; since units are used once, detailed unit testing effort is not justified and can become obsolete after a feature refactoring |
| **Separate unit test**      | **Rather YES** — tested through bigger units AND can be tested alone                                                       | **Rather NO** — tested within as a bigger unit (integration/component test)                                                                                    |

## Key Takeaways

- **Infrastructure code** (HTTP clients, i18n, string utilities, shared services) has high reuse, a stable API, and low refactoring risk — isolate and unit-test these aggressively.
- **Feature code** (business-domain logic tied to a specific screen or workflow) is used once, evolves with the feature, and is hard to test without its surrounding context — prefer integration or component tests here.
- The distinction helps **prioritise testing effort**: writing fine-grained unit tests for feature-specific code creates fragile tests that break with every internal refactor.
- Infra code that passes through many clients naturally develops a cleaner, more testable interface — the high usage acts as design pressure towards better APIs.

---

## The Biggest Problem with Mocks

> Disclaimer: this section only considers mocks in a pure-code / functional-code situation. External systems such as micro-services are not considered.

### The Problem

To isolate a tested unit (`Function1`) from its real collaborators (`F2`, `F3`), every collaborator must be replaced by a static copy — a mock (`FMock2`, `FMock3`). The result is a **net of static copies** that the test author must create, own, and keep in sync with the production code they duplicate.

```text
Tested unit          Productive code       Static copy (managed by test)
──────────────       ───────────────       ─────────────────────────────
Function1()  ──────► F2()                  FMock2()  ◄── managed
             ──────► F3()                  FMock3()  ◄── managed
```

The motivation is isolation. The price is the extra mocked code.

### Why This Matters

| Concern                | Effect                                                                                                                  |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Duplication**        | Every real collaborator gets a parallel mock implementation that must mirror the original                               |
| **Maintenance burden** | When production code changes, all mocks of that collaborator must be updated                                            |
| **False confidence**   | Tests can pass while the real integration is broken — the mock and the real function drift silently                     |
| **Refactoring cost**   | Moving a function to a different stack level invalidates existing mocks (their signatures or behaviour no longer match) |

### Implication for the Unit Size Decision

This is another argument for the infrastructure vs. feature split:

- **Infrastructure code** has a stable, wide-used API → mocks are written once and rarely change → mocking cost is low and justified.
- **Feature code** changes with the feature → mocks written for it become obsolete quickly → the mocking cost exceeds the isolation benefit → prefer integration tests that exercise the real collaborators.

---

## Solution: Rethink Your Unit Size

The answer to the mocks dilemma is not better mock tooling — it is **enlarging the tested unit** so that collaborators are included rather than replaced.

### Core Principles

- Extend the unit boundary to a "comfortable" size — be flexible about what counts as "one unit"
- Use **real collaborators** inside the test instead of mocks
- Accept less isolation in exchange for almost never writing mocks again
- Corner cases that live deep inside a single collaborator (e.g. `F3()`) can still get their own smaller, focused test
- High base coverage is provided by the bigger unit test; the corner-case test covers the remaining ~20%

### How It Looks in Practice

```text
┌─────────────────────────────────────────────┐
│  Tested Unit (enlarged boundary)            │
│                                             │
│  F1()  ──Produktivcode──►  F2()             │
│        ──Produktivcode──►  F3()             │
│                             └─ Extra Case   │
│                                (20%)        │
└─────────────────────────────────────────────┘
        ▲                          ▲
        │                          │
Unit Test F1()              Unit Test F3()
(sociable test,             (corner-case only,
 uses real F2 & F3)          covers the 20%)
```

### Trade-off Summary

| Aspect               | Classic isolated unit test       | Sociable / enlarged unit test            |
| -------------------- | -------------------------------- | ---------------------------------------- |
| Isolation            | High                             | Lower                                    |
| Mock maintenance     | High (one mock per collaborator) | Near zero                                |
| Refactoring safety   | Fragile — mocks drift            | Stable — real code is exercised          |
| Corner case coverage | Inline with the main test        | Separate small test per corner case      |
| Recommended for      | Infra code with stable APIs      | Feature code with internal collaborators |

### Key Insight

> Abolish mocks — let your test use real collaborators. Increase the unit size. Write extra tests only for corner cases that the bigger test cannot reach economically.

---

## The Testing Trophy (Kent C. Dodds)

A general guide for the **return on investment** of different testing forms for JavaScript applications.

```text
        ╱ End to End ╲          ← least, highest cost per test
       ╱───────────────╲
      ╱                 ╲
     ╱    Integration    ╲      ← most investment here (widest layer)
    ╱─────────────────────╲
    ╲       Unit          ╱     ← targeted, focused
     ╲───────────────────╱
      ╲     Static       ╱      ← foundation (types, lint)
       ╲───────────────╱
```

### Layers (bottom to top)

| Layer           | Tools                     | Purpose                                                                         |
| --------------- | ------------------------- | ------------------------------------------------------------------------------- |
| **Static**      | TypeScript / Flow, ESLint | Catch typos and type errors without running code — free and always-on           |
| **Unit**        | Jest / Vitest             | Test pure functions and isolated infra code in isolation                        |
| **Integration** | Jest / Vitest             | Test how multiple units work together — the highest-ROI layer                   |
| **End to End**  | Cypress                   | Validate full user flows through the real UI — highest confidence, highest cost |

### Key Insight

The trophy shape is intentional: **Integration tests give the best return** — they exercise real collaborators (no mocks), cover meaningful behaviour, and are less brittle than fine-grained unit tests. This directly reinforces the "enlarged unit / sociable test" approach above.

Static analysis (TypeScript + lint) is the cheapest safety net and should always be fully enabled. E2E tests are valuable but expensive — use them for critical user journeys only.

---

## Validation: Did We Reach What We Wanted? ✓

Outcome check for the sociable / enlarged-unit approach against the four core testing criteria.

| #   | Criteria                  | Verdict    | Reason                                                                                                                                       |
| --- | ------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Covered**               | Yes        | Big units bring high coverage with low effort                                                                                                |
| 2   | **Correct**               | Mostly Yes | Asserting state at database or global level gives basic correctness; the network of all tests reaches most cases without high mocking effort |
| 3   | **Developer friendly**    | Yes        | Executing as fully rendered components but without a browser gives reasonable speed                                                          |
| 4   | **Refactoring resistant** | Mostly Yes | Black-box testing, central data management, and generated HTTP responses make fast change possible                                           |

### Reading the "Mostly Yes" entries

- **Correctness** is not absolute because the approach trades fine-grained mock-level assertions for broader state-level assertions — some subtle edge-cases require dedicated corner-case tests.
- **Refactoring resistance** is high but not perfect: large structural changes (e.g. replacing a whole service boundary) may still require test updates. Generated HTTP responses (tapes/fixtures) absorb most of that churn automatically.

---

## Dynamic Correctness: Dynamic Test Data

Test data used in tests is called **Fixtures**. Keeping fixtures alive and in sync with the real system is what makes tests dynamically correct.

### Fixture Sources by Layer

| Layer        | Fixture type                                       |
| ------------ | -------------------------------------------------- |
| **Frontend** | Simple values, object trees (JSON), REST responses |
| **Backend**  | Values, object trees, persistent data (DB state)   |

### Two Kinds of Fixture Data

```text
┌────────────────────────────────┐   ┌────────────────────────────────┐
│  Code-internal system data     │   │  Code-external system data     │
│  (smaller data sets /          │   │  (HTTP responses or            │
│   object trees)                │   │   database records)            │
└────────────────────────────────┘   └────────────────────────────────┘
```

### Principles

- **System-wide test data**: fixtures should control the whole test suite on both schema and data — one source of truth, not per-test copies.
- **Automated data sync**: fixtures for external system data (REST calls, DB) must be synced automatically (e.g. recorded tapes, generated API responses) rather than maintained by hand.

### Common Mistake

> A test that owns its own local data copy will **drift out of sync** with the real schema and data over time — tests keep passing while the production contract has changed.

The fix: centralise fixtures and automate their refresh from the real external system.

---

## Boundary Tests: Reference Constants, Not Literals

When production code enforces a boundary through a named constant, tests should
import and derive values from that constant — not repeat the number.

### The Problem

```python
# Bad — hardcoded boundary; survives a constant change silently
keys = [f"p{i}" for i in range(2)]          # breaks if _MIN_PHOTOS → 3
assert any("300" in e for e in errors)       # breaks if _MIN_DIMENSION → 400
```

If `_MIN_PHOTOS` changes from 2 to 3, the test still uses `range(2)` and no
longer tests "one below the minimum" — it silently tests a valid case instead.

### The Fix

Import the constant and express all boundary values relative to it:

```python
from app.application.pipeline.nodes.photo_validator import (
    _MAX_PHOTOS,
    _MIN_DIMENSION,
    _MIN_PHOTOS,
)

# One below minimum — always the real boundary
keys = [f"p{i}" for i in range(_MIN_PHOTOS - 1)]

# One above maximum
keys = [f"p{i}" for i in range(_MAX_PHOTOS + 1)]

# Exactly one pixel too small
small = _MIN_DIMENSION - 1
data = make_jpeg(small, small)
assert any(str(small) in e for e in errors)
```

### Why It Works

| Concern | Hardcoded literal | Constant reference |
|---|---|---|
| Constant changes | Test silently stops testing the boundary | Test immediately fails — surfaces the drift |
| Intent clarity | Reader must infer what `2` means | `_MIN_PHOTOS - 1` is self-documenting |
| Error message assertion | Asserts a stale number | Asserts the actual value fed to the validator |

### Where to Apply

Any test that exercises a boundary enforced by a named constant: file size
limits, count limits, dimension minimums, rate-limit thresholds, free-tier caps.
