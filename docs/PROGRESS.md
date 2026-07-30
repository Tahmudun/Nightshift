# PROGRESS

> Read this first, every session. If the repo state does not match what this
> file claims, fix this file before writing code.

**Current milestone: M0 — Foundation with a heartbeat**
**Status: NOT COMPLETE. Blocked on one host prerequisite.**
**Last updated: 2026-07-29**

---

## Next exact action

**A human must run one command:**

```bash
sudo mkdir -p /usr/local/cli-plugins && sudo chown "$(whoami)" /usr/local/cli-plugins
```

Then, in order:

```bash
brew install --cask docker-desktop   # was rolled back mid-install; see Blockers
open -a Docker                       # accept the privileged-helper prompt once
make demo
```

`make demo` is the M0 acceptance run. Everything it exercises is written and
unit-tested; none of it has been executed against a live Postgres or Redis,
because this machine has no container runtime. Details in **Blockers** below.

After `make demo` succeeds, walk the acceptance table below, replace every
`BLOCKED` with real recorded output, and only then mark M0 complete.

---

## Blockers

### B1 — No container runtime on this machine (blocks M0 acceptance)

Docker Desktop had been uninstalled previously, leaving five dangling symlinks in
`/usr/local/bin` pointing into a deleted `/Applications/Docker.app`. Those were
removed (they were broken; nothing was lost). `brew install --cask
docker-desktop` then got as far as installing the app and rolled itself back on:

```
Error: Failure while executing; `/usr/bin/sudo -E -- mkdir -p -- /usr/local/cli-plugins` exited with 1.
sudo: a terminal is required to read the password
```

`/usr/local` is `root:wheel`, so creating that one directory needs an interactive
sudo. That is the whole blocker. The command is in **Next exact action**.

Consequence: everything requiring a live database or Redis is written, typechecked,
and unit-tested, but **unverified**. Nothing in this repo claims otherwise.

---

## Acceptance criteria — M0

Per invariant I6, "the code exists" is not evidence. Each row is either verified
with recorded output or explicitly marked blocked.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Clean clone → `make setup && make demo` works, documented, no hidden steps | **BLOCKED (B1)** | `make setup` verified: venv built, 183 py tests + 19 web tests run from a fresh install. `make demo` needs `docker compose up --wait` |
| 2 | CI green | **UNVERIFIED** | `.github/workflows/ci.yml` written with four jobs (python, web, migrations, secrets). No git remote exists, so it has never executed. Every step it runs was run locally and passes — see rows 3–6 |
| 3 | Migrations apply and roll back | **PARTIAL** | `alembic upgrade head --sql` renders complete, correct DDL for all 8 tables and 8 enum types (offline mode, no connection). Apply/rollback/re-apply against a live cluster is BLOCKED (B1). CI job `migrations` runs up → down → up → drift-probe |
| 4 | `/health` reports DB + Redis honestly, including when they are down | **PARTIAL** | Down path verified end to end: Playwright `a missing API is reported, not hidden` passes — the UI renders "api unreachable" and "Could not load roles" rather than an empty state. Healthy path (real PG + Redis, 200 + latencies) is BLOCKED (B1) |
| 5 | One real Greenhouse board's jobs appear in the browser | **PARTIAL** | Real board fetched live 2026-07-29: `boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true` → HTTP 200, 5,309,493 bytes, 426 postings, 134 naming New York. 10 recorded verbatim into a committed fixture; all 10 normalize, and `test_normalization_is_deterministic` passes twice over. Rendering from Postgres is BLOCKED (B1) |
| 6 | No secrets committed | **VERIFIED** | No key-shaped strings anywhere in the tree (scanned for `sk-*`, `AKIA*`, `ghp_*`, PEM private keys). `.env` is gitignored (`.gitignore:2`), confirmed via `git check-ignore`. Only credential-shaped value in the repo is `citysignal_dev_only`, the local compose password, allowlisted in `.gitleaks.toml` for the three files entitled to contain it |

**M0 is not complete.** Rows 1–5 are not satisfied.

---

## Verified locally (recorded output)

These ran on this machine and passed:

| Check | Command | Result |
|---|---|---|
| Python format | `ruff format --check services/api` | 35 files already formatted |
| Python lint | `ruff check services/api` | All checks passed |
| Python types | `mypy citysignal` | Success: no issues found in 28 source files (strict) |
| Python tests | `pytest -q` | **183 passed** in 3.82s |
| Web types | `tsc --noEmit` | clean, `strict` + `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes` |
| Web lint | `eslint . --max-warnings 0` | clean |
| Web tests | `vitest run` | **19 passed** (3 files) |
| Web build | `next build` | compiled, 7 static routes, 102 kB shared JS |
| E2E | `playwright test` | **5 passed** in 35.2s |
| Migration renders | `alembic upgrade head --sql` | full DDL emitted, 8 tables, 8 enums |
| Live source reachable | `GET /v1/boards/datadog/jobs` | HTTP 200, 426 postings |

**Total: 207 automated tests passing** (183 Python, 19 web unit, 5 e2e).

### What those tests actually cover

The counts are only meaningful if the tests can fail. The invariant-bearing ones:

- **I1 (no fabricated locations)** — 98 location-parser assertions driven by
  `tests/fixtures/locations.yaml`, whose cases are real unedited
  `location.name` strings from the live board plus labelled synthetic edge
  cases. Includes the ten-location posting that mixes one physical office with
  nine remote states. Plus: `test_never_produces_coordinates` asserts
  structurally that `ParsedLocation` has no latitude/longitude field at all;
  `test_country_only_does_not_round_up_to_city_only`;
  `test_unrecognised_country_is_unknown_not_guessed`. On the web side, six Zod
  tests reject a point whose confidence does not justify it, in both directions.
- **I3 (no silent closure)** — `TestInvariantI3`, six cases: 404, connect
  timeout, 503, malformed JSON, and a 200 with the wrong shape all produce
  `ok=False`; a genuine empty board produces `ok=True` and
  `is_authoritative_empty=True`. That last one matters — without it the
  invariant could be satisfied by never trusting anything.
- **A10 (fields that are usually null)** — `test_absent_deadline_stays_none`,
  `test_last_modified_is_never_stored_as_a_publication_date`,
  `test_pay_transparency_range_is_extracted` (asserts `salary_period is None`,
  because Greenhouse states no period and inferring one from magnitude would be
  a guess presented as data).
- **A2 (many locations per job)** —
  `test_multi_location_posting_yields_one_row_per_place`, on real data.
- **Determinism** — `test_normalization_is_deterministic` and
  `test_parse_is_deterministic`, both asserted from M0 so M1's "byte-identical
  output twice" criterion cannot quietly become false first.
- **Company identity** — 30 assertions organised around the two ways
  `normalize_company_name` can fail: splitting one employer in two, or merging
  two real ones. Includes the false merges a fuzzy matcher would make
  (Meta/Metabase, Ramp/Rampart) and the suffixes that must *not* be stripped
  (Palantir vs Palantir Technologies). **This suite found a real bug** — see the
  session log.
- **Board registry** — 29 assertions on the file that decides which boards get
  polled, where a typo means silently never seeing a company's jobs. Includes
  path-traversal rejection on the token, since it is interpolated into a URL.

---

## What exists

### `services/api` — FastAPI + ARQ (one deployable, A11)

```
citysignal/
  config.py              pydantic-settings; refuses to start on a bad value
  logging.py             structlog, console locally / JSON in production
  cli.py                 seed | ingest | enqueue | stats
  adapters/
    base.py              JobSourceAdapter Protocol, FetchOutcome, RawJob
    http.py              PoliteClient — the ONLY module importing httpx
    greenhouse.py        real adapter, field shapes read off a live response
  domain/
    locations.py         location parsing; I1 lives here
    companies.py         conservative company-name normalization
    registry.py          board-registry.yaml loading + validation
    ingestion.py         fetch → preserve → normalize → persist
  db/
    base.py              declarative base, 8 PG enums as StrEnum
    types.py             UTCDateTime — rejects naive datetimes at the boundary
    models.py            8 tables
    session.py           one async engine per process
  api/
    main.py              app factory
    routes/health.py     /health, /health/live
    routes/jobs.py       GET /jobs, GET /jobs/{id}
    routes/sources.py    /sources, /ingestion-runs, /stats, /registry
  workers/
    main.py              ARQ WorkerSettings, hourly cron at :17
    tasks.py             ingest_greenhouse — one real task, not a no-op
migrations/              alembic, async env, one reversible migration
tests/                   124 tests; fixtures/ committed
```

**Schema (8 tables):** `users`, `companies`, `sources`, `source_job_records`,
`jobs`, `job_locations`, `job_source_links`, `ingestion_runs`.

Deliberately narrower than PRODUCT-SPEC §6 — applications, match results,
snapshots, and user skills arrive at the milestone that reads them. What is here
is shaped for what comes later: `users` exists so every user-owned table can
carry a real FK from its first migration (A3); raw payloads are preserved and
canonical jobs are reachable only through `job_source_links`, so M1's dedupe adds
a merge step rather than restructuring anything.

### `apps/web` — Next.js App Router

```
src/
  app/layout.tsx         shell: wordmark, ModeNav, HealthTelemetry, skip link
  app/explore/           jobs list + confidence legend + corpus readout
  app/operate/           source health table
  app/analyze/           corpus readout + why nothing is geocoded
  components/
    ConfidenceLadder     the signature element (below)
    CorpusReadout        counts incl. "placeable on a map: 0"
    HealthTelemetry      polls /health every 10s; can say "down"
    JobRow / JobList     one confidence ladder per location
    SourceHealthTable    labels fixture sources in gold
  lib/
    schemas.ts           Zod at every network boundary; I1 re-checked here
    api.ts               single API client
    confidence.ts        the five-value scale + user-facing meanings
```

**The confidence ladder** is the product's signature UI element: five ticks of
increasing height, lit to the precision actually achieved, with a text label and
an accessible name. It appears on every location of every job. In M0 no ladder
anywhere in the app rises above three ticks — which is the truth, rendered.
§4.3 requires the interface to document its own visual language, so the legend
ships as a permanent panel rather than a tooltip (§12.4: no essential
information available only through hover).

### Infrastructure

- `infra/docker-compose.yml` — postgres + redis, real healthchecks. The Postgres
  healthcheck asserts PostGIS **and** pgvector exist, so "healthy" means
  "usable" rather than "accepting connections during initdb".
- `infra/postgres/Dockerfile` — see ADR 0001.
- `Makefile` — 20 targets; every command runs from the repo root.
- `scripts/dev.py` — runs api + worker + web with correct group shutdown.
- `scripts/doctor.py` — names a missing prerequisite instead of failing deep in a
  pip build. It reports B1 correctly.
- `scripts/record_fixture.py` — regenerates a committed fixture from a live board.

### Documentation

- 4 ADRs: 0001 Postgres image, 0002 I1 in the schema, 0003 `FetchOutcome` and I3,
  0004 fixture seeding labelled in the data.
- `docs/architecture/costs.md` — required from M0 by A9. **$0/month, 0 API keys.**
- `docs/QUESTIONS.md` — 3 open questions, none blocking.

---

## Not real yet

Everything half-built or standing in for something real. Nothing in this list is
presented to a user as working.

| Thing | What it actually is | Real at |
|---|---|---|
| `FixtureGreenhouseAdapter` (`cli.py`) | Subclasses the real adapter, overrides only `fetch_board` to read a committed JSON file. Constructed with no HTTP client, so it cannot make a request. Attributed to source `greenhouse_fixture` with `source_type='fixture'`, badged **"committed fixture"** in the Operate UI. ADR 0004 | Permanent — this is the offline demo path, not a stopgap |
| Geocoding | **Does not exist.** No coordinate has ever been written. Every location is `city_only`, `remote`, or `unknown`; `mappable_locations` reads 0 and the UI says "nothing geocoded yet" | M1 (NYC GeoSearch, A4) |
| Closure state machine | `records_closed` is hardcoded to 0. `jobs.status` only ever holds `open`. Nothing can close a listing, which is the safe direction under I3 | M1 |
| Dedupe | None. One canonical job per source record, linked with `match_confidence=1.0` and `link_reason='sole_source_record'` — a claim about provenance, not about identity | M1 |
| `job_locations.geom` | Column and GiST index exist; always NULL | M1 |
| Internship employment-type fixtures | The recorded Datadog board contains **zero** internship postings (recorded in `datadog_board.meta.json` → `coverage_not_available_on_this_board`). That branch is covered by clearly-labelled synthetic unit tests against the function, not by a fabricated "recorded" payload | M1, when a board with internships is added |
| `normalize_title` | Whitespace and dash folding only. Deliberately does **not** attempt role-family normalization — asserted by `test_does_not_attempt_role_family_normalisation` | M3 |
| `jobs.role_family`, `jobs.seniority` | Columns exist, always NULL. NULL means "not classified", never a guessed default | M3 |
| Location parser breadth | Handles the shapes Greenhouse produces. Lever and Ashby will add shapes; A2 requires the fixture file to grow before the parser does | M1 |
| Stripe board registry entry | Verified live (HTTP 200) but `status: disabled`. Polling more boards before the closure machine exists would mean ingesting jobs the system cannot honestly age out | M1 |
| `/registry` route | Read-only view of the YAML. The token *resolution* pipeline (probe a careers page, emit a candidate for review) does not exist | M1 |
| 3D city, map, MapLibre, Three.js | Not started, not scaffolded, no dependency added. Explore is a list and says so | M4 |
| Auth | None. Single seeded `dev_user`, id in config (A3). Every user-owned table will still carry a real `user_id` FK from its first migration | M5 |

---

## Session log

### 2026-07-29 — M0 build

Read CLAUDE.md, AMENDMENTS (all 15), and the relevant PRODUCT-SPEC sections.

Verified the Greenhouse endpoint against a live board before writing the adapter,
per A1's instruction to re-verify field shapes. That paid for itself immediately —
five things the spec did not say, now encoded in the code and its comments:

1. `content` arrives **HTML-escaped** (`&lt;p&gt;`), so unescaping must precede
   any tag handling.
2. `location.name` is one `;`-delimited string that routinely names ten places.
   Concrete proof of A2 — the messiest real value found was
   `"Boston, Massachusetts, USA; Connecticut, USA, Remote; … ; Rhode Island, USA, Remote"`.
3. `application_deadline` was **null on all 426 postings**. A10, confirmed on
   real data.
4. Compensation is not a top-level field; it hides in `metadata` as
   `value_type == "currency_range"`, and it is present on NYC postings
   (pay-transparency law) while absent on most others.
5. `updated_at` is a last-modified stamp and `first_published` is the real
   publication date. They are carried in separately-named columns and there is no
   `posted_at` anywhere in the codebase to be misread.

Wrote `tests/fixtures/locations.yaml` **before** the parser, as A2 directs.

**Two real bugs found by tooling rather than by reading:**

1. mypy strict caught `IngestionRun.source` being used by `GET /sources` but never
   defined as a relationship on the model — a runtime `AttributeError` on a route
   that had no test yet.
2. The company-normalization suite, written during the milestone review, caught
   `normalize_company_name("Moody's")` returning `"moody s"`. The apostrophe was
   being replaced with a space, leaving a dangling token, so `Moody's Analytics`
   and `Moodys Analytics` would have become two separate companies in a table
   whose `normalized_name` is unique. Real NYC employers affected: Moody's,
   Macy's, Lowe's, McDonald's. Fixed by deleting apostrophes rather than spacing
   them, and both the typewriter and typographic forms are now covered.

The second one is the argument for writing those tests earlier: it was a pure
function with no database dependency, so nothing was stopping me.

Deviations from spec, all deliberate and documented above: no
`discover_companies()` (A1), location on its own table (A2), ARQ (A11), no
Turborepo (A12), schema narrower than §6.

Did not start the 3D city. It is at M4 for a reason.
