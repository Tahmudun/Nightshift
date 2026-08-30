"""`job_locations` gains `landmass`.

archipelago.md §4. Four values, because collapsing any two would discard a fact
the posting stated: a role in San Francisco and a role that says only "Remote —
United States" are both *not New York*, and they differ on the two things a
reader filters on, work authorisation and time zone.

**Stored rather than derived.** `landmass_for()` is a pure function of the row's
own columns, so a view or a property would give the same answer — but the
reader's filter is a `WHERE` clause over 1200 rows and climbing, and a Python
property cannot be indexed. The column is written at ingestion and backfilled
by `python -m nightshift.cli backfill-landmass`.

**The server default is `unplaced`, and that is the honest value for a row this
migration has not looked at.** Every existing row gets it; the backfill is a
separate step, on purpose, so that "the column exists" and "the column is
correct" are two events with two pieces of evidence rather than one migration
that claims both.

The type is created and dropped by hand, for the reason `0025` recorded: a bare
`sa.Enum` inside `add_column` emits the `ALTER TABLE` without the `CREATE TYPE`
before it, and a type left behind on downgrade makes the next upgrade fail with
"already exists".
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_landmass"
down_revision: str | None = "0029_job_location_clears_scores"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Created and dropped by hand. See the module docstring and `0025`.
landmass = sa.Enum(
    "new_york",
    "elsewhere_city",
    "elsewhere_broad",
    "unplaced",
    name="landmass",
    create_type=False,
)


def upgrade() -> None:
    landmass.create(op.get_bind(), checkfirst=False)
    op.add_column(
        "job_locations",
        sa.Column("landmass", landmass, server_default="unplaced", nullable=False),
    )
    op.create_index("ix_job_locations_landmass", "job_locations", ["landmass"])


def downgrade() -> None:
    op.drop_index("ix_job_locations_landmass", table_name="job_locations")
    op.drop_column("job_locations", "landmass")
    # See the module docstring: the column is gone but the type is not.
    op.execute("DROP TYPE IF EXISTS landmass")
