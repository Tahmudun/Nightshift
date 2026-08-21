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
    Boolean,
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
    func,
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
    CaptureStatus,
    CredentialMethod,
    EligibilityState,
    EmploymentType,
    EventActor,
    EvidenceSource,
    ExtractionKind,
    ExtractionStatus,
    IngestionRunStatus,
    InternshipSeason,
    JobStatus,
    JobTextField,
    LocationConfidence,
    MatchComponent,
    PenaltyName,
    ProficiencyLevel,
    ProjectStatus,
    RemotePolicy,
    RemotePreference,
    RequirementKind,
    RequirementNecessity,
    ResolutionMethod,
    ResumeSourceKind,
    ResumeVariant,
    RoleFamily,
    Seniority,
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
        # A negative years figure would sail through the gate's `>=` comparison
        # and quietly pass every experience requirement. Rejected by the
        # database rather than by the form, per CLAUDE.md §7.
        CheckConstraint(
            "years_experience IS NULL OR years_experience >= 0",
            name="years_experience_is_not_negative",
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
    #: M3b. Both nullable, and null means "has not told us" — which the gate
    #: treats as `uncertain`, never as zero and never as false.
    #:
    #: Added because the gate asks five questions and `users` could answer three
    #: of them. Without these two, `_years_rule` and `_enrollment_rule` return
    #: `cannot_tell` for every real person forever, and the job page would print
    #: "tell us your years of experience" beside a profile that has nowhere to
    #: say it — a dead end, which is the M2c finding about a provenance link
    #: that 404s, one milestone on.
    #:
    #: Neither is ever inferred. `graduation_year` is right there and a
    #: subtraction would produce a plausible number for both, which is exactly
    #: what invariant I2 forbids: `domain/profile.py` stays the only writer and
    #: only a person may set them.
    years_experience: Mapped[int | None] = mapped_column(SmallInteger)
    is_enrolled: Mapped[bool | None] = mapped_column(Boolean)
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

    credentials: Mapped[list[UserCredential]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    skills: Mapped[list[UserSkill]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list[UserProject]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One way a person can prove they are themselves. ADR 0037.

    ``users`` has no ``password_hash`` column and never will. A credential is a
    row here, keyed by method, so the sign-in method can change without
    touching a single account: adding Google is an insert, not a migration, and
    a person who holds both rows may use either.

    The unique constraint is on ``(user_id, method)`` rather than on
    ``user_id``: one password per person, and one Google link per person, but
    not one credential per person.
    """

    __tablename__ = "user_credentials"
    __table_args__ = (
        UniqueConstraint("user_id", "method", name="uq_user_credentials_user_id_method"),
        # An empty secret would make `verify()` the only thing standing between
        # an account and anybody who asks for it. argon2 emits a long encoded
        # string; nothing legitimate is shorter than this.
        CheckConstraint("length(secret) >= 16", name="credential_secret_is_not_empty"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[CredentialMethod] = mapped_column(
        _enum(CredentialMethod, "credential_method"), nullable=False
    )
    #: For ``password``: the full argon2id encoded hash, salt and parameters
    #: included. Never the password, and never anything reversible.
    secret: Mapped[str] = mapped_column(String(255), nullable=False)

    user: Mapped[User] = relationship(back_populates="credentials")


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A signed-in browser or client. ADR 0037.

    **Sessions live in the database, not in a signed token.** A JWT cannot be
    revoked, and both "sign out everywhere" and account deletion have to
    actually end a session rather than wait for one to expire. The cost is a
    primary-key lookup per request on the one Postgres box CLAUDE.md §8 says is
    the answer.

    **The token is stored hashed**, so a database dump is a list of expiry
    times rather than a set of live logins. SHA-256 rather than argon2 —
    deliberately, and it is the opposite of the choice made for a password.
    A password is short and human-chosen, so slowness is the defence. This
    token is 256 bits from ``secrets``: there is no dictionary for it, nothing
    to slow down, and argon2 on every request would be a real cost buying
    nothing.

    **There is deliberately no ``last_seen_at``.** The first draft had one, for
    a future "signed in on these devices" screen. Resolving a session is a read
    path, and `get_db_session` commits nothing on a read path by design — so
    the column could only be written on requests that happened to commit for
    unrelated reasons. A column nobody can keep correct is worse than no
    column; M13 can add one alongside the write path that maintains it.
    """

    __tablename__ = "user_sessions"
    __table_args__ = (
        # Expiry is set from `created_at` at insert time; a row that expires
        # before it began is a clock or a caller bug, and it would be an
        # already-dead session rather than a loud failure.
        CheckConstraint("expires_at > created_at", name="session_expires_after_it_began"),
        Index("ix_user_sessions_user_id_expires_at", "user_id", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: SHA-256 of the bearer token, hex. Unique so a lookup is one index hit and
    #: so two sessions can never collide on a token.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    #: Set when somebody signs out. A revoked row is kept rather than deleted so
    #: "this session ended, deliberately" stays distinguishable from "this
    #: session was never here" — the same reasoning as invariant I3.
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class UserSkill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A skill the user **confirmed**. Never a proposal (invariant I2).

    ``confidence`` from §6.2 is deliberately absent. A confirmed skill has no
    confidence score — a person said yes — and a column that stays NULL until M3
    is shape with no use. I4 forbids surfacing a number with no breakdown behind
    it.
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
    #: §6.2's `skill_id`, deferred at M2c and made real by M3's taxonomy
    #: (`matching.md` §4.4). **It is the taxonomy's canonical name, and it is not
    #: a foreign key**, because the taxonomy is `data/skills.yaml` — a versioned
    #: file (CLAUDE.md §3) whose identifier for a skill *is* its canonical name,
    #: which is also what `job_requirements.value` stores. Mirroring that file
    #: into a `skills` table would create a second source of truth that can
    #: disagree with it, and inventing opaque slugs would create a second
    #: identifier space that has to be kept in step with the names the extractor
    #: already emits. If the taxonomy ever grows real ids, they land in this
    #: column and the change is a data migration over a table with a handful of
    #: rows.
    #:
    #: **Null is the load-bearing value.** `add_skill` accepts free text — a
    #: person may confirm a skill the vocabulary has never heard of — and null
    #: says exactly that: confirmed, and outside the taxonomy. Such a skill can
    #: never match a `job_requirements.value`, and the score has to say so rather
    #: than quietly resolve it to a neighbour.
    #:
    #: `normalized_name` stays beside it. A rename in the taxonomy must not
    #: orphan a fact a human confirmed, so the confirmed name is stored
    #: independently of whatever the vocabulary calls it today.
    skill_id: Mapped[str | None] = mapped_column(String(120), index=True)
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
    locations: Mapped[list[CompanyLocation]] = relationship(back_populates="company")


class CompanyLocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An office address a human confirmed. The only thing that can be a building.

    PRODUCT-SPEC §6.6 specified this table and nothing built it until M4a, when
    a census gave it a reason nobody had measured before: **no ATS posting names
    a street.** 0 of 247, across 139 distinct location strings, 10
    location-bearing fields and three providers — including Ashby's structured
    `address.postalAddress`, whose key set is only ever some subset of
    `{addressCountry, addressLocality, addressRegion}`.

    Under invariant I1 that settles the question of where a building comes from.
    A job can never place itself, because its own text tops out at a city name.
    So a beacon sits on a building only by inheriting the office of the company
    that posted it, and this table is the set of offices that exist.

    **Which is why the confirmation columns are not optional metadata.**
    `city.md` §4.4 rules out the alternatives: scraping is out on policy
    (`CLAUDE.md` §8), and OSM and Wikidata are of uneven quality and unknown
    currency — good enough to propose, never to confirm. A row here means a
    human wrote an address down. `confirmed_at` and `confirmed_by` are
    `NOT NULL` so that a row cannot exist without saying who vouched for it,
    which makes "a lit building is a verified fact" a property of the schema
    rather than a habit.

    This is the third instance of a pattern this project already runs twice:
    `source_job_records → jobs`, and `resume_extractions → ` confirmed user
    facts (ADR 0013). Proposal and confirmation live in different places, so no
    bug in a proposer can produce a confirmed address.
    """

    __tablename__ = "company_locations"
    __table_args__ = (
        Index("ix_company_locations_company_id", "company_id"),
        Index("ix_company_locations_geom", "geom", postgresql_using="gist"),
        Index("ix_company_locations_location_confidence", "location_confidence"),
        # One primary office per company. A second would make "the building" a
        # question the renderer has to answer arbitrarily.
        Index(
            "uq_company_locations_one_primary",
            "company_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
        # I1, identical to `job_locations`. Not shared via a mixin on purpose:
        # a constraint is worth reading at the table it protects, and the two
        # tables are free to diverge without one quietly loosening the other.
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
        # The claim this table exists to make. `verified` is what puts a beacon
        # on a specific building, and the only input that earns it is a street
        # address — §4.1 measured that a city name never can. Without this, a
        # row geocoded from "New York, NY" could be stored as `verified` and the
        # renderer would place it on whichever building the centroid landed in.
        CheckConstraint(
            "location_confidence <> 'verified' OR street_address IS NOT NULL",
            name="verified_requires_a_street_address",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # "New York HQ", "Brooklyn Navy Yard". Shown in the detail panel so a person
    # can tell two offices apart without reading two addresses.
    label: Mapped[str] = mapped_column(String(200), nullable=False)

    street_address: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
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

    # NYC's Building Identification Number, when the geocoder returned one.
    #
    # A4 assumed the footprint join would be computed in PostGIS — take the
    # point, find the polygon containing it. NYC GeoSearch returns the BIN in
    # the same response as the coordinates, so M4b's extrusion layer joins on a
    # key rather than guessing which of four abutting footprints a point fell
    # inside. Point-in-polygon stays available as the fallback for rows that
    # somehow have coordinates and no BIN.
    #
    # Nullable, and deliberately not part of the `verified` constraint: a real
    # address outside NYC would be `verified` with no BIN, and the day this
    # product covers a second city that has to still be true.
    building_id: Mapped[str | None] = mapped_column(String(20))

    # Who vouched for the address, and when. Not nullable: see the class
    # docstring. `confirmed_by` is free text rather than a user FK because the
    # curated file predates auth (A3) and "the file, at commit abc1234" is a
    # more useful provenance string than a single seeded dev_user id.
    confirmed_by: Mapped[str] = mapped_column(String(200), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)

    company: Mapped[Company] = relationship(back_populates="locations")


class GeocodeCache(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Every address ever geocoded, and what came back. Permanent.

    A4: *"Cache every geocode by normalized address string, permanently. Never
    re-geocode an address you have already resolved."* A table rather than an
    in-process dict, for two reasons that are not about speed. It has to survive
    a restart, and it has to be **inspectable** — when somebody says a beacon is
    on the wrong building, the question is what the provider actually returned
    for that string on that day, and a cache nobody can query cannot answer it.

    **A miss is cached. An outage is not.** This is invariant I3's reasoning
    applied one subsystem over. *"We asked and NYC has no such address"* is an
    answer, it will not change tomorrow, and re-asking it every poll is a
    request spent to learn nothing. *"The provider was unreachable"* is not an
    answer about the address at all — caching it would turn one bad afternoon
    into a permanent refusal to place a building that was always placeable.
    `refusal` is therefore nullable and never holds `provider_unavailable`,
    enforced by a check constraint rather than by remembering.
    """

    __tablename__ = "geocode_cache"
    __table_args__ = (
        # The lookup key. Unique per (address, rung): the same string may be
        # asked of GeoSearch and of Nominatim, and those are two different
        # answers worth keeping apart.
        Index(
            "uq_geocode_cache_query",
            "normalized_query",
            "resolution_method",
            unique=True,
        ),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name="coordinates_are_paired",
        ),
        # A row is either a hit or a miss, never both and never neither. Without
        # this, a bug that wrote a refusal alongside coordinates would produce a
        # row whose meaning depends on which column the reader looked at first.
        CheckConstraint(
            "(latitude IS NULL) <> (refusal IS NULL)",
            name="a_row_is_a_hit_or_a_miss",
        ),
        # The rule the class docstring argues for, made structural.
        CheckConstraint(
            "refusal IS NULL OR refusal <> 'provider_unavailable'",
            name="an_outage_is_never_cached",
        ),
    )

    #: Exactly what was asked, kept so the normalisation is auditable.
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    #: Casefolded, whitespace-collapsed. The key.
    normalized_query: Mapped[str] = mapped_column(String(500), nullable=False)

    resolution_method: Mapped[ResolutionMethod] = mapped_column(
        _enum(ResolutionMethod, "resolution_method"), nullable=False
    )

    latitude: Mapped[float | None] = mapped_column(NUMERIC(9, 6))
    longitude: Mapped[float | None] = mapped_column(NUMERIC(9, 6))
    location_confidence: Mapped[LocationConfidence | None] = mapped_column(
        _enum(LocationConfidence, "location_confidence")
    )
    building_id: Mapped[str | None] = mapped_column(String(20))
    #: What the provider said it matched. The first thing to look at when a
    #: placement is disputed.
    matched_text: Mapped[str | None] = mapped_column(String(500))

    #: Why nothing was found, for a miss. Null on a hit.
    refusal: Mapped[str | None] = mapped_column(String(50))

    resolved_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)


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
    # Populated by M3b's classifier. Still nullable, and **null keeps meaning
    # "not yet classified"** — distinct from `unclear`, which is the classifier
    # having read the posting and declined to guess. Merging those two would
    # make the coverage figure unreadable: you could not tell an unrun
    # classifier from a corpus full of ambiguous titles.
    #
    # PG enums as of M3b rather than `String(100)`, per CLAUDE.md §7. The
    # strings were a placeholder from M1 and nothing had written one, so the
    # migration converts two empty columns.
    role_family: Mapped[RoleFamily | None] = mapped_column(_enum(RoleFamily, "role_family"))
    seniority: Mapped[Seniority | None] = mapped_column(_enum(Seniority, "seniority"))
    # Two columns rather than PRODUCT-SPEC §6.9's single `internship_season`,
    # and the corpus is the reason: two of its nineteen internships state a
    # year and no season, so a combined `summer_2027` could keep them only by
    # inventing the season or discarding the year. The spec's word is kept for
    # the season itself, which is what the word means.
    #
    # Null on every non-internship posting, always — the season is gated on
    # `is_internship`, because six non-internship titles in the corpus carry a
    # season or a year and reading any of them would be wrong.
    internship_season: Mapped[InternshipSeason | None] = mapped_column(
        _enum(InternshipSeason, "internship_season")
    )
    #: SmallInteger: a calendar year needs two bytes, and a column typed wider
    #: than its domain is one that will eventually hold something else.
    internship_year: Mapped[int | None] = mapped_column(SmallInteger)
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
    requirements: Mapped[list[JobRequirement]] = relationship(
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


class JobRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What a posting asks for, and the characters where it says so.

    **Invariant I2 does not govern this table**, though it looks like it should.
    I2 is about claims regarding a *person's* qualifications, which is why
    `resume_extractions` proposes and never confirms. A job requirement is a
    claim about a *posting*, checkable against a payload committed in the same
    repository. It needs no confirmation step.

    It still quotes its span, enforced by trigger, because a requirement nobody
    can trace back to a sentence is not auditable — and the job page shows the
    sentence rather than asking anyone to trust a summary.
    """

    __tablename__ = "job_requirements"
    __table_args__ = (
        Index("ix_job_requirements_job_id", "job_id"),
        # The extractor emits one row per (kind, value, span). A second run over
        # unchanged text must not double the rows.
        UniqueConstraint("job_id", "kind", "value", "char_start", name="uq_job_requirements_span"),
        CheckConstraint("char_start >= 0", name="char_start_is_not_negative"),
        CheckConstraint("char_end > char_start", name="span_runs_forwards"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[RequirementKind] = mapped_column(
        _enum(RequirementKind, "requirement_kind"), nullable=False
    )
    #: Normalized: a skill name from `data/skills.yaml`, a year range, an integer
    #: as a string. `raw_text` is what the posting actually said.
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_text: Mapped[str] = mapped_column(String(500), nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    necessity: Mapped[RequirementNecessity] = mapped_column(
        _enum(RequirementNecessity, "requirement_necessity"), nullable=False
    )
    #: "or equivalent experience". A13: this is not a hard blocker, and M3b's
    #: gate must resolve it to `uncertain` rather than `ineligible`.
    has_equivalence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    extractor_version: Mapped[str] = mapped_column(String(40), nullable=False)

    job: Mapped[Job] = relationship(back_populates="requirements")


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


class MatchResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One score, decomposed into the six components that produced it (§6.13).

    **Invariant I4 is the whole shape of this table.** The components are
    columns rather than a JSON blob because a component with no evidence row is
    refused at commit by `match_results_component_needs_evidence`, and a trigger
    cannot reason about a blob's keys. A bare number is a bug; a number that
    cannot be stored without its parts is the fix.

    Three deliberate departures from §6.13, each named so none of them looks
    like an oversight:

    * **`explanation` is not here.** §6.13 lists it and `matching.md` §6 says no
      explanation text is generated — every line is assembled from
      `match_evidence` rows at render time. A stored copy is a second version of
      the same claim that can disagree with the rows, which is why `resumes`
      dropped §6.4's `structured_profile` at M2c for the same reason. It is also
      precisely the failure §2.2 forbids: text written after the fact to justify
      a number that did not come from it.
    * **`penalty_score` is one column, not two.** §5.1 keeps two penalties and
      this stores their sum, because the trigger that binds a component to its
      evidence binds the six positive components (§4.3's enum has no penalty
      member) and a split column would imply an evidence link that does not
      exist. What each penalty cost is `match_evidence`'s business at Task 5 or
      the explanation's; what the score owes them is one number.
    * **`eligibility_status` sits beside the score and is never inside it**
      (§5.2). A job can be an 82 and `uncertain`, and this row shows both
      without reconciling them.

    **A stale row is never served.** `ruleset_version` is `"<logic>+<data>"`
    (`matching_weights.ruleset_version()`), and the API refuses any row whose
    version is not the current one, reporting it as not-yet-computed. Rows are
    also *deleted* — not updated — whenever an input moves: four triggers watch
    `jobs.description_text`, `job_requirements`, `user_skills` and
    `user_projects`. An absent score is honest; a score computed under rules
    that no longer exist is not.
    """

    __tablename__ = "match_results"
    __table_args__ = (
        # §4.2. One row per (person, job, ruleset), so a version bump computes
        # alongside rather than overwriting what it is being compared against.
        UniqueConstraint(
            "user_id", "job_id", "ruleset_version", name="uq_match_results_user_job_ruleset"
        ),
        # The ranked query: one person's corpus, best first, within a band.
        Index("ix_match_results_user_ranking", "user_id", "eligibility_status", "overall_score"),
        CheckConstraint(
            "role_score >= 0 AND skill_score >= 0 AND project_evidence_score >= 0"
            " AND location_score >= 0 AND freshness_score >= 0 AND priority_score >= 0",
            name="components_are_not_negative",
        ),
        # A penalty that adds points is the arithmetic saying the opposite of
        # what the word means. The ceilings live in `data/matching.yaml`; that
        # this is a subtraction is not a tunable.
        CheckConstraint("penalty_score <= 0", name="a_penalty_never_adds"),
        # **The total is its parts.** Not a restatement of the scorer — it is the
        # assertion I4 rests on, and without it "every score decomposes" is a
        # property of whichever function last wrote the row. The floor at zero is
        # the one policy inside it: components reach 100 and penalties reach -55,
        # so a score can go negative in arithmetic and cannot in meaning. Changing
        # that floor is a change in what the number *is* and costs a migration,
        # which is the right price for it.
        CheckConstraint(
            "overall_score = GREATEST(0, role_score + skill_score + project_evidence_score"
            " + location_score + freshness_score + priority_score + penalty_score)",
            name="the_total_is_its_parts",
        ),
        # `assessed_out_of` is the sum of the weights of the components that
        # could be assessed, and the weights sum to 100 by an assertion in
        # `matching_weights` that Task 1 showed able to fail. Zero is legal and
        # is not a degenerate case: five pairs in the committed corpus reach it,
        # and they are the pairs where nothing could be asked at all.
        CheckConstraint(
            "assessed_out_of >= 0 AND assessed_out_of <= 100",
            name="assessed_out_of_is_a_share_of_one_hundred",
        ),
        # **The fraction can never exceed one.** Each component is capped at its
        # own weight and only assessable components contribute, so the numerator
        # is bounded by the denominator before the penalties — which only
        # subtract — are applied. Written as a constraint rather than trusted
        # because it is the one arithmetic claim the ranked list depends on: a
        # posting sorting above a perfect match would come from exactly this
        # inequality quietly failing, and nothing else in the row would look
        # wrong. It also catches the specific mistake of storing a denominator
        # from one weights version beside a total from another.
        CheckConstraint(
            "overall_score <= assessed_out_of",
            name="a_score_never_exceeds_what_was_assessed",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: §6.13. Which stored resume best covers the required set (`matching.md`
    #: §6). Null until there is a resume to recommend, and `SET NULL` on delete
    #: because losing a resume must not delete the score computed beside it.
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL")
    )
    overall_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: What `overall_score` is out of (`matching.md` §5.1.1, §5.1.2). **Not
    #: always 100**, and not recoverable from the six component columns: a
    #: component that scored zero and a component the posting said too little to
    #: assess both store `0`, and telling those apart is the entire content of
    #: §5.1.1. The ranked list sorts on `overall_score / assessed_out_of`, so the
    #: denominator is part of the value a sort needs in the database — which is
    #: the same argument §4.2 used to precompute the score at all.
    #:
    #: `overall_score` stays the literal sum of the parts. Normalising the
    #: stored total to 100 would break `the_total_is_its_parts` and destroy the
    #: distinction that constraint exists to preserve; the fraction is a division
    #: the query performs, never a number written down.
    assessed_out_of: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    eligibility_status: Mapped[EligibilityState] = mapped_column(
        _enum(EligibilityState, "eligibility_state"), nullable=False
    )
    role_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    skill_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    project_evidence_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    location_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    freshness_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    priority_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    #: The two §5.1 penalties, summed. Zero or negative.
    penalty_score: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    #: The embedding that produced the proposals on this row's evidence, or null
    #: when no proposal touched it. Null is the honest value for a rules-only
    #: score and is what every row carries until Task 11 exists.
    model_version: Mapped[str | None] = mapped_column(String(80))
    #: `"<logic>+<data>"`. One column covering both, because M3's acceptance
    #: criterion is *identical inputs + identical ruleset_version → identical
    #: output* and two columns would let a rule move while the weights version
    #: stayed put (§4.2).
    ruleset_version: Mapped[str] = mapped_column(String(80), nullable=False)

    evidence: Mapped[list[MatchEvidence]] = relationship(
        back_populates="match_result", cascade="all, delete-orphan"
    )
    assessments: Mapped[list[MatchComponentAssessment]] = relationship(
        back_populates="match_result", cascade="all, delete-orphan"
    )
    penalties: Mapped[list[MatchPenalty]] = relationship(
        back_populates="match_result", cascade="all, delete-orphan"
    )


class MatchPenalty(UUIDPrimaryKeyMixin, Base):
    """What each of the two subtractions cost, and why.

    Added at M3c Task 10, and it is `MatchComponentAssessment`'s argument one row
    down. §4.2 stores the two §5.1 penalties as **one** column and that decision
    stands — `match_evidence.component` has no penalty member, so a split score
    column would imply an evidence link that does not exist, and
    `the_total_is_its_parts` still adds `penalty_score` exactly once.

    What §4.2 left to somebody else is *"what each penalty cost belongs to the
    explanation"*, and nothing carried it. A reader saw `-18` with no way to learn
    that 12 of it was three unmet technologies and 6 was a title pitched above
    their stated years. That is invariant I4's *"stores its components, **its
    penalties**"* going unmet in the one place a person reads.

    **Not the `explanation` column §4.2 refused.** `why` is
    `penalize_missing_requirements`'s own sentence, returned by the same call and
    from the same inputs as the points beside it — a sibling of the number, not a
    summary of it. Re-deriving it at render time is the second-derivation failure
    `matching.posting_for` documents.

    **Both rows always exist**, applicable or not, and the trigger asserts it.
    *"There was nothing to ask"* and *"nothing was missing"* are different
    sentences and both are worth printing; a row that is simply absent prints
    neither while `penalty_score` still adds up.
    """

    __tablename__ = "match_penalties"
    __table_args__ = (
        # What makes "exactly two rows" a count rather than a set comparison, and
        # what makes the count mean anything at all given `PenaltyName` closes the
        # column's domain.
        UniqueConstraint("match_result_id", "name", name="uq_match_penalties_result_name"),
        # The assertion `match_results.a_penalty_never_adds` makes about the
        # total, made about the part.
        CheckConstraint("points <= 0", name="a_penalty_never_adds"),
        CheckConstraint("applicable OR points = 0", name="an_inapplicable_penalty_costs_nothing"),
        CheckConstraint("length(btrim(why)) > 0", name="a_reason_is_never_blank"),
    )

    match_result_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[PenaltyName] = mapped_column(_enum(PenaltyName, "penalty_name"), nullable=False)
    #: Zero or negative, and zero has two meanings the row keeps apart with
    #: `applicable`: nothing was missing, versus there was nothing to ask.
    points: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    applicable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: The rule's own sentence — "2 of 5 required technologies have no evidence",
    #: "this profile states no years of experience". Rendered verbatim.
    why: Mapped[str] = mapped_column(Text, nullable=False)
    #: What the rule weighed: the required list and the unmet subset, or the
    #: title's implied years against the stated ones. §6's *"why it may not fit"*
    #: is read from here rather than re-derived on the page, so the list a person
    #: is shown is the list the subtraction was computed from.
    compared: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    match_result: Mapped[MatchResult] = relationship(back_populates="penalties")


class MatchComponentAssessment(UUIDPrimaryKeyMixin, Base):
    """What each of the six components has to say for itself.

    Added at M3c Task 9, when a score first had a *reader*. `matching.md` §5.1.1
    requires the page to name the components that could not be assessed **and
    why**, and neither half of that survives in `match_results` alone:

    * **`assessable` is not recoverable from the points.** A component that
      scored zero and a component the posting said too little to assess both
      store `0` in their score column — that indistinguishability is the entire
      content of §5.1.1, and `assessed_out_of` does not resolve it either,
      because the six weights (20, 30, 20, 10, 10, 10) have several subsets
      summing to the same number.
    * **`why` is the only sentence the component ever produces.** The three
      exempt components record their compared values in `match_evidence.compared`
      and quote nobody; an assessable component that scored zero has no evidence
      row at all. Without this column those components reach the page as a bare
      number, which is I4 one level down from the total.

    **This is not the `explanation` column §4.2 refused**, and the difference is
    where the text comes from rather than how long it is. That column would have
    held a narrative assembled *from* `match_evidence`, so it could disagree with
    the rows it was built from. `why` is the scoring rule's own output, returned
    by the same call and from the same inputs as the points beside it — a sibling
    of the evidence rows, not a summary of them. The alternative is re-running the
    scorer at render time, which is a second derivation that can disagree with the
    stored number: the failure `matching.posting_for` documents, one table over.

    **Six rows, exactly, one per component**, enforced at commit by
    `match_results_components_are_assessed` — the database's copy of
    `MatchScore.__post_init__`. Five components sum to a smaller total *and* a
    smaller denominator, so the fraction still looks plausible and nothing
    downstream notices.
    """

    __tablename__ = "match_component_assessments"
    __table_args__ = (
        # One statement per component per score. The unique constraint is what
        # makes "exactly six rows" checkable as a count rather than as a set
        # comparison.
        UniqueConstraint(
            "match_result_id", "component", name="uq_match_component_assessments_result_component"
        ),
        # §5.1.1 asks for the reason, not for the fact that there is one. A blank
        # `why` renders as a component that could not be assessed for no stated
        # reason, which is the shape of a page nobody can check.
        CheckConstraint("length(btrim(why)) > 0", name="a_reason_is_never_blank"),
    )

    match_result_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False
    )
    component: Mapped[MatchComponent] = mapped_column(
        _enum(MatchComponent, "match_component"), nullable=False
    )
    #: False means *the posting did not say enough to ask the question*, and it
    #: is never the same statement as zero points. The trigger asserts the one
    #: direction that is checkable in SQL: an unassessable component scored
    #: nothing.
    assessable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    #: The rule's own sentence — "3 of 5 required technologies confirmed",
    #: "this source gave no publication date". Rendered verbatim; nothing
    #: paraphrases it.
    why: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    match_result: Mapped[MatchResult] = relationship(back_populates="assessments")


class MatchEvidence(UUIDPrimaryKeyMixin, Base):
    """One link a score rests on: what the posting said, and what the person has.

    `matching.md` §4.3. Two guards in the database, in two tiers, and they guard
    different things:

    1. **Every positive component has a row here.** A deferrable constraint
       trigger on `match_results`, checked at commit, plus a matching one here so
       deleting the last row for a component fails the same way. This is what
       makes "a score with no evidence cannot be committed" true of the schema
       rather than of the code that happens to write it.
    2. **Every claim about the person quotes both sides.** A check constraint:
       `role`, `skill` and `project` rows must carry `job_span_text` *and*
       `user_span_text`. `location`, `freshness` and `priority` may not — they
       compare a posting's own values against a stated preference and assert
       nothing about anybody's qualifications, so there is no user-side span to
       quote and requiring one would mean inventing one (§2.1).

    The job-side span is stored with its offsets and refused by
    `match_evidence_span_must_quote` if it does not literally quote
    `jobs.description_text`, the same trigger pattern `job_requirements` and
    `resume_extractions` carry. The offsets live here rather than being read
    through `job_requirement_id` because Task 11's embedding proposals point at
    spans that are not requirement rows at all.

    No timestamps beyond `created_at`: a row is written with its score and dies
    with it. There is nothing here to update.
    """

    __tablename__ = "match_evidence"
    __table_args__ = (
        Index("ix_match_evidence_match_result_id_component", "match_result_id", "component"),
        # Tier 2 of §4.3, in two halves, and the reason it is a CHECK rather
        # than a convention: a `skill` row with a null `user_span_text` is a
        # claim about a person with nothing quoted behind it, which is invariant
        # I2 failing quietly.
        CheckConstraint(
            "component NOT IN ('role', 'skill', 'project')"
            " OR (job_span_text IS NOT NULL AND user_span_text IS NOT NULL)",
            name="a_person_claim_quotes_both_sides",
        ),
        # The other half, and it was written second because a test found it
        # missing. The single biconditional this replaces — `component IN (...)
        # = (both spans non-null)` — passes a `freshness` row carrying a
        # user-side span and no job span, because both sides of it are then
        # false. That row is a quotation of somebody's own words filed under a
        # component that makes no claim about them, which is a fabricated claim
        # wearing an exempt label, and M3d's hallucination check would then have
        # to go looking for it in confirmed data.
        #
        # A *job*-side span on an exempt component stays legal on purpose: the
        # priority component reads the posting's own seniority and quoting the
        # sentence it read is more auditable, not less. Only the user side is
        # restricted, because only the user side is a claim about a person.
        CheckConstraint(
            "component IN ('role', 'skill', 'project') OR user_span_text IS NULL",
            name="only_a_person_claim_quotes_a_person",
        ),
        # The job-side span travels as a unit: text and both offsets, or none of
        # the three. Half a span cannot be checked against anything.
        CheckConstraint(
            "(job_span_text IS NULL) = (job_char_start IS NULL)"
            " AND (job_char_start IS NULL) = (job_char_end IS NULL)"
            # Added at Task 8 with the column. The field is the fourth part of
            # the same unit: offsets with no field name are offsets into an
            # unknown string, which the quoting trigger cannot check and a human
            # reading the row cannot resolve either.
            " AND (job_char_end IS NULL) = (job_span_field IS NULL)",
            name="the_job_span_travels_together",
        ),
        CheckConstraint(
            "job_char_start IS NULL OR job_char_start >= 0",
            name="job_char_start_is_not_negative",
        ),
        CheckConstraint(
            "job_char_end IS NULL OR job_char_end > job_char_start",
            name="the_job_span_runs_forwards",
        ),
        # Points are what this row justifies. A negative one would mean evidence
        # arguing against the component it is filed under; penalties are a column
        # on `match_results` and are not evidenced here (§4.3's enum has no
        # penalty member).
        CheckConstraint("points >= 0", name="evidence_never_subtracts"),
    )

    match_result_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False
    )
    component: Mapped[MatchComponent] = mapped_column(
        _enum(MatchComponent, "match_component"), nullable=False
    )
    #: The requirement this row answers, when there is one. `CASCADE`: a
    #: requirement that no longer exists cannot go on being cited. Deleting one
    #: also deletes the whole score, via
    #: `job_requirements_change_clears_match_results` — so this cascade is a
    #: belt-and-braces guard rather than the mechanism.
    job_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("job_requirements.id", ondelete="CASCADE")
    )
    #: The words in the posting, and where they are. Null for the three exempt
    #: components, which quote nothing and record their compared values in
    #: `compared` instead.
    job_span_text: Mapped[str | None] = mapped_column(Text)
    #: Which string the offsets index into, added at Task 8 when the first score
    #: reached the database. `description_text` for every component but one;
    #: role relevance is decided on the **title** and its offsets are meaningless
    #: against the description. Without this the quoting trigger checks one
    #: column for spans that come from two, and rejects every correct role row.
    job_span_field: Mapped[JobTextField | None] = mapped_column(
        _enum(JobTextField, "job_text_field")
    )
    job_char_start: Mapped[int | None] = mapped_column(Integer)
    job_char_end: Mapped[int | None] = mapped_column(Integer)
    user_skill_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_skills.id", ondelete="CASCADE")
    )
    user_project_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user_projects.id", ondelete="CASCADE")
    )
    #: The words in the user's own **confirmed** data — never
    #: `resume_extractions`, which holds proposals. M3d's hallucination check is
    #: an equality over this column and that one is the substrate it must not be
    #: found in.
    user_span_text: Mapped[str | None] = mapped_column(Text)
    #: What the two exempt sides actually were: `{"job": "New York, NY",
    #: "preference": "hybrid"}`. §2.1 exempts these components from quoting a
    #: user-side span because there is no claim about the person to quote — it
    #: does not exempt them from being inspectable, which is what I4 needs.
    compared: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    proposed_by: Mapped[EvidenceSource] = mapped_column(
        _enum(EvidenceSource, "evidence_source"),
        nullable=False,
        server_default=text("'rule'"),
    )
    #: The contribution this row justifies. Deliberately **not** constrained to
    #: sum to its component's score: a component is capped at its weight while
    #: the evidence under it may propose more, so an equality here would be
    #: wrong the first time a cap bites. The relationship between the two is a
    #: scoring rule and is asserted in the scoring tests, where the cap lives.
    points: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=False, server_default=func.now()
    )

    match_result: Mapped[MatchResult] = relationship(back_populates="evidence")


class CapturedPosting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A posting a person handed us, before anybody agreed it is real.

    M5a / AMENDMENTS A16. Every other row in ``source_job_records`` arrived
    because a provider served it at a URL we can go back to. This one arrived
    because somebody pasted it, which changes two things and only two:

    1. **Nothing can re-read it.** There is no board to poll, so freshness and
       closure have no signal here. I3 already says silence is not evidence a
       job closed; for a captured posting silence is *all there is*.
    2. **The parse can be wrong in a way a provider's JSON cannot.** Greenhouse
       tells us which string is the company. Pasted text does not, and guessing
       wrong is not a cosmetic error: a company name resolves to a company,
       which resolves to that company's confirmed office, which puts a beacon
       on a **building**. A misparsed employer is invariant I1 violated through
       the side door, so no proposed field is trusted until a person confirms.

    ``proposed_*`` is what the parser offered and what the form was seeded
    with. It is **not** what got created — confirmation submits the values the
    person actually approved, and those go straight to the normalizer. These
    columns are kept so a bad parse is diagnosable after the fact rather than
    overwritten by the correction.

    **Why this does not mirror ``resume_extractions``.** That table stores one
    row per extracted fact with a span, and a trigger that refuses a row whose
    span does not literally quote the résumé. It earns that machinery because a
    résumé yields dozens of facts a person accepts individually against a
    highlighted document. A capture is one short form reviewed against text the
    person pasted seconds ago and can still see. The guarantee that matters is
    identical and is enforced here by ``confirmed_rows_carry_a_job``: a row
    cannot claim to be confirmed without pointing at the job it produced, and
    cannot point at a job without being confirmed.

    The capture is user-owned; the **job it produces is not**. A posting is
    public information and the corpus is shared, exactly as it is for polled
    boards. What stays private is the application — that lives in
    ``applications`` behind a ``user_id``, and nothing here changes it.
    """

    __tablename__ = "captured_postings"
    __table_args__ = (
        CheckConstraint("length(btrim(raw_text)) > 0", name="capture_has_text"),
        CheckConstraint(
            "(status = 'confirmed') = (job_id IS NOT NULL)",
            name="confirmed_rows_carry_a_job",
        ),
        CheckConstraint(
            "(status = 'pending') = (decided_at IS NULL)",
            name="decided_rows_carry_a_time",
        ),
        Index("ix_captured_postings_user_id_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Verbatim, exactly as pasted. The same contract as
    #: ``source_job_records.raw_payload``: the parse is always re-derivable, so
    #: a parser bug is a backfill rather than "ask the user to paste it again".
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Where the person says it came from. Never fetched — see the class note.
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    status: Mapped[CaptureStatus] = mapped_column(
        _enum(CaptureStatus, "capture_status"),
        nullable=False,
        server_default=CaptureStatus.PENDING.value,
    )

    #: What the parser offered. NULL means it declined to guess, which is a
    #: real answer and the one the parser is biased toward.
    proposed_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    proposed_company_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    proposed_location_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: Pinned so a proposal can be judged against the parser that made it.
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)

    job_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
