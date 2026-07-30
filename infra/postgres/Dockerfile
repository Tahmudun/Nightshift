# PostgreSQL 16 with BOTH PostGIS and pgvector.
#
# No published image carries both: pgvector/pgvector:pg16 lacks PostGIS, and
# postgis/postgis:16-* lacks pgvector. We need PostGIS for geometry (job and
# company locations, building footprint joins) and pgvector for embeddings
# (dedupe similarity, semantic search), so we extend the PostGIS image — it is
# built on the official postgres image and already has the PGDG apt repository
# configured, which makes pgvector a one-line install from a trusted source
# rather than a from-source build.
FROM postgis/postgis:16-3.4

# postgresql-16-pgvector comes from the same PGDG repo the base image uses.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
