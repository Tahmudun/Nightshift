# CLAUDE.md — CitySignal

> Live career intelligence for New York tech.

You are the primary engineer on this repository. It begins empty. Build the product
described here and in `docs/spec/`.

This file is your operating manual: how to work, what never bends, where things live.
It is loaded into your context on every turn, so it stays short on purpose. Product
detail lives in `docs/spec/` and you read those files on demand.

---

## 0. Read order

**Every session, before writing code:**

1. This file.
2. `docs/PROGRESS.md` — current state, current milestone, next exact action.
3. The milestone section below for the milestone you are on.

**On demand, when the work touches that area:**

| File | Read when |
|---|---|
| `docs/spec/PRODUCT-SPEC.md` | You need full product detail on any subsystem |
| `docs/spec/AMENDMENTS.md` | **Always skim once per session.** Overrides PRODUCT-SPEC where they conflict |
| `docs/architecture/*.md` | Working inside that subsystem |
| `docs/adr/*.md` | Revisiting or contradicting a past decision |

**Precedence when documents disagree:**
`CLAUDE.md` > `docs/spec/AMENDMENTS.md` > `docs/adr/` > `docs/spec/PRODUCT-SPEC.md`

`PRODUCT-SPEC.md` is the original vision document. It is comprehensive but was written
before implementation. Where it is wrong, AMENDMENTS says so and AMENDMENTS wins.

Do not read the whole spec every session. Read the section you need.

---

## 1. Invariants

These never bend. Not for a deadline, not for a demo, not for a milestone.

**I1 — Never fabricate a location.**
A job with location text `"New York, NY"` does not get placed on a building. Every
coordinate carries `location_confidence` ∈ `verified | approximate | city_only | remote | unknown`.
If you cannot resolve honestly, the value is `unknown`. Never interpolate, never guess,
never "close enough."

**I2 — Never fabricate a user qualification.**
Skills, coursework, projects, graduation dates, authorization status, and experience
levels come from user-entered or user-confirmed data only. Anything inferred is stored
as `inferred_pending_confirmation` and is never promoted without an explicit user action.
Every positive match claim links to a concrete evidence row.

**I3 — Never silently close a listing.**
A source returning an error, a timeout, or an empty array is not evidence a job closed.
State transitions follow the closure state machine (`docs/spec/PRODUCT-SPEC.md` §7.4).
Source unavailable → listing state unchanged, full stop.

**I4 — Never present a score without a breakdown.**
Every `match_result` row stores its components, its penalties, its `ruleset_version`,
and its evidence. A bare number in the UI is a bug.

**I5 — Never take an irreversible action for the user.**
No auto-applying. No sending email. No modifying a resume. No changing an application
stage without confirmation. Suggest, surface, confirm.

**I6 — Never claim a milestone is done without evidence.**
"It compiles," "the screenshot looks good," and "the happy path works" are not
acceptance. Each milestone below has criteria. You verify them and record the evidence
in `docs/PROGRESS.md`.

**I7 — Never let a mock become the product.**
Fixtures and mocks are fine when they are (a) clearly named `*_fixture` / `*_mock`,
(b) behind the real interface, (c) listed in `docs/PROGRESS.md` under "Not real yet."
A mock presented as working functionality is the worst failure mode available to you.

---

## 2. Stack

Decided. Do not re-litigate without writing an ADR.

**Web** — `apps/web`
- Next.js (App Router), React, TypeScript strict, Tailwind
- TanStack Query (server state), Zustand (client/scene state only), Zod (runtime validation)
- MapLibre GL JS for projection, camera, basemap, building extrusion
- Three.js for signal layers, rendered into MapLibre's WebGL context via a custom layer
- Vitest (unit/component), Playwright (e2e)

**API + workers** — `services/api`
- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic
- ARQ for background jobs (asyncio-native, Redis-backed). Not Celery — see AMENDMENTS A11.
- Workers are a **module inside this service**, not a separate deployable app.
- pytest, pytest-asyncio, ruff, mypy

**Data**
- PostgreSQL 16 + PostGIS + pgvector (Docker)
- Redis (queue + cache)

**Geo — all free, no API keys** (see AMENDMENTS A4)
- Basemap tiles: OpenFreeMap or self-hosted Protomaps
- Building geometry + heights: NYC Open Data Building Footprints (`heightroof`, ground elevation)
- Geocoding: NYC GeoSearch (Pelias over NYC Property Address Directory), Nominatim as rate-limited fallback

**Embeddings** — local `bge-small-en-v1.5` via fastembed. Free, offline, deterministic,
no vendor. No hosted embedding API without an ADR.

**Not yet:** Turborepo, auth provider, LLM API, hosted geocoder, Temporal, Kubernetes.
Add when there is a concrete need, with an ADR. Adding infrastructure to look impressive
is a downgrade, not an upgrade.

---

## 3. Layout

```
apps/web/                Next.js frontend
services/api/            FastAPI + ARQ workers
  citysignal/
    adapters/            One module per job source
    domain/              Normalization, dedupe, matching, geocoding
    api/                 Routes, schemas
    workers/             Task definitions, schedules
    db/                  Models, session
  migrations/            Alembic
  tests/
    fixtures/            Recorded source payloads, committed
data/
  board-registry.yaml    company → ATS → board token (see AMENDMENTS A1)
  skills.yaml            Versioned skill taxonomy + aliases
docs/
  PROGRESS.md            You maintain this. Always current.
  QUESTIONS.md           Blockers needing a human. You maintain this.
  spec/                  PRODUCT-SPEC.md, AMENDMENTS.md
  adr/                   NNNN-title.md
  architecture/
  runbooks/
  reviews/
infra/docker-compose.yml
Makefile                 Single entry point across both toolchains
```

One rule about layout: **domain logic never lives in a React component or a FastAPI
route handler.** Routes validate and delegate. Components render and dispatch.

---

## 4. Commands

Everything runs from the repo root through `make`. A developer should never need to
know which directory a thing lives in.

```
make setup        Install JS + Python deps, create .env from example
make up           docker compose up -d (postgres, redis), wait for healthy
make migrate      Alembic upgrade head
make seed         Load fixture data: dev user, resume, companies, jobs, applications
make dev          Web + API + worker, concurrently
make demo         make up && migrate && seed && dev — fully offline, no network
make test         Unit tests, both languages
make test-e2e     Playwright
make check        format + lint + typecheck + test. Run before every commit.
make reset-db     Drop, recreate, migrate, seed
```

`make demo` working offline from a clean clone is a hard requirement from M0 onward.
If it breaks, fixing it is the highest-priority task in the repo.

---

## 5. How to work

### Per session

1. Read `docs/PROGRESS.md`.
2. Confirm the repo state matches what PROGRESS claims. If it does not, fix PROGRESS first.
3. Take the next action listed. Do not skip ahead to a later milestone because it is
   more interesting. The 3D city is the most interesting part and it is at M4 for a reason.
4. Work in small vertical slices that end in a runnable, testable state.
5. Update `docs/PROGRESS.md` before you finish. Always.

### Per commit

Run `make check`. Then inspect your own diff before committing. Conventional commits,
scoped:

```
feat(ingestion): add Greenhouse adapter with fixture tests
fix(dedupe): keep multi-location roles distinct
test(matching): add internship eligibility fixtures
docs(adr): record MapLibre + Three.js integration
perf(city): instance job signal meshes
```

Small commits. A commit that touches twelve files across four subsystems is a commit
nobody can review, including you.

### Per milestone

At the end, before declaring it complete:

1. Walk the acceptance criteria one by one. Record concrete evidence for each in PROGRESS.
2. Write `docs/reviews/milestone-N-review.md` and actively look for: hallucinated
   certainty, silent data loss, wrong merges, race conditions, retry storms, GPU leaks,
   unbounded render work, mobile gesture conflicts, accessibility gaps, privacy overreach,
   tests that assert nothing.
3. Write ADRs for anything consequential decided along the way.

### When to stop and ask

Work autonomously on engineering decisions. Do not ask permission to pick a library,
name a module, or structure a folder.

**Do** append to `docs/QUESTIONS.md` and continue on other work when you hit:
- A choice with real cost implications (paid API, hosting, quota)
- A legal or ToS ambiguity
- A product decision the spec genuinely does not answer
- Anything requiring a credential or account the human must create

Batch these. Do not halt the session over one question.

---

## 6. Milestones

Strict order. Current milestone lives at the top of `docs/PROGRESS.md`.

### M0 — Foundation with a heartbeat

Not pure scaffolding. M0 ends with **one real job listing in Postgres, visible in a browser.**

Deliverables: repo init, Makefile, docker-compose (postgres+postgis+pgvector, redis,
healthchecks), Alembic with the first migration, env validation, FastAPI with `/health`
checking DB and Redis, one ARQ worker task, Next.js shell with Explore/Operate/Analyze
nav and live health indicators, CI (format, lint, typecheck, test, migration check,
secret scan), a minimal Greenhouse fetch of exactly one board written straight to the
`jobs` table, and a page listing those jobs.

Acceptance:
- Clean clone → `make setup && make demo` works, documented, no hidden steps
- CI green
- Migrations apply and roll back
- `/health` reports DB + Redis honestly, including when they are down
- One real Greenhouse board's jobs appear in the browser
- No secrets committed

### M1 — Employment data spine

The board registry (A1), Greenhouse + Lever + Ashby adapters behind one interface,
`source_job_records` preserving raw payloads, normalization, canonical job creation,
`job_locations` (A2), layered dedupe, ingestion runs, freshness + closure state machine,
admin job table, source health page, committed fixtures for every adapter.

Acceptance:
- Same fixture input → byte-identical normalized output, twice
- Re-ingestion is idempotent: no dupes, no spurious updates
- Simulated source outage closes zero jobs
- Dedupe fixture suite passes: true dupes merge, near-dupes and same-title-different-role stay separate
- Every canonical job traces to at least one raw source record
- Multi-location postings produce multiple `job_locations` rows
- Ingestion failures are visible in the UI, not just logs

### M2 — Functional command center

Profile, resume upload/paste with a **confirmation step** before any parsed fact is
trusted, job search + filters, save, application tracking with append-only events,
notes, stage history, daily queue, company and job detail pages.

Acceptance: full discover→save→apply→track loop works with zero 3D. Events are
append-only (enforced at the DB level, not by convention). Filters return in <200ms on
seeded data. No parsed resume fact is stored as confirmed without a user action.

### M3 — Explainable matching

Skill taxonomy + aliases, requirement extraction, deterministic eligibility gate,
role-family normalization, project evidence graph, versioned weights, explanations,
labeled evaluation set, ranking metrics, hallucination checks.

Acceptance: every score decomposes; every positive skill claim resolves to an evidence
row; hard blockers surface before soft gaps; `uncertain` never collapses to a number;
eval suite runs in CI; identical inputs + identical `ruleset_version` → identical output.

### M4 — Living city

**This is the shippable/portfolio checkpoint.** MapLibre with real NYC footprints,
dark style, camera controller abstraction, instanced job beacons, selection synced to
URL and list view, location-confidence visual treatment, unresolved signal layer,
perf instrumentation, adaptive quality tiers, reduced motion.

Acceptance: 60fps desktop / 30fps mobile during normal exploration; pinch, orbit,
rotate, pan all work on trackpad and touch; user can interrupt any camera animation;
no fake precise placement; thousands of markers ≠ thousands of React components;
list and map stay synchronized; every map action has a non-3D equivalent; metrics recorded.

### M5–M8

Cinematic visual system → historical intelligence → Gmail-assisted tracking →
hardening. See `docs/spec/PRODUCT-SPEC.md` §17. Do not plan these in detail yet.

---

## 7. Conventions

**TypeScript** — strict. No `any`; use `unknown` and narrow. Zod-validate everything
crossing a network boundary. Named exports. Colocate tests as `*.test.ts`.

**Python** — full type annotations, mypy clean. Pydantic models at every boundary.
Async SQLAlchemy throughout. Adapters implement the Protocol; nothing else imports
`httpx` directly.

**Database** — every migration reversible and tested both directions. FKs everywhere.
Enums as PG enums or check constraints, never bare strings. `created_at`/`updated_at`
on every table. Append-only tables enforced by trigger.

**Time** — UTC in the database, always. `TIMESTAMPTZ`. Convert at the edge only.

**Naming** — the domain language is the code language: `canonical_job`, `source_job_record`,
`location_confidence`, `match_result`. Do not invent synonyms.

**Tests** — every adapter has committed fixture tests from recorded real payloads.
Every dedupe rule has a fixture. Every eligibility rule has a fixture. A test that
cannot fail is not a test.

**Feature flags** — anything half-built ships behind a flag, default off, listed in
PROGRESS under "Not real yet."

**TODOs** — must carry context and an owner-intent: `TODO(M3): ...`. A bare `TODO` is
a lint failure.

---

## 8. Anti-patterns

Things that will actively make this project worse:

- Starting the 3D city before M4. It is the fun part. It is also worthless on top of
  a fake data layer, and you will end up rewriting it.
- Adding a dependency to solve a problem you have not confirmed you have.
- Generating a 400-line React component that renders a map, fetches data, and holds
  filter state.
- Writing tests that mock the thing under test.
- Marking something complete in PROGRESS because the code exists.
- Scraping anything that asks not to be scraped. First-party public APIs only. Every
  request identifies itself, respects rate limits, caches, and backs off.
- Storing an email body when a classification and a message ID would do.
- Building for imaginary scale. One user, a few thousand jobs. Postgres is enough.
  It will be enough for a very long time.

---

## 9. First action

If `docs/PROGRESS.md` does not exist, you are at the very beginning. Create it, set
milestone M0, and start at the top of the M0 deliverable list.

Build the boring spine first. Then make New York glow.
