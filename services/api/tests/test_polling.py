"""One board's poll cycle, and the scheduler that decides when it happens.

ADR 0007 and ``docs/architecture/conditional-polling.md`` §7.

The shape is ``next_poll_at`` on the board row, drained by a small cron, rather
than a cron per tier. Boards drift apart instead of stampeding at ``:00``,
per-board backoff has somewhere to live, "what is overdue" is a query the
coverage page already needs, and the state survives a worker restart because it
is in Postgres rather than in the queue.

The load-bearing test here is ``test_a_304_writes_no_job_state``. It is M1
criterion 13 at the level a human runs it, and it asserts row counts and miss
counters before and after rather than reading a log line.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, ListedPosting, RawJob
from nightshift.config import get_settings
from nightshift.db.base import BoardTier, JobStatus, SourceType
from nightshift.db.models import (
    BoardPollState,
    Job,
    JobEmbedding,
    JobLocation,
    JobSourceLink,
    JobStatusEvent,
    SourceJobRecord,
)
from nightshift.db.types import utcnow
from nightshift.domain.polling import (
    due_boards,
    failure_backoff,
    next_interval,
    poll_one_board,
    sync_board_poll_state,
)
from tests.conftest import requires_db


class TestIntervals:
    """Pure functions. No database, no event loop."""

    def test_hot_is_hourly_and_warm_is_daily(self) -> None:
        assert next_interval(BoardTier.HOT) == timedelta(hours=1)
        assert next_interval(BoardTier.WARM) == timedelta(days=1)

    def test_hot_is_polled_more_often_than_warm(self) -> None:
        """The relationship, not just the numbers. Getting these the wrong way
        round would poll 2,600 long-tail boards hourly and the handful of
        interesting ones daily — the exact inversion ADR 0007 budgets against."""
        assert next_interval(BoardTier.HOT) < next_interval(BoardTier.WARM)

    def test_backoff_grows_and_then_stops(self) -> None:
        assert failure_backoff(0) == timedelta(minutes=15)
        assert failure_backoff(1) == timedelta(minutes=30)
        assert failure_backoff(2) == timedelta(hours=1)
        assert failure_backoff(50) == timedelta(hours=24)

    def test_backoff_never_returns_zero(self) -> None:
        """A zero backoff is a hot loop against a provider that is already
        failing, which is the retry storm §7.3 forbids — self-inflicted."""
        assert all(failure_backoff(n) > timedelta(0) for n in range(0, 60))

    def test_backoff_ceiling_matches_the_warm_tier(self) -> None:
        """A dead board must stop costing requests without falling out of the
        system. At the ceiling it is polled exactly as often as a live long-tail
        board, so recovery is noticed within a day."""
        assert failure_backoff(99) == next_interval(BoardTier.WARM)

    def test_backoff_does_not_overflow_on_a_long_outage(self) -> None:
        """2**500 is a perfectly good Python int and a perfectly terrible
        timedelta. A board that has failed for months must not raise here."""
        assert failure_backoff(500) == timedelta(seconds=get_settings().poll_backoff_max_seconds)


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestSyncingFromTheRegistry:
    async def test_it_creates_a_row_for_every_pollable_board(
        self, db_session: AsyncSession
    ) -> None:
        created = await sync_board_poll_state(db_session, now=utcnow())
        await db_session.flush()

        rows = (await db_session.execute(select(BoardPollState))).scalars().all()
        assert created == len(rows)
        assert ("greenhouse", "datadog") in {(r.ats, r.token) for r in rows}

    async def test_a_disabled_board_gets_no_row(self, db_session: AsyncSession) -> None:
        """Stripe sits at `status: disabled` pending exactly this milestone. A
        poll-state row for it would poll it, which is the one thing the human
        who disabled it asked not to happen."""
        await sync_board_poll_state(db_session, now=utcnow())
        await db_session.flush()

        rows = (await db_session.execute(select(BoardPollState))).scalars().all()
        assert ("greenhouse", "stripe") not in {(r.ats, r.token) for r in rows}

    async def test_it_is_idempotent(self, db_session: AsyncSession) -> None:
        """Runs on every scheduler tick, so it must not duplicate rows — and
        must not reset a schedule, which would mean a board polled every tick
        forever."""
        now = utcnow()
        await sync_board_poll_state(db_session, now=now)
        await db_session.flush()
        first = (await db_session.execute(select(BoardPollState))).scalars().all()
        for row in first:
            row.next_poll_at = now + timedelta(hours=5)
        await db_session.flush()

        created = await sync_board_poll_state(db_session, now=now)
        await db_session.flush()
        second = (await db_session.execute(select(BoardPollState))).scalars().all()

        assert created == 0
        assert len(second) == len(first)
        assert all(r.next_poll_at == now + timedelta(hours=5) for r in second)

    async def test_a_new_board_is_due_immediately(self, db_session: AsyncSession) -> None:
        """A board a human just approved should be polled on the next tick, not
        a day later."""
        now = utcnow()
        await sync_board_poll_state(db_session, now=now)
        await db_session.flush()

        rows = (await db_session.execute(select(BoardPollState))).scalars().all()
        assert all(r.next_poll_at <= now for r in rows)

    async def test_it_records_the_parser_that_will_poll_the_board(
        self, db_session: AsyncSession
    ) -> None:
        await sync_board_poll_state(db_session, now=utcnow())
        await db_session.flush()

        rows = (await db_session.execute(select(BoardPollState))).scalars().all()
        assert all(r.parser_version for r in rows)


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestDueBoards:
    async def test_only_overdue_boards_are_returned(self, db_session: AsyncSession) -> None:
        now = utcnow()
        await _a_board(db_session, token="due", next_poll_at=now - timedelta(minutes=1))
        await _a_board(db_session, token="notdue", next_poll_at=now + timedelta(hours=1))
        await db_session.flush()

        due = await due_boards(db_session, now=now)
        assert [b.token for b in due] == ["due"]

    async def test_the_longest_overdue_go_first(self, db_session: AsyncSession) -> None:
        """Ordering is what stops a board starving under a batch cap: without
        it, the same arbitrary subset is drained every tick and the rest wait
        forever."""
        now = utcnow()
        for n in (1, 5, 3):
            await _a_board(db_session, token=f"b{n}", next_poll_at=now - timedelta(hours=n))
        await db_session.flush()

        due = await due_boards(db_session, now=now)
        assert [b.token for b in due] == ["b5", "b3", "b1"]

    async def test_the_batch_limit_is_honoured(self, db_session: AsyncSession) -> None:
        """A scheduler waking after an outage finds everything overdue. Without
        a cap it queues the whole registry at once, which is the stampede
        `next_poll_at` was chosen to avoid, reintroduced by the recovery path."""
        now = utcnow()
        for n in range(10):
            await _a_board(db_session, token=f"b{n}", next_poll_at=now - timedelta(minutes=n + 1))
        await db_session.flush()

        due = await due_boards(db_session, now=now, limit=3)
        assert len(due) == 3
        assert [b.token for b in due] == ["b9", "b8", "b7"]


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestThePollCycle:
    async def test_a_304_writes_no_job_state(self, db_session: AsyncSession) -> None:
        """M1 criterion 13, at the level a human runs it.

        Asserted by counting rows and summing miss counters before and after,
        not by reading a log line. The board's own bookkeeping row *does* move
        — that is the point of polling — and it is excluded deliberately, which
        is why the criterion is claimed as "zero writes to job state" rather
        than "zero writes".
        """
        state = await _a_board(db_session, token="datadog", etag='W/"abc"')
        await db_session.flush()
        before = await _job_state_snapshot(db_session)

        now = utcnow()
        result = await poll_one_board(
            db_session,
            _adapter_returning(_not_modified()),
            ats="greenhouse",
            token="datadog",
            now=now,
        )

        assert result.last_status == 304
        assert result.etag == 'W/"abc"', "a 304 leaves the ETag that earned it in place"
        assert result.consecutive_failures == 0
        assert result.last_success_at == now
        assert result.last_polled_at == now
        assert result.next_poll_at == now + next_interval(state.tier)
        assert await _job_state_snapshot(db_session) == before

    async def test_a_failure_backs_off_and_closes_nothing(self, db_session: AsyncSession) -> None:
        """I3 at board level. A provider outage must cost requests, not jobs."""
        await _a_board(db_session, token="datadog")
        await db_session.flush()
        before = await _job_state_snapshot(db_session)

        now = utcnow()
        result = await poll_one_board(
            db_session,
            _adapter_returning(_failed()),
            ats="greenhouse",
            token="datadog",
            now=now,
        )

        assert result.consecutive_failures == 1
        assert result.last_error is not None
        assert result.last_success_at is None
        assert result.last_polled_at == now
        assert result.next_poll_at == now + failure_backoff(0)
        assert await _job_state_snapshot(db_session) == before

    async def test_repeated_failures_back_off_further_each_time(
        self, db_session: AsyncSession
    ) -> None:
        await _a_board(db_session, token="datadog", consecutive_failures=2)
        await db_session.flush()

        now = utcnow()
        result = await poll_one_board(
            db_session,
            _adapter_returning(_failed()),
            ats="greenhouse",
            token="datadog",
            now=now,
        )

        assert result.consecutive_failures == 3
        assert result.next_poll_at == now + failure_backoff(2)

    async def test_a_success_clears_a_previous_failure(self, db_session: AsyncSession) -> None:
        """A board that comes back must return to its normal cadence rather
        than staying at the backoff ceiling because of an old outage."""
        await _a_board(db_session, token="datadog", consecutive_failures=5, last_error="HTTP 503")
        await db_session.flush()

        now = utcnow()
        result = await poll_one_board(
            db_session,
            _adapter_returning(_not_modified()),
            ats="greenhouse",
            token="datadog",
            now=now,
        )

        assert result.consecutive_failures == 0
        assert result.last_error is None
        assert result.next_poll_at == now + next_interval(BoardTier.WARM)

    async def test_a_stale_parser_version_discards_the_stored_etag(
        self, db_session: AsyncSession
    ) -> None:
        """ADR 0007. A changed parser plus a stale ETag means the new parser
        never sees the payload it was written for — and because the provider
        keeps answering 304, nothing anywhere reports a problem."""
        await _a_board(db_session, token="datadog", etag='W/"abc"', parser_version="0")
        await db_session.flush()

        adapter = _adapter_returning(_listing())
        await poll_one_board(db_session, adapter, ats="greenhouse", token="datadog", now=utcnow())

        assert adapter.seen_etags == [None], "a stale ETag must not be sent"

    async def test_a_current_parser_version_keeps_the_etag(self, db_session: AsyncSession) -> None:
        await _a_board(db_session, token="datadog", etag='W/"abc"', parser_version="1")
        await db_session.flush()

        adapter = _adapter_returning(_listing())
        await poll_one_board(db_session, adapter, ats="greenhouse", token="datadog", now=utcnow())

        assert adapter.seen_etags == ['W/"abc"']

    async def test_a_new_etag_is_stored_for_the_next_poll(self, db_session: AsyncSession) -> None:
        await _a_board(db_session, token="datadog", parser_version="1")
        await db_session.flush()

        result = await poll_one_board(
            db_session,
            _adapter_returning(_listing(etag='W/"fresh"')),
            ats="greenhouse",
            token="datadog",
            now=utcnow(),
        )

        assert result.etag == 'W/"fresh"'
        assert result.parser_version == "1"

    async def test_a_stale_parser_version_is_refreshed_after_a_successful_poll(
        self, db_session: AsyncSession
    ) -> None:
        """Otherwise the ETag is discarded on every poll forever, and the
        board never gets the cheap path back."""
        await _a_board(db_session, token="datadog", etag='W/"abc"', parser_version="0")
        await db_session.flush()

        result = await poll_one_board(
            db_session,
            _adapter_returning(_listing(etag='W/"fresh"')),
            ats="greenhouse",
            token="datadog",
            now=utcnow(),
        )

        assert result.parser_version == "1"
        assert result.etag == 'W/"fresh"'

    async def test_polling_an_unknown_board_is_an_error_not_a_silent_no_op(
        self, db_session: AsyncSession
    ) -> None:
        """A queued job naming a board with no row means the registry and the
        queue disagree. Silently returning would drop that poll forever."""
        with pytest.raises(LookupError):
            await poll_one_board(
                db_session,
                _adapter_returning(_listing()),
                ats="greenhouse",
                token="never-heard-of-it",
                now=utcnow(),
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BOARD = BoardRef(company="Acme", ats="greenhouse", token="datadog")


def _not_modified() -> FetchOutcome:
    return FetchOutcome(board=BOARD, ok=True, not_modified=True, etag='W/"abc"', http_status=304)


def _failed() -> FetchOutcome:
    return FetchOutcome(board=BOARD, ok=False, http_status=503, error="HTTP 503")


def _listing(*, etag: str | None = 'W/"fresh"') -> FetchOutcome:
    return FetchOutcome(
        board=BOARD,
        ok=True,
        listed=(ListedPosting(source_job_id="1"),),
        etag=etag,
        http_status=200,
    )


class _StubAdapter:
    """Stands in for a real adapter. Records the ETag it was handed.

    Single-phase: `fetch_postings` is never reached, and asserting on
    `seen_etags` rather than only on the stored result is what makes the
    parser-version tests non-vacuous.
    """

    source_name = "greenhouse"
    source_type = SourceType.ATS_GREENHOUSE
    parser_version = "1"
    is_two_phase = False

    def __init__(self, outcome: FetchOutcome) -> None:
        self._outcome = outcome
        self.seen_etags: list[str | None] = []

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        self.seen_etags.append(etag)
        return self._outcome

    def normalize(self, raw_job: RawJob, board: BoardRef) -> object:
        raise AssertionError("no postings are fetched in these tests")


def _adapter_returning(outcome: FetchOutcome) -> _StubAdapter:
    return _StubAdapter(outcome)


async def _a_board(
    session: AsyncSession,
    *,
    token: str,
    next_poll_at: object = None,
    **kw: object,
) -> BoardPollState:
    from nightshift.domain.ingestion import get_or_create_source

    source = await get_or_create_source(
        session, name="greenhouse", source_type=SourceType.ATS_GREENHOUSE
    )
    defaults: dict[str, object] = {
        "source_id": source.id,
        "ats": "greenhouse",
        "token": token,
        "parser_version": "1",
        "tier": BoardTier.WARM,
        "next_poll_at": next_poll_at or utcnow(),
    }
    defaults.update(kw)
    state = BoardPollState(**defaults)  # type: ignore[arg-type]
    session.add(state)
    await session.flush()
    return state


async def _job_state_snapshot(session: AsyncSession) -> tuple[int, ...]:
    """Everything a poll must not touch when it answers 304.

    Row counts alone are insufficient: a regression that increments every miss
    counter changes no count at all, and closure is three polls away. So the
    miss sum and the closed count are part of the snapshot.
    """
    counts: list[int] = []
    for model in (
        SourceJobRecord,
        Job,
        JobLocation,
        JobSourceLink,
        JobStatusEvent,
        JobEmbedding,
    ):
        counts.append(
            int((await session.execute(select(func.count()).select_from(model))).scalar_one())
        )
    counts.append(
        int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(SourceJobRecord.consecutive_misses), 0))
                )
            ).scalar_one()
        )
    )
    counts.append(
        int(
            (
                await session.execute(
                    select(func.count()).select_from(Job).where(Job.status == JobStatus.CLOSED)
                )
            ).scalar_one()
        )
    )
    return tuple(counts)


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestTierIsRecomputedByThePoll:
    """The tier has to be updated by something, and the poll is the only thing
    that knows the postings just changed."""

    async def test_a_304_does_not_recompute_the_tier(self, db_session: AsyncSession) -> None:
        """Nothing changed, so the postings the tier derives from cannot have
        changed either. Recomputing would be a join per board per poll, bought
        for no possible difference in the answer."""
        await _a_board(db_session, token="datadog", tier=BoardTier.HOT)
        await db_session.flush()

        result = await poll_one_board(
            db_session,
            _adapter_returning(_not_modified()),
            ats="greenhouse",
            token="datadog",
            now=utcnow(),
        )

        assert result.tier is BoardTier.HOT, "a 304 must leave the tier alone"

    async def test_a_200_recomputes_the_tier(self, db_session: AsyncSession) -> None:
        """A board with no NYC postings demotes on its next real poll, even if
        it was hot before — which is the direction that keeps the hot tier from
        growing to contain everything."""
        await _a_board(db_session, token="datadog", tier=BoardTier.HOT)
        await db_session.flush()

        result = await poll_one_board(
            db_session,
            _adapter_returning(_listing()),
            ats="greenhouse",
            token="datadog",
            now=utcnow(),
        )

        assert result.tier is BoardTier.WARM

    async def test_the_new_tier_decides_the_next_interval(self, db_session: AsyncSession) -> None:
        """Recomputed *before* next_poll_at, so a board promoted by this poll
        starts behaving like a hot board now rather than a day from now."""
        await _a_board(db_session, token="datadog", tier=BoardTier.HOT)
        await db_session.flush()

        now = utcnow()
        result = await poll_one_board(
            db_session,
            _adapter_returning(_listing()),
            ats="greenhouse",
            token="datadog",
            now=now,
        )

        assert result.tier is BoardTier.WARM
        assert result.next_poll_at == now + next_interval(BoardTier.WARM), (
            "the interval must follow the tier this poll just derived, not the one "
            "the board arrived with"
        )
