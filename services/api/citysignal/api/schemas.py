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

from citysignal.db.base import (
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


class JobListOut(BaseModel):
    items: list[JobSummaryOut]
    total: int
    limit: int
    offset: int


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
