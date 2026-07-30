-- Runs once, on first cluster initialisation, before any migration.
--
-- Extensions live here rather than in an Alembic migration because CREATE
-- EXTENSION requires superuser, and the application role should not be one.
-- The compose healthcheck asserts both of these exist, so a cluster that fails
-- this script never reports healthy.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- Trigram index support for the fuzzy title matching that dedupe needs (M1).
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- gen_random_uuid() without depending on uuid-ossp.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
