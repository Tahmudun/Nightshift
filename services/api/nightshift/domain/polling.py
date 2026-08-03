"""Polling one board, and deciding when each board is next due.

ADR 0007 and ``docs/architecture/conditional-polling.md`` §7.

**The scheduling shape is ``next_poll_at`` on the board row, drained by a small
cron**, rather than one cron per tier. Two alternatives were considered and
rejected in the design:

* *A cron per tier*, each enqueueing its whole tier. It is what ADR 0007
  literally describes and the least machinery, but every board in a tier fires
  in the same instant and per-board backoff has nowhere to live.
* *Each poll enqueueing its own successor.* Elegant, needs no scheduler at all,
  and one lost job stops a board being polled forever with nothing to notice.

What the chosen shape buys: load spreads as boards drift apart; backoff is free,
because a failing board simply pushes itself out; "what is overdue" is a SQL
query the coverage page already needs; and the state survives a worker restart
because it lives in Postgres rather than in the queue.

This module owns *when* and *whether*. What a poll does with what it gets back
is :mod:`nightshift.domain.ingestion`, which is where I3 lives.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol, cast

import structlog
from sqlalchemy import CursorResult, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.ashby import AshbyAdapter
from nightshift.adapters.base import JobSourceAdapter
from nightshift.adapters.greenhouse import GreenhouseAdapter
from nightshift.adapters.http import PoliteClient
from nightshift.adapters.lever import LeverAdapter
from nightshift.config import get_settings
from nightshift.db.base import BoardTier, SourceType
from nightshift.db.models import BoardPollState
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from nightshift.domain.registry import get_registry

log = structlog.get_logger(__name__)


class AdapterFactory(Protocol):
    """An adapter class: constructible from a client, and self-describing.

    Typed as a Protocol rather than `type` so `parser_version` is reachable
    without an attribute error — the version has to be readable off the class,
    because `sync_board_poll_state` records it for boards it has never polled
    and therefore has no instance of.
    """

    parser_version: str

    # Non-optional deliberately, even though Lever and Ashby also accept None:
    # every caller here has a live client, and `None` is a construction the
    # fixture adapters use for a purpose this factory has nothing to do with.
    # A wider parameter still satisfies a narrower one, so those two conform.
    def __call__(self, client: PoliteClient) -> JobSourceAdapter: ...


@dataclass(frozen=True, slots=True)
class AdapterSpec:
    """How to build an adapter for one ATS, and what to attribute it to."""

    factory: AdapterFactory
    source_name: str
    source_type: SourceType
    base_url: str


#: The complete set of ATS names this system can poll. Keyed by the same string
#: the registry YAML uses, so a registry entry naming an unknown ATS fails at
#: lookup rather than being silently skipped — a board nobody polls and nobody
#: reports is the failure A1's registry exists to prevent.
ADAPTERS: dict[str, AdapterSpec] = {
    "greenhouse": AdapterSpec(
        GreenhouseAdapter,
        "greenhouse",
        SourceType.ATS_GREENHOUSE,
        "https://boards-api.greenhouse.io",
    ),
    "lever": AdapterSpec(LeverAdapter, "lever", SourceType.ATS_LEVER, "https://api.lever.co"),
    "ashby": AdapterSpec(AshbyAdapter, "ashby", SourceType.ATS_ASHBY, "https://api.ashbyhq.com"),
}


def next_interval(tier: BoardTier) -> timedelta:
    """How long until a healthy board of this tier is due again."""
    settings = get_settings()
    seconds = (
        settings.poll_hot_interval_seconds
        if tier is BoardTier.HOT
        else settings.poll_warm_interval_seconds
    )
    return timedelta(seconds=seconds)


def failure_backoff(consecutive_failures: int) -> timedelta:
    """Board-level backoff: 15 minutes doubling to a 24-hour ceiling.

    Separate from :data:`PoliteClient`'s per-request retry backoff, which
    handles one flaky response and is measured in seconds. This one handles a
    board that is simply gone.

    The ceiling matches the warm tier deliberately: a dead board stops costing
    requests without falling out of the system, so if it comes back it is
    noticed within a day. ``min`` is applied to the *exponent* as well as the
    result, because ``2 ** 500`` is a fine Python integer and a useless
    ``timedelta``.
    """
    settings = get_settings()
    # 40 doublings is already far past any sane ceiling; capping the exponent
    # keeps the arithmetic small no matter how long a board has been dead.
    exponent = min(max(consecutive_failures, 0), 40)
    seconds = min(
        settings.poll_backoff_base_seconds * (2**exponent),
        settings.poll_backoff_max_seconds,
    )
    return timedelta(seconds=seconds)


def adapter_for(ats: str, client: PoliteClient) -> JobSourceAdapter:
    """Build the adapter for one ATS, or raise for one we cannot poll."""
    spec = ADAPTERS.get(ats)
    if spec is None:
        raise LookupError(f"no adapter registered for ats {ats!r}")
    adapter: JobSourceAdapter = spec.factory(client)
    return adapter


async def sync_board_poll_state(session: AsyncSession, *, now: datetime) -> int:
    """Give every pollable registry board a poll-state row. Returns rows created.

    Runs on every scheduler tick, so it must be idempotent in the strong sense:
    not merely "adds no duplicates" but "changes nothing about a board it has
    already seen". Resetting ``next_poll_at`` here would mean every board is due
    on every tick, forever.

    ``ON CONFLICT DO NOTHING`` rather than check-then-insert: this runs from a
    worker, and ADR 0007's queue-driven polling makes concurrency routine.
    M1a made ``get_or_create_source`` an upsert for the same reason.

    Only ``pollable()`` boards get a row. A board a human set to ``disabled``
    has no row and therefore cannot be polled — the guarantee they were asking
    for when they disabled it.
    """
    created = 0
    for entry in get_registry().pollable():
        spec = ADAPTERS.get(entry.ats)
        if spec is None:
            log.warning("board_has_no_adapter", ats=entry.ats, token=entry.token)
            continue

        source = await get_or_create_source(
            session, name=spec.source_name, source_type=spec.source_type, base_url=spec.base_url
        )
        # An UPDATE/INSERT always yields a CursorResult, which is where
        # `rowcount` lives; `session.execute` is typed as returning the wider
        # Result. Cast rather than getattr, so a changed statement type is a
        # type error and not a silent zero.
        result = cast(
            "CursorResult[Any]",
            await session.execute(
                pg_insert(BoardPollState)
                .values(
                    source_id=source.id,
                    ats=entry.ats,
                    token=entry.token,
                    parser_version=spec.factory.parser_version,
                    tier=BoardTier.WARM,
                    # Due immediately: a board a human just approved should be
                    # polled on the next tick, not a day later.
                    next_poll_at=now,
                )
                .on_conflict_do_nothing(index_elements=["ats", "token"])
            ),
        )
        created += int(result.rowcount or 0)

    if created:
        log.info("board_poll_state_synced", created=created)
    return created


async def due_boards(
    session: AsyncSession, *, now: datetime, limit: int | None = None
) -> list[BoardPollState]:
    """Boards whose ``next_poll_at`` has passed, longest-overdue first.

    The ordering is what stops a board starving under the batch cap: without
    it the same arbitrary subset drains every tick and the rest wait forever.
    """
    batch = limit if limit is not None else get_settings().poll_enqueue_batch_limit
    rows = (
        await session.execute(
            select(BoardPollState)
            .where(BoardPollState.next_poll_at <= now)
            .order_by(BoardPollState.next_poll_at)
            .limit(batch)
        )
    ).scalars()
    return list(rows)


async def poll_one_board(
    session: AsyncSession,
    adapter: JobSourceAdapter,
    *,
    ats: str,
    token: str,
    now: datetime,
) -> BoardPollState:
    """Poll one board and write down what happened. Returns the updated row.

    The stored ETag is sent only when it was earned by the parser currently
    running (ADR 0007). A changed parser plus a stale ETag means the provider
    keeps answering ``304`` and the new parser never sees the payload it was
    written for — which reports as a perfectly healthy board, indefinitely.
    """
    state = (
        await session.execute(
            select(BoardPollState).where(BoardPollState.ats == ats, BoardPollState.token == token)
        )
    ).scalar_one_or_none()
    if state is None:
        # The queue and the registry disagree. Returning quietly would drop
        # this poll and every future one for this board with nothing to show.
        raise LookupError(f"no board_poll_state row for {ats}:{token}")

    entry = get_registry().by_token(ats, token)
    if entry is None:
        raise LookupError(f"{ats}:{token} has a poll-state row but is not in the registry")

    spec = ADAPTERS[ats]
    source = await get_or_create_source(
        session, name=spec.source_name, source_type=spec.source_type, base_url=spec.base_url
    )

    usable_etag = state.etag if state.parser_version == adapter.parser_version else None
    if state.etag is not None and usable_etag is None:
        log.info(
            "etag_discarded_stale_parser",
            board=token,
            stored=state.parser_version,
            current=adapter.parser_version,
        )

    _run, stats = await ingest_boards(
        session,
        adapter,
        [entry.to_ref()],
        source=source,
        now=now,
        etags={token: usable_etag},
    )

    state.last_polled_at = now
    if stats.boards_failed:
        state.consecutive_failures += 1
        state.last_error = stats.error_summary
        state.next_poll_at = now + failure_backoff(state.consecutive_failures - 1)
        log.warning(
            "board_poll_failed",
            board=token,
            consecutive_failures=state.consecutive_failures,
            next_poll_at=state.next_poll_at.isoformat(),
        )
    else:
        state.last_success_at = now
        state.consecutive_failures = 0
        state.last_error = None
        state.last_status = 304 if token in stats.not_modified else 200
        # A 304 carries no new ETag, so keep the one that earned it.
        served = stats.etags.get(token)
        if served is not None:
            state.etag = served
        # Only now is the stored ETag known to belong to this parser.
        state.parser_version = adapter.parser_version
        state.next_poll_at = now + next_interval(state.tier)

    await session.flush()
    return state
