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
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import EmploymentType, JobStatus, RemotePolicy
from nightshift.db.models import Job
from nightshift.domain.queue import QueueSectionKey, queue_selects
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


async def _plan(
    session: AsyncSession, statement: Any, *, literal_binds: bool = False
) -> dict[str, Any]:
    """EXPLAIN this statement with sequential scans discouraged.

    The job-search statements are compiled with ``paramstyle="named"`` and the
    parameters passed through, rather than with ``literal_binds``. Literal
    binding cannot render every type: ``websearch_to_tsquery``'s first argument
    is a ``REGCONFIG``, and SQLAlchemy raises ``CompileError: No literal value
    renderer is available`` on it. Named parameters sidestep that, and Postgres
    still plans an index scan for a parameterised tsquery.

    **The queue statements need the opposite** (``literal_binds=True``), and
    both halves of the reason are real rather than a preference:

    * a UUID parameter renders as ``:user_id_1::UUID``, and feeding that back
      through ``text()`` is a Postgres syntax error at the second colon;
    * ``current_stage NOT IN (...)`` compiles to ``__[POSTCOMPILE_...]``, which
      is expanded at execution time and is not valid SQL on its own.

    Neither statement contains a ``tsquery``, so the constraint that forced
    named parameters on the search queries does not apply to them.
    """
    dialect = postgresql.dialect(paramstyle="named")
    if literal_binds:
        compiled = statement.compile(dialect=dialect, compile_kwargs={"literal_binds": True})
        params: dict[str, Any] = {}
    else:
        compiled = statement.compile(dialect=dialect)
        params = dict(compiled.params)
    # SET LOCAL, so it reverts with the surrounding transaction and cannot leak
    # into another test's planner.
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    raw = (await session.execute(text(f"EXPLAIN (FORMAT JSON) {compiled}"), params)).scalar_one()
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


#: The index each queue section exists to be served by, named rather than
#: implied. **"Some index was used" is not good enough here**, and that is not a
#: hypothetical: every queue statement joins ``jobs`` and ``companies``, so
#: ``pk_jobs`` and ``pk_companies`` appear in all four plans no matter what the
#: filter does. An assertion that only checked for a non-empty index list would
#: have passed with both M2d indexes deleted — measured, not assumed.
QUEUE_INDEXES: dict[QueueSectionKey, str] = {
    QueueSectionKey.FOLLOW_UP: "ix_application_events_user_activity",
    QueueSectionKey.INTERVIEWS_APPROACHING: "ix_application_events_interviews",
    QueueSectionKey.STALE_SAVED: "ix_application_events_user_activity",
    QueueSectionKey.CLOSED_WHILE_SAVED: "ix_jobs_status_last_seen_at",
}


@pytest.mark.parametrize("key", [pytest.param(key, id=key.value) for key in QueueSectionKey])
async def test_every_queue_section_uses_the_index_it_was_given(
    db_session: AsyncSession, key: QueueSectionKey
) -> None:
    """M2d. The queue runs on every page load and grows with the user's
    pipeline, so each of its four queries must be servable by an index — and by
    the specific one that exists for it."""
    statement = queue_selects(user_id=uuid.uuid4(), now=datetime(2026, 8, 4, tzinfo=UTC))[key]
    plan = await _plan(db_session, statement, literal_binds=True)
    used = _index_nodes(plan)
    assert QUEUE_INDEXES[key] in used, (
        f"{key.value} did not use {QUEUE_INDEXES[key]}; it used {used}. {json.dumps(plan)[:600]}"
    )
