"""The M0 schema.

Scope note: this is deliberately not the whole domain model from
``docs/spec/PRODUCT-SPEC.md`` §6. M0 needs the ingestion spine and nothing more.
Applications, match results, snapshots, and user skills arrive at the milestone
that uses them, because a table nobody reads is a table nobody keeps correct.

What *is* here is shaped correctly for what comes later:

* ``users`` exists and every user-owned table will carry a ``user_id`` FK from
  its first migration (AMENDMENTS A3), so M5 auth is a middleware and not a
  migration of every table in the schema.
* Raw payloads live in ``source_job_records`` and canonical rows join back
  through ``job_source_links``, so provenance is available from day one and
  M1's dedupe has somewhere to record a merge.
* Locations are a separate table from the start (AMENDMENTS A2) because
  collapsing ``"Boston, MA; New York, NY; Remote"`` to one point is exactly the
  fabrication invariant I1 forbids.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nightshift.db.base import (
    Base,
    EmploymentType,
    IngestionRunStatus,
    JobStatus,
    LocationConfidence,
    RemotePolicy,
    ResolutionMethod,
    SourceStatus,
    SourceType,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    pg_enum_values,
)
from nightshift.db.types import UTCDateTime


def _enum(enum_cls: type, name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=pg_enum_values,
        native_enum=True,
        create_type=True,
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row in M0-M4 (the seeded ``dev_user``), but never assumed to be one.

    AMENDMENTS A3: no auth until M5, yet nothing in the codebase may assume a
    single user. Queries filter on ``user_id`` even when there is only one.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/New_York")


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    # Casefolded, punctuation-stripped form used for joins and dedupe. Unique:
    # "Datadog" and "Datadog, Inc." must resolve to one company, not two.
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    website: Mapped[str | None] = mapped_column(String(500))

    jobs: Mapped[list[Job]] = relationship(back_populates="company")


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per ATS provider, not per company board.

    ``last_success_at`` / ``last_failure_at`` drive the source health page. They
    are also why I3 is enforceable: a source that failed is distinguishable
    from a source that returned an empty list.
    """

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source_type: Mapped[SourceType] = mapped_column(
        _enum(SourceType, "source_type"), nullable=False
    )
    base_url: Mapped[str | None] = mapped_column(String(500))
    is_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_failure_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    records: Mapped[list[SourceJobRecord]] = relationship(back_populates="source")


class SourceJobRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The raw truth, preserved verbatim.

    ``raw_payload`` is the source's JSON exactly as received. Normalization is
    always re-derivable from it, which is what makes M1's "same fixture in,
    byte-identical output, twice" criterion checkable, and what lets a
    normalization bug be fixed by a backfill rather than a re-crawl.
    """

    __tablename__ = "source_job_records"
    __table_args__ = (
        # Idempotent re-ingestion depends on this: the second poll of a board
        # updates rows rather than inserting duplicates.
        UniqueConstraint(
            "source_id", "source_job_id", name="uq_source_job_records_source_id_source_job_id"
        ),
        Index("ix_source_job_records_last_seen_at", "last_seen_at"),
        Index("ix_source_job_records_source_company_key", "source_company_key"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    # The source's own identifier, as a string: Greenhouse uses ints, Lever uses
    # UUIDs, Ashby uses its own ids. Storing the provider's native type would
    # mean a column per provider.
    source_job_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_company_key: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(1000))

    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    # sha256 of the normalized description text. Cheap change detection that
    # does not require diffing two JSON blobs.
    description_hash: Mapped[str | None] = mapped_column(String(64))
    #: The provider's own last-modified stamp for *this* posting on *this*
    #: board, when it publishes one. Greenhouse does; Lever and Ashby do not
    #: (measured 2026-08-02) and leave it NULL.
    #:
    #: Deliberately duplicated from ``jobs.source_updated_at`` rather than read
    #: from there. After a merge one canonical job carries records from several
    #: boards, and its timestamp reflects whichever wrote last — so comparing a
    #: board's listing against it would refetch postings that had not changed
    #: and skip ones that had. The record is the per-board fact, and the
    #: phase-2 diff is a per-board question.
    source_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    # Distinct from last_seen_at: "we fetched the board and it was listed" is
    # weaker evidence than "we hit the posting's own endpoint and it was open".
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    consecutive_misses: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    source_status: Mapped[SourceStatus] = mapped_column(
        _enum(SourceStatus, "source_status"),
        nullable=False,
        server_default=SourceStatus.ACTIVE.value,
    )

    source: Mapped[Source] = relationship(back_populates="records")
    links: Mapped[list[JobSourceLink]] = relationship(
        back_populates="source_job_record", cascade="all, delete-orphan"
    )


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A canonical job: one real-world opening, however many sources describe it.

    Note the absence of ``latitude`` / ``longitude`` / ``location_confidence``
    columns that PRODUCT-SPEC §6.9 lists. AMENDMENTS A2 moved them to
    ``job_locations``; ``primary_location_id`` is the denormalized pointer for
    cheap sorting and is never the only representation.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_status_last_seen_at", "status", "last_seen_at"),
        Index("ix_jobs_normalized_title", "normalized_title"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="salary_range_ordered",
        ),
        # I3: a closed job has a closure timestamp and an open one does not.
        # Enforced here so a buggy transition is a database error.
        CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)",
            name="closed_at_matches_status",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(500), nullable=False)
    # role_family and seniority are populated by M3's classifier. Nullable now,
    # and null means "not yet classified" — never a guessed default.
    role_family: Mapped[str | None] = mapped_column(String(100))
    seniority: Mapped[str | None] = mapped_column(String(50))
    employment_type: Mapped[EmploymentType] = mapped_column(
        _enum(EmploymentType, "employment_type"),
        nullable=False,
        server_default=EmploymentType.UNKNOWN.value,
    )

    description_html: Mapped[str | None] = mapped_column(Text)
    description_text: Mapped[str | None] = mapped_column(Text)

    # AMENDMENTS A10: sparse in practice. Null means "not provided by source",
    # which the UI states explicitly rather than hiding the row.
    salary_min: Mapped[float | None] = mapped_column(NUMERIC(12, 2))
    salary_max: Mapped[float | None] = mapped_column(NUMERIC(12, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[str | None] = mapped_column(String(20))
    application_deadline: Mapped[datetime | None] = mapped_column(UTCDateTime)

    remote_policy: Mapped[RemotePolicy] = mapped_column(
        _enum(RemotePolicy, "remote_policy"),
        nullable=False,
        server_default=RemotePolicy.UNKNOWN.value,
    )

    # AMENDMENTS A10: named for what it actually is. Greenhouse's `updated_at`
    # is a last-modified stamp, so it does not go in a column called posted_at.
    source_published_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    source_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Ours, not the source's. Never presented to a user as "posted".
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), nullable=False, server_default=JobStatus.OPEN.value
    )
    canonical_description_hash: Mapped[str | None] = mapped_column(String(64))

    primary_location_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        # SET NULL rather than CASCADE: losing the pointer must never delete the
        # job, and use_alter breaks the circular FK for DDL ordering.
        ForeignKey("job_locations.id", ondelete="SET NULL", use_alter=True),
    )

    company: Mapped[Company] = relationship(back_populates="jobs")
    locations: Mapped[list[JobLocation]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        foreign_keys="JobLocation.job_id",
        order_by="desc(JobLocation.is_primary)",
    )
    primary_location: Mapped[JobLocation | None] = relationship(
        foreign_keys=[primary_location_id], post_update=True, viewonly=True
    )
    source_links: Mapped[list[JobSourceLink]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobLocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per location a posting actually names (AMENDMENTS A2).

    Invariant I1 lives here. ``raw_text`` is the exact substring from the
    source, kept so a parsing decision is always auditable against what the
    posting said. ``latitude``/``longitude`` are null unless a real geocoder
    returned them; there is no interpolation path that can populate them.
    """

    __tablename__ = "job_locations"
    __table_args__ = (
        Index("ix_job_locations_job_id", "job_id"),
        Index("ix_job_locations_geom", "geom", postgresql_using="gist"),
        Index("ix_job_locations_location_confidence", "location_confidence"),
        # I1, at the database level: coordinates and a precision claim travel
        # together. A point with `unknown` confidence, or a `verified` claim
        # with no point, cannot be stored at all.
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name="coordinates_are_paired",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude BETWEEN -90 AND 90)",
            name="latitude_in_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude BETWEEN -180 AND 180)",
            name="longitude_in_range",
        ),
        CheckConstraint(
            """
            CASE
                WHEN location_confidence IN ('verified', 'approximate')
                    THEN latitude IS NOT NULL
                WHEN location_confidence IN ('city_only', 'remote', 'unknown')
                    THEN latitude IS NULL
            END
            """,
            name="confidence_matches_coordinates",
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    raw_text: Mapped[str] = mapped_column(String(500), nullable=False)
    city: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))

    latitude: Mapped[float | None] = mapped_column(NUMERIC(9, 6))
    longitude: Mapped[float | None] = mapped_column(NUMERIC(9, 6))
    geom: Mapped[Any | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False)
    )

    location_confidence: Mapped[LocationConfidence] = mapped_column(
        _enum(LocationConfidence, "location_confidence"),
        nullable=False,
        server_default=LocationConfidence.UNKNOWN.value,
    )
    resolution_method: Mapped[ResolutionMethod] = mapped_column(
        _enum(ResolutionMethod, "resolution_method"),
        nullable=False,
        server_default=ResolutionMethod.NOT_ATTEMPTED.value,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    is_primary: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))

    job: Mapped[Job] = relationship(back_populates="locations", foreign_keys=[job_id])


class JobSourceLink(UUIDPrimaryKeyMixin, Base):
    """Provenance edge. Many raw records may describe one canonical job.

    Append-only in spirit and unique per pair, so a merge in M1 adds an edge
    rather than rewriting history. ``link_reason`` records *why* the merge was
    made, which is what makes it reviewable and reversible (§7.5).
    """

    __tablename__ = "job_source_links"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "source_job_record_id", name="uq_job_source_links_job_id_source_job_record_id"
        ),
        CheckConstraint(
            "match_confidence BETWEEN 0 AND 1", name="match_confidence_is_a_probability"
        ),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    source_job_record_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_job_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_confidence: Mapped[float] = mapped_column(NUMERIC(4, 3), nullable=False)
    link_reason: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now()")
    )

    job: Mapped[Job] = relationship(back_populates="source_links")
    source_job_record: Mapped[SourceJobRecord] = relationship(back_populates="links")


class IngestionRun(UUIDPrimaryKeyMixin, Base):
    """One row per ingestion attempt, successful or not.

    §2.6 requires source reliability to be visible, and I3 requires an outage
    to be distinguishable from an empty result. Both need failures to be a row
    in a table the UI can query, not a line in a log nobody reads.
    """

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        Index("ix_ingestion_runs_source_id_started_at", "source_id", "started_at"),
        CheckConstraint(
            "(status = 'running') = (finished_at IS NULL)", name="finished_at_matches_status"
        ),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    # Which registry entries this run touched. Lets the source health page show
    # "Datadog board 404'd" instead of "the Greenhouse run was partial".
    board_tokens: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[IngestionRunStatus] = mapped_column(
        _enum(IngestionRunStatus, "ingestion_run_status"), nullable=False
    )

    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_created: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_unchanged: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    # Stays 0 for any run that saw a source error. I3 is not a suggestion.
    records_closed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_summary: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now()")
    )

    source: Mapped[Source] = relationship(lazy="raise")


class JobStatusEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only record of every closure-machine transition (ADR 0009).

    Exists because reopening is permitted. A reposted job returns to ``open``
    with ``closed_at`` back to NULL, so without this table the fact that it ever
    closed is gone — and I6's standard of evidence would have nothing to point
    at. ``reason`` is the sentence the decision function produced at the time,
    which is what a human reads when asking why a job disappeared.

    Append-only is enforced by a trigger, per CLAUDE.md §7. A table that is
    append-only by convention is a comment.
    """

    __tablename__ = "job_status_events"
    __table_args__ = (Index("ix_job_status_events_job_id_created_at", "job_id", "created_at"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    # Null on the first event of a job's life: it transitioned from nothing, and
    # writing `open -> open` would be a fabricated event.
    from_status: Mapped[JobStatus | None] = mapped_column(_enum(JobStatus, "job_status"))
    to_status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    # Which poll produced this. SET NULL rather than CASCADE: pruning old run
    # rows must never delete the closure history they caused.
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    observed_misses: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now()")
    )


class JobEmbedding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One vector per canonical job description (AMENDMENTS A5).

    ``model_name`` and ``dimension`` are stored on every row so that replacing
    the model is a backfill rather than a mystery. ``source_hash`` is the
    description hash the vector was computed from, which is what lets a re-poll
    of an unchanged posting skip the model entirely.

    No vector index, deliberately. At a few thousand jobs a sequential scan
    within one company's candidates beats maintaining one, and an ivfflat index
    built on a nearly-empty table returns wrong neighbours rather than slow
    ones. Add an index with a measurement behind it, not in advance.
    """

    __tablename__ = "job_embeddings"
    __table_args__ = (UniqueConstraint("job_id", name="uq_job_embeddings_job_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class JobMergeEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only record of one dedupe merge, with the evidence behind it.

    Invariant I4 in spirit, one milestone before I4's subsystem exists: a merge
    stores its reason, its confidence and its ruleset version, not just its
    verdict. ``loser_job_id`` deliberately carries no foreign key — the row it
    names is deleted by the merge, and an FK would make the audit trail
    unstorable at the exact moment it becomes useful.

    Reversibility does not depend on ``loser_snapshot`` being complete: canonical
    jobs are derived from ``source_job_records.raw_payload``, which is preserved
    verbatim. The snapshot makes an un-merge cheap; the raw payloads make it
    possible.
    """

    __tablename__ = "job_merge_events"
    __table_args__ = (
        Index("ix_job_merge_events_winner_job_id", "winner_job_id"),
        CheckConstraint(
            "match_confidence BETWEEN 0 AND 1", name="merge_confidence_is_a_probability"
        ),
        # A self-merge deletes the winner. Cheap insurance against a
        # candidate-generation bug that stops excluding the job itself.
        CheckConstraint("winner_job_id <> loser_job_id", name="merge_has_two_distinct_jobs"),
    )

    winner_job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    loser_job_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    loser_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    match_confidence: Mapped[float] = mapped_column(NUMERIC(4, 3), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("now()")
    )
