# CitySignal

> Live career intelligence for New York tech.

A job-search system that will not lie to you about where a job is, whether you
qualify for it, or whether it is still open.

**Current state: milestone 0, not yet complete.** See [`docs/PROGRESS.md`](docs/PROGRESS.md)
for exactly what works, what does not, and what is standing in for something real.

---

## Setup

Requires Python 3.12+, Node 20+, and a container runtime (Docker Desktop or
OrbStack).

```bash
make doctor    # checks prerequisites and names anything missing
make setup     # installs Python + JS deps, creates .env from .env.example
make demo      # starts postgres + redis, migrates, seeds, runs everything
```

Then open <http://localhost:3000>.

`make demo` is fully offline. It seeds from a committed fixture — a real
Greenhouse response recorded from a live board — and makes no network requests.
Outbound HTTP is off by default (`OUTBOUND_HTTP_ENABLED=false`), so a clean clone
physically cannot reach a job board until you turn it on.

To poll the live board instead:

```bash
# set OUTBOUND_HTTP_ENABLED=true in .env, then
make ingest
```

Run `make` with no arguments to list every target.

---

## What it is

Three modes over one honest dataset:

- **Explore** — find roles. Becomes a 3D New York at milestone 4; is a list
  today, and the list remains the permanent accessible equivalent, not a
  placeholder.
- **Operate** — work the pipeline. Source health today; application tracking at
  milestone 2.
- **Analyze** — see the patterns. Corpus honesty today; historical trends at
  milestone 6.

## What makes it different

Most job tools guess. This one is built around seven invariants that never bend,
and they are enforced by constraints and tests rather than by good intentions:

1. **Never fabricate a location.** A job whose posting says "New York, NY" does
   not get placed on a building. Every coordinate carries a
   `location_confidence`, and the database physically cannot store a point whose
   confidence does not justify it. See [ADR 0002](docs/adr/0002-invariant-i1-enforced-in-the-schema.md).
2. **Never fabricate a qualification.** Skills and experience come from what you
   entered or confirmed. Anything inferred stays `inferred_pending_confirmation`.
3. **Never silently close a listing.** A source that times out is not evidence a
   job closed. See [ADR 0003](docs/adr/0003-fetchoutcome-carries-the-i3-distinction.md).
4. **Never show a score without a breakdown.** A bare number is a bug.
5. **Never take an irreversible action for you.** No auto-applying, no sending
   email. Suggest, surface, confirm.
6. **Never claim a milestone is done without evidence.**
7. **Never let a mock become the product.** Fixtures are named, labelled in the
   data, and listed in PROGRESS. See [ADR 0004](docs/adr/0004-fixture-seeding-is-labelled-in-the-data.md).

The interface shows the fifth one on every row. Each location carries a
five-tick confidence ladder, lit to the precision actually achieved. In milestone
0 nothing has been geocoded, so no ladder rises above three ticks — and the app
says "placeable on a map: 0, nothing geocoded yet" rather than hiding the number
until it looks better.

## Stack

| Layer | Choice |
|---|---|
| Web | Next.js App Router, React 19, TypeScript strict, Tailwind v4, TanStack Query, Zod |
| API + workers | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Alembic, ARQ |
| Data | PostgreSQL 16 + PostGIS + pgvector, Redis 7 |
| Geo (M1+) | NYC GeoSearch, NYC Open Data building footprints, OpenFreeMap tiles |
| Map (M4) | MapLibre GL JS + Three.js |

**Cost: $0/month. API keys: 0.** Every external dependency is free and
unauthenticated, and that is an architectural decision rather than an accident —
see [`docs/architecture/costs.md`](docs/architecture/costs.md).

## Layout

```
apps/web/          Next.js frontend
services/api/      FastAPI + ARQ workers (one deployable)
data/              board-registry.yaml — ATS board tokens, human-reviewed
docs/
  PROGRESS.md      current state; read first, always current
  QUESTIONS.md     things needing a human
  spec/            PRODUCT-SPEC.md + AMENDMENTS.md (amendments win)
  adr/             architecture decision records
infra/             docker-compose + the Postgres image
```

## Development

```bash
make check       # format + lint + typecheck + test, both languages
make test        # unit tests only
make test-e2e    # Playwright
make reset-db    # drop, recreate, migrate, seed
make ps / logs   # container state
```

`make check` before every commit.

## Contributing to this repo

Read [`CLAUDE.md`](CLAUDE.md) first — it is the operating manual, and its
precedence rules matter: `CLAUDE.md` > `docs/spec/AMENDMENTS.md` > `docs/adr/` >
`docs/spec/PRODUCT-SPEC.md`. PRODUCT-SPEC is the original vision document, written
before implementation; where it is wrong, AMENDMENTS says so and AMENDMENTS wins.
