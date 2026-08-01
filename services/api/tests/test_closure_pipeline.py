"""Closure against a real database.

The load-bearing test here is ``test_a_failed_board_does_not_increment_a_miss``.
I3 is usually stated as "an outage closes nothing", but the way it actually
breaks is subtler than a wrong status: an outage that quietly increments a miss
counter closes jobs three polls later, and by then nothing in the data says
why. Asserting the status alone would pass while that bug shipped.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, NormalizedSourceJob, RawJob
from nightshift.adapters.lever import LeverAdapter
from nightshift.db.base import JobStatus, SourceStatus, SourceType
from nightshift.db.models import Job, JobStatusEvent, SourceJobRecord
from nightshift.domain.ingestion import IngestionStats, get_or_create_source, ingest_boards
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

FIXTURES = Path(__file__).parent / "fixtures"
BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)
BOARD_JOB_COUNT = 9


def _payload() -> list[dict[str, Any]]:
    return json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())


class _StubAdapter:
    """The real adapter with only its network call replaced.

    ``normalize`` is the real implementation — replacing that would be mocking
    the thing under test. Only ``fetch_board`` is swapped, which is the network
    boundary a unit test is entitled to replace.
    """

    def __init__(self, outcome: FetchOutcome) -> None:
        self._inner = LeverAdapter(client=None)
        self._outcome = outcome
        self.source_name = self._inner.source_name
        self.source_type = self._inner.source_type

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        return self._outcome

    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
        return self._inner.normalize(raw_job, board)


def _outcome(jobs: list[dict[str, Any]], *, ok: bool = True) -> FetchOutcome:
    if not ok:
        return FetchOutcome(board=BOARD, ok=False, http_status=503, error="HTTP 503")
    return FetchOutcome(
        board=BOARD,
        ok=True,
        http_status=200,
        jobs=tuple(
            RawJob(
                source_job_id=str(j["id"]),
                source_company_key="alloy",
                canonical_url=j.get("hostedUrl"),
                payload=j,
            )
            for j in jobs
        ),
    )


async def _poll(
    session: AsyncSession, outcome: FetchOutcome, now: datetime
) -> tuple[Any, IngestionStats]:
    source = await get_or_create_source(
        session, name="lever_closure_test", source_type=SourceType.ATS_LEVER
    )
    return await ingest_boards(session, _StubAdapter(outcome), [BOARD], source=source, now=now)


async def _status_counts(session: AsyncSession) -> dict[JobStatus, int]:
    rows = (await session.execute(select(Job.status, func.count()).group_by(Job.status))).all()
    return dict(rows)  # type: ignore[arg-type]


async def _misses(session: AsyncSession) -> set[int]:
    return set((await session.execute(select(SourceJobRecord.consecutive_misses))).scalars().all())


START = datetime(2026, 8, 1, tzinfo=UTC)


async def test_a_job_still_listed_stays_open(db_session: AsyncSession) -> None:
    await _poll(db_session, _outcome(_payload()), START)
    await _poll(db_session, _outcome(_payload()), START + timedelta(days=1))
    assert await _status_counts(db_session) == {JobStatus.OPEN: BOARD_JOB_COUNT}
    assert await _misses(db_session) == {0}


async def test_a_failed_board_does_not_increment_a_miss(db_session: AsyncSession) -> None:
    """I3, at the counter rather than at the status.

    A failed fetch that bumps the miss count closes jobs three polls later,
    which looks like a closure rule working correctly and is not. Five failed
    polls here is well past every threshold in ADR 0009.
    """
    await _poll(db_session, _outcome(_payload()), START)

    for day in range(1, 6):
        await _poll(db_session, _outcome([], ok=False), START + timedelta(days=day))

    assert await _misses(db_session) == {0}
    assert await _status_counts(db_session) == {JobStatus.OPEN: BOARD_JOB_COUNT}


async def test_a_failed_board_closes_nothing_even_after_a_real_absence(
    db_session: AsyncSession,
) -> None:
    """The combination that catches a counter which is only conditionally safe:
    three genuine misses, then an outage. The outage must not be the poll that
    tips the job over the seven-day line."""
    await _poll(db_session, _outcome(_payload()), START)
    for day in (1, 2, 3):
        await _poll(db_session, _outcome([]), START + timedelta(days=day))
    assert await _status_counts(db_session) == {JobStatus.POSSIBLY_STALE: BOARD_JOB_COUNT}

    _, stats = await _poll(db_session, _outcome([], ok=False), START + timedelta(days=10))
    assert stats.closed == 0
    assert await _status_counts(db_session) == {JobStatus.POSSIBLY_STALE: BOARD_JOB_COUNT}


async def test_an_empty_but_live_board_does_increment(db_session: AsyncSession) -> None:
    """The other side of I3. A live board returning [] is real evidence.

    M1a recorded the plaid empty board as its own fixture precisely so this
    branch is distinguishable from the 404 one, and this is the test that makes
    that distinction pay.
    """
    await _poll(db_session, _outcome(_payload()), START)
    await _poll(db_session, _outcome([]), START + timedelta(days=1))
    assert await _misses(db_session) == {1}


async def test_a_missing_record_is_marked_missing(db_session: AsyncSession) -> None:
    await _poll(db_session, _outcome(_payload()), START)
    await _poll(db_session, _outcome([]), START + timedelta(days=1))
    statuses = set(
        (await db_session.execute(select(SourceJobRecord.source_status))).scalars().all()
    )
    assert statuses == {SourceStatus.MISSING}


async def test_three_misses_makes_a_job_stale_not_closed(db_session: AsyncSession) -> None:
    await _poll(db_session, _outcome(_payload()), START)
    for day in (1, 2, 3):
        await _poll(db_session, _outcome([]), START + timedelta(days=day))
    assert await _status_counts(db_session) == {JobStatus.POSSIBLY_STALE: BOARD_JOB_COUNT}
    closed_at = (await db_session.execute(select(Job.closed_at))).scalars().all()
    assert set(closed_at) == {None}


async def test_seven_days_of_absence_closes(db_session: AsyncSession) -> None:
    await _poll(db_session, _outcome(_payload()), START)
    for day in (1, 2, 3, 7):
        await _poll(db_session, _outcome([]), START + timedelta(days=day))

    assert await _status_counts(db_session) == {JobStatus.CLOSED: BOARD_JOB_COUNT}
    jobs = (await db_session.execute(select(Job))).scalars().all()
    for job in jobs:
        assert job.closed_at is not None


async def test_closing_is_recorded_in_the_run(db_session: AsyncSession) -> None:
    """M1 acceptance: ingestion outcomes are visible in data, not only logs."""
    await _poll(db_session, _outcome(_payload()), START)
    for day in (1, 2, 3):
        await _poll(db_session, _outcome([]), START + timedelta(days=day))
    run, stats = await _poll(db_session, _outcome([]), START + timedelta(days=7))
    assert stats.closed == BOARD_JOB_COUNT
    assert run.records_closed == BOARD_JOB_COUNT


async def test_a_reappearing_job_reopens_and_keeps_its_history(
    db_session: AsyncSession,
) -> None:
    """Reposts are ordinary, so reopening is permitted — and the history has to
    survive it. This is the entire reason job_status_events exists: reopening
    nulls closed_at, so the column that showed the closure is gone."""
    await _poll(db_session, _outcome(_payload()), START)
    for day in (1, 2, 3, 7):
        await _poll(db_session, _outcome([]), START + timedelta(days=day))
    await _poll(db_session, _outcome(_payload()), START + timedelta(days=8))

    assert await _status_counts(db_session) == {JobStatus.OPEN: BOARD_JOB_COUNT}
    for job in (await db_session.execute(select(Job))).scalars().all():
        assert job.closed_at is None

    closures = (
        await db_session.execute(
            select(func.count())
            .select_from(JobStatusEvent)
            .where(JobStatusEvent.to_status == JobStatus.CLOSED)
        )
    ).scalar_one()
    assert closures == BOARD_JOB_COUNT


async def test_a_transition_writes_an_event_with_a_readable_reason(
    db_session: AsyncSession,
) -> None:
    await _poll(db_session, _outcome(_payload()), START)
    for day in (1, 2, 3):
        await _poll(db_session, _outcome([]), START + timedelta(days=day))

    events = (
        (
            await db_session.execute(
                select(JobStatusEvent).where(JobStatusEvent.to_status == JobStatus.POSSIBLY_STALE)
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == BOARD_JOB_COUNT
    for event in events:
        assert event.from_status is JobStatus.OPEN
        assert "consecutive polls" in event.reason
        assert event.ingestion_run_id is not None
        assert event.observed_misses == 3


async def test_a_no_op_poll_writes_no_event(db_session: AsyncSession) -> None:
    """A job that was open and is still open has not transitioned. Writing a
    row per poll would bury the real transitions under thousands of no-ops."""
    await _poll(db_session, _outcome(_payload()), START)
    before = (
        await db_session.execute(select(func.count()).select_from(JobStatusEvent))
    ).scalar_one()

    await _poll(db_session, _outcome(_payload()), START + timedelta(days=1))
    after = (
        await db_session.execute(select(func.count()).select_from(JobStatusEvent))
    ).scalar_one()
    assert after == before
