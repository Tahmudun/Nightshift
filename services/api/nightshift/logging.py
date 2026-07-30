"""Structured logging setup.

structlog with key-value output, because the things worth logging here are
events with fields — ``ingest_board_failed board=datadog http_status=503`` — and
grepping a prose sentence for a board token is worse in every way.
"""

from __future__ import annotations

import logging
import sys

import structlog

from nightshift.config import get_settings

_configured = False


def configure_logging() -> None:
    """Idempotent: uvicorn's reloader imports the app more than once."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper())

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    # Human-readable locally, JSON in production where something parses it.
    if settings.nightshift_env == "production":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True
