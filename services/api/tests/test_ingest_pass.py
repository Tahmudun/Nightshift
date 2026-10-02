"""`make ingest`: one pass over every pollable board, through the scheduler's path.

Until 2026-10-02 the command hardcoded ``pollable(ats="greenhouse")`` and reached
2 of the 23 registered boards (PROGRESS, 2026-08-24): the registry is mostly
Ashby, and two of the three adapters M1 built had no live CLI entry point. The
properties a pass has to keep, each tested here:

* **every ATS** in the registry is polled, through ``poll_one_board``, so
  ``board_poll_state`` is read and written exactly as a scheduler tick would;
* **one client** serves the whole pass, because the rate limiter lives in the
  client and a client per board would start every board with a fresh one;
* **one transaction per board**, and a board that fails, or that the registry
  and the poll-state table disagree about, is reported without ending the pass.

The command layer is tested with its I/O replaced, so it never reaches a live
board, whatever the developer's ``.env`` says about outbound HTTP.
"""

from __future__ import annotations

import argparse
from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift import cli
from nightshift.adapters.base import BoardRef, FetchOutcome, JobSourceAdapter, RawJob
from nightshift.adapters.http import PoliteClient
from nightshift.db.base import BoardTier, SourceType
from nightshift.db.models import BoardPollState
from nightshift.db.types import utcnow
from nightshift.domain.polling import BoardPollReport, poll_every_board, sync_board_poll_state
from nightshift.domain.registry import get_registry
from tests.conftest import make_settings, requires_db

# Real registry boards, one per ATS, plus a second Ashby one.
DATADOG = ("greenhouse", "datadog")
ALLOY = ("lever", "alloy")
RAMP = ("ashby", "ramp")
A16Z = ("ashby", "a16z-new-media")


class _Stub:
    """An adapter that answers every board with a fixed outcome, and records them.

    Answers ``304`` by default, so no posting is ever fetched or normalized: a
    pass's bookkeeping is what is under test, not ingestion.
    """

    parser_version = "1"
    is_two_phase = False

    def __init__(self, ats: str, *, failing: frozenset[str] = frozenset()) -> None:
        self.source_name = ats
        self.source_type = SourceType.ATS_GREENHOUSE
        self._failing = failing
        self.seen: list[str] = []

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        self.seen.append(board.token)
        if board.token in self._failing:
            return FetchOutcome(board=board, ok=False, http_status=503, error="HTTP 503")
        return FetchOutcome(
            board=board, ok=True, not_modified=True, etag='W/"same"', http_status=304
        )

    def normalize(self, raw_job: RawJob, board: BoardRef) -> object:
        raise AssertionError("a 304 fetches no postings")


class _Factory:
    """Stands in for ``adapter_for``: one stub per ATS, and the client each was given."""

    def __init__(self, *, failing: frozenset[str] = frozenset()) -> None:
        self._failing = failing
        self.stubs: dict[str, _Stub] = {}
        self.calls: list[tuple[str, object]] = []

    def __call__(self, ats: str, client: PoliteClient) -> JobSourceAdapter:
        self.calls.append((ats, client))
        self.stubs[ats] = _Stub(ats, failing=self._failing)
        return cast(JobSourceAdapter, self.stubs[ats])


def _scopes(session: AsyncSession) -> tuple[list[int], Any]:
    """A ``session_scope`` over the test's session, one savepoint per board.

    The savepoint gives each board the commit-or-roll-back behaviour of the real
    ``session_scope`` without leaving the test's outer transaction, and the
    counter is how a test can tell one transaction per board from one around
    the whole pass.
    """
    opened: list[int] = []

    @asynccontextmanager
    async def scope() -> AsyncIterator[AsyncSession]:
        opened.append(1)
        async with session.begin_nested():
            yield session

    return opened, scope


async def _row(session: AsyncSession, ats: str, token: str) -> BoardPollState:
    return (
        await session.execute(
            select(BoardPollState).where(BoardPollState.ats == ats, BoardPollState.token == token)
        )
    ).scalar_one()


async def _pass(
    session: AsyncSession, boards: Sequence[tuple[str, str]], factory: _Factory
) -> tuple[list[BoardPollReport], list[int]]:
    await sync_board_poll_state(session, now=utcnow())
    await session.flush()
    opened, scope = _scopes(session)
    reports = await poll_every_board(
        boards,
        client=cast(PoliteClient, object()),
        session_scope=cast("Any", scope),
        make_adapter=factory,
    )
    return reports, opened


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestThePass:
    async def test_every_ats_is_polled_not_only_greenhouse(self, db_session: AsyncSession) -> None:
        factory = _Factory()
        boards = [DATADOG, ALLOY, RAMP]
        reports, _ = await _pass(db_session, boards, factory)

        assert [(r.ats, r.token) for r in reports] == boards
        assert all(not r.failed and r.status == 304 for r in reports)
        assert {ats: stub.seen for ats, stub in factory.stubs.items()} == {
            "greenhouse": ["datadog"],
            "lever": ["alloy"],
            "ashby": ["ramp"],
        }
        # Through poll_one_board, so the scheduler's row moved: the next tick
        # will not poll these again until they are due.
        for ats, token in boards:
            row = await _row(db_session, ats, token)
            assert row.last_status == 304
            assert row.last_polled_at is not None
            assert row.next_poll_at > row.last_polled_at

    async def test_one_client_serves_the_whole_pass(self, db_session: AsyncSession) -> None:
        """Two Ashby boards, one Ashby adapter, and every adapter around the same
        client. A client per board would give each board a fresh rate limiter."""
        factory = _Factory()
        await _pass(db_session, [RAMP, DATADOG, A16Z], factory)

        assert [ats for ats, _ in factory.calls] == ["ashby", "greenhouse"]
        assert len({id(client) for _, client in factory.calls}) == 1
        assert factory.stubs["ashby"].seen == ["ramp", "a16z-new-media"]

    async def test_each_board_is_its_own_transaction(self, db_session: AsyncSession) -> None:
        boards = [DATADOG, ALLOY, RAMP, A16Z]
        _, opened = await _pass(db_session, boards, _Factory())
        assert len(opened) == len(boards)

    async def test_a_failing_board_is_reported_and_the_pass_goes_on(
        self, db_session: AsyncSession
    ) -> None:
        factory = _Factory(failing=frozenset({"alloy"}))
        reports, _ = await _pass(db_session, [DATADOG, ALLOY, RAMP], factory)

        by_board = {(r.ats, r.token): r for r in reports}
        assert by_board[ALLOY].failed
        assert by_board[ALLOY].status is None
        assert "HTTP 503" in (by_board[ALLOY].error or "")
        assert by_board[ALLOY].consecutive_failures == 1
        assert not by_board[DATADOG].failed
        assert not by_board[RAMP].failed
        assert factory.stubs["ashby"].seen == ["ramp"]

    async def test_a_board_without_a_row_does_not_end_the_pass(
        self, db_session: AsyncSession
    ) -> None:
        """The registry and the poll-state table disagreeing is a LookupError from
        poll_one_board. Raising it out of the pass would cost every later board
        its poll, and roll back nothing that was wrong."""
        stale = ("ashby", "never-heard-of-it")
        reports, _ = await _pass(db_session, [stale, DATADOG], _Factory())

        assert reports[0].failed
        assert "no board_poll_state row" in (reports[0].error or "")
        assert not reports[1].failed
        assert (await _row(db_session, *DATADOG)).last_status == 304


# ---------------------------------------------------------------------------
# The command: which boards it asks for, and what it does with the answers.
# ---------------------------------------------------------------------------


class _FakeClient:
    instances = 0

    def __init__(self) -> None:
        _FakeClient.instances += 1

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


def _command(
    monkeypatch: pytest.MonkeyPatch, *, failing: bool = False
) -> list[list[tuple[str, str]]]:
    """Wire `cmd_ingest` to fakes. Returns the board lists it asked to poll."""
    asked: list[list[tuple[str, str]]] = []

    async def fake_pass(
        boards: Sequence[tuple[str, str]], **kwargs: object
    ) -> list[BoardPollReport]:
        assert isinstance(kwargs["client"], _FakeClient)
        asked.append(list(boards))
        return [
            BoardPollReport(
                ats=ats,
                token=token,
                status=None if failing else 200,
                tier=None if failing else BoardTier.WARM,
                consecutive_failures=1 if failing else 0,
                error="HTTP 503" if failing else None,
            )
            for ats, token in boards
        ]

    @asynccontextmanager
    async def no_session() -> AsyncIterator[None]:
        yield None

    async def nothing(*args: object, **kwargs: object) -> int:
        return 0

    _FakeClient.instances = 0
    monkeypatch.setattr(cli, "get_settings", lambda: make_settings(outbound_http_enabled=True))
    monkeypatch.setattr(cli, "PoliteClient", _FakeClient)
    monkeypatch.setattr(cli, "poll_every_board", fake_pass)
    monkeypatch.setattr(
        cli, "session_scope", cast("type[AbstractAsyncContextManager[None]]", no_session)
    )
    monkeypatch.setattr(cli, "sync_board_poll_state", nothing)
    monkeypatch.setattr(cli, "_print_summary", nothing)
    return asked


@pytest.mark.asyncio(loop_scope="session")
class TestTheCommand:
    async def test_it_asks_for_every_pollable_board_through_one_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = _command(monkeypatch)
        assert await cli.cmd_ingest(argparse.Namespace(ats=None)) == 0

        expected = [(entry.ats, entry.token) for entry in get_registry().pollable()]
        assert asked == [expected]
        assert {ats for ats, _ in expected} >= {"greenhouse", "lever", "ashby"}
        assert _FakeClient.instances == 1

    async def test_ats_narrows_the_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        asked = _command(monkeypatch)
        assert await cli.cmd_ingest(argparse.Namespace(ats="lever")) == 0
        assert asked and {ats for ats, _ in asked[0]} == {"lever"}

    async def test_it_fails_only_when_nothing_answered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _command(monkeypatch, failing=True)
        assert await cli.cmd_ingest(argparse.Namespace(ats=None)) == 1

    async def test_it_refuses_without_outbound_http(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        asked = _command(monkeypatch)
        monkeypatch.setattr(cli, "get_settings", lambda: make_settings())
        assert await cli.cmd_ingest(argparse.Namespace(ats=None)) == 1
        assert asked == []
        assert "outbound HTTP is disabled" in capsys.readouterr().err


def test_the_parser_accepts_only_known_ats_names() -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["ingest", "--ats", "workday"])
    assert raised.value.code == 2
