# Cost and quota budget

Required from M0 by AMENDMENTS A9. Every external dependency gets a row: name,
purpose, free tier, what happens at the limit, replacement plan.

**Current monthly cost: $0.00. API keys in use: 0.**

Target for M0–M4 is $0/month and zero keys, and the stack in A4/A5 achieves it.
Any change that introduces a recurring cost or a rate-limited key needs an ADR
naming the monthly figure and the degradation behaviour when the quota runs out.
"Degrades to `unknown` confidence" is an acceptable answer. "Breaks" is not.

---

## In use as of M0

| Dependency | Purpose | Free tier | At the limit | Replacement plan |
|---|---|---|---|---|
| Greenhouse Job Board API | Job listings. `boards-api.greenhouse.io/v1/boards/{token}/jobs` | Unauthenticated, no published quota | No documented limit. We self-limit to 2 req/s with backoff and jitter. A 429 is retried; repeated failure marks the run `failed` and **changes no listing state** (I3) | None needed. If a board 404s persistently the registry entry is marked `dead` for human review |
| PostgreSQL 16 + PostGIS + pgvector | Primary datastore | Free, self-hosted via Docker | Disk. One user and a few thousand jobs is megabytes | None needed. CLAUDE.md §8: Postgres is enough and will be for a long time |
| Redis 7 | ARQ queue + geocode cache | Free, self-hosted via Docker | `maxmemory 256mb`, `allkeys-lru`. Everything in it is regenerable | None needed. Losing Redis costs a re-poll, not data |

## Committed for M1–M4, verified free, not yet integrated

| Dependency | Purpose | Free tier | At the limit | Replacement plan |
|---|---|---|---|---|
| NYC GeoSearch (`geosearch.planninglabs.nyc`) | Primary geocoder. Pelias over the authoritative Property Address Directory | Free, no key | No published quota. We cache every result permanently by normalised address and never re-geocode a resolved one | Fall through to Nominatim → neighbourhood centroid → `city_only`/`unknown`. Never a fabricated point |
| Nominatim | Fallback geocoder | Free, 1 req/s, must identify itself | Exceeding it gets you blocked, which is why the cache is permanent and the limiter is shared | Fall through to `approximate` centroid or `unknown` |
| NYC Open Data Building Footprints | Real per-building extrusion heights (`heightroof`, ground elevation) | Free, no key, bulk download | Not a runtime dependency. Loaded once into PostGIS, tiles generated once, refreshed quarterly | None needed |
| OpenFreeMap / self-hosted Protomaps | Basemap tiles | Free, no key, no quota | OpenFreeMap is donation-funded and could disappear | Self-host Protomaps from a one-off extract. This is why the tile source is a config value, not a hardcoded URL |
| `bge-small-en-v1.5` via fastembed | Embeddings for dedupe and semantic search | Free, offline, ~130MB ONNX model, CPU | None — it runs locally | None needed. Model name and dimension are stored on every embedding row, so a future swap is a backfill, not a mystery |

## Added at M2c

| Dependency | Purpose | Free tier | At the limit | Replacement plan |
|---|---|---|---|---|
| `pypdf` | Reading the text out of an uploaded PDF resume | n/a — a local library, BSD-3-Clause | Nothing. No network call, no key, no quota. Work is bounded per request by a 2 MB size cap and a 20-page cap | Paste, which is already a first-class supported input. Dropping PDF support would cost a step, not a capability |
| `python-multipart` | Lets FastAPI parse a file upload at all | n/a — a local library, Apache-2.0 | Nothing. No network call | Base64 in a JSON body, or paste-only |

**Still $0/month and zero keys.** Both are pure Python and offline, so `make
demo` from a clean clone with no network is unaffected. Neither was added
speculatively: the human chose PDF as an accepted resume format on 2026-08-03,
and FastAPI cannot read a multipart upload without the second one.

## Deliberately not used

| Thing | Why not |
|---|---|
| Hosted embedding APIs (OpenAI, Cohere, Voyage) | Cost, a key, and — the real objection — non-determinism. Dedupe fixture tests must be reproducible, and they are not if embeddings come from a versioned remote model. AMENDMENTS A5 |
| Hosted geocoders (Google, Mapbox, HERE) | For NYC specifically the free NYC GeoSearch is *more* authoritative, being built on the city's own address directory. Paying would buy less accuracy |
| Mapbox GL JS | Licence and per-load pricing. MapLibre GL JS is the community fork with no key and no quota |
| LLM APIs | No confirmed need. Requirement extraction and eligibility (M3) are deterministic, versioned rules, which is what makes invariant I4 satisfiable — a score has to decompose, and a model that emits a number does not |
| Google Gmail API | Deferred to M7 and constrained by AMENDMENTS A8: `gmail.readonly` is a restricted scope, an unverified app is capped at a handful of test users, and full verification requires a security assessment that is not realistic here. Public demo mode and Gmail are mutually exclusive |

## Review

Update this file in the same commit as any dependency change. If a row's "at the
limit" column would read "breaks", the change does not ship.
