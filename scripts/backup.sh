#!/usr/bin/env bash
#
# Dump the Nightshift database to a file.
#
# Written before the reader's own data exists, deliberately: after that, their
# application history lives in exactly one place and `make reset-db` drops it.
# A backup nobody has ever restored is a hope, not a backup, so `restore.sh` is
# its sibling and `test_backup_roundtrip.py` runs both.
#
#   ./scripts/backup.sh                 -> backups/nightshift-<utc timestamp>.dump
#   ./scripts/backup.sh path/to/file    -> that file
#
# The custom format (`-Fc`) rather than plain SQL: it restores selectively, it
# compresses, and `pg_restore --clean` can rebuild into a database that already
# has the schema — which is the situation a restore always actually meets.
set -euo pipefail

CONTAINER="${NIGHTSHIFT_PG_CONTAINER:-nightshift-postgres-1}"
DB="${POSTGRES_DB:-nightshift}"
USER="${POSTGRES_USER:-nightshift}"

if [ "$#" -ge 1 ]; then
  TARGET="$1"
else
  mkdir -p backups
  TARGET="backups/nightshift-$(date -u +%Y%m%dT%H%M%SZ).dump"
fi

mkdir -p "$(dirname "$TARGET")"

if ! docker exec "$CONTAINER" pg_isready -U "$USER" -d "$DB" -q; then
  echo "error: $CONTAINER is not accepting connections for $DB" >&2
  echo "       run 'make up' first" >&2
  exit 1
fi

# Straight to the file, and only then checked. A zero-byte dump that reported
# success is the failure this whole script exists to prevent.
docker exec "$CONTAINER" pg_dump -U "$USER" -d "$DB" -Fc > "$TARGET"

if [ ! -s "$TARGET" ]; then
  echo "error: $TARGET is empty — the dump failed" >&2
  rm -f "$TARGET"
  exit 1
fi

SIZE=$(wc -c < "$TARGET" | tr -d ' ')
echo "==> backed up $DB to $TARGET ($SIZE bytes)"
