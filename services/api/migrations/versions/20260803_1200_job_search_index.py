"""jobs.search_vector and the M2a filter indexes

M2a filters on text, employment type, remote policy, first-seen date, salary
and city. Every one of those is a sequential scan without an index, and the
milestone's acceptance criterion is that filters stay fast.

``search_vector`` is a STORED generated column rather than a trigger-maintained
one. A trigger is a second write path that can be forgotten; a generated column
cannot go stale because Postgres computes it. The regconfig is the literal
'english' because ``to_tsvector`` is only IMMUTABLE with a fixed configuration,
and only IMMUTABLE expressions are legal in a generated column.

``ix_job_locations_city_lower`` indexes the expression ``lower(city)``, because
the city filter compares ``lower(city)`` and a plain btree on ``city`` cannot
serve that.

It is created here with raw SQL — ``op.create_index`` has no clean expression
form — **and** declared on ``JobLocation.__table_args__`` as
``Index("ix_job_locations_city_lower", text("lower(city)"))``. Both are
required, and the plan for this task originally said the opposite. Measured
rather than argued: with the index in the database and absent from the model,
``alembic check`` reports ``remove_index`` and fails, because autogenerate
compares against a model that does not mention it. With it declared, the check
is clean. If a later change makes autogenerate emit a phantom diff on this
index, the fix is an ``include_object`` exclusion in ``env.py``, not deleting
the declaration.

Hand-checked after autogenerate for the defect recorded at the head of
``0002``: autogenerate emits ``nightshift.db.types.UTCDateTime`` without
importing ``nightshift``, which is a NameError at upgrade time rather than a
review-time complaint. No UTCDateTime column is added here, but the check is
cheap and this is the third migration that note has applied to.

The downgrade drops the generated column, which takes its GIN index with it.
The other five indexes are dropped explicitly.

Revision ID: 0005_job_search
Revises: 0004_board_poll_state
Create Date: 2026-08-03 12:00:00+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_job_search"
down_revision: str | None = "0004_board_poll_state"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_VECTOR = "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description_text, ''))"


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_VECTOR, persisted=True),
            nullable=False,
        ),
    )
    op.create_index("ix_jobs_search_vector", "jobs", ["search_vector"], postgresql_using="gin")
    op.create_index("ix_jobs_employment_type", "jobs", ["employment_type"])
    op.create_index("ix_jobs_remote_policy", "jobs", ["remote_policy"])
    op.create_index("ix_jobs_first_seen_at", "jobs", ["first_seen_at"])
    op.create_index("ix_jobs_salary_max", "jobs", ["salary_max"])
    op.execute("CREATE INDEX ix_job_locations_city_lower ON job_locations (lower(city))")


def downgrade() -> None:
    op.drop_index("ix_job_locations_city_lower", table_name="job_locations")
    op.drop_index("ix_jobs_salary_max", table_name="jobs")
    op.drop_index("ix_jobs_first_seen_at", table_name="jobs")
    op.drop_index("ix_jobs_remote_policy", table_name="jobs")
    op.drop_index("ix_jobs_employment_type", table_name="jobs")
    op.drop_index("ix_jobs_search_vector", table_name="jobs")
    op.drop_column("jobs", "search_vector")
