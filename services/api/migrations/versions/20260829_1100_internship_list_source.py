"""`source_type` gains `internship_list`.

the-hunt.md §5.2. A publicly published, machine-readable list of internship
postings is not an ATS: one request returns hundreds of employers, and each
entry is a *pointer* rather than a posting — no description, so any score built
on one alone is thin and has to say so. That difference has to survive into the
database, because the UI badge, the freshness rules and the score's own
confidence all read `source_type` to decide what this row is allowed to claim.

**The downgrade is long for the reason `0026_captured_postings` recorded.**
PostgreSQL has `ALTER TYPE ... ADD VALUE` and no `DROP VALUE`, so reversing the
addition means rebuilding the type and converting the one column that uses it.
The `USING` cast fails loudly if a surviving row is an `internship_list`
source, which is correct: the value is in use, so the schema that lacks it is
not a schema this data fits.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0031_internship_list_source"
down_revision: str | None = "0030_landmass"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADDED_SOURCE_TYPE = "internship_list"

#: `source_type` exactly as it stood before this migration. The downgrade
#: rebuilds it from this list, so it is the definition of "before" rather than a
#: comment about it.
_SOURCE_TYPE_BEFORE = (
    "ats_greenhouse",
    "ats_lever",
    "ats_ashby",
    "government",
    "fixture",
    "manual_capture",
)


def upgrade() -> None:
    op.execute(f"ALTER TYPE source_type ADD VALUE IF NOT EXISTS '{_ADDED_SOURCE_TYPE}'")


def downgrade() -> None:
    # See the module docstring: no DROP VALUE, so the type is rebuilt. `sources`
    # is the only table that uses it and it carries no default to preserve.
    values = ", ".join(f"'{value}'" for value in _SOURCE_TYPE_BEFORE)
    op.execute("ALTER TYPE source_type RENAME TO source_type_old")
    op.execute(f"CREATE TYPE source_type AS ENUM ({values})")
    op.execute(
        "ALTER TABLE sources ALTER COLUMN source_type "
        "TYPE source_type USING source_type::text::source_type"
    )
    op.execute("DROP TYPE source_type_old")
