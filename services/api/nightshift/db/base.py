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


class ApplicationStage(enum.StrEnum):
    """PRODUCT-SPEC §10.1's ten stages, in their default order.

    ``discovered`` is unreachable in M2: nothing enters the pipeline without a
    click, so every application starts at ``saved``. The value exists because
    M3's matching engine will put roles here on the user's behalf, and adding
    an enum value later is a migration.
    """

    DISCOVERED = "discovered"
    SAVED = "saved"
    PREPARING = "preparing"
    APPLIED = "applied"
    ASSESSMENT = "assessment"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    CLOSED = "closed"


class ApplicationPriority(enum.StrEnum):
    """The user's own ranking. Never computed — that would be I4's problem."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class TransitionClass(enum.StrEnum):
    """How a stage change relates to the default order (§3 of the M2 design)."""

    ADVANCE = "advance"
    CORRECTION = "correction"
    REOPEN = "reopen"


class EventActor(enum.StrEnum):
    """Who caused an event. Invariant I5 turns on this column.

    A ``system`` actor may record a fact about the world — a listing closed —
    and may never move a stage. That is a check constraint on
    ``application_events``, not a convention.
    """

    USER = "user"
    SYSTEM = "system"


class ApplicationEventType(enum.StrEnum):
    """The eight kinds of thing M2b actually writes.

    **This deliberately diverges from PRODUCT-SPEC §6.12's example list**, which
    is mostly stage names (``applied``, ``rejected``, ``offer_received``). A
    stage change already records ``from_stage``, ``to_stage`` and
    ``transition_class``, so mirroring each stage as an event type would give
    two representations of one fact and let them disagree. ADR 0012 records the
    decision.

    Nothing is listed here that M2b does not write. M7's Gmail classifications
    add their values with a migration, when there is code to write them.
    """

    SAVED = "saved"
    STAGE_CHANGED = "stage_changed"
    NOTE_ADDED = "note_added"
    DETAIL_UPDATED = "detail_updated"
    INTERVIEW_SCHEDULED = "interview_scheduled"
    ARCHIVED = "archived"
    RESTORED = "restored"
    LISTING_CLOSED = "listing_closed"


class WorkAuthorization(enum.StrEnum):
    """A claim about legal status, and therefore never inferred (I2).

    The resume extractor has no member for this and no rule that could produce
    one — ``ExtractionKind`` below deliberately omits it. ``unspecified`` is the
    default and the honest answer until a person picks another in a form.
    """

    UNSPECIFIED = "unspecified"
    US_CITIZEN = "us_citizen"
    PERMANENT_RESIDENT = "permanent_resident"
    F1_STUDENT = "f1_student"
    OTHER_AUTHORIZED = "other_authorized"
    NEEDS_SPONSORSHIP = "needs_sponsorship"


class RemotePreference(enum.StrEnum):
    """The user's own preference. Distinct from a job's ``RemotePolicy``."""

    NO_PREFERENCE = "no_preference"
    ON_SITE = "on_site"
    HYBRID = "hybrid"
    REMOTE = "remote"


class ProficiencyLevel(enum.StrEnum):
    """Only the user sets this. Nothing reads a level off a resume — a page
    cannot show how well somebody knows a thing (I2)."""

    UNSPECIFIED = "unspecified"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class SkillSourceType(enum.StrEnum):
    """PRODUCT-SPEC §6.2's list.

    ``inferred_pending_confirmation`` exists here and is **refused** by a check
    constraint on ``user_skills``: that table holds confirmed facts only, and a
    pending one belongs in ``resume_extractions``. The value is kept so the
    refusal is expressible rather than implicit — the same reason
    ``LocationConfidence`` keeps ``unknown``.
    """

    MANUAL = "manual"
    RESUME = "resume"
    PROJECT = "project"
    COURSEWORK = "coursework"
    ASSESSMENT = "assessment"
    GITHUB = "github"
    INFERRED_PENDING_CONFIRMATION = "inferred_pending_confirmation"


class ProjectStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ResumeSourceKind(enum.StrEnum):
    """How the text arrived. Matches ``resume_text.ResumeFormat`` exactly, and
    a test asserts the two sets are equal — a drift would store a
    ``source_kind`` nothing can read back."""

    PASTE = "paste"
    TXT = "txt"
    PDF = "pdf"


class ResumeVariant(enum.StrEnum):
    """PRODUCT-SPEC §6.4's variants. The user picks; nothing classifies."""

    GENERAL_SWE = "general_swe"
    BACKEND = "backend"
    FULL_STACK = "full_stack"
    DATA_ML = "data_ml"
    INFRASTRUCTURE = "infrastructure"
    CUSTOM = "custom"


class ExtractionKind(enum.StrEnum):
    """What a proposal is about. Matches ``resume_extraction.ProposalKind``.

    There is no member for work authorization, seniority, or years of
    experience, and adding one is a migration — which is the point (I2).
    """

    SKILL = "skill"
    GRADUATION = "graduation"
    DEGREE = "degree"
    SCHOOL = "school"
    PROJECT = "project"


class ExtractionStatus(enum.StrEnum):
    """A proposal is pending until a person decides. Nothing else decides."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class RequirementKind(enum.StrEnum):
    """What a posting is asking for. Each value is something a rule can find.

    Deliberately absent: anything about culture, drive, or "passion". A rule
    cannot find those and a score built on them would be taste wearing a
    number's clothes.
    """

    DEGREE = "degree"
    GRADUATION_WINDOW = "graduation_window"
    YEARS_EXPERIENCE = "years_experience"
    TECHNOLOGY = "technology"
    AUTHORIZATION = "authorization"
    ENROLLMENT = "enrollment"
    ROLE_LEVEL = "role_level"


class RequirementNecessity(enum.StrEnum):
    """How hard the ask is. `matching.md` §4.1: this is the column the product
    turns on.

    Only ``required`` may produce a missing-requirement penalty or appear as a
    gap. Ramp's Android internship lists nine technologies under "nice to
    haves"; treating those as required reports nine false gaps against a
    candidate who is fully qualified.
    """

    REQUIRED = "required"
    PREFERRED = "preferred"
    MENTIONED = "mentioned"


class RoleFamily(enum.StrEnum):
    """What kind of work a posting is for. M3b.

    The human's decision on 2026-08-05: the tech families, plus an explicit
    ``NOT_TECH``, plus ``UNCLEAR``. Those last two are the design. Collapsed
    into one value, a rise in ``unclear`` could mean the corpus gained
    non-engineering postings or the classifier got worse, and there would be no
    way to tell which — so a number that is supposed to measure the classifier
    would measure the market instead.

    ``HARDWARE`` was added while labeling, from two FPGA and low-latency roles
    in the corpus that ``NOT_TECH`` would misdescribe and ``INFRASTRUCTURE``
    would blur. Recorded in `eligibility_labels.ROLE_FAMILY_VALUES`, which is
    the vocabulary this enum is asserted equal to.
    """

    SOFTWARE_ENGINEERING = "software_engineering"
    DATA_ENGINEERING = "data_engineering"
    ML_AI = "ml_ai"
    INFRASTRUCTURE = "infrastructure"
    SECURITY = "security"
    QUANT_TRADING = "quant_trading"
    HARDWARE = "hardware"
    PRODUCT = "product"
    DESIGN = "design"
    #: Read, and deliberately outside this product's scope.
    NOT_TECH = "not_tech"
    #: Could not decide. Never a default, and never what an unclassified job
    #: gets — a job the classifier has not seen has ``role_family IS NULL``.
    UNCLEAR = "unclear"


class Seniority(enum.StrEnum):
    """The level a posting is pitched at. M3b.

    Harvested from the 60 labeled titles rather than invented — the lesson M3a's
    Task 7 paid for. ``STAFF`` covers the Lead / Staff / Principal band because
    the corpus writes "Lead" and never "Staff", and these postings do not
    reliably distinguish an IC lead from a people-manager one.

    **Never a gate input.** `matching.md` §5.1 makes a seniority mismatch a
    score penalty, which is M3c. A senior title is not a legal barrier, and
    treating one as a blocker is exactly the wrong-``ineligible`` A13 ranks as
    the worst output this engine can produce.
    """

    INTERNSHIP = "internship"
    NEW_GRAD = "new_grad"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    DIRECTOR = "director"
    UNCLEAR = "unclear"


class EligibilityState(enum.StrEnum):
    """PRODUCT-SPEC §8.3. Never collapsed into a number (`matching.md` §5.2).

    Deliberately **not** a PostgreSQL enum yet, unlike everything else in this
    module. M3b computes a verdict on read and stores none: a stored verdict
    goes stale the moment a person edits their graduation year, and there is no
    column to attach a type to until `match_results` arrives at M3c. Creating a
    database type with no column would be shape with no use, which is the same
    reason `user_skills.confidence` was left out at M2c.
    """

    ELIGIBLE = "eligible"
    LIKELY_ELIGIBLE = "likely_eligible"
    UNCERTAIN = "uncertain"
    LIKELY_INELIGIBLE = "likely_ineligible"
    INELIGIBLE = "ineligible"


def pg_enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """``values_callable`` helper: store enum *values*, not member names."""
    return [member.value for member in enum_cls]
