# WallRay — Project Context

> AI-powered building defect analysis. One photo → instant AI verdict on cracks, damp, and mold. Portfolio project, not a live commercial service.

@.claude/project-specifics.md

## Stack

| Layer | Dir | Tech |
|---|---|---|
| Backend | `be/` | Python 3.13, FastAPI, LangGraph, uv, ruff, mypy strict |
| Frontend | `fe/` | Next.js 16, TypeScript, Tailwind, pnpm, Biome |
| DB | — | PostgreSQL + Alembic migrations |

## Key Commands

```bash
mise run "code:clean"       # Lint + typecheck both sides
mise run "code:clean:fe"    # Frontend only
mise run "code:clean:be"    # Backend only
cd be && uv run alembic revision --autogenerate -m "description"  # DB migration
```

Note: `code:clean:fe` / `code:clean` regenerates `fe/services/tech/BuildTimeS.ts` on every run — always check `git status` and stage it.

## Frontend Architecture (4-layer)

```
ui/business/  →  ui/base/
     ↓               ↓
services/business/ → services/tech/
                            ↓
                        types/api.ts
```

- **`ui/base/`**: Design-system primitives (Row, Col, Text, Card, Button, etc.). Zero domain knowledge. No `'use client'`.
- **`ui/business/`**: Domain components. Consume business services + base UI. Mark `'use client'`.
- **`services/tech/`**: Infrastructure (HTTP, env, routing). No hooks.
- **`services/business/`**: Domain logic + React hooks. Consume tech services.

Rules: never import upward or sideways. `app/` pages import from `ui/business/` only. No `lib/` or `utils/` directories. Services are named `XxxS` — single `export default` object.

## Backend Architecture

- `be/app/adapters/` — infrastructure (persistence, HTTP, CLI)
- `be/app/logic/` — pure domain logic, no I/O
- `be/app/api/` — FastAPI routes
- `be/app/agents/` — LangGraph agent graphs

Schema changes: edit `be/app/adapters/persistence/orm_models.py`, then generate an Alembic migration.

## Design Conventions

Encapsulation: a method owns everything needed to fulfill its contract — it generates its own IDs, timestamps, hashes. Callers pass intent, not implementation details. If a layer persists something, it creates the identity for it. If a method creates something, it returns it.

## Git Workflow

- Never commit, push, or amend without user confirmation (exception: "qa and push" command)
- Commit messages: write as a human developer — no mention of AI assistance or co-author lines

## Docs

- Architecture + build sequence: `docs/TECH_PLAN.md`
- Business plan: `docs/BUSINESS_PLAN.md`
- Marketing channels: `docs/business/MARKETING.md`

## Skills (loaded on demand)

`.claude/skills/`: `codebase-index`, `code-clean`, `orm-migrations`, `code-review-criteria`, `cluster-photos`, `logs`, `qa-push`, `e2e`. Global: `mise-commands`, `server-management`, `react-fe-domain-rules`, `markdown-standards`.
