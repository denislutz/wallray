# WallRay — Frontend

Next.js 16 · TypeScript · Tailwind · Biome

---

## Architecture

The frontend is organized into four domain layers with strict one-direction dependencies,
overlaid on the Next.js App Router server/client split.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Next.js App Router                                                             │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  SERVER  (no JS shipped)                                                │   │
│  │                                                                         │   │
│  │   app/layout.tsx              app/page.tsx                              │   │
│  │   html shell · fonts          page composition · metadata               │   │
│  └──────────────────────────────────────┬────────────────────────────────┘   │
│                                          │  imports across 'use client'        │
│  ┌───────────────────────────────────────┼────────────────────────────────┐   │
│  │  CLIENT                               │                                │   │
│  │                                       ▼                                │   │
│  │                           ┌─────────────────────┐                      │   │
│  │   ui/business/            │  HealthBadge.tsx     │  maps status →      │   │
│  │                           │  'use client'        │  presentation       │   │
│  │                           └──────────┬──────────┘                      │   │
│  │                                      │                                  │   │
│  │                         ┌────────────┴────────────┐                    │   │
│  │                         │                          │                    │   │
│  │                         ▼                          ▼                    │   │
│  │   ui/base/        ┌───────────────┐    ┌────────────────────────┐      │   │
│  │                   │ StatusDot.tsx │    │ services/business/     │      │   │
│  │                   │ variant dot   │    │ HealthS.ts             │      │   │
│  │                   │ generic prim. │    │ check() · useHealth()  │      │   │
│  │                   └───────────────┘    └────────────┬───────────┘      │   │
│  │                                                     │                   │   │
│  │                                                     ▼                   │   │
│  │   services/tech/                       ┌────────────────────────┐      │   │
│  │                                        │ HttpS.ts               │      │   │
│  │                                        │ fetch-based get<T>()   │      │   │
│  │                                        │                        │      │   │
│  │                                        │ EnvS.ts                │      │   │
│  │                                        │ NEXT_PUBLIC_API_URL    │      │   │
│  │                                        └────────────┬───────────┘      │   │
│  └─────────────────────────────────────────────────────┼──────────────────┘   │
│                                                         │  fetch               │
└─────────────────────────────────────────────────────────┼────────────────────┘
                                                          │  :8000
                                                          ▼
                                             ┌────────────────────────┐
                                             │  FastAPI  (be/)        │
                                             │  GET /health           │
                                             │  POST /analyze  …      │
                                             └────────────────────────┘
```

---

## Domain Layers

| Layer | Directory | Rule |
|---|---|---|
| Tech service | `services/tech/` | Infrastructure only — HTTP, env, utils. No React. |
| Business service | `services/business/` | Domain logic + React hooks. Imports tech services. |
| Base UI | `ui/base/` | Generic primitives. No domain knowledge. No service imports. |
| Business UI | `ui/business/` | Domain components. Imports business services + base UI. |

**Import direction:** business UI → (base UI, business service) → tech service → `types/`  
Reverse imports are never allowed.

**Naming:** services are `XxxS` — single default-export object: `const HealthS = { check, useHealth }`.  
**`'use client'`:** only on business UI components that call hooks, never on `.ts` service files.

---

## File Tree

```
fe/
├── app/                        Next.js App Router
│   ├── layout.tsx              root layout (server)
│   └── page.tsx                home page (server, mounts HealthBadge)
├── ui/
│   ├── base/
│   │   └── StatusDot.tsx       generic dot indicator primitive
│   └── business/
│       └── HealthBadge.tsx     API health status component ('use client')
├── services/
│   ├── tech/
│   │   ├── EnvS.ts             env var accessors
│   │   └── HttpS.ts            fetch-based HTTP client
│   └── business/
│       └── HealthS.ts          health check logic + useHealth hook
└── types/
    └── api.ts                  shared API types (HealthStatus, …)
```

---

## Dev

```bash
mise run fe-start          # next dev on :3000
mise run "code:clean:fe"   # biome autofix + tsc
```
