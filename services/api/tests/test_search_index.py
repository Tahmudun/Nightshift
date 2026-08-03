"""The search index exists in the database, and it indexes what we think it does.

A GIN index that was never created is invisible until the corpus is large
enough for the difference to matter, which is exactly when it is expensive to
discover. These tests ask the live catalogue rather than trusting the model.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


async def test_search_vector_column_exists_and_is_generated(db_session: AsyncSession) -> None:
    row = (
        await db_session.execute(
            text(
                """
                SELECT data_type, is_generated
                FROM information_schema.columns
                WHERE table_name = 'jobs' AND column_name = 'search_vector'
                """
            )
        )
    ).one_or_none()
    assert row is not None, "jobs.search_vector is missing"
    data_type, is_generated = row
    assert data_type == "tsvector"
    # ALWAYS, not NEVER: a column the application has to remember to update is
    # a column that goes stale on the one write path somebody forgets.
    assert is_generated == "ALWAYS"


@pytest.mark.parametrize(
    "index_name",
    [
        "ix_jobs_search_vector",
        "ix_jobs_employment_type",
        "ix_jobs_remote_policy",
        "ix_jobs_first_seen_at",
        "ix_jobs_salary_max",
        "ix_job_locations_city_lower",
    ],
)
async def test_index_exists(db_session: AsyncSession, index_name: str) -> None:
    found = (
        await db_session.execute(
            text("SELECT 1 FROM pg_indexes WHERE indexname = :name"), {"name": index_name}
        )
    ).scalar_one_or_none()
    assert found == 1, f"{index_name} is not in pg_indexes"


async def test_the_vector_indexes_title_and_description(db_session: AsyncSession) -> None:
    """Both source columns reach the vector, and stop words do not."""
    vector = (
        await db_session.execute(
            text(
                """
                SELECT to_tsvector(
                    'english',
                    coalesce(:title, '') || ' ' || coalesce(:description, '')
                )::text
                """
            ),
            {"title": "Senior Platform Engineer", "description": "Kubernetes and Terraform"},
        )
    ).scalar_one()
    assert "platform" in vector
    assert "kubernet" in vector  # stemmed
    # "and" is an english stop word and must not occupy a lexeme slot.
    assert "'and'" not in vector
