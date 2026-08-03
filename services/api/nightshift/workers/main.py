"""ARQ worker entry point.

ARQ rather than Celery (AMENDMENTS A11): asyncio-native, so it shares the async
SQLAlchemy session and the async httpx client with the API instead of fighting
them. The worker is a module inside this service, not a third deployable app.

Run with:  arq nightshift.workers.main.WorkerSettings
"""

from __future__ import annotations

from typing import Any, ClassVar

import structlog
from arq.connections import RedisSettings
from arq.cron import cron

from nightshift.config import get_settings
from nightshift.db.session import dispose_engine
from nightshift.logging import configure_logging
from nightshift.workers.tasks import enqueue_due_boards, ingest_greenhouse, poll_board

log = structlog.get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    log.info("worker_starting", **get_settings().redacted())


async def shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine()
    log.info("worker_stopped")


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings(
        host=settings.redis_host, port=settings.redis_port, database=settings.redis_db
    )


class WorkerSettings:
    """ARQ configuration.

    ClassVar on the collections because ARQ reads them off the class; they are
    configuration, not per-instance state.
    """

    functions: ClassVar[list[Any]] = [ingest_greenhouse, enqueue_due_boards, poll_board]

    # Off-peak and hourly. Polling a board more often than it changes is just
    # load on someone else's server (§7.3), and these endpoints are poll-only so
    # there is no push alternative to lighten it.
    cron_jobs: ClassVar[list[Any]] = [
        cron(
            ingest_greenhouse,
            minute=17,  # not :00 — every scheduler in the world fires on the hour
            run_at_startup=False,
        ),
        # M1d, ADR 0007. Every five minutes rather than hourly: this tick does
        # not poll anything, it asks which boards are *due* and queues those.
        # A short tick is what turns "hourly" into "within five minutes of
        # hourly" while letting boards drift apart instead of stampeding, and
        # it is what makes per-board backoff expressible at all.
        #
        # Offset by two minutes for the same reason `ingest_greenhouse` is at
        # :17 — nothing is gained by sharing a wakeup with every other
        # scheduler on the machine.
        cron(
            enqueue_due_boards,
            minute={2, 7, 12, 17, 22, 27, 32, 37, 42, 47, 52, 57},
            run_at_startup=False,
        ),
    ]

    on_startup = startup
    on_shutdown = shutdown

    # Still one at a time. ADR 0007 makes polling queue-driven so that raising
    # this is a configuration change rather than a rewrite — but raising it is
    # not free: `PoliteClient`'s rate limiter is per process, so two concurrent
    # jobs against one provider halve the spacing that limiter enforces. The
    # day this goes above 1, the limiter has to become per-host and shared.
    # Recorded here rather than in a plan, because this is the line that would
    # be changed.
    max_jobs = 1
    job_timeout = 600
    # Retries are the adapter's job, with backoff and jitter. Retrying at the
    # queue level on top of that is how you get a retry storm.
    max_tries = 1
    keep_result = 3600

    # ARQ reads this as an attribute, not a callable, so it is evaluated at
    # import. That is fine here and useful: an invalid Redis config fails when
    # the worker starts rather than when the first job is dequeued.
    redis_settings = _redis_settings()
