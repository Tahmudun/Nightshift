"""``board_poll_state`` — what polling knows about each board. M1d, ADR 0007.

The registry YAML stays the declarative source of *which* boards exist. This
table is runtime knowledge *about* them: the stored ETag, the tier, when the
board is next due. Two separate tables of knowledge, and the name is chosen so
they cannot be confused.

The uniqueness assertions are the point of this file. Two rows for one board
means two schedules, twice the requests against one provider, and — once
polling is queue-driven — two workers writing the same ETag over each other.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import BoardTier, SourceType
from nightshift.db.models import BoardPollState
from nightshift.db.types import utcnow
from nightshift.domain.ingestion import get_or_create_source
from tests.conftest import requires_db


# Applied per class rather than per module. The closed-set check on `BoardTier`
# is a pure assertion about a StrEnum — it needs neither a database nor an event
# loop, and a module-wide mark would file it as an async database test and warn
# on every run. `db_session` binds its asyncpg connection to conftest's
# session-scoped loop, so anything touching it must run on that loop too.
async def _source(session: AsyncSession, name: str = "ashby") -> object:
    return await get_or_create_source(
        session, name=name, source_type=SourceType.ATS_ASHBY, base_url="https://api.ashbyhq.com"
    )


def _state(source_id: object, *, ats: str = "ashby", token: str = "ramp", **kw: object) -> object:
    defaults: dict[str, object] = {
        "source_id": source_id,
        "ats": ats,
        "token": token,
        "tier": BoardTier.WARM,
        "parser_version": "1",
        "next_poll_at": utcnow(),
    }
    defaults.update(kw)
    return BoardPollState(**defaults)  # type: ignore[arg-type]


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestBoardIdentity:
    async def test_one_row_per_board(self, db_session: AsyncSession) -> None:
        """Two rows for one board means two schedules and double the requests
        against a provider that has been generous with unauthenticated access."""
        source = await _source(db_session)
        db_session.add(_state(source.id))  # type: ignore[attr-defined]
        await db_session.flush()

        db_session.add(_state(source.id))  # type: ignore[attr-defined]
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_the_same_token_on_two_providers_is_two_boards(
        self, db_session: AsyncSession
    ) -> None:
        """`ramp` on Ashby and `ramp` on Greenhouse are different employers'
        boards. Keying on the token alone would silently drop one of them —
        and which one you lose depends on insert order."""
        ashby = await _source(db_session, "ashby")
        greenhouse = await get_or_create_source(
            db_session, name="greenhouse", source_type=SourceType.ATS_GREENHOUSE
        )
        db_session.add(_state(ashby.id, ats="ashby", token="ramp"))  # type: ignore[attr-defined]
        db_session.add(  # type: ignore[attr-defined]
            _state(greenhouse.id, ats="greenhouse", token="ramp")
        )
        await db_session.flush()  # must not raise

        rows = (await db_session.execute(select(BoardPollState))).scalars().all()
        assert {(r.ats, r.token) for r in rows} == {("ashby", "ramp"), ("greenhouse", "ramp")}


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestScheduling:
    async def test_next_poll_at_rejects_a_naive_datetime(self, db_session: AsyncSession) -> None:
        """`UTCDateTime` guards the boundary. A naive timestamp here means a
        board scheduled in an unknown timezone, which is a board polled at the
        wrong hour or not at all."""
        source = await _source(db_session)
        db_session.add(_state(source.id, next_poll_at=datetime(2026, 8, 3)))  # noqa: DTZ001
        with pytest.raises((ValueError, StatementError, DBAPIError)):
            await db_session.flush()

    async def test_a_board_starts_warm(self, db_session: AsyncSession) -> None:
        """Hot is earned from ingested postings (ADR 0007), never assumed. A
        board defaulting to hourly would poll every discovered board 24x more
        than the design budgeted for."""
        source = await _source(db_session)
        state = BoardPollState(
            source_id=source.id,  # type: ignore[attr-defined]
            ats="ashby",
            token="ramp",
            parser_version="1",
            next_poll_at=utcnow(),
        )
        db_session.add(state)
        await db_session.flush()
        await db_session.refresh(state)

        assert state.tier is BoardTier.WARM

    async def test_failures_start_at_zero(self, db_session: AsyncSession) -> None:
        source = await _source(db_session)
        state = _state(source.id)  # type: ignore[attr-defined]
        db_session.add(state)
        await db_session.flush()
        await db_session.refresh(state)  # type: ignore[arg-type]

        assert state.consecutive_failures == 0  # type: ignore[attr-defined]

    async def test_due_boards_are_findable_by_next_poll_at(self, db_session: AsyncSession) -> None:
        """The scheduler's only query (design §7). Asserted here rather than
        only in the scheduler, because it is what the index exists for."""
        source = await _source(db_session)
        now = utcnow()
        db_session.add(_state(source.id, token="due", next_poll_at=now - timedelta(minutes=1)))  # type: ignore[attr-defined]
        db_session.add(_state(source.id, token="later", next_poll_at=now + timedelta(hours=1)))  # type: ignore[attr-defined]
        await db_session.flush()

        due = (
            (
                await db_session.execute(
                    select(BoardPollState).where(BoardPollState.next_poll_at <= now)
                )
            )
            .scalars()
            .all()
        )
        assert [r.token for r in due] == ["due"]


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestRevalidationState:
    async def test_a_board_may_have_no_etag_yet(self, db_session: AsyncSession) -> None:
        """A board nobody has polled has nothing to revalidate against, and NULL
        says that rather than an empty string pretending to be a value."""
        source = await _source(db_session)
        state = _state(source.id)  # type: ignore[attr-defined]
        db_session.add(state)
        await db_session.flush()

        assert state.etag is None  # type: ignore[attr-defined]

    async def test_an_etag_is_stored_with_the_parser_that_earned_it(
        self, db_session: AsyncSession
    ) -> None:
        """ADR 0007. A stored ETag is only valid for the parser version that
        earned it: a changed parser plus a stale ETag means the new parser never
        sees the payload it was written for, and the board silently stops being
        re-read for as long as the provider keeps answering 304."""
        source = await _source(db_session)
        state = _state(source.id, etag='W/"job-board:291499f3"', parser_version="1")  # type: ignore[attr-defined]
        db_session.add(state)
        await db_session.flush()
        await db_session.refresh(state)  # type: ignore[arg-type]

        assert state.etag == 'W/"job-board:291499f3"'  # type: ignore[attr-defined]
        assert state.parser_version == "1"  # type: ignore[attr-defined]

    async def test_a_long_provider_etag_fits(self, db_session: AsyncSession) -> None:
        """Ashby's is 78 characters and content-addressed; a column sized for
        Greenhouse's 34-character one would truncate it into a value that never
        matches, so every poll would be a full fetch and nothing would say why."""
        source = await _source(db_session)
        long_etag = 'W/"job-board:' + ("a" * 64) + '"'
        state = _state(source.id, etag=long_etag)  # type: ignore[attr-defined]
        db_session.add(state)
        await db_session.flush()
        await db_session.refresh(state)  # type: ignore[arg-type]

        assert state.etag == long_etag  # type: ignore[attr-defined]

    async def test_success_and_poll_times_are_tracked_separately(
        self, db_session: AsyncSession
    ) -> None:
        """A failing board is still polled. Collapsing these two would make
        "how long since this board actually answered" unanswerable, which is
        the one question the health page exists to answer."""
        source = await _source(db_session)
        polled = utcnow()
        succeeded = polled - timedelta(days=2)
        state = _state(  # type: ignore[attr-defined]
            source.id,
            last_polled_at=polled,
            last_success_at=succeeded,
            last_status=503,
            last_error="HTTP 503",
            consecutive_failures=4,
        )
        db_session.add(state)
        await db_session.flush()
        await db_session.refresh(state)  # type: ignore[arg-type]

        assert state.last_polled_at == polled  # type: ignore[attr-defined]
        assert state.last_success_at == succeeded  # type: ignore[attr-defined]
        assert state.last_status == 503  # type: ignore[attr-defined]
        assert state.consecutive_failures == 4  # type: ignore[attr-defined]


class TestTheEnum:
    """No database needed, so no database marks — see the note at the top."""

    def test_it_has_exactly_two_tiers(self) -> None:
        """ADR 0007 rejected a weekly tier explicitly: a company's first NYC
        posting could sit unseen for six days, which breaks the one promise the
        product makes. Adding a third member should mean reopening that ADR, so
        the closed set is asserted rather than assumed."""
        assert {t.value for t in BoardTier} == {"hot", "warm"}


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestTheEnumInTheDatabase:
    async def test_it_refuses_a_tier_that_is_not_one_of_them(
        self, db_session: AsyncSession
    ) -> None:
        """A PG enum, not a bare string (CLAUDE.md §7). A text column would
        accept "hourly" and then poll that board never — a board silently
        dropped out of the schedule with nothing to show for it."""
        source = await _source(db_session)
        db_session.add(_state(source.id, tier="weekly"))  # type: ignore[attr-defined]
        with pytest.raises((DBAPIError, LookupError, StatementError, ValueError)):
            await db_session.flush()
