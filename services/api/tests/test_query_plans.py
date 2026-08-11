"""Every supported filter is servable by an index.

Nothing here asserts "the plan has no Seq Scan" *as written by the planner on
its own terms*. On the seeded corpus Postgres chooses a sequential scan for
every query, because scanning tens of rows really is cheaper than an index
lookup — so a naked "no Seq Scan" assertion would fail on correct code, and its
inverse would pass on a table with no indexes at all. Both are useless.

Every query here therefore runs with ``enable_seqscan = off``, which makes the
planner prefer any usable index. Under that setting the two questions below
become answerable, and they are different questions asked in two different ways:

* **The job-search filters (M2a)** assert an index node appears at all. Those
  statements read one table, so "some index was used" is a real claim about the
  filter.
* **The queue sections (M2d)** assert their table is *not* sequentially scanned.
  They join three tables, so an index node always appears — the primary keys —
  and counting index nodes would be vacuous. Under ``enable_seqscan = off`` a
  sequential scan means no usable index exists, which is the same question
  phrased so that a join cannot answer it by accident. See
  ``test_no_queue_section_scans_its_table`` for why naming the expected index
  instead is worse.

Both forms have a non-vacuity guard beside them —
``test_a_filter_on_an_unindexed_column_is_detectable`` and
``test_a_sequential_scan_is_detectable``. Without those, either set would pass
for anything.
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


def _sequential_scans(node: dict[str, Any]) -> list[str]:
    """Every relation this plan reads by sequential scan, at any depth."""
    found: list[str] = []
    if node.get("Node Type") == "Seq Scan" and "Relation Name" in node:
        found.append(str(node["Relation Name"]))
    for child in node.get("Plans", []):
        found.extend(_sequential_scans(child))
    return found


#: The table whose *filter* each queue section depends on. `applications` is
#: excluded on purpose: it is the driving table and reading all of one user's
#: applications is what these queries are for.
QUEUE_TABLES: dict[QueueSectionKey, str] = {
    QueueSectionKey.FOLLOW_UP: "application_events",
    QueueSectionKey.INTERVIEWS_APPROACHING: "application_events",
    QueueSectionKey.STALE_SAVED: "application_events",
    QueueSectionKey.CLOSED_WHILE_SAVED: "jobs",
    # M3d Task 7. The filter is `jobs.seniority` and `jobs.first_seen_at`; the
    # driving table is `match_results`, which is this person's rows and is the
    # analogue of `applications` above.
    QueueSectionKey.BEST_NEW_INTERNSHIPS: "jobs",
}


@pytest.mark.parametrize("key", [pytest.param(key, id=key.value) for key in QueueSectionKey])
async def test_no_queue_section_scans_its_table(
    db_session: AsyncSession, key: QueueSectionKey
) -> None:
    """M2d. The queue runs on every page load and grows with the pipeline, so
    none of its four queries may fall back to reading a whole table.

    **This asserts a capability, not a plan.** Two weaker or stricter forms were
    tried first and both were wrong, which is why the shape is spelled out here:

    * ``assert _index_nodes(plan)`` — "some index was used" — is **vacuous**.
      Every queue statement joins ``jobs`` and ``companies``, so ``pk_jobs`` and
      ``pk_companies`` appear in all four plans whatever the filter does.
      Measured: with both M2d indexes dropped, all four plans still reported
      index nodes.
    * Naming the exact index per section is **brittle**, and it broke within the
      hour. ``interviews_approaching`` used ``ix_application_events_interviews``
      against one corpus and ``ix_application_events_application_id_occurred_at``
      against another a few applications larger — the planner switching from a
      time scan to a nested loop, which is it doing its job rather than a
      regression. Asserting the plan pins a decision that is not ours to make.

    With ``enable_seqscan = off`` a sequential scan means **no usable index
    exists**, which is the property that actually has to hold. It fails the day
    somebody filters on an unindexed column and survives the planner changing
    its mind.
    """
    statement = queue_selects(user_id=uuid.uuid4(), now=datetime(2026, 8, 4, tzinfo=UTC))[key]
    plan = await _plan(db_session, statement, literal_binds=True)
    scanned = _sequential_scans(plan)
    assert QUEUE_TABLES[key] not in scanned, (
        f"{key.value} reads all of {QUEUE_TABLES[key]}; scans: {scanned}. {json.dumps(plan)[:600]}"
    )


async def test_a_sequential_scan_is_detectable(db_session: AsyncSession) -> None:
    """Non-vacuity for the four above. ``description_text`` has no index and a
    leading-wildcard LIKE could not use one anyway, so this plan must contain
    the Seq Scan the assertions above forbid — otherwise they would pass for
    anything."""
    statement = select(func.count()).select_from(Job).where(Job.description_text.like("%zzz%"))
    assert "jobs" in _sequential_scans(await _plan(db_session, statement))
