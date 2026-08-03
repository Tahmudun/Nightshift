"""Declarative base, shared column types, and the domain enums.

Enums are PostgreSQL enums, not bare strings (CLAUDE.md §7). The point is that
an invalid ``location_confidence`` is rejected by the database, so invariant I1
survives a bug in application code rather than depending on it.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit constraint naming, so Alembic autogenerate produces stable,
# reversible names instead of database-assigned ones that differ per machine.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """``created_at`` / ``updated_at`` on every table, in UTC (CLAUDE.md §7).

    Both defaults are server-side: rows written by a migration, a seed script,
    or psql get correct timestamps too, not just rows written through the ORM.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid.uuid4,
    )


# ---------------------------------------------------------------------------
# Domain enums
# ---------------------------------------------------------------------------
#
# `enum.StrEnum` so a member IS its string value — no `Class.MEMBER` leaking into
# a log line or a JSON body. SQLAlchemy is additionally told
# `values_callable=lambda e: [m.value for m in e]` at each column so the stored
# PG labels are the lowercase values, not the uppercase Python member names.


class LocationConfidence(enum.StrEnum):
    """Invariant I1. There is no sixth value and no default of convenience.

    ``unknown`` is the honest answer whenever resolution failed or was not
    attempted. It is never upgraded by inference — only by a real geocode.
    """

    VERIFIED = "verified"
    APPROXIMATE = "approximate"
    CITY_ONLY = "city_only"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class ResolutionMethod(enum.StrEnum):
    """How a ``job_locations`` row got whatever precision it has."""

    NOT_ATTEMPTED = "not_attempted"
    SOURCE_TEXT_PARSE = "source_text_parse"
    NYC_GEOSEARCH = "nyc_geosearch"
    NOMINATIM = "nominatim"
    NEIGHBORHOOD_CENTROID = "neighborhood_centroid"
    MANUAL = "manual"


class JobStatus(enum.StrEnum):
    """Closure state machine (§7.4). Invariant I3 governs the transitions."""

    OPEN = "open"
    POSSIBLY_STALE = "possibly_stale"
    UNVERIFIED = "unverified"
    CLOSED = "closed"


class SourceStatus(enum.StrEnum):
    """State of a raw record as last reported by its source."""

    ACTIVE = "active"
    MISSING = "missing"
    REMOVED = "removed"


class BoardTier(enum.StrEnum):
    """How often a board is polled (ADR 0007).

    Derived from ingested postings, never hand-set: a board is ``hot`` because
    of what its postings said, not because someone ticked a flag in the
    registry YAML.

    **A weekly tier was considered and rejected**, and this closed set is where
    that decision lives. Daily on the long tail is what keeps "the day of" true
    for a company posting its first NYC role; at weekly, that role could sit
    unseen for six days, which breaks the one promise the product makes. Adding
    a third member should mean reopening ADR 0007.
    """

    HOT = "hot"
    WARM = "warm"


class SourceType(enum.StrEnum):
    ATS_GREENHOUSE = "ats_greenhouse"
    ATS_LEVER = "ats_lever"
    ATS_ASHBY = "ats_ashby"
    GOVERNMENT = "government"
    FIXTURE = "fixture"


class EmploymentType(enum.StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    INTERNSHIP = "internship"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class RemotePolicy(enum.StrEnum):
    ON_SITE = "on_site"
    HYBRID = "hybrid"
    REMOTE = "remote"
    UNKNOWN = "unknown"


class IngestionRunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    # A run that reached some sources but not others. Distinct from `failed`
    # because I3 depends on knowing a source was unreachable.
    PARTIAL = "partial"
    FAILED = "failed"


def pg_enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """``values_callable`` helper: store enum *values*, not member names."""
    return [member.value for member in enum_cls]
