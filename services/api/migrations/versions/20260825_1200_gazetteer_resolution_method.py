"""`resolution_method` gains `gazetteer`.

ADR 0040. A bare city name that ADR 0008's decided list declines is now looked
up in `data/city-gazetteer.tsv`, a committed artifact whose every judgement was
made at build time. Rows resolved that way must be distinguishable from rows the
posting's own structure corroborated — *"this posting named a city and a state"*
and *"this posting named one word that a list recognised"* are different claims,
and the difference is what makes ADR 0040 reversible without a re-crawl: every
affected row is one query away.

**The downgrade is long for the reason `0020_company_locations` documented.**
PostgreSQL has `ALTER TYPE ... ADD VALUE` and no `DROP VALUE`, so reversing the
addition means rebuilding the type and converting every column that uses it —
now three of them, `geocode_cache` having joined since. It fails loudly if any
surviving row holds `gazetteer`, which is correct: you cannot downgrade past
data that needs the value, and a migration that quietly rewrote those rows to
`source_text_parse` would be destroying the provenance this value exists to
record.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0028_gazetteer_resolution_method"
down_revision: str | None = "0027_capture_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADDED_VALUE = "gazetteer"

_RESOLUTION_METHOD_BEFORE = (
    "not_attempted",
    "source_text_parse",
    "nyc_geosearch",
    "nominatim",
    "neighborhood_centroid",
    "manual",
    "company_office",
)

# Every column on the enum, with the default it carries. Rebuilding the type
# means dropping and restoring each default, because a default is stored as a
# parsed expression against the old type and does not survive the swap.
_COLUMNS = (
    ("job_locations", "resolution_method", "not_attempted"),
    ("company_locations", "resolution_method", "not_attempted"),
    ("geocode_cache", "resolution_method", None),
)


def upgrade() -> None:
    # ADD VALUE must land before any DDL that references it, and PostgreSQL 12+
    # permits it inside a transaction so long as the new value is not *used* in
    # the same one. Nothing here uses it; the backfill is a separate step.
    op.execute(f"ALTER TYPE resolution_method ADD VALUE IF NOT EXISTS '{_ADDED_VALUE}'")


def downgrade() -> None:
    values = ", ".join(f"'{value}'" for value in _RESOLUTION_METHOD_BEFORE)
    op.execute("ALTER TYPE resolution_method RENAME TO resolution_method_old")
    op.execute(f"CREATE TYPE resolution_method AS ENUM ({values})")

    for table, column, default in _COLUMNS:
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        # The USING cast fails loudly if a surviving row holds `gazetteer`.
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE resolution_method USING {column}::text::resolution_method"
        )
        if default is not None:
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {column} "
                f"SET DEFAULT '{default}'::resolution_method"
            )

    op.execute("DROP TYPE resolution_method_old")
