"""Every supported filter is servable by an index.

This deliberately does **not** assert "the plan has no Seq Scan". On the seeded
corpus Postgres chooses a sequential scan for every query, because scanning
tens of rows really is cheaper than an index lookup — so that assertion would
fail on correct code, and its inverse would pass on a table with no indexes at
all. Both are useless.

Instead each query runs with ``enable_seqscan = off``, which makes the planner
prefer any usable index, and the test asserts one was used. That answers the
question that actually matters: **is this filter servable by an index?** It
fails the day somebody adds a filter on an unindexed column, and it does not
depend on how big the corpus happens to be.

``test_a_filter_on_an_unindexed_column_is_detectable`` is the non-vacuity
guard: without it, the assertions above would pass for anything.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import EmploymentType, JobStatus, RemotePolicy
from nightshift.db.models import Job
from nightshift.domain.search import JobSearchQuery, build_filters
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

INDEXED_QUERIES = [
    pytest.param(JobSearchQuery(q="engineer"), id="title_text"),
    pytest.param(JobSearchQuery(q="engineer", include_description=True), id="description_text"),
    pytest.param(JobSearchQuery(employment_type=EmploymentType.INTERNSHIP), id="employment_type"),
    pytest.param(JobSearchQuery(remote_policy=RemotePolicy.REMOTE), id="remote_policy"),
    pytest.param(JobSearchQuery(job_status=JobStatus.OPEN), id="status"),
    pytest.param(
        JobSearchQuery(first_seen_after=datetime(2026, 1, 1, tzinfo=UTC)),
        id="first_seen_after",
    ),
    pytest.param(JobSearchQuery(salary_at_least=50000.0), id="salary_at_least"),
    pytest.param(JobSearchQuery(city="New York"), id="city"),
]


def _index_nodes(node: dict[str, Any]) -> list[str]:
    """Every index this plan touches, at any depth."""
    found: list[str] = []
    if "Index Name" in node:
        found.append(str(node["Index Name"]))
    for child in node.get("Plans", []):
        found.extend(_index_nodes(child))
    return found


async def _plan(session: AsyncSession, statement: Any) -> dict[str, Any]:
    """EXPLAIN this statement with sequential scans discouraged.

    Compiled with ``paramstyle="named"`` and the parameters passed through,
    rather than with ``literal_binds``. Literal binding cannot render every
    type: ``websearch_to_tsquery``'s first argument is a ``REGCONFIG``, and
    SQLAlchemy raises ``CompileError: No literal value renderer is available``
    on it. Named parameters sidestep that, and Postgres still plans an index
    scan for a parameterised tsquery.
    """
    compiled = statement.compile(dialect=postgresql.dialect(paramstyle="named"))
    # SET LOCAL, so it reverts with the surrounding transaction and cannot leak
    # into another test's planner.
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    raw = (
        await session.execute(text(f"EXPLAIN (FORMAT JSON) {compiled}"), dict(compiled.params))
    ).scalar_one()
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return dict(parsed[0]["Plan"])


@pytest.mark.parametrize("query", INDEXED_QUERIES)
async def test_the_filter_can_be_served_by_an_index(
    db_session: AsyncSession, query: JobSearchQuery
) -> None:
    statement = select(func.count()).select_from(Job).where(*build_filters(query))
    used = _index_nodes(await _plan(db_session, statement))
    assert used, f"no index node in the plan for {query.model_dump(exclude_none=True)}"


async def test_a_filter_on_an_unindexed_column_is_detectable(
    db_session: AsyncSession,
) -> None:
    """Non-vacuity. ``description_text`` has no index, and a LIKE with a
    leading wildcard could not use one anyway, so this plan must contain no
    index node — otherwise the assertions above would pass for anything."""
    statement = select(func.count()).select_from(Job).where(Job.description_text.like("%zzz%"))
    assert _index_nodes(await _plan(db_session, statement)) == []
