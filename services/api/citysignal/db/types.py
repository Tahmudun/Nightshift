"""Custom column types.

``UTCDateTime`` exists because "UTC in the database, always" (CLAUDE.md §7) is
not self-enforcing. ``TIMESTAMPTZ`` accepts a naive datetime and silently
interprets it in the server's timezone, which is how a timestamp ends up four
hours wrong and nobody notices until a freshness calculation looks strange.
This type rejects naive datetimes at the boundary instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """``TIMESTAMPTZ`` that refuses naive values and always returns UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            raise ValueError(
                "naive datetime rejected — attach a timezone (CLAUDE.md §7: UTC in the database)"
            )
        return value.astimezone(UTC)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected datetime from the database, got {type(value).__name__}")
        # asyncpg returns aware datetimes for TIMESTAMPTZ; normalise the tzinfo
        # so equality comparisons in tests do not depend on the server offset.
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def utcnow() -> datetime:
    """Timezone-aware now. Use this, never ``datetime.utcnow()``."""
    return datetime.now(UTC)
