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
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, NUMERIC, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationPriority,
    ApplicationStage,
    Base,
    BoardTier,
    EmploymentType,
    EventActor,
    ExtractionKind,
    ExtractionStatus,
    IngestionRunStatus,
    JobStatus,
    LocationConfidence,
    ProficiencyLevel,
    ProjectStatus,
    RemotePolicy,
    RemotePreference,
    ResolutionMethod,
    ResumeSourceKind,
    ResumeVariant,
    SkillSourceType,
    SourceStatus,
    SourceType,
    TimestampMixin,
    TransitionClass,
    UUIDPrimaryKeyMixin,
    WorkAuthorization,
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
    __table_args__ = (
        CheckConstraint(
            "graduation_month IS NULL OR graduation_year IS NOT NULL",
            name="graduation_month_needs_a_year",
        ),
        CheckConstraint(
            "graduation_month IS NULL OR graduation_month BETWEEN 1 AND 12",
            name="graduation_month_is_a_month",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/New_York")

    # -- Confirmed profile (M2c) --------------------------------------------
    #
    # Every column below holds a fact a human confirmed. Nothing outside
    # `domain/profile.py` writes any of them, and `tests/test_nothing_infers.py`
    # is what keeps that true (invariant I2).
    #
    #: A resume says "May 2027". It does not say a day, and inventing one to
    #: fill a DATE column is exactly the fabrication I1 forbids — the same
    #: reasoning that moved location off `jobs` in AMENDMENTS A2. M3's
    #: eligibility window needs a month and a year, which is what a resume
    #: actually says. ADR 0013.
    graduation_year: Mapped[int | None] = mapped_column(SmallInteger)
    graduation_month: Mapped[int | None] = mapped_column(SmallInteger)
    degree: Mapped[str | None] = mapped_column(String(200))
    school: Mapped[str | None] = mapped_column(String(300))
    work_authorization: Mapped[WorkAuthorization] = mapped_column(
        _enum(WorkAuthorization, "work_authorization"),
        nullable=False,
        server_default=text("'unspecified'"),
    )
    #: Free text, as the person wrote it. Not geocoded — M4 owns coordinates,
    #: and a home address is the last thing that should be resolved early.
    home_location_text: Mapped[str | None] = mapped_column(String(300))
    remote_preference: Mapped[RemotePreference] = mapped_column(
        _enum(RemotePreference, "remote_preference"),
        nullable=False,
        server_default=text("'no_preference'"),
    )
    minimum_salary: Mapped[int | None] = mapped_column(Integer)
    #: JSONB arrays of strings rather than tables: nothing filters on them in
    #: M2, so a table would be shape with no use (command-center.md §2.3).
    preferred_roles: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    preferred_locations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    skills: Mapped[list[UserSkill]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list[UserProject]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSkill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A skill the user **confirmed**. Never a proposal (invariant I2).

    ``skill_id`` from §6.2 is deliberately absent: the taxonomy is M3's, and
    this table stores the canonical name from ``data/skills.yaml`` along with
    the vocabulary version that produced it, so a rename there is traceable.

    ``confidence`` from §6.2 is also absent. A confirmed skill has no confidence
    score — a person said yes — and a column that stays NULL until M3 is shape
    with no use. I4 forbids surfacing a number with no breakdown behind it.
    """

    __tablename__ = "user_skills"
    __table_args__ = (
        UniqueConstraint("user_id", "normalized_name", name="uq_user_skills_user_id_name"),
        # This table is the confirmed side of the boundary. A pending fact
        # belongs in `resume_extractions`, so the value is refused here rather
        # than merely avoided by convention.
        CheckConstraint(
            "source_type <> 'inferred_pending_confirmation'",
            name="confirmed_only",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Casefolded, for the uniqueness constraint. "PostgreSQL" and "postgresql"
    #: are one skill.
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
    proficiency_level: Mapped[ProficiencyLevel] = mapped_column(
        _enum(ProficiencyLevel, "proficiency_level"),
        nullable=False,
        server_default=text("'unspecified'"),
    )
    source_type: Mapped[SkillSourceType] = mapped_column(
        _enum(SkillSourceType, "skill_source_type"), nullable=False
    )
    #: Where it came from, in a form a human can follow back:
    #: ``resume:<uuid>#214-229``, or ``manual``.
    source_reference: Mapped[str | None] = mapped_column(String(200))
    vocabulary_version: Mapped[str | None] = mapped_column(String(40))

    user: Mapped[User] = relationship(back_populates="skills")


class UserProject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """PRODUCT-SPEC §6.3. ``evidence`` is the text M3's evidence graph cites."""

    __tablename__ = "user_projects"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_projects_user_id_name"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    repository_url: Mapped[str | None] = mapped_column(String(500))
    demo_url: Mapped[str | None] = mapped_column(String(500))
    technologies: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    #: The literal bullets the claim rests on. M3 cites this rather than
    #: re-deriving anything, which is how a match explanation stays honest.
    evidence: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ProjectStatus] = mapped_column(
        _enum(ProjectStatus, "project_status"),
        nullable=False,
        server_default=text("'completed'"),
    )

    user: Mapped[User] = relationship(back_populates="projects")


class Resume(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """PRODUCT-SPEC §6.4, minus the file.

    **The uploaded bytes are never stored.** An upload is read in memory, its
    text extracted, and the bytes discarded; what survives is the filename, a
    hash of the *text*, and the text itself. This is the most personal data the
    project holds (§13) and the smallest honest footprint for it.

    ``content_hash`` is over ``parsed_text``, not over the file, so a PDF and a
    paste of the same content are one resume rather than two.

    ``structured_profile`` from §6.4 is deliberately absent: the proposals in
    ``resume_extractions`` *are* the structure, and they carry spans. A second
    denormalised copy could disagree with them.
    """

    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_resumes_user_id_content_hash"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    variant_type: Mapped[ResumeVariant] = mapped_column(
        _enum(ResumeVariant, "resume_variant"),
        nullable=False,
        server_default=text("'custom'"),
    )
    source_kind: Mapped[ResumeSourceKind] = mapped_column(
        _enum(ResumeSourceKind, "resume_source_kind"), nullable=False
    )
    #: Null for a paste, which has no file and should not pretend to.
    original_filename: Mapped[str | None] = mapped_column(String(300))
    parsed_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_default: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))

    extractions: Mapped[list[ResumeExtraction]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class ResumeExtraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A proposal awaiting a human decision. The pending side of invariant I2.

    Not in PRODUCT-SPEC. Justified by I2 and by ``command-center.md`` §2.2:
    keeping proposals in a different table from confirmed facts makes "no bug in
    the extractor can produce a confirmed fact" a property of the schema rather
    than a claim about every write path.

    Every row carries the span it came from, and a trigger
    (``resume_extractions_span_must_quote``) refuses any row whose span does not
    literally quote ``resumes.parsed_text``. So the highlight on the screen and
    the claim in the row cannot disagree — not by policy, by wiring.
    """

    __tablename__ = "resume_extractions"
    __table_args__ = (
        CheckConstraint("char_start >= 0", name="span_starts_in_the_text"),
        # "A proposal with no span is unrepresentable" (command-center.md §6.1).
        CheckConstraint("char_end > char_start", name="span_is_not_empty"),
        CheckConstraint(
            "(status = 'pending') = (decided_at IS NULL)",
            name="decided_rows_carry_a_time",
        ),
        Index("ix_resume_extractions_resume_id_status", "resume_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("resumes.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[ExtractionKind] = mapped_column(
        _enum(ExtractionKind, "extraction_kind"), nullable=False
    )
    #: The proposed fact, shaped by kind: ``{"name": "Python"}`` for a skill,
    #: ``{"year": 2027, "month": 5}`` for a graduation.
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The literal words. Redundant with the span on purpose: the trigger
    #: compares the two, which is what makes a fabricated quote impossible.
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[ExtractionStatus] = mapped_column(
        _enum(ExtractionStatus, "extraction_status"),
        nullable=False,
        server_default=text("'pending'"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    resume: Mapped[Resume] = relationship(back_populates="extractions")


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
        # M2a's filter set. Every one of these is a sequential scan without an
        # index, and `tests/test_query_plans.py` asserts each stays servable.
        Index("ix_jobs_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_jobs_title_vector", "title_vector", postgresql_using="gin"),
        Index("ix_jobs_employment_type", "employment_type"),
        Index("ix_jobs_remote_policy", "remote_policy"),
        Index("ix_jobs_first_seen_at", "first_seen_at"),
        Index("ix_jobs_salary_max", "salary_max"),
        # Both bounds, because the salary floor is an OR across the pair and
        # Postgres needs an index on each side to build a BitmapOr. With only
        # salary_max indexed the whole filter falls back to a sequential scan —
        # found by tests/test_query_plans.py, not by reading the code.
        Index("ix_jobs_salary_min", "salary_min"),
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

    # Full-text search, computed by Postgres rather than by us. STORED means it
    # is written on insert and update and read straight off the heap; the GIN
    # index in __table_args__ is what makes `@@` cheap.
    #
    # The regconfig is the literal 'english' rather than a column, because
    # to_tsvector is only IMMUTABLE — and therefore only legal in a generated
    # column — when the configuration is fixed at definition time.
    #
    # Typed Any, matching `geom` below: TSVECTOR has no Python equivalent and
    # annotating it `str` makes mypy strict reject the mapping.
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description_text, ''))",
            persisted=True,
        ),
        nullable=False,
    )

    # Title only, and it is the *default* search target. Measured on the
    # recorded Alloy board: searching the description for "developer" returns
    # all nine postings, because it stems to 'develop' and every description
    # says "business development" or "professional development" somewhere.
    #
    # That is not a bug in the index — it is what full-text search over long
    # documents does without relevance ranking to sort the noise down. Ranking
    # is M3 (PRODUCT-SPEC §24), so until it exists the honest default is the
    # field a person means when they type a job title, and `search_vector`
    # above is opt-in for the case where they want to find a rare term like
    # "Kubernetes" that only ever appears in the body.
    title_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(title, ''))", persisted=True),
        nullable=False,
    )

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
        # Expression index: the city filter compares lower(city), and a plain
        # btree on `city` cannot serve that.
        Index("ix_job_locations_city_lower", text("lower(city)")),
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


class BoardPollState(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What polling knows about one board. M1d, ADR 0007.

    ``data/board-registry.yaml`` stays the declarative source of *which* boards
    exist; this is runtime knowledge *about* them. Two separate tables of
    knowledge, and the name is chosen so they cannot be mistaken for each other:
    nothing here decides whether a board should be polled, only when it was and
    when it is next due.

    **Freshness for display reads from here, not from each posting.** A board
    that answers ``304`` for sixty days leaves its postings' ``last_seen_at``
    sixty days old while those postings are open and correctly so — no misses
    were taken. "How long since we actually heard from this board" is
    ``last_success_at`` on this row, and computing it from posting timestamps
    would report a healthy board as stale.
    """

    __tablename__ = "board_poll_state"
    __table_args__ = (
        # One row per board. Two would mean two schedules, double the requests
        # against one provider, and — once polling is queue-driven — two workers
        # writing the same ETag over each other. On the pair, not the token:
        # `ramp` on Ashby and `ramp` on Greenhouse are different employers.
        UniqueConstraint("ats", "token", name="uq_board_poll_state_ats_token"),
        # The scheduler's only query (design §7).
        Index("ix_board_poll_state_next_poll_at", "next_poll_at"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    ats: Mapped[str] = mapped_column(String(50), nullable=False)
    token: Mapped[str] = mapped_column(String(200), nullable=False)

    #: The last ETag the provider served for this board's listing. NULL means
    #: "never polled", which is different from "polled and served none" only in
    #: that both poll unconditionally — so one column says both honestly.
    #:
    #: 500 chars because the three providers measured 36, 37 and 78 (2026-08-02)
    #: and Ashby's is content-addressed, so it grows with whatever it hashes. A
    #: truncated ETag never matches, which means every poll is a full fetch and
    #: nothing anywhere says why.
    etag: Mapped[str | None] = mapped_column(String(500))
    #: ADR 0007: a stored ETag is only valid for the parser that earned it. When
    #: this differs from the adapter's current `parser_version` the ETag is
    #: discarded and the poll proceeds unconditionally — otherwise a parser
    #: change plus a provider that keeps answering 304 means the new parser
    #: never sees the payload it was written for, silently and indefinitely.
    parser_version: Mapped[str] = mapped_column(String(20), nullable=False)

    tier: Mapped[BoardTier] = mapped_column(
        _enum(BoardTier, "board_tier"),
        nullable=False,
        # Warm by default. Hot is earned from ingested postings; defaulting to
        # hourly would poll every discovered board 24x more than ADR 0007
        # budgeted for, against providers who have been generous with
        # unauthenticated access.
        server_default=BoardTier.WARM.value,
    )
    next_poll_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    #: Every poll, including the ones that failed and the ones that 304'd.
    last_polled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    #: Only a 200 or a 304 moves this. Kept separate from `last_polled_at`
    #: because a failing board is still polled, and collapsing the two makes
    #: "how long since this board actually answered" unanswerable — which is
    #: the one question the source health page exists to answer.
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_status: Mapped[int | None] = mapped_column(Integer)
    #: Cleared on success, so a stale error cannot outlive the failure.
    last_error: Mapped[str | None] = mapped_column(Text)
    #: Drives per-board backoff. A dead board pushes itself out and stops
    #: costing requests without anyone having to disable it — and keeps its
    #: registry entry, because A1 deletes nothing.
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    source: Mapped[Source] = relationship()


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per (user, job). Saving and tracking are the same object.

    PRODUCT-SPEC §10.1 lists ``saved`` as a stage, so there is no separate
    ``saved_jobs`` table: clicking Save creates this row at stage ``saved``.
    One row, one history, and no migration on the day a saved job becomes a
    real application.

    ``notes`` from §6.11 is deliberately **not** a column here. A note is a
    ``note_added`` event, which makes note history free and unrewritable
    (M2 design §2.4).

    ``selected_resume_id`` from §6.11 arrived in M2c, with the ``resumes`` table
    it points at — M2b deferred it because a nullable UUID with no foreign key
    is a dangling reference (CLAUDE.md §7: FKs everywhere).
    """

    __tablename__ = "applications"
    __table_args__ = (
        # A3: the key is (user, job), not job. Nothing here assumes one user.
        UniqueConstraint("user_id", "job_id", name="uq_applications_user_id_job_id"),
        Index("ix_applications_user_id_current_stage", "user_id", "current_stage"),
        # M2d's daily queue reads this column across the whole table.
        Index("ix_applications_next_action_at", "next_action_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # RESTRICT, not CASCADE: a job in somebody's pipeline must not vanish
    # because of a data-cleanup script. Jobs close; they are not deleted.
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="RESTRICT"), nullable=False
    )
    current_stage: Mapped[ApplicationStage] = mapped_column(
        _enum(ApplicationStage, "application_stage"),
        nullable=False,
        server_default=text("'saved'"),
    )
    priority: Mapped[ApplicationPriority] = mapped_column(
        _enum(ApplicationPriority, "application_priority"),
        nullable=False,
        server_default=text("'normal'"),
    )
    # Set by the user recording that they applied. Never set by the system.
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    next_action_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Where the user actually applied, which is not always our canonical_url.
    application_url: Mapped[str | None] = mapped_column(String(1000))
    source_of_application: Mapped[str | None] = mapped_column(String(200))
    # Archive is the only removal there is — see the model comment on
    # ApplicationEvent, and test_an_application_cannot_be_deleted_either.
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # SET NULL, not CASCADE: deleting a resume must not delete the application
    # it was attached to. The person keeps the application and loses only the
    # pointer, which is the honest outcome of removing the file.
    selected_resume_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL")
    )

    job: Mapped[Job] = relationship()
    events: Mapped[list[ApplicationEvent]] = relationship(
        back_populates="application", order_by="ApplicationEvent.occurred_at"
    )


class ApplicationEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only history of one application (§6.12).

    Enforced by trigger, per CLAUDE.md §7. Because the trigger fires on a
    cascading delete too, the parent application cannot be deleted either —
    which is the behaviour we want and is asserted by name.

    ``occurred_at`` is when the thing happened in the world and may be in the
    future: an ``interview_scheduled`` event carries the interview's time, which
    is what M2d's "interviews approaching" row reads. ``created_at`` is when we
    wrote the row. They are never merged.

    The column the spec calls ``metadata`` is named ``payload`` here.
    ``metadata`` is reserved on SQLAlchemy's declarative base and cannot be a
    mapped attribute.
    """

    __tablename__ = "application_events"
    __table_args__ = (
        Index(
            "ix_application_events_application_id_occurred_at",
            "application_id",
            "occurred_at",
        ),
        # M2d. The queue asks "when did this person last touch this
        # application?" across the whole table, and `actor` is not the leading
        # column of the index above. Partial, because system events are
        # deliberately excluded from that answer (command-center.md §7.2) and
        # indexing them would be dead weight.
        Index(
            "ix_application_events_user_activity",
            "application_id",
            "occurred_at",
            postgresql_where=text("actor = 'user'"),
        ),
        # M2d. "Interviews in the next fortnight" scans by time across every
        # application, so application_id being the leading column of the index
        # above makes it unusable here.
        Index(
            "ix_application_events_interviews",
            "occurred_at",
            postgresql_where=text("event_type = 'interview_scheduled'"),
        ),
        # Invariant I5, at the lowest level available. A system actor may record
        # a fact about the world; it may never move a stage.
        CheckConstraint(
            "to_stage IS NULL OR actor = 'user'",
            name="only_a_user_moves_a_stage",
        ),
        # A destination with no classification is half a transition.
        CheckConstraint(
            "(to_stage IS NULL AND transition_class IS NULL)"
            " OR (to_stage IS NOT NULL AND transition_class IS NOT NULL)",
            name="stage_fields_travel_together",
        ),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[ApplicationEventType] = mapped_column(
        _enum(ApplicationEventType, "application_event_type"), nullable=False
    )
    actor: Mapped[EventActor] = mapped_column(_enum(EventActor, "event_actor"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    # Null on the first stage change of an application's life for the same
    # reason JobStatusEvent.from_status is: it came from nothing.
    from_stage: Mapped[ApplicationStage | None] = mapped_column(
        _enum(ApplicationStage, "application_stage")
    )
    to_stage: Mapped[ApplicationStage | None] = mapped_column(
        _enum(ApplicationStage, "application_stage")
    )
    transition_class: Mapped[TransitionClass | None] = mapped_column(
        _enum(TransitionClass, "transition_class")
    )
    # The note, or the sentence explaining a system-recorded fact.
    body: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    #: `clock_timestamp()`, not `now()`. `now()` is the *transaction* timestamp
    #: and is identical for every row written in one transaction, so two events
    #: from a single request would be indistinguishable in write order and the
    #: timeline would fall back to ordering by a random UUID. Measured: three
    #: inserts in one transaction produce 1 distinct `now()` and 3 distinct
    #: `clock_timestamp()`. Every other table in this schema keeps `now()`,
    #: which is correct for them — this is the only append-only log where the
    #: order rows were written is itself the data.
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=text("clock_timestamp()")
    )

    application: Mapped[Application] = relationship(back_populates="events")
