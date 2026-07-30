# Amendments to PRODUCT-SPEC.md

`PRODUCT-SPEC.md` is the original vision document. It is thorough, but it was written
before any implementation and contains a few things that are wrong, unimplementable, or
underspecified.

**These amendments override PRODUCT-SPEC wherever they conflict.** Skim this file once
per session. Read the relevant amendment in full before working in that area.

---

## A1 — There is no company directory. Build a board registry.

**Overrides:** §7.1 adapter contract, §7.2 initial sources.

The adapter Protocol in §7.1 includes `discover_companies()`. **This method cannot be
implemented.** Greenhouse, Lever, and Ashby all expose public unauthenticated job board
APIs, but none of them expose a way to enumerate their customers. There is no master
list, no search endpoint, no directory. You must know each company's board token in
advance.

Verified live endpoints (confirmed July 2026 — re-verify against a live board before
relying on field shapes):

| ATS | Endpoint | Auth |
|---|---|---|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` | none |
| Lever | `https://api.lever.co/v0/postings/{company}?mode=json` | none |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true` | none |

All three are poll-only. No webhooks. You discover changes by re-fetching and diffing.

### What to build instead

Remove `discover_companies()` from the Protocol. Replace it with a **board registry**:
a version-controlled file at `data/board-registry.yaml`, treated as source data.

```yaml
- company: Stripe
  ats: greenhouse
  token: stripe
  added: 2026-07-29
  verified_at: 2026-07-29
  status: active          # active | dead | moved | disabled
  nyc_presence: true      # known NYC office; used for prioritizing polls
  notes: ""
```

Alongside it, build a **token resolution pipeline** as a separate, explicitly-invoked
tool (not part of scheduled ingestion):

1. Input: a company name or careers URL.
2. Probe the careers page for an embedded board (`boards.greenhouse.io/x`,
   `jobs.lever.co/x`, `jobs.ashbyhq.com/x`) or an iframe/widget reference.
3. Validate by calling the candidate endpoint and confirming a non-empty response.
4. Emit a registry entry for human review. **Never auto-commit.**

Community internship aggregator repos are a legitimate input here — but as a source of
*company names to resolve into board tokens*, never as a source of listings. Every
listing in the database must come from a first-party ATS endpoint.

### Registry health

Track per entry: consecutive failures, last success, last successful job count. An entry
returning 404 for N consecutive runs is marked `dead` and surfaces on the source health
page for human review. It does not silently disappear, and it does not close the jobs it
previously produced (see I3).

### Why this matters

This is the most interesting infrastructure problem in the project and the spec omitted
it entirely. "I maintain a self-healing registry of ATS board tokens with automated
liveness detection and human-in-the-loop verification" is a better interview answer than
anything in the matching engine.

---

## A2 — Canonical jobs need many locations.

**Overrides:** §6.9.

§6.9 puts a single `latitude` / `longitude` / `location_text` / `location_confidence` on
the canonical job. §7.5 then asks for dedupe fixtures covering "jobs in multiple
locations." These contradict.

Real postings routinely read `"New York, NY; San Francisco, CA; Remote"`. Collapsing that
to one point is exactly the kind of fabrication I1 forbids.

**Move location onto its own table:**

```
job_locations
  id
  job_id                FK
  raw_text              exact substring from the source
  city
  state
  country
  latitude              nullable
  longitude             nullable
  geom                  PostGIS point, nullable
  location_confidence   verified | approximate | city_only | remote | unknown
  is_primary            boolean
  resolution_method     enum
  resolved_at
  created_at / updated_at
```

Keep a denormalized `primary_location_id` on `jobs` for cheap sorting. Never let it
become the only representation.

Location parsing is its own unit-tested module with a fixture suite of real, messy
location strings. Build the fixture file before the parser.

---

## A3 — No auth until M5. Multi-user shape from day one.

**Overrides:** §5.6.

Single user. Do not build login, sessions, password reset, or OAuth in M0–M4. A seeded
`dev_user` with its ID in config is enough, and it removes an entire category of work
from the critical path.

**But:** every table that belongs to a user carries a real `user_id` foreign key from
the first migration, and every query filters on it. Never write a query that assumes one
user exists. When auth arrives at M5 it is an adapter plus a middleware, not a migration
of every table in the schema.

---

## A4 — The free NYC geo stack.

**Extends:** §21, §9.2.

The spec says "trusted geocoding result" without naming a provider. For NYC specifically,
the free options are better than the paid ones.

**Geocoding — NYC GeoSearch** (`geosearch.planninglabs.nyc`). Pelias-based, built by NYC
Planning Labs on the authoritative Property Address Directory. Free, no key, covers every
address in the five boroughs. Use as primary. Anything it resolves is
`location_confidence = verified`.

Fallback chain:
1. NYC GeoSearch → `verified`
2. Nominatim (1 req/sec, identify yourself, cache aggressively) → `approximate`
3. Neighborhood centroid from a static lookup → `approximate`, flagged
4. Nothing → `city_only` or `unknown`

Cache every geocode by normalized address string, permanently. Never re-geocode an
address you have already resolved. Store the provider, the confidence, and the timestamp
on every result.

**Buildings — NYC Open Data Building Footprints.** Includes per-building roof height
above ground elevation and ground elevation at base, updated daily by the city. This gives
real extrusion heights for the whole city instead of OSM guesses. Load once into PostGIS,
join company locations to the containing footprint by BIN, refresh quarterly.

Practical note: the full dataset is large. Filter to the boroughs and bounding boxes you
render, generate vector tiles once, serve statically. Do not query PostGIS per frame.

**Tiles — OpenFreeMap or self-hosted Protomaps.** Free, no key, no quota. Write the map
style yourself; the dark aesthetic in §4.2 needs a custom style anyway.

Net cost of the entire geographic stack: zero dollars, zero API keys, zero quotas. Write
this in the ADR — "no vendor lock-in and no recurring cost for geographic data" is a real
architectural decision worth defending.

---

## A5 — Embeddings run locally.

**Extends:** §5.3, §7.5, §8.

pgvector is specified; no embedding provider is. Use **`bge-small-en-v1.5` via fastembed**
(ONNX, CPU, ~130MB). Reasons:

- Free and offline, so `make demo` works with no network and no key
- Deterministic, so dedupe fixture tests are reproducible — with a hosted API they are not
- Fast enough at this volume (thousands of jobs, not millions)
- Model name and dimension stored on every embedding row, so a future swap is a
  backfill rather than a mystery

Do not introduce a hosted embedding API without an ADR that names the cost.

---

## A6 — M0 is a vertical slice.

**Overrides:** §28.

§27.2 says "implement the smallest coherent vertical slice." §28 then lists ten steps of
purely horizontal scaffolding that produce no job data. Follow §27.2.

M0 is not complete when the infrastructure exists. M0 is complete when **one real job
listing from one real Greenhouse board is in Postgres and rendered in a browser**, with
all the scaffolding underneath it earning its place by being load-bearing.

This costs nothing extra — it is the same infrastructure in a different order — and it
means you find out on day one whether the fetch → normalize → store → render path
actually works.

---

## A7 — Fix two entries in the visual language table.

**Overrides:** §4.3.

Two rows in the semantic visual table are mistakes.

**"Intermittent glitch = stale or unverified listing."** A glitch reads as a rendering
bug, not as information. Users will report it as broken; you will start ignoring it.
Replace with a *steady* treatment: reduced opacity plus a small explicit "last verified
N days ago" badge in the detail panel. Uncertainty communicated through legibility, not
through simulated malfunction.

**"Red static fracture = rejection."** This is a tool opened daily during a job search.
Rendering accumulated rejections as red fractures across the skyline makes the product
worse to use over exactly the period it is most needed, and the visual noise grows
monotonically with time. Rejections should settle to a **dim neutral archived state** —
present in the data, queryable, visible in Analyze, not dramatized on the map. Put
outcome visibility behind an explicit toggle, default off.

General principle to apply beyond these two rows: visual intensity should track *what
the user can act on*, not *what happened to them*. An approaching deadline earns a gold
beacon. A rejection from three weeks ago earns dimming.

---

## A8 — Gmail: scope reality before you build it.

**Extends:** §11.

`gmail.readonly` is a Google **restricted scope**. An unverified app is capped at a small
number of test users and shows an unverified-app warning screen. Full verification
requires a security assessment that is not realistic here.

Consequences to plan around now:

- Personal single-user use: fine, works, use a test-user OAuth client.
- **Public demo mode and Gmail are mutually exclusive.** The public demo (§18) uses
  synthetic classified-message fixtures only. Never a real inbox.
- Store the minimum: message ID, thread ID, sender, subject, timestamp, classification,
  extracted dates, confidence, associations. **Not bodies.** If a classifier needs body
  text, it processes in memory and stores only its output.
- Disconnect must revoke the token *and* delete every derived row, verifiably, with a
  test proving it.

Write this into the ADR before implementing, so M7 does not end in a surprise.

---

## A9 — Cost and quota budget.

**New section.**

Maintain `docs/architecture/costs.md` from M0. Every external dependency gets a row:
name, purpose, free tier, what happens at the limit, replacement plan.

Target for M0–M4: **$0/month and zero API keys**, achievable with the stack in A4/A5.

Any change that introduces a recurring cost or a rate-limited key needs an ADR naming
the monthly figure and the degradation behavior when the quota is exhausted. "Degrades
to `unknown` confidence" is an acceptable answer. "Breaks" is not.

---

## A10 — Fields that are usually null.

**Extends:** §6.9, §12.3.

Do not design UI that depends on fields most postings omit. From real ATS payloads:

- `application_deadline` — rarely present. Never sort or filter by it as a default.
  Never show a countdown you cannot substantiate.
- `salary_min` / `salary_max` — present on Ashby with `includeCompensation=true`, and on
  postings subject to pay-transparency law (which does include NYC), but sparse overall.
- `posted_at` — often actually a last-updated timestamp, not an original post date. Store
  what the source gives you, name the column for what it actually is, and never present
  `first_seen_at` as "posted."

For every such field, the UI states "not provided by source" rather than hiding the row.
Absence of data is data.

---

## A11 — ARQ, not Celery.

**Overrides:** §5.4.

Celery is sync-first and awkward alongside async SQLAlchemy and async httpx; the
integration friction is real and constant. ARQ is asyncio-native, Redis-backed, small,
and supports scheduled jobs, retries with backoff, and result inspection — everything
§5.4 requires.

Workers live inside `services/api` as a module, sharing models, config, and session
management. They are not a third deployable app.

If job orchestration genuinely outgrows ARQ, migrating is an ADR and a week. Do not
pre-pay that cost.

---

## A12 — No Turborepo yet.

**Overrides:** §5.1.

Turborepo earns its keep when multiple TS packages share build outputs. This repo has
one TS app and one Python service. A root `Makefile` orchestrates both, and it is
simpler, faster to debug, and language-agnostic.

Skip `packages/*` entirely at the start. Create a shared package only when there is
actual TS code duplicated across two consumers — which, with a single frontend, may
be never.

Revisit if `apps/web` splits or a second TS consumer appears. Until then this is
premature structure.

---

## A13 — Seniority and eligibility parsing is the hard problem.

**Extends:** §8, §23.

The spec treats eligibility as a rules gate, which is right, but understates the
difficulty. The genuinely hard cases, all of which occur constantly:

- A posting titled "Intern" containing "3+ years of experience required"
- "New Grad" roles requiring a graduation date inside a window stated only in prose
- Experience requirements in preferred-qualifications rather than requirements
- "Bachelor's degree or equivalent experience" — this is not a hard blocker
- Multi-level postings ("Software Engineer I/II") that span eligibility boundaries
- Return-offer internships with different eligibility from the general posting

Build the eligibility ruleset against a **hand-labeled fixture set of at least 50 real
postings** — collected first, labeled first, before writing the rules. Track precision
and recall on it in CI. When a rule cannot decide, it returns `uncertain`. A wrong
`ineligible` is worse than an `uncertain`: it silently removes an opportunity the user
would have wanted, and they never learn it existed.

---

## A14 — Defer these.

**Overrides:** §14.4, §16.

The full testing pyramid and CI matrix in the spec is more than the project can carry
early, and a slow CI is a CI you start skipping.

Defer to the milestone shown:

| Item | Defer to |
|---|---|
| Visual regression tests | M5 (nothing visually stable to regress against before then) |
| 3D performance tests in CI | M5 (instrument in M4, gate in M5) |
| Load tests | M8 |
| Automated accessibility tests | M4 (manual keyboard + screen-reader passes from M2) |
| Coverage thresholds | M3 (measure and report from M0, do not gate) |
| License scanning | M8 |

Keep in CI from M0: format, lint, typecheck, unit tests both languages, migration
up/down, build, secret scan. Target under five minutes.

---

## A15 — Define "shippable" at M4.

**New section.**

The Long-Term Definition of Done in §30 has sixteen items and describes M8. That is a
year of work and a demotivating target to hold as the only definition of finished.

**M0–M4 is the portfolio project.** At the end of M4 you have: a real ingestion pipeline
across three ATS providers with provenance and honest freshness, a deduplicated canonical
job database, an explainable matching engine with an evaluation suite, and a genuinely
interactive 3D New York that does not lie about where anything is.

That is deployable, demoable, and defensible in an interview. Treat M4 as a real ship —
deploy it, write the case study, put it on the resume — before starting M5. Everything
after M4 is upside on a project that already counts.
