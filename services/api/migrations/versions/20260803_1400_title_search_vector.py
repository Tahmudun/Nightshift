"""jobs.title_vector — the default search target

``0005`` added ``search_vector`` over title *and* description, and using it as
the default search target was wrong. Measured against the committed Alloy
board: ``q=developer`` matches **all nine** postings, because 'developer' stems
to 'develop' and every one of those descriptions contains "business
development" or "professional development".

That is not a defect in the index. It is what full-text search over long
documents does when there is no relevance ranking to sort the noise downward.
Ranking is M3 work (PRODUCT-SPEC §24) and depends on the match score, so
inventing a relevance order here would be building half of M3 badly.

The honest fix is to make the *default* the field a person means when they type
a job title, and keep the wide search as an explicit opt-in
(``include_description=true``) for the case it is genuinely good at: a rare
term like "Kubernetes" that only ever appears in the body.

Both columns are STORED generated columns for the same reason ``0005`` gives.

Revision ID: 0006_title_search
Revises: 0005_job_search
Create Date: 2026-08-03 14:00:00+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_title_search"
down_revision: str | None = "0005_job_search"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_TITLE_VECTOR = "to_tsvector('english', coalesce(title, ''))"


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "title_vector",
            postgresql.TSVECTOR(),
            sa.Computed(_TITLE_VECTOR, persisted=True),
            nullable=False,
        ),
    )
    op.create_index("ix_jobs_title_vector", "jobs", ["title_vector"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_jobs_title_vector", table_name="jobs")
    op.drop_column("jobs", "title_vector")
