# ADR 0001 — Build our own Postgres image for PostGIS + pgvector

- **Status:** accepted
- **Date:** 2026-07-29
- **Milestone:** M0

## Context

CLAUDE.md §2 specifies PostgreSQL 16 with both PostGIS and pgvector. PostGIS is
needed for geometry — job and company locations, and the building-footprint joins
that M4 depends on. pgvector is needed for embeddings — dedupe similarity in M1
and semantic search in M3.

No published image carries both:

- `pgvector/pgvector:pg16` has pgvector, no PostGIS.
- `postgis/postgis:16-3.4` has PostGIS, no pgvector.

## Options considered

1. **Extend `postgis/postgis:16-3.4` with the PGDG pgvector package.** One
   `apt-get install postgresql-16-pgvector`. The base image is the official
   Postgres image with the PGDG apt repository already configured, so the package
   comes from the same trusted source the base image itself uses.
2. **Compile pgvector from source in a Dockerfile.** Adds a build toolchain, a
   version to track by hand, and a slower image build.
3. **Use a third-party bundle image.** Shorter, but adds a maintainer we do not
   control to the critical path of local development.
4. **Drop pgvector until M1 needs it.** Tempting, and consistent with "do not add
   a dependency for a problem you have not confirmed you have" — but the cost is
   an extra migration and a rebuilt container later, and the extension is inert
   until something creates a vector column.

## Decision

Option 1. `infra/postgres/Dockerfile` extends `postgis/postgis:16-3.4` and
installs `postgresql-16-pgvector` from PGDG.

Extensions are created by `infra/postgres/init/001-extensions.sql`, which runs
once at cluster initialisation, rather than by an Alembic migration. `CREATE
EXTENSION` requires superuser and the application role should not be one.

The compose healthcheck asserts both extensions exist:

```
select count(*) from pg_extension where extname in ('postgis','vector')
```

so a cluster that failed the init script never reports healthy, and `make up
--wait` fails loudly instead of handing a broken database to `make migrate`.
`/health` runs the same query, for the same reason.

## Consequences

- One extra image build on first `make up`, roughly 30 seconds, cached after.
- `pg_trgm` and `pgcrypto` are enabled in the same script: `pg_trgm` for the
  fuzzy title matching M1's dedupe needs, `pgcrypto` for `gen_random_uuid()`
  without depending on `uuid-ossp`.
- CI does not build this image — it uses a prebuilt bundle image and runs the
  same init SQL. That is a deliberate divergence to keep CI under five minutes
  (A14), and it is safe because the migration and the health check both assert
  the extensions rather than assuming them.
- The Python `pgvector` package is **not** a dependency yet. The extension is
  available; the column type arrives with the first embedding table in M1.
