"""Job search: the query model, and the filters it becomes.

Routes validate and delegate (CLAUDE.md §3), so the decisions live here rather
than in ``api/routes/jobs.py``. The decisions worth naming:

* A blank search box is not a filter. ``q=""`` returns the corpus, not nothing.
* ``salary_at_least`` cannot silently hide the majority of the corpus. Most
  postings state no salary at all (A10), so the route counts what this filter
  excluded and the UI says so out loud.
* There is no borough filter, and its absence is an I1 matter rather than a
  scheduling one. See ``DEFERRED_FILTERS``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import ColumnElement, func, or_, select

from nightshift.db.base import (
    EmploymentType,
    JobStatus,
    LocationConfidence,
    RemotePolicy,
)
from nightshift.db.models import (
    Company,
    Job,
    JobLocation,
    JobSourceLink,
    Source,
    SourceJobRecord,
)


def _require_aware(value: datetime | None) -> datetime | None:
    """UTC in the database, always (CLAUDE.md §7). Naive input is a caller bug."""
    if value is not None and value.tzinfo is None:
        raise ValueError("first_seen_after must carry a timezone")
    return value


class JobSearchQuery(BaseModel):
    """Everything M2a can filter on, and nothing it cannot."""

    q: str | None = None
    company: str | None = None
    city: str | None = None
    employment_type: EmploymentType | None = None
    remote_policy: RemotePolicy | None = None
    job_status: JobStatus | None = None
    confidence: LocationConfidence | None = None
    source: str | None = None
    first_seen_after: Annotated[datetime | None, AfterValidator(_require_aware)] = None
    salary_at_least: float | None = Field(default=None, ge=0)


class DeferredFilter(BaseModel):
    """A filter PRODUCT-SPEC §12.2 asks for that M2a will not fake.

    Serialised to the client so the panel can render it disabled with the
    reason showing, rather than omitting it and leaving the gap invisible.
    """

    name: str
    blocked_on: str
    reason: str


DEFERRED_FILTERS: tuple[DeferredFilter, ...] = (
    DeferredFilter(
        name="match_score",
        blocked_on="M3",
        reason="No score exists yet. I4 forbids presenting one without a breakdown.",
    ),
    DeferredFilter(
        name="eligibility",
        blocked_on="M3",
        reason="Requires the deterministic eligibility gate.",
    ),
    DeferredFilter(
        name="skill",
        blocked_on="M3",
        reason="Requires the skill taxonomy and its aliases.",
    ),
    DeferredFilter(
        name="internship_season",
        blocked_on="M3",
        reason="Requires the seniority and role-family classifier.",
    ),
    DeferredFilter(
        name="borough",
        blocked_on="M4",
        reason=(
            "A posting that says 'New York, NY' does not say which borough it is in, "
            "and inferring one would be the interpolation invariant I1 forbids. "
            "Boroughs arrive with the geocoder at M4. Filter by city instead."
        ),
    ),
)


def salary_excluded_filter() -> ColumnElement[bool]:
    """Jobs the salary floor necessarily hides: the ones stating no salary.

    Exported so the route can count them. A filter that quietly drops most of
    the corpus is the A10 failure this project keeps designing against.
    """
    return Job.salary_min.is_(None) & Job.salary_max.is_(None)


def build_filters(query: JobSearchQuery) -> list[ColumnElement[bool]]:
    """Turn the query model into SQLAlchemy predicates, in a stable order."""
    filters: list[ColumnElement[bool]] = []

    if query.q and query.q.strip():
        # websearch_to_tsquery, not plainto_tsquery: it understands quoted
        # phrases and a leading '-' for exclusion, and it never raises on
        # syntax a person typed. plainto_ would treat a quote as a word.
        filters.append(
            Job.search_vector.op("@@")(func.websearch_to_tsquery("english", query.q.strip()))
        )

    if query.company and query.company.strip():
        needle = query.company.strip().lower()
        filters.append(Job.company.has(func.lower(Company.canonical_name).contains(needle)))

    if query.city and query.city.strip():
        # Matches what the source actually wrote. lower() to hit
        # ix_job_locations_city_lower rather than scanning.
        needle = query.city.strip().lower()
        filters.append(
            Job.id.in_(select(JobLocation.job_id).where(func.lower(JobLocation.city) == needle))
        )

    if query.employment_type is not None:
        filters.append(Job.employment_type == query.employment_type)

    if query.remote_policy is not None:
        filters.append(Job.remote_policy == query.remote_policy)

    if query.job_status is not None:
        filters.append(Job.status == query.job_status)

    if query.confidence is not None:
        filters.append(
            Job.id.in_(
                select(JobLocation.job_id).where(
                    JobLocation.location_confidence == query.confidence
                )
            )
        )

    if query.source and query.source.strip():
        needle = query.source.strip().lower()
        filters.append(
            Job.id.in_(
                select(JobSourceLink.job_id)
                .join(
                    SourceJobRecord,
                    SourceJobRecord.id == JobSourceLink.source_job_record_id,
                )
                .join(Source, Source.id == SourceJobRecord.source_id)
                .where(func.lower(Source.name).contains(needle))
            )
        )

    if query.first_seen_after is not None:
        filters.append(Job.first_seen_at >= query.first_seen_after)

    if query.salary_at_least is not None:
        # Either bound clearing the floor is enough: a range of 80k-120k does
        # pay at least 90k for somebody. A posting with no salary at all cannot
        # satisfy this and is counted separately rather than silently dropped.
        filters.append(
            or_(
                Job.salary_max >= query.salary_at_least,
                Job.salary_min >= query.salary_at_least,
            )
        )

    return filters
