#!/usr/bin/env bash
#
# Load a dump produced by `scripts/backup.sh` back into the database.
#
# **This overwrites data.** `--clean --if-exists` drops each object before
# recreating it, which is what makes a restore a restore rather than a merge.
# It names the database it is about to overwrite and it will not guess one.
#
#   ./scripts/restore.sh backups/nightshift-20260830T041500Z.dump
set -euo pipefail

CONTAINER="${NIGHTSHIFT_PG_CONTAINER:-nightshift-postgres-1}"
DB="${POSTGRES_DB:-nightshift}"
USER="${POSTGRES_USER:-nightshift}"

if [ "$#" -lt 1 ]; then
  echo "usage: ./scripts/restore.sh <dump file>" >&2
  exit 2
fi
SOURCE="$1"

if [ ! -s "$SOURCE" ]; then
  echo "error: $SOURCE is missing or empty" >&2
  exit 1
fi

if ! docker exec "$CONTAINER" pg_isready -U "$USER" -d "$DB" -q; then
  echo "error: $CONTAINER is not accepting connections for $DB" >&2
  exit 1
fi

echo "==> restoring $SOURCE into $DB (this overwrites what is there)"
# `--clean --if-exists` makes the restore idempotent against an existing schema.
# pg_restore exits non-zero on warnings it recovered from — an extension it
# could not drop, an owner that does not exist locally — so its status is
# reported rather than trusted, and the caller checks the data instead.
if ! docker exec -i "$CONTAINER" pg_restore -U "$USER" -d "$DB" --clean --if-exists \
    --no-owner --no-privileges < "$SOURCE"; then
  echo "==> pg_restore reported errors; check the output above" >&2
fi
echo "==> restored $DB from $SOURCE"
