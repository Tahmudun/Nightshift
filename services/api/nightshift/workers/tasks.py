"""Background task definitions.

M0 has exactly one real task: poll the Greenhouse boards marked ``active`` in the
registry and persist what comes back. It is a real task doing real work, not a
placeholder that logs "hello" — a scheduler wired to a no-op teaches you nothing
about whether the scheduler works.
"""

from __future__ import annotations

from typing import Any

import structlog

from nightshift.adapters.greenhouse import GreenhouseAdapter
from nightshift.adapters.http import PoliteClient
from nightshift.db.base import SourceType
from nightshift.db.session import session_scope
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
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
