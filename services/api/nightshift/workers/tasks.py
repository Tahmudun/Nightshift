"""Background task definitions.

M0 had exactly one: poll the Greenhouse boards marked ``active`` and persist
what comes back. Real work, not a placeholder — a scheduler wired to a no-op
teaches you nothing about whether the scheduler works.

M1d adds the pair ADR 0007 describes. ``enqueue_due_boards`` runs on a short
cron and queues whichever boards are overdue; ``poll_board`` handles exactly
one board. **One ARQ job per board, not a loop inside one long task**: that is
the decision that makes going from 22 boards to 100,000 a worker-count question
rather than a rewrite, and it costs nothing today.

``ingest_greenhouse`` stays as it is. It is what ``make ingest`` and the M0 cron
use, and deleting it would remove the only path that polls without consulting
``board_poll_state``.
"""

from __future__ import annotations

from typing import Any

import structlog

from nightshift.adapters.greenhouse import GreenhouseAdapter
from nightshift.adapters.http import PoliteClient
from nightshift.config import get_settings
from nightshift.db.base import SourceType
from nightshift.db.session import session_scope
from nightshift.db.types import utcnow
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from nightshift.domain.polling import (
    adapter_for,
    due_boards,
    next_interval,
    poll_one_board,
    sync_board_poll_state,
)
from nightshift.domain.registry import get_registry

log = structlog.get_logger(__name__)

GREENHOUSE_SOURCE_NAME = "greenhouse"


async def ingest_greenhouse(ctx: dict[str, Any]) -> dict[str, Any]:
    """Poll every ``active`` Greenhouse board in the registry.

    Returns a summary dict rather than None so ARQ's result inspection shows
    what a run did without needing the logs.
    """
    boards = [entry.to_ref() for entry in get_registry().pollable(ats="greenhouse")]
    if not boards:
        log.info("ingest_greenhouse_skipped", reason="no active greenhouse boards in registry")
        return {"status": "skipped", "reason": "no active boards"}

    async with PoliteClient() as client, session_scope() as session:
        adapter = GreenhouseAdapter(client)
        source = await get_or_create_source(
            session,
            name=GREENHOUSE_SOURCE_NAME,
            source_type=SourceType.ATS_GREENHOUSE,
            base_url="https://boards-api.greenhouse.io",
        )
        run, stats = await ingest_boards(session, adapter, boards, source=source)
        return {
            "run_id": str(run.id),
            "status": run.status.value,
            "fetched": stats.fetched,
            "created": stats.created,
            "updated": stats.updated,
            "unchanged": stats.unchanged,
            "failed": stats.failed,
            "boards_ok": stats.boards_ok,
            "boards_failed": stats.boards_failed,
        }


async def poll_board(ctx: dict[str, Any], ats: str, token: str) -> dict[str, Any]:
    """Poll exactly one board (ADR 0007).

    One ARQ job per board rather than an iteration inside a long task. Rate
    limiting stays per-provider-host in ``PoliteClient``, so adding boards never
    raises the request rate against any one provider — which is what keeps
    board-discovery.md §10's scale path a capacity question.
    """
    async with PoliteClient() as client, session_scope() as session:
        adapter = adapter_for(ats, client)
        state = await poll_one_board(session, adapter, ats=ats, token=token, now=utcnow())
        return {
            "ats": ats,
            "token": token,
            "status": state.last_status,
            "tier": state.tier.value,
            "consecutive_failures": state.consecutive_failures,
            "next_poll_at": state.next_poll_at.isoformat(),
        }


async def enqueue_due_boards(ctx: dict[str, Any]) -> dict[str, Any]:
    """Queue every board whose ``next_poll_at`` has passed.

    ``next_poll_at`` is pushed forward **before** the jobs run, not after. A
    poll slower than the tick interval would otherwise be enqueued again by the
    following tick, and again by the one after that — stacking jobs against a
    single provider, which is the retry storm §7.3 forbids, self-inflicted.

    The consequence of ordering it this way is that a board whose poll is lost
    waits one full interval rather than being retried immediately. That is the
    right trade: a missed poll costs freshness on one board, while a stacking
    loop costs the project its data supply.
    """
    settings = get_settings()
    now = utcnow()

    async with session_scope() as session:
        created = await sync_board_poll_state(session, now=now)
        due = await due_boards(session, now=now, limit=settings.poll_enqueue_batch_limit)
        queued = [(board.ats, board.token) for board in due]
        for board in due:
            board.next_poll_at = now + next_interval(board.tier)

    redis = ctx.get("redis")
    if redis is None:  # pragma: no cover - only when invoked outside ARQ
        log.warning("enqueue_due_boards_no_redis", due=len(queued))
        return {"boards_created": created, "enqueued": 0, "due": len(queued)}

    for ats, token in queued:
        await redis.enqueue_job("poll_board", ats, token)

    log.info("boards_enqueued", created=created, enqueued=len(queued))
    return {"boards_created": created, "enqueued": len(queued), "due": len(queued)}
