# Nightshift

A geospatial job-search and application-management system for New York tech, combining job-board ingestion, explainable matching, and an interactive 3D city.

**Status:** active development. Public `main` includes M0–M5 and the initial M6 corpus expansion; M6 and deployment remain unfinished. The newer local M6 development branch is separate. See [PROGRESS](docs/PROGRESS.md) for acceptance evidence and outstanding limitations.

## Implemented capabilities

- Job-board adapters, background polling, canonical records and source-health tracking. Failed fetches do not silently close listings.
- Location confidence and placement rules: city-level evidence cannot place a role on a specific building.
- Evidence-linked matching, requirement extraction and local embeddings, with score components exposed to the reader.
- Application tracking, interviews and user-owned records protected by authentication and ownership checks.
- MapLibre city navigation and Three.js signal rendering, linked to a searchable list and detail panel.
- Manual posting capture and an authenticated MCP interface: assisted captures remain proposals for user confirmation.

## Architecture

```text
Job boards → adapters → ARQ workers → canonical jobs + location evidence
                                      PostgreSQL / PostGIS / pgvector
                                                  ↕
                                  FastAPI + async SQLAlchemy
                                                  ↕
                               Next.js / React / TypeScript
                             list + MapLibre / Three.js city
```

Redis supports background work. Alembic manages schema changes. The [architecture documents](docs/architecture/) and [decision records](docs/adr/) explain preservation of provenance, confidence, ownership and explicit score breakdowns.

## Engineering evidence

[Rendering acceptance](docs/reviews/milestone-4c-review.md) documents a controlled synthetic case with 5,000 roles and a fixed DOM count. This is a rendering-structure check, not a production throughput claim; visual density and device coverage have documented limits.

The [M5 acceptance walk](docs/reviews/milestone-5-acceptance.md) checks user isolation and capture provenance, including deliberate fault injection. CI covers Python, web tests, migrations, browser acceptance and secret scanning. Historical results and failures are recorded in [PROGRESS](docs/PROGRESS.md); they are not claims of tests rerun for this README.

## Run locally

Requires Python 3.12+, Node 20+, and Docker Desktop or OrbStack.

```sh
git clone https://github.com/Tahmudun/Nightshift.git
cd Nightshift
make doctor
make setup
make demo
```

Open http://localhost:3000. The offline demo uses a labelled committed job-board fixture. Outbound HTTP is disabled by default. For live ingestion, review the board registry and configuration, set `OUTBOUND_HTTP_ENABLED=true` in your local `.env`, then run `make ingest`. Never commit credentials or personal job-search data.

```sh
make check           # format, lint, typecheck and unit/integration tests
make test-e2e        # browser tests
```

**Test database warning:** the Python suite can truncate the configured development database. Use a disposable test database; preserve personal application data before running it. See [PROGRESS](docs/PROGRESS.md) and [CLAUDE.md](CLAUDE.md).

## Stack and repository

Python, FastAPI, async SQLAlchemy, PostgreSQL, PostGIS, pgvector, Redis, ARQ, Alembic; TypeScript, Next.js, React, MapLibre, Three.js; pytest, Vitest, Playwright, mypy and GitHub Actions.

`apps/web/` contains the frontend; `services/api/` contains API and workers; `infra/` contains local infrastructure; `data/` contains the reviewed board registry. Existing design, review and evaluation documents remain under `docs/`.

## Remaining work

M6 data and geographic coverage, later visual refinement, deployment and operational qualification remain in progress. No working public deployment is claimed here. Offline examples are labelled; historical live-ingestion counts describe a dated corpus rather than current users or production scale.

## Development approach

Designed and developed by Tahmudun Nabi using Claude Code and Codex assistance, with responsibility for product decisions, architecture, debugging, testing, integration and iteration. Existing co-author attribution is preserved.
