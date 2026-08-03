"""jobs.salary_min index — the other half of the salary floor

``0005`` indexed ``salary_max`` and stopped there, which was wrong. The salary
floor is ``salary_max >= :floor OR salary_min >= :floor``, and Postgres can
only serve an OR from indexes when **both** sides have one — it combines them
with a BitmapOr. With one side unindexed the entire filter degrades to a
sequential scan.

Found by ``tests/test_query_plans.py``, which is the whole reason that test
exists: the omission is invisible in the code, invisible in the API response,
and invisible in a correctness test, because the wrong plan returns exactly the
right rows. It only shows up as slowness, and only once the corpus is large
enough that slowness is expensive to fix.

Revision ID: 0007_salary_min_index
Revises: 0006_title_search
Create Date: 2026-08-03 15:00:00+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_salary_min_index"
down_revision: str | None = "0006_title_search"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_jobs_salary_min", "jobs", ["salary_min"])


def downgrade() -> None:
    op.drop_index("ix_jobs_salary_min", table_name="jobs")
