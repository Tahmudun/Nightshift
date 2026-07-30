"""The fetch -> preserve -> normalize -> persist pipeline, against a real database.

Every test here needs Postgres, because the behaviour under test is
transactional: savepoints, unique constraints, FK ordering and idempotency are
not observable against a fake session. Run `make up && make migrate` first —
or, if Postgres is already up (as it is in this environment), the `db_engine`
fixture in conftest.py finds it itself; nothing here reads an env var to
decide whether to run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob
from nightshift.adapters.lever import LeverAdapter
from nightshift.db.base import JobStatus, SourceType
from nightshift.db.models import Company, Job, JobLocation, JobSourceLink, SourceJobRecord
from nightshift.domain.ingestion import (
    get_or_create_company,
    get_or_create_source,
    ingest_boards,
)
from tests.conftest import requires_db

# `db_session` binds its asyncpg connection on the session-scoped event loop
# (conftest.db_engine), because asyncpg connections cannot cross loops. Every
# test that uses it must therefore run on that same loop, or the connection
# raises "attached to a different loop" the instant it awaits.
pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

FIXTURES = Path(__file__).parent / "fixtures"
LEVER_BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)


class _StubAdapter:
    """A real adapter with its network call replaced by a recorded outcome.

    The adapter's own normalize() runs untouched — replacing that would be
    mocking the thing under test.
    """

    def __init__(self, inner: Any, outcome: FetchOutcome) -> None:
        self._inner = inner
        self._outcome = outcome
        self.source_name = inner.source_name
        self.source_type = inner.source_type

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        return self._outcome

    def normalize(self, raw_job: RawJob, board: BoardRef) -> Any:
        # JobSourceAdapter has exactly one normalize method (raw_job, board) —
        # there is no normalize_with_board on the Protocol.
        return self._inner.normalize(raw_job, board)


def _lever_outcome(ok: bool = True) -> FetchOutcome:
    payload = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    jobs = tuple(
        RawJob(
            source_job_id=str(j["id"]),
            source_company_key="alloy",
            canonical_url=j.get("hostedUrl"),
            payload=j,
        )
        for j in payload
    )
    if not ok:
        return FetchOutcome(board=LEVER_BOARD, ok=False, http_status=503, error="HTTP 503")
    return FetchOutcome(board=LEVER_BOARD, ok=True, jobs=jobs, http_status=200)


async def _count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def _ingest(session: AsyncSession, outcome: FetchOutcome) -> Any:
    source = await get_or_create_source(
        session, name="lever_test", source_type=SourceType.ATS_LEVER
    )
    adapter = _StubAdapter(LeverAdapter(client=None), outcome)
    return await ingest_boards(session, adapter, [LEVER_BOARD], source=source)


async def test_every_canonical_job_traces_to_a_raw_record(db_session: AsyncSession) -> None:
    """M1 acceptance criterion, asserted directly."""
    await _ingest(db_session, _lever_outcome())

    orphans = (
        await db_session.execute(
            select(func.count())
            .select_from(Job)
            .outerjoin(JobSourceLink, JobSourceLink.job_id == Job.id)
            .where(JobSourceLink.id.is_(None))
        )
    ).scalar_one()
    assert orphans == 0
    assert await _count(db_session, SourceJobRecord) == 9


async def test_reingestion_is_idempotent(db_session: AsyncSession) -> None:
    """M1 acceptance: no dupes, no spurious updates."""
    _, first = await _ingest(db_session, _lever_outcome())
    assert first.created == 9
    assert first.updated == 0

    jobs_after_first = await _count(db_session, Job)

    _, second = await _ingest(db_session, _lever_outcome())
    assert second.created == 0
    assert second.updated == 0, "a re-poll of unchanged data reported an update"
    assert second.unchanged == 9
    assert await _count(db_session, Job) == jobs_after_first


async def test_a_failed_board_closes_nothing(db_session: AsyncSession) -> None:
    """M1 acceptance: simulated source outage closes zero jobs (I3)."""
    await _ingest(db_session, _lever_outcome())
    open_before = int(
        (
            await db_session.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN)
            )
        ).scalar_one()
    )
    assert open_before == 9

    _, stats = await _ingest(db_session, _lever_outcome(ok=False))

    assert stats.closed == 0
    assert stats.boards_failed == ["alloy"]
    open_after = int(
        (
            await db_session.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN)
            )
        ).scalar_one()
    )
    assert open_after == open_before


async def test_multi_location_posting_yields_multiple_rows(db_session: AsyncSession) -> None:
    """A2 and an M1 acceptance criterion, end to end into the table."""
    await _ingest(db_session, _lever_outcome())
    per_job = (
        await db_session.execute(
            select(JobLocation.job_id, func.count()).group_by(JobLocation.job_id)
        )
    ).all()
    assert per_job
    assert max(count for _, count in per_job) >= 1
    assert await _count(db_session, JobLocation) >= 9


async def test_no_location_row_has_a_coordinate(db_session: AsyncSession) -> None:
    """I1 at the storage layer. Geocoding has not run, so nothing is placed."""
    await _ingest(db_session, _lever_outcome())
    placed = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(JobLocation)
                .where(JobLocation.latitude.is_not(None))
            )
        ).scalar_one()
    )
    assert placed == 0


async def test_repeated_company_creation_does_not_duplicate(db_session: AsyncSession) -> None:
    """Task 8's upsert, exercised through the name variants that must merge.

    test_companies.py proves normalize_company_name folds these together; this
    proves the insert path honours it rather than raising on the unique index.
    """
    for name in ("Moody's Analytics", "Moodys Analytics", "MOODY'S ANALYTICS"):
        await get_or_create_company(db_session, name)
    await db_session.flush()
    assert await _count(db_session, Company) == 1


async def test_a_posting_that_fails_to_persist_does_not_abort_the_board(
    db_session: AsyncSession,
) -> None:
    """The savepoint in _persist_outcome, proven by making one posting fail.

    Without the savepoint the failed statement poisons the transaction and
    every posting after it in the board fails too — so this asserts the
    survivors, not just the failure count.
    """
    outcome = _lever_outcome()
    broken = outcome.jobs[0].model_copy(update={"payload": {**outcome.jobs[0].payload, "text": ""}})
    outcome = outcome.model_copy(update={"jobs": (broken, *outcome.jobs[1:])})

    _, stats = await _ingest(db_session, outcome)

    assert stats.failed == 1
    assert stats.created == 8
    assert await _count(db_session, Job) == 8


async def test_ingestion_run_records_the_failure(db_session: AsyncSession) -> None:
    """M1 acceptance: ingestion failures are visible, not only in logs."""
    run, _ = await _ingest(db_session, _lever_outcome(ok=False))
    assert run.error_summary is not None
    assert "alloy" in run.error_summary
    assert run.records_closed == 0
