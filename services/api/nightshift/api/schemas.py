"""API response schemas.

Two rules shape everything here.

Invariant I1: a location is never serialised as a bare coordinate pair. Every
location carries its ``location_confidence`` and the ``raw_text`` it came from,
so a client physically cannot render a point without also having the precision
claim attached to it.

AMENDMENTS A10: a field the source did not provide is ``null`` with a companion
flag rather than an omitted key or a zero. "Absence of data is data", and the UI
is required to say "not provided by source" instead of hiding the row.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from nightshift.db.base import (
    BoardTier,
    EmploymentType,
    IngestionRunStatus,
    JobStatus,
    LocationConfidence,
    RemotePolicy,
    ResolutionMethod,
)


class HealthComponent(BaseModel):
    """One dependency's health. ``ok=False`` always carries an ``error``."""

    ok: bool
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    """Reports honestly, including when things are down (M0 acceptance).

    ``status`` is ``degraded`` rather than ``ok`` whenever any component is
    failing, and the endpoint returns HTTP 503 in that case so a probe does not
    have to parse the body to learn the truth.
    """

    status: str = Field(description="ok | degraded")
    version: str
    environment: str
    database: HealthComponent
    redis: HealthComponent
    checked_at: datetime


class JobLocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_text: str = Field(description="The exact location substring from the source")
    city: str | None
    state: str | None
    country: str | None
    latitude: float | None
    longitude: float | None
    location_confidence: LocationConfidence
    resolution_method: ResolutionMethod
    is_primary: bool

    @property
    def is_mappable(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canonical_name: str
    website: str | None


class JobSourceOut(BaseModel):
    """Provenance, exposed. Every canonical job traces to a raw source record."""

    source_name: str
    source_job_id: str
    canonical_url: str | None
    first_seen_at: datetime
    last_seen_at: datetime


class SalaryOut(BaseModel):
    """A10: sparse. ``provided=False`` is what the UI renders as an explicit absence."""

    provided: bool
    minimum: float | None = None
    maximum: float | None = None
    currency: str | None = None
    # Greenhouse publishes a range without stating annual vs hourly. Guessing
    # from magnitude would be a fabrication, so this stays null and the UI says
    # the period was not specified.
    period: str | None = None


class JobSummaryOut(BaseModel):
    """List-view job. Deliberately excludes the description: a jobs list that
    ships every full description is a slow list."""

    id: UUID
    title: str
    company: CompanyOut
    employment_type: EmploymentType
    remote_policy: RemotePolicy
    status: JobStatus
    locations: list[JobLocationOut]
    salary: SalaryOut

    # Named for what they are (A10). `source_published_at` is the source's own
    # publication date; `first_seen_at` is when *we* first saw it and is never
    # presented as "posted".
    source_published_at: datetime | None
    source_updated_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    application_deadline: datetime | None

    @property
    def has_any_mappable_location(self) -> bool:
        return any(loc.latitude is not None for loc in self.locations)


class JobDetailOut(JobSummaryOut):
    description_text: str | None
    description_html: str | None
    sources: list[JobSourceOut]


class DeferredFilterOut(BaseModel):
    """A filter the spec asks for that this milestone will not fake.

    Serialised so the panel renders it disabled with its reason visible. An
    omitted filter is an invisible gap; a named one is a decision a reader can
    check. Same move as `/analyze/coverage` makes for source coverage.
    """

    name: str
    blocked_on: str
    reason: str


class JobListOut(BaseModel):
    items: list[JobSummaryOut]
    total: int
    limit: int
    offset: int
    # A10: how many jobs the salary floor necessarily hid, because they state
    # no salary at all. Zero when no floor was given. Without this number a
    # salary filter silently removes most of the corpus and looks like a result.
    excluded_no_salary: int = 0
    deferred_filters: list[DeferredFilterOut] = []


class JobStatusCounts(BaseModel):
    """How many jobs sit in each closure state.

    Every field defaults to zero and none is optional, so a state with no jobs
    reads as an explicit `0` rather than vanishing from the response. A missing
    key and a real zero are different claims, and the UI must not have to guess
    which it received.
    """

    open: int = 0
    possibly_stale: int = 0
    unverified: int = 0
    closed: int = 0


class SourceHealthOut(BaseModel):
    """§2.6: source reliability must be visible, and visible on the bad days."""

    name: str
    source_type: str
    is_enabled: bool
    last_success_at: datetime | None
    last_failure_at: datetime | None
    job_count: int
    last_run_status: IngestionRunStatus | None
    last_run_started_at: datetime | None
    last_run_error: str | None
    # Added at M1b. Without a breakdown, a source whose jobs have all gone
    # stale looks identical to a healthy one — the job_count above does not
    # move when a job closes, because the provenance link survives closure.
    job_status_counts: JobStatusCounts = Field(default_factory=lambda: JobStatusCounts())


class BoardPollStateOut(BaseModel):
    """One board's polling state (M1d, ADR 0007).

    **`last_success_at` here, not a posting's `last_seen_at`, is what "fresh"
    means for a board.** A board answering `304` for sixty days leaves its
    postings' timestamps sixty days old while those postings are open and
    correctly so — no misses were taken, because a 304 ages nothing. A UI
    computing staleness from posting timestamps would report a perfectly
    healthy board as rotten.

    `last_status` is carried so a `304` is distinguishable from a `200`. They
    are both success, and a surface that renders "no new jobs" as a warning
    trains people to ignore warnings.
    """

    model_config = ConfigDict(from_attributes=True)

    ats: str
    token: str
    tier: BoardTier
    #: 200, 304, or an error status. None until the board has ever been polled.
    last_status: int | None
    last_polled_at: datetime | None
    #: Only a 200 or a 304 moves this; a failure does not. That is what makes
    #: "how long since this board actually answered" answerable.
    last_success_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    next_poll_at: datetime
    #: Whether a stored ETag exists, not the ETag itself. The value is an opaque
    #: provider string of no use to a reader, and printing it invites treating
    #: it as an identifier rather than a cache token.
    has_etag: bool


class IngestionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_name: str
    board_tokens: list[str]
    started_at: datetime
    finished_at: datetime | None
    status: IngestionRunStatus
    records_fetched: int
    records_created: int
    records_updated: int
    records_unchanged: int
    records_closed: int
    records_failed: int
    error_summary: str | None


class LocationConfidenceBreakdown(BaseModel):
    """Counts per confidence value.

    Exists so the honesty of the data set is a first-class, visible number
    rather than something you would have to query the database to learn.
    """

    verified: int = 0
    approximate: int = 0
    city_only: int = 0
    remote: int = 0
    unknown: int = 0


class StatsOut(BaseModel):
    total_jobs: int
    open_jobs: int
    total_companies: int
    total_source_records: int
    location_confidence: LocationConfidenceBreakdown
    mappable_locations: int = Field(
        description="Locations with real coordinates. Zero until M1 adds geocoding."
    )


class JobAdminRowOut(BaseModel):
    """One row of the admin job table.

    Deliberately not the same shape as :class:`JobSummaryOut`. This view answers
    operational questions — is it still listed, how many sources describe it,
    was it merged — and putting those into the user-facing schema would show a
    job seeker the pipeline's internals.
    """

    id: UUID
    title: str
    company_name: str
    status: JobStatus
    first_seen_at: datetime
    last_seen_at: datetime
    closed_at: datetime | None
    source_count: int
    location_count: int
    merge_count: int


class JobAdminListOut(BaseModel):
    items: list[JobAdminRowOut]
    total: int
    status_counts: JobStatusCounts


class JobStatusEventOut(BaseModel):
    """One transition, in the words the closure machine used at the time.

    ``from_status`` is null on a job's first event: it transitioned from
    nothing, and inventing `open -> open` would be a fabricated row.
    """

    model_config = ConfigDict(from_attributes=True)

    from_status: JobStatus | None
    to_status: JobStatus
    reason: str
    observed_misses: int | None
    created_at: datetime


class BlindSpotOut(BaseModel):
    """One thing the system cannot see, and why.

    ``count`` is nullable on purpose and null is the common case. For most of
    these gaps the size is genuinely unknown — counting the NYC employers on
    Workday would mean enumerating NYC employers, which is the problem itself —
    and reporting ``0`` there would be a fabricated statistic. Null renders as
    "unknown" and the page says so in words.
    """

    id: str
    title: str
    explanation: str
    count: int | None = Field(
        default=None,
        description="Size of the gap, or null when it is genuinely unknown. Never 0 as a stand-in.",
    )


class BoardCoverageOut(BaseModel):
    total: int
    pollable: int
    by_ats: dict[str, int]
    by_status: dict[str, int]
    with_nyc_presence: int


class CoverageOut(BaseModel):
    """What is covered, and what is not.

    Deliberately carries **no percentage of the market**. There is no
    denominator: nobody knows how many tech roles open in New York, so any such
    figure would be arithmetic on a number nobody has. The M1 criterion this
    schema serves is that the gaps are named, not that the coverage is high.
    """

    boards: BoardCoverageOut
    candidates: dict[str, int]
    candidates_total: int
    blind_spots: list[BlindSpotOut]
