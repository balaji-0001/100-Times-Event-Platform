# 100 Times — Architecture Audit

Read-only audit. No files were modified to produce this report. Snapshot as of 2026-09-16.

---

## 1. Current Architecture (text diagram)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  REPO ROOT  (pnpm workspace: artifacts/*, lib/*, lib/integrations/*, scripts)│
│                                                                               │
│  main.py / start_dev.py  → launches both dev servers (sys.path shim)        │
│  replit.md                → STALE template docs (describes a different,     │
│                              never-built Express+Drizzle stack)             │
│  backend/__init__.py      → empty stub package, name-collides with the      │
│                              real backend one level down                    │
│  infra/n8n/*.json         → workflow definitions, not wired to any code     │
│  scripts/src/hello.ts     → template stub, unused                          │
└─────────────────────────────────────────────────────────────────────────────┘
        │                                            │
        │  used                                      │  NOT used by anything
        ▼                                            ▼
┌───────────────────────────┐            ┌─────────────────────────────────┐
│ lib/api-client-react       │            │ lib/db (Drizzle ORM, Postgres)   │
│ lib/api-spec (openapi.yaml)│            │ artifacts/mockup-sandbox         │
│ lib/api-zod                │            │  → dead relative to the running  │
│  → orval-generated client, │            │    app; see §5                   │
│    STALE (26 paths only;   │            └─────────────────────────────────┘
│    admin agent endpoints   │
│    are missing from it)    │
└───────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  FRONTEND — artifacts/100-times (React 19 + Vite + wouter + TanStack Query)│
│                                                                             │
│  App.tsx (3,364 lines) ─── the ENTIRE public marketplace app:             │
│     Explore/Home, Event/Organizer/Venue/City/Category pages, Dashboards,  │
│     Networking, AI Concierge chat UI, auth screens, NotFoundPage (inline) │
│     → talks to backend via generated hooks (@workspace/api-client-react)  │
│                                                                             │
│  src/ops/* (2,111 lines, 13 files) ─── Admin console, modular:            │
│     DashboardPage, DiscoveryPage, OrganizersPage, OrganizerProfilePage,   │
│     OutreachPage, OutreachDrawer, EventDrawer, ActivityPage,              │
│     SettingsPage, ManualResearch, OpsLayout, api.ts, ui.tsx               │
│     → talks to backend via RAW customFetch (not the generated client,    │
│       because openapi.yaml doesn't describe these routes at all)          │
│                                                                             │
│  src/pages/not-found.tsx ─── ORPHANED, never imported (see §5)           │
└───────────────────────────────────────────────────────────────────────────┘
        │ HTTP (JWT Bearer / cookie)
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│  BACKEND — artifacts/api-server/backend (FastAPI + SQLAlchemy + Alembic)  │
│                                                                             │
│  main.py → 10 routers mounted under /api:                                │
│    auth · dashboard · events · directories · networking                  │
│    ai (deterministic "AI Concierge" — NOT an LLM agent)                  │
│    acquisition (legacy agent admin API — NO auth guard)                  │
│    outreach   (Agent 2 admin API  — ADMIN-gated)                         │
│    discovery  (Agent 1 admin API  — ADMIN-gated)                         │
│    workflow   (LangGraph orchestration API — ADMIN-gated)                │
│    redirect   (short-link click tracking, no /api prefix)                │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │ AGENT 1 — Organizer Discovery  (services/discovery_agent/)         │   │
│  │   query_seeds → source_finder (web search) → page_extractor        │   │
│  │   → organizer_identifier → validation → discovery_dedup → storage  │   │
│  │   manual-trigger only, writes DiscoveredEvent/DiscoveredOrganizer  │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │ AGENT 2 — Organizer Outreach  (services/social_agent/outreach/)    │   │
│  │   eligibility → duplicate_check → message_generator (AI/template)  │   │
│  │   → human APPROVAL gate → senders/smtp (mock unless configured)    │   │
│  │   → suppression, followup (2-stage)                                │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │ WORKFLOW — LangGraph layer  (services/workflow/)  [NEW]            │   │
│  │   tools.py  → StructuredTools wrapping routes.discovery /          │   │
│  │               routes.outreach functions directly (layering issue, │   │
│  │               see §3)                                              │   │
│  │   graph.py  → discover → draft_outreach → process_followups        │   │
│  │               → finalize, MemorySaver checkpoint, RetryPolicy      │   │
│  │   llm.py    → structured_llm() Runnable over ai_client, currently  │   │
│  │               unused by the two agents' own code (parallel path)   │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │ LEGACY — Social Media Attendee Acquisition Agent                   │   │
│  │   (services/social_agent/* minus outreach/ and workflow/)          │   │
│  │   connectors/ (reddit,discord,telegram,x,linkedin,instagram; mock  │   │
│  │     unless credentialed) → unified_processor (rate limit) →        │   │
│  │   pipeline/ (normalize → intent_extraction[AI] → qualification →   │   │
│  │     event_matching → policy_check → content_generation[AI]) →      │   │
│  │   approval queue (AcquisitionOpportunity) → publishers/            │   │
│  │     (Discord/Telegram real; StubPublisher for the rest)            │   │
│  │   Hidden from the admin console UI (routes still live, unauth'd)   │   │
│  │   acquisition_agent.py: deterministic IntentDetectionAgent +       │   │
│  │     EventMatchingEngine — still used by pipeline/event_matching.py │   │
│  │     AND by a separate regex shortcut in social_agent/orchestrator  │   │
│  │     → two intent-classification paths, see §3                     │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  services/social_agent/ai_client.py ─── the ONE place any LLM is called: │
│    AIClient interface → GeminiAIClient | AnthropicAIClient, chosen by    │
│    AI_PROVIDER. Used by discovery_agent, outreach, the legacy pipeline,  │
│    and services/workflow/llm.py. Nothing else imports a vendor SDK.     │
│                                                                             │
│  services/social_agent/scheduler.py ─── one asyncio loop, 4 timed ticks  │
│    (attendee-scan, organizer-scan, outreach-followup, event-discovery); │
│    fully OFF by default (ENABLE_BACKGROUND_SCHEDULER=false)             │
│                                                                             │
│  models.py (593 lines, 31 ORM classes, three "eras" in one file):        │
│    Marketplace (User, Event, Organizer, Venue, Registration, ...)        │
│    Legacy agent (Community, Discussion, AcquisitionOpportunity, ...)     │
│    New agents   (DiscoveredEvent, DiscoveredOrganizer, OutreachMessage,  │
│                   AgentRun, OutreachCampaign, SuppressedContact, ...)    │
└───────────────────────────────────────────────────────────────────────────┘
        │
        ▼
   SQLite (dev, AUTO_CREATE_SCHEMA + manual Alembic catch-up) /
   PostgreSQL (prod, Alembic migrations = source of truth)
```

---

## 2. Important Files and Their Purpose

### Root
| File | Purpose |
|---|---|
| `main.py` | Dev entrypoint; puts `artifacts/api-server` on `sys.path`, imports `backend.main:app` |
| `start_dev.py` | Launches backend + Vite frontend together for local dev |
| `backend/__init__.py` | Empty stub — see §5 |
| `replit.md` | Unfilled template; describes a stack that doesn't match reality — see §5 |
| `pnpm-workspace.yaml` | Workspace package list + supply-chain-safety pnpm settings |
| `infra/n8n/*.json` | n8n workflow definitions; not invoked by any running code |

### Backend — `artifacts/api-server/backend`
| File | Purpose |
|---|---|
| `main.py` | FastAPI app, CORS, lifespan (schema create + seed + scheduler), router registration |
| `core/config.py` | All settings: DB URL, JWT, `AI_PROVIDER`/Gemini/Anthropic keys, discovery/outreach tuning, SMTP, scheduler toggle |
| `core/security.py` | Password hashing + JWT encode/decode |
| `db.py` | SQLAlchemy engine/session factory (SQLite dev path resolution, Postgres URL normalization) |
| `dependencies.py` | `get_current_user`, `optional_current_user`, `require_roles(*roles)` |
| `models.py` | All 31 ORM models (three eras — see diagram) |
| `schemas.py` / `serializers.py` | Pydantic API models (camelCase) and ORM→API mapping |
| `seed.py` | Demo data; also directly drives the legacy agent once at startup |
| `routes/acquisition.py` | Legacy agent admin API (1,073 lines) — **no auth guard** |
| `routes/discovery.py` | Agent 1 admin API — ADMIN-gated |
| `routes/outreach.py` | Agent 2 admin API — ADMIN-gated |
| `routes/workflow.py` | LangGraph pipeline API — ADMIN-gated |
| `routes/ai.py` | Deterministic keyword-scoring "AI Concierge" — not an LLM agent |
| `services/social_agent/ai_client.py` | The single LLM-vendor boundary (Gemini/Anthropic) |
| `services/discovery_agent/orchestrator.py` | Agent 1's own run loop |
| `services/social_agent/outreach/orchestrator.py` | Agent 2's own run loop |
| `services/workflow/{tools,graph,llm}.py` | LangChain tools + LangGraph sequencing over Agents 1 & 2 |
| `services/acquisition_agent.py` | Legacy deterministic intent/matching engine, still live (two call sites) |
| `services/social_agent/scheduler.py` | The one in-process background scheduler (4 loops, off by default) |
| `alembic/versions/*` | Production schema migrations (source of truth for Postgres) |

### Frontend — `artifacts/100-times/src`
| File | Purpose |
|---|---|
| `App.tsx` | Entire public marketplace app — routing + every page component (3,364 lines) |
| `main.tsx` | React root; wires `@workspace/api-client-react`'s base URL + auth token getter |
| `ops/api.ts` | All admin-console data hooks, via raw `customFetch` |
| `ops/OpsLayout.tsx` | Admin shell: nav, auth gate, global search |
| `ops/DiscoveryPage.tsx`, `OrganizersPage.tsx`, `OutreachPage.tsx`, etc. | One file per admin-console screen |
| `ops/ManualResearch.tsx` | The manual-trigger form/drawer for Agent 1 |
| `components/ui/*` (55 files) | Vendored shadcn primitives |
| `pages/not-found.tsx` | Orphaned — see §5 |

### `lib/` workspace packages
| Package | Purpose | Status |
|---|---|---|
| `lib/api-spec` | `openapi.yaml` + orval codegen config | Stale — 26 paths, missing all agent/admin routes |
| `lib/api-client-react` | Generated React Query hooks + `customFetch` | **Used**, but only for the public-app surface |
| `lib/api-zod` | Generated Zod schemas from the same spec | Generated, not confirmed used anywhere in app code |
| `lib/db` | Drizzle ORM schema targeting Postgres | **Unused** — zero imports from either app; see §5 |

---

## 3. Problems Found

**Structural / layering**
- `services/workflow/tools.py` imports functions directly from `routes/discovery.py` and `routes/outreach.py` — a service module depending on route handlers (inverted layering). It works today (no literal import cycle), but couples the workflow layer to FastAPI route signatures/dependencies instead of to a clean service function, so a route refactor can silently break it.
- Two different intent-classification implementations exist for the same conceptual step: `pipeline/intent_extraction.py` (real LLM call) vs. `acquisition_agent.py`'s `IntentDetectionAgent` (regex-based), the latter used only by one shortcut path (`SocialAgentOrchestrator.run_instagram_content_cycle`).
- The frontend has two separate, undocumented ways of calling the backend: generated hooks for the public app, raw `fetch` for the admin console — a direct consequence of `openapi.yaml` never being regenerated after the agent endpoints were added.

**Security / consistency**
- `routes/acquisition.py` (the legacy agent's full admin API — trigger scans, approve/reject/publish content, view analytics) has **no** `require_roles` guard, while the newer `discovery`, `outreach`, and `workflow` routers are all ADMIN-gated. Same class of endpoint, inconsistent protection.
- `routes/ai.py` and `services/social_agent/ai_client.py` both have "AI" in their name/domain but mean completely different things (deterministic keyword scorer vs. the LLM vendor wrapper) — easy to confuse when reading logs, tests, or route lists.

**Documentation drift**
- `replit.md` is an unfilled template describing an Express + Drizzle + Postgres stack. The real stack is FastAPI + SQLAlchemy/Alembic with a React/Vite frontend. Anyone reading it first would misunderstand the whole project.
- `lib/api-spec/openapi.yaml` covers roughly a third of the backend's actual routes (health/home/events/categories/cities/venues/organizers/auth/dashboard-ish surface only) — none of `acquisition`, `discovery`, `outreach`, or `workflow` appear in it.

**Scale / maintainability**
- `App.tsx` is 3,364 lines and contains essentially the entire public-facing application (every page, every dialog, routing, and an inline 404 page) in one file, while the admin console (`ops/`) is cleanly split into ~13 focused files. The asymmetry makes the public app much harder to navigate and to test in isolation.
- `routes/acquisition.py` is 1,073 lines — the largest single route file, mixing scan triggers, approval actions, analytics, rate-limit admin, and an AI insight endpoint.

**Dead / orphaned code** — see §5 for the full list and evidence.

**Documented workarounds (intentional, not bugs)** — worth knowing about, not necessarily worth "fixing":
- `ENABLE_BACKGROUND_SCHEDULER` defaults to `false` specifically because the first scheduler tick would run at full configured scope and spend real API credits — a deliberate safety choice, not an oversight.
- SQLite dev DB needs a manual `alembic upgrade head` after a schema change, because `AUTO_CREATE_SCHEMA` only creates missing tables, never adds columns to existing ones.
- `main.py`'s unhandled-exception handler returns raw exception text when `ENVIRONMENT=development` — correct for local dev, but would leak internals if that setting were ever left on in a real deployment.

---

## 4. What Should Be Kept

- The three-router split for the new agent system (`discovery.py` / `outreach.py` / `workflow.py`), all ADMIN-gated, all following the same `AgentRun` audit pattern.
- The single LLM boundary, `services/social_agent/ai_client.py` — provider-neutral, well-isolated, the right place to keep it.
- The `services/workflow/` LangGraph layer's design principle: it orchestrates *between* the two agents rather than rewriting either agent's internals — this kept the migration low-risk and is worth preserving as a pattern for any future agent.
- The admin console's file-per-page structure under `src/ops/` — a good model the rest of the frontend doesn't yet follow.
- The human-approval gate on Agent 2 (nothing sends without an explicit approve action) and the manual-trigger-only posture for both new agents.
- Alembic as the schema source of truth for production, with the dev-DB catch-up already documented.
- The test suite's `FakeAIClient` pattern — zero live network/LLM calls across 156 tests.

## 5. What Should Be Removed

| Item | Evidence | Why |
|---|---|---|
| `lib/db/**` (Drizzle schema, `drizzle.config.ts`, generated client) | `grep` for `@workspace/db` / `lib/db` across both apps returns nothing | Not imported by the Python backend or the React frontend; the real schema is `backend/models.py` + Alembic |
| `artifacts/mockup-sandbox/**` | `grep` for `mockup-sandbox` outside itself returns nothing | Standalone shadcn/Vite sandbox, not referenced by any build, route, or import |
| `artifacts/100-times/src/pages/not-found.tsx` | `App.tsx` defines and routes to its own inline `NotFoundPage`; this file is never imported | Orphaned duplicate of functionality that already lives in `App.tsx` |
| `backend/__init__.py` (root-level stub) | Empty file; `artifacts/api-server/backend/` is the real package | Name collision risk — harmless only because of current `sys.path` ordering |
| `scripts/src/hello.ts` + its workspace package | Single-line template stub, no other file references it | Leftover scaffolding |
| `replit.md` | Content contradicts the real stack throughout | Actively misleading; either delete or fully rewrite (see §6) |

Before deleting `lib/db` or `lib/api-zod`, do a final repo-wide `pnpm -r why` / grep pass — this audit is read-only and a static grep, not a build-graph analysis.

## 6. What Should Be Refactored

1. **Split `App.tsx`** into one file per page/route (mirroring the `ops/` pattern), pulling out `NotFoundPage`, the AI Concierge UI, and each dashboard variant. This is the single highest-value cleanup for maintainability.
2. **Add `require_roles("ADMIN")` to `routes/acquisition.py`**, matching the posture already applied to `discovery`/`outreach`/`workflow` — closes the one real inconsistency in the auth model. (Flagged as a known gap in this project's own working notes; not previously acted on.)
3. **Fix the `services/workflow/tools.py` → `routes/*` dependency direction** — extract the three route bodies' actual logic into plain service functions (or have the routes call the same service functions the tools call), so `workflow` depends on services, not on route handlers.
4. **Regenerate or retire `lib/api-spec/openapi.yaml`.** Either point orval at the live FastAPI `/openapi.json` (which already exists and is complete) so the generated client stays in sync, or accept that the admin console's raw-fetch pattern is permanent and document it — right now it's an accident of staleness, not a decision.
5. **Rename for clarity**: `routes/ai.py` → something like `routes/recommendations.py` (it's deterministic scoring, not an LLM feature) to stop it colliding conceptually with `ai_client.py` and the two real agents.
6. **Resolve the duplicate intent-classification path** — either have the Instagram-content shortcut call the real `pipeline/intent_extraction.py`, or document explicitly why the deterministic `IntentDetectionAgent` is intentionally kept for that one fast path.
7. **Rewrite `replit.md`** to describe the actual stack (FastAPI/SQLAlchemy/Alembic + React/Vite/wouter/TanStack Query), or delete it if it's not load-bearing for any tooling.
8. **Split `routes/acquisition.py`** (1,073 lines) into smaller modules by concern (scan triggers, opportunity actions, analytics, rate limits) the way `discovery`/`outreach`/`workflow` already are.

## 7. Proposed Clean Target Architecture

```
repo/
├── apps/
│   ├── web/                      # was artifacts/100-times
│   │   └── src/
│   │       ├── app/               # public marketplace, split by route
│   │       │   ├── explore/  events/  organizers/  venues/
│   │       │   ├── dashboard/  networking/  concierge/
│   │       │   └── routes.tsx     # thin router, no page bodies inline
│   │       ├── admin/              # was src/ops — unchanged, it's already right
│   │       └── shared/             # components/ui, hooks, lib/utils
│   └── api/                       # was artifacts/api-server
│       └── backend/
│           ├── core/               # config, security
│           ├── db/                 # engine, session, Alembic
│           ├── models/             # split by domain: marketplace.py,
│           │                       # legacy_agent.py, discovery_agent.py,
│           │                       # outreach_agent.py  (still one Base)
│           ├── routes/             # one auth posture: everything ADMIN-
│           │                       # gated or explicitly public, no gaps
│           ├── services/
│           │   ├── ai_client.py    # unchanged — the one LLM boundary
│           │   ├── discovery_agent/
│           │   ├── outreach_agent/
│           │   ├── legacy_social_agent/   # clearly labeled as legacy
│           │   └── workflow/       # depends only on services/*, never routes/*
│           └── tests/
├── packages/
│   ├── api-client/                 # was lib/api-client-react, regenerated
│   │                                # from the live FastAPI schema, full coverage
│   └── ui/                         # shared design tokens if ever needed
├── infra/
│   └── n8n/                        # keep only if actually deployed somewhere;
│                                    # otherwise move to docs as reference, not code
└── docs/
    └── ARCHITECTURE.md              # kept current; replaces replit.md's role
```

Key differences from today:
- No unused `lib/db`, no `mockup-sandbox`, no root `backend/` stub.
- One consistent way for the frontend to reach the backend (a regenerated, complete client), with the admin console kept as its own clearly-scoped area rather than a separate calling convention.
- One consistent auth posture across every admin-facing route.
- `workflow/` depends downward on services only, never sideways into `routes/`.
- The legacy listening agent is explicitly labeled `legacy_social_agent/` rather than living under the generic `social_agent/` name that the new outreach agent and the shared `ai_client.py`/`state_machine.py`/`scheduler.py` also use today — reduces the chance of assuming "social_agent" means one specific agent.

---

*This report is a static analysis (directory listings, grep, and targeted file reads). No package-manager dependency graph or bundler analysis was run, so "unused" findings for TypeScript packages should get one confirming pass (e.g. `pnpm -r why <package>`) before deletion.*
