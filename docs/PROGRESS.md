# PROGRESS

> Read this first, every session. If the repo state does not match what this
> file claims, fix this file before writing code.

**Current milestone: M0 — Foundation with a heartbeat**
**Status: 5 of 6 acceptance criteria VERIFIED. Row 2 (CI green) needs a git remote.**
**Last updated: 2026-07-30**

---

## Next exact action

**Two things need a human, and both are host problems rather than code.**

1. **Restart Docker Desktop from the GUI.** It died when the disk filled and now
   shows an error dialog instead of starting (B3). Then run `make acceptance` to
   re-confirm the 6 seeded browser tests, which are the only checks not re-run
   after the last commit.
2. **Create a git remote** so CI can run — acceptance row 2, below.

Row 2 cannot be verified locally at all: CI green means a real run on real
infrastructure.

```bash
# Create an empty repo (no README, no .gitignore), then:
git remote add origin git@github.com:<you>/citysignal.git
git push -u origin main
```

Then check the Actions tab. Five jobs must pass: `python`, `web`, `migrations`,
`e2e`, `secrets`. Record the run URL in row 2 below and mark M0 complete.

`make acceptance` is the single-command acceptance run. At commit `bb46732` it
passed from a wiped Docker volume with nothing pre-started:

```
18 verify checks + 6 seeded browser tests, all green
```

---

## Blockers

### B1 — No container runtime — RESOLVED 2026-07-30

Docker Desktop was installed by the human after `brew install --cask
docker-desktop` had rolled itself back on an interactive-sudo step
(`mkdir -p /usr/local/cli-plugins`; `/usr/local` is `root:wheel`).

Everything B1 had been blocking is now verified with recorded output. Kept here
because the acceptance table's history refers to it.

### B3 — Docker Desktop is down and needs GUI attention

Caused by B2. The daemon died mid-session with `no space left on device` (in
`~/Library/Containers/com.docker.docker/Data/log/host/com.docker.backend.log`),
then came back showing an Electron error dialog rather than starting. Quitting it
cleanly and relaunching with `open -a Docker` did not bring it back; it needs
someone to look at the dialog.

Disk pressure is relieved (7.5 GB free after deleting `apps/web/.next` and
Playwright artefacts), so a restart should now succeed.

**What this does and does not invalidate.** Every acceptance row was verified at
commit `bb46732`, before this happened. One commit landed afterwards, `f0cb5a6`,
which is CSS tokens plus class renames plus a new unit test. It cannot touch
migrations, `/health`, the constraint probes, the API, or the seed path, so rows
1, 3, 4 and 6 are unaffected. Re-run after that commit: `make check` (215 unit
tests) and `make test-e2e` (5 tests, which render all three routes in a real
browser with the new palette). **Not re-run: the 6 seeded browser tests behind
row 5.** Their assertions are text and ARIA based rather than colour based, so
there is no specific reason to expect breakage — but they have not been run, and
that is the honest state of it. First thing to do once Docker is back:

```bash
make acceptance
```

### B2 — Host disk is full (degrades verification, blocks nothing)

`/System/Volumes/Data`: 210 GB used of 233 GB, **1.2 GB free**. A fresh clone of
this repo needs ~730 MB of `node_modules` plus venv, which would leave the
machine under 500 MB. The final clean-clone run was therefore skipped rather than
risk destabilising the host; the earlier clean-clone run at `0830589` stands, and
row 1 says precisely what that does and does not cover.

Docker's own reclaimable space was already pruned (build cache and dangling
images, ~477 MB). The remaining large image, `hg-engine:latest` (2.06 GB), is not
part of this project and was left alone.

---

## Acceptance criteria — M0

Per invariant I6, "the code exists" is not evidence. Each row is either verified
with recorded output or explicitly marked blocked.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Clean clone → `make setup && make demo` works, documented, no hidden steps | **VERIFIED** | Genuine `git clone` into a scratch directory at commit `0830589`, no `.env`, no Docker volumes: `make setup` built the venv and installed JS deps in **47.8s**, then `make setup && make acceptance` passed **18/18** checks. Postgres initialised from an empty volume, so the extension init script ran for real. Three commits landed after that run (`b4e515a`, `0c230f1`, `bb46732`); they were verified in place, not by re-cloning, because the host disk is full (B2). Of those, only the Makefile `browsers` target touches the setup path, and it was exercised — including its ~100 MB first-run download |
| 2 | CI green | **UNVERIFIED — needs a git remote** | `.github/workflows/ci.yml`, five jobs: `python`, `web`, `migrations`, `e2e`, `secrets`. `git remote -v` is empty and `gh` is not installed, so it has never run. Every command it issues was run locally and passes (see the table below), and the YAML parses — but "the same commands pass on my laptop" is **not** the criterion, and this row stays UNVERIFIED until a real run exists |
| 3 | Migrations apply and roll back | **VERIFIED** | Against live PostGIS 16 + pgvector. Before: 12 tables, 8 enum types. `make migrate-down` → the 8 project tables and **all 8 enum types** dropped, leaving only `alembic_version` and PostGIS's own `geography_columns` / `geometry_columns` / `spatial_ref_sys`. A downgrade that forgets `DROP TYPE` leaves enums behind and this is how you see it. `make migrate` → 12 tables and 8 enums restored; re-seeding produced a byte-identical corpus (10 jobs, 21 locations, same confidence split) |
| 4 | `/health` reports DB + Redis honestly, including when they are down | **VERIFIED** | Real containers stopped, not mocked. Both up → `200 {"status":"ok",…"database":{"ok":true,"detail":"postgis + pgvector present","latency_ms":4.27},"redis":{"ok":true,"detail":"PONG","latency_ms":3.2}}`. Postgres stopped → `503 "degraded"`, `database.ok:false`, `detail:"ConnectionRefusedError: [Errno 61] Connection refused"`, **redis still `ok:true`** — the two are reported independently. Redis stopped too → both false, with distinguishable details. `/health/live` stayed `204` throughout, as a liveness probe should. Both restarted → `200`, and `/stats` still reported all 10 jobs open: an outage closed nothing (I3) |
| 5 | One real Greenhouse board's jobs appear in the browser | **VERIFIED** | Board fetched live 2026-07-29: `boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true` → HTTP 200, 5,309,493 bytes, 426 postings, 134 naming New York. 10 recorded verbatim into a committed fixture. Now rendered in a real Chromium via `apps/web/e2e-seeded/` — **6 tests, all passing** — which reads the expected titles from the API at run time and finds them in the DOM. Also asserts the A2 multi-location rows, the I7 "committed fixture" badge, and that no job ladder claims verified/approximate placement |
| 6 | No secrets committed | **VERIFIED** | No key-shaped strings anywhere in the tree (scanned for `sk-*`, `AKIA*`, `ghp_*`, PEM private keys). `.env` is gitignored (`.gitignore:2`), confirmed via `git check-ignore`. Only credential-shaped value in the repo is `citysignal_dev_only`, the local compose password, allowlisted in `.gitleaks.toml` for the three files entitled to contain it. `tests/test_env_example.py` now asserts this rather than trusting it |

**M0 is not complete.** Row 2 is unsatisfied and it needs a human to create a
remote. Rows 1 and 3–6 are verified with the recorded output above.

Row 2 is not a formality: CI is the only thing that runs the `migrations` up →
down → up sequence and the drift probe on every change, and it is where the
`e2e` job guards acceptance row 5 from regressing.

---

## Verified locally (recorded output)

These ran on this machine and passed:

| Check | Command | Result |
|---|---|---|
| Python format | `ruff format --check services/api` | 35 files already formatted |
| Python lint | `ruff check services/api` | All checks passed |
| Python types | `mypy citysignal` | Success: no issues found in 28 source files (strict) |
| Python tests | `pytest -q` | **196 passed** in 2.26s |
| Web types | `tsc --noEmit` | clean, `strict` + `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes` |
| Web lint | `eslint . --max-warnings 0` | clean |
| Web tests | `vitest run` | **35 passed** (4 files) |
| Colour contrast | `vitest run colour-contrast` | 16 assertions on measured WCAG 2.1 ratios |
| Web build | `next build` | compiled, 7 static routes, 102 kB shared JS |
| E2E — degraded (no API) | `make test-e2e` | **5 passed** in 15.0s |
| E2E — seeded corpus | `make test-e2e-seeded` | **6 passed** in 18.7s |
| Migration renders | `alembic upgrade head --sql` | full DDL emitted, 8 tables, 8 enums |
| Migration round trip | `make migrate-down && make migrate` | 8 tables + 8 enum types dropped and restored, live cluster |
| Whole-stack acceptance | `make acceptance` | **18 checks + 6 browser tests**, from an empty volume, nothing pre-started |
| Live source reachable | `GET /v1/boards/datadog/jobs` | HTTP 200, 426 postings |

**Total: 242 automated tests passing** (196 Python, 35 web unit, 5 degraded e2e,
6 seeded e2e), plus the 18 assertions in `scripts/verify.py`, which are not
pytest tests but do gate `make acceptance` with an exit code.

Caveat per B3: the 6 seeded e2e tests last ran at commit `bb46732`, one commit
back. Everything else in this table was run at `f0cb5a6`.

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

### 2026-07-30 — M0 acceptance

Docker Desktop installed by the human, clearing B1. Ran the acceptance criteria
against live infrastructure for the first time. Four bugs, every one of them found
by running the thing rather than by reading it.

**1. `make demo` failed on a clean clone.** The reported symptom:

```
.env: line 53: syntax error near unexpected token `('
.env: line 53: `HTTP_USER_AGENT=CitySignal/0.1 (+https://github.com/tahmudun/citysignal)'
make[1]: *** [migrate] Error 1
```

The Makefile loads config with `set -a && source .env`, because Alembic and the
seed CLI read the process environment rather than pydantic-settings. An unquoted
`(` is a bash syntax error. Three parsers read this file — bash, `docker compose
--env-file`, python-dotenv — with three different quoting rules, and only
python-dotenv had ever been exercised. `tests/test_env_example.py` now sources the
file exactly as the Makefile does and requires bash and python-dotenv to agree on
every value.

This is the M0 acceptance criterion that matters most and it was broken by one
missing pair of quotes. Worth remembering that the failure had nothing to do with
the interesting parts of the system.

**2. Acceptance row 5 had no automated coverage at all.** The existing Playwright
suite runs with *no API* on purpose — it proves the app reports "api unreachable"
instead of rendering an empty list, which is the right thing to test. But it meant
nothing asserted that real rows from Postgres ever reach a screen. Added
`apps/web/e2e-seeded/`, and an `e2e` job to CI so the criterion cannot regress
silently.

While writing it: the first version of the I1 test failed, and the app was right
and the test was wrong. `ConfidenceLegend` renders the same ladder component for
all five levels to document the visual language, so an unscoped
`getByRole('img')` was asserting against the legend rather than against job data.
Scoped to `role="article"`. Then added the assertion that the rejected label *does*
appear in the legend — otherwise over-narrow scoping would make the test pass by
matching nothing, which is the failure mode CLAUDE.md §7 means by "a test that
cannot fail is not a test."

**3. `make setup` never installed Playwright's browser.** It ships separately from
the npm package and the required build changes on minor upgrades, so
`make test-e2e` could not work from a clean clone. The e2e targets provision it
now; keeping it out of `make setup` avoids putting a 100 MB download in front of
every first run.

**4. `make acceptance` had a hidden step — mine.** I added the seeded suite to the
target, but `verify.py` starts its own uvicorn and tears it down on exit, so the
suite that ran after it had nothing to talk to. Six tests failed on
`ECONNREFUSED`. It had passed when I first ran it only because I had started
uvicorn by hand — precisely the class of thing acceptance criterion 1 exists to
forbid, committed by me while verifying that criterion. `playwright.seeded.config.ts`
now declares both servers, gated on `/health`, and the duplicate CI step is gone.

**5. The palette failed WCAG AA, and worse than the review guessed.** Review action
6 was "measure contrast on `paper-faint`/`ink-500`; lighten if below 4.5:1".
Measured: `paper-faint` 3.89:1, a genuine fail for the 9-11px labels it carries.
But `ink-500` — a *surface* shade — was being used as a text colour in fourteen
places at **1.69:1**, which is close to invisible. The palette had three named
text weights and a fourth unnamed one that nobody had decided on. Fixed by
lightening `paper-faint` to 5.43:1 and moving every `text-ink-500` onto it, so
there are now exactly three text steps and all three are readable.

`colour-contrast.test.ts` computes the ratios from the real tokens rather than
trusting a comment. Confirmed non-vacuous by restoring the old value: three tests
fail. It also pins `ink-500` *below* 3:1, so lightening it to reuse as text trips
a failure that points at the explanation.

**Verified against live infrastructure:** migration down/up dropping and restoring
all 8 enum types; `/health` degrading per-dependency with real containers stopped;
all four `job_locations` check constraints refusing their violations. The review's
line — *"a constraint nobody has seen reject anything is a comment with extra
syntax"* — is now settled: each one raised `IntegrityError`.

**Not verified:** CI (no remote exists, B-none — it needs an account decision), the
final clean-clone re-run (host disk, B2), and the 6 seeded browser tests after the
last commit (Docker died, B3). Each of those three has its own entry saying exactly
what it covers and what it leaves open.

The disk filling up was self-inflicted in part: I made two full clones of the repo
to test the clean-clone path, ~730 MB each in `node_modules` and venvs, on a
machine that had ~2 GB free to begin with. Both are deleted. Testing the
clean-clone path is right; doing it twice without checking `df` first was not.

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
