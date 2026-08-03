"""Job read routes.

Routes validate and delegate (CLAUDE.md §3). The mapping from ORM rows to
response models lives in ``to_summary`` / ``_to_detail`` here because it is
serialisation, not domain logic; anything that makes a *decision* about a job
belongs in ``nightshift.domain``.

``to_summary`` is public rather than underscored because
``routes/applications.py`` reuses it: one row, one serialiser. Two mappings of
the same row drift, and they drift silently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.api.schemas import (
    CompanyOut,
    DeferredFilterOut,
    JobAdminListOut,
    JobAdminRowOut,
    JobDetailOut,
    JobListOut,
    JobLocationOut,
    JobSourceOut,
    JobStatusCounts,
    JobStatusEventOut,
    JobSummaryOut,
    SalaryOut,
)
from nightshift.db.base import EmploymentType, JobStatus, LocationConfidence, RemotePolicy
from nightshift.db.models import (
    Company,
    Job,
    JobLocation,
    JobMergeEvent,
    JobSourceLink,
    JobStatusEvent,
    SourceJobRecord,
)
from nightshift.db.session import get_db_session
from nightshift.domain.search import (
    DEFERRED_FILTERS,
    JobSearchQuery,
    build_filters,
    salary_excluded_filter,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

MAX_LIMIT = 100


def _to_salary(job: Job) -> SalaryOut:
    """A10: never present an absent salary as a zero or an omitted field."""
    provided = job.salary_min is not None or job.salary_max is not None
    if not provided:
        return SalaryOut(provided=False)
    return SalaryOut(
        provided=True,
        minimum=float(job.salary_min) if job.salary_min is not None else None,
        maximum=float(job.salary_max) if job.salary_max is not None else None,
        currency=job.salary_currency,
        period=job.salary_period,
    )


def _to_location(row: JobLocation) -> JobLocationOut:
    return JobLocationOut(
        id=row.id,
        raw_text=row.raw_text,
        city=row.city,
        state=row.state,
        country=row.country,
        latitude=float(row.latitude) if row.latitude is not None else None,
        longitude=float(row.longitude) if row.longitude is not None else None,
        # I1: the confidence travels with the coordinates, always, in both
        # directions. There is no serialisation path that emits one without the
        # other.
        location_confidence=row.location_confidence,
        resolution_method=row.resolution_method,
        is_primary=row.is_primary,
    )


def to_summary(job: Job) -> JobSummaryOut:
    return JobSummaryOut(
        id=job.id,
        title=job.title,
        company=CompanyOut(
            id=job.company.id,
            canonical_name=job.company.canonical_name,
            website=job.company.website,
        ),
        employment_type=job.employment_type,
        remote_policy=job.remote_policy,
        status=job.status,
        locations=[_to_location(row) for row in job.locations],
        salary=_to_salary(job),
        source_published_at=job.source_published_at,
        source_updated_at=job.source_updated_at,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        application_deadline=job.application_deadline,
    )


@router.get("", response_model=JobListOut)
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(description="Full-text search over the job title")] = None,
    include_description: Annotated[
        bool, Query(description="Widen `q` to search descriptions as well as titles")
    ] = False,
    company: Annotated[str | None, Query(description="Filter by company name substring")] = None,
    city: Annotated[str | None, Query(description="City exactly as the source wrote it")] = None,
    employment_type: Annotated[EmploymentType | None, Query()] = None,
    remote_policy: Annotated[RemotePolicy | None, Query()] = None,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    confidence: Annotated[
        LocationConfidence | None,
        Query(description="Only jobs with at least one location at this confidence"),
    ] = None,
    source: Annotated[str | None, Query(description="Source name substring")] = None,
    first_seen_after: Annotated[datetime | None, Query()] = None,
    salary_at_least: Annotated[float | None, Query(ge=0)] = None,
) -> JobListOut:
    """Search canonical jobs, most-recently-seen first.

    Ordering is recency, not relevance. PRODUCT-SPEC §24's ranking is M3 work
    and depends on the match score, so ranking by a relevance number here would
    be inventing half of it.
    """
    query = JobSearchQuery(
        q=q,
        include_description=include_description,
        company=company,
        city=city,
        employment_type=employment_type,
        remote_policy=remote_policy,
        job_status=job_status,
        confidence=confidence,
        source=source,
        first_seen_after=first_seen_after,
        salary_at_least=salary_at_least,
    )
    filters = build_filters(query)

    total = (
        await session.execute(select(func.count()).select_from(Job).where(*filters))
    ).scalar_one()

    # What the salary floor necessarily removed, counted against the *other*
    # filters so the number describes this result set rather than the corpus.
    excluded_no_salary = 0
    if query.salary_at_least is not None:
        without_salary = build_filters(query.model_copy(update={"salary_at_least": None}))
        excluded_no_salary = (
            await session.execute(
                select(func.count())
                .select_from(Job)
                .where(*without_salary, salary_excluded_filter())
            )
        ).scalar_one()

    rows = (
        (
            await session.execute(
                select(Job)
                .where(*filters)
                .options(selectinload(Job.company), selectinload(Job.locations))
                # Deterministic: id breaks ties so pagination cannot skip or repeat
                # a row when several jobs share a last_seen_at, which they always do
                # because a whole board is ingested with one timestamp.
                .order_by(Job.last_seen_at.desc(), Job.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return JobListOut(
        items=[to_summary(job) for job in rows],
        total=total,
        limit=limit,
        offset=offset,
        excluded_no_salary=excluded_no_salary,
        deferred_filters=[
            DeferredFilterOut(name=e.name, blocked_on=e.blocked_on, reason=e.reason)
            for e in DEFERRED_FILTERS
        ],
    )


@router.get("/admin", response_model=JobAdminListOut)
async def list_jobs_for_admin(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobAdminListOut:
    """Operational view of the canonical job table.

    Declared before ``/{job_id}`` deliberately: FastAPI matches in declaration
    order, so the other way round this path resolves as a job whose id is the
    string "admin" and returns 422.

    Includes closed jobs by default, unlike the user-facing list. Hiding them
    here would make the closure machine unobservable — which is the one thing
    this view exists to prevent.
    """
    counted = (await session.execute(select(Job.status, func.count()).group_by(Job.status))).all()
    status_counts = JobStatusCounts(**{state.value: count for state, count in counted})

    filters = [Job.status == job_status] if job_status is not None else []

    total = (
        await session.execute(select(func.count()).select_from(Job).where(*filters))
    ).scalar_one()

    rows = (
        await session.execute(
            select(
                Job,
                Company.canonical_name,
                func.count(func.distinct(JobSourceLink.id)),
                func.count(func.distinct(JobLocation.id)),
                func.count(func.distinct(JobMergeEvent.id)),
            )
            .join(Company, Company.id == Job.company_id)
            .outerjoin(JobSourceLink, JobSourceLink.job_id == Job.id)
            .outerjoin(JobLocation, JobLocation.job_id == Job.id)
            .outerjoin(JobMergeEvent, JobMergeEvent.winner_job_id == Job.id)
            .where(*filters)
            .group_by(Job.id, Company.canonical_name)
            # id breaks ties, as in list_jobs: a whole board shares one
            # last_seen_at, so without it pagination can skip or repeat a row.
            .order_by(Job.last_seen_at.desc(), Job.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return JobAdminListOut(
        items=[
            JobAdminRowOut(
                id=job.id,
                title=job.title,
                company_name=company_name,
                status=job.status,
                first_seen_at=job.first_seen_at,
                last_seen_at=job.last_seen_at,
                closed_at=job.closed_at,
                source_count=source_count,
                location_count=location_count,
                merge_count=merge_count,
            )
            for job, company_name, source_count, location_count, merge_count in rows
        ],
        total=total,
        status_counts=status_counts,
    )


@router.get("/{job_id}/history", response_model=list[JobStatusEventOut])
async def job_history(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[JobStatusEventOut]:
    """Every transition this job has been through, oldest first.

    This is the answer to "why did this job disappear?", and it survives the job
    reopening — which is the whole reason ``job_status_events`` is append-only.
    A reposted job has ``closed_at`` back to null, so the column that showed the
    closure is gone and only these rows remain.
    """
    exists = (await session.execute(select(Job.id).where(Job.id == job_id))).scalar_one_or_none()
    if exists is None:
        # 404 rather than an empty list: "this job has no transitions" and "this
        # job does not exist" are different answers and must not look alike.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    events = (
        (
            await session.execute(
                select(JobStatusEvent)
                .where(JobStatusEvent.job_id == job_id)
                .order_by(JobStatusEvent.created_at, JobStatusEvent.id)
            )
        )
        .scalars()
        .all()
    )
    return [JobStatusEventOut.model_validate(event) for event in events]


@router.get("/{job_id}", response_model=JobDetailOut)
async def get_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JobDetailOut:
    job = (
        (
            await session.execute(
                select(Job)
                .where(Job.id == job_id)
                .options(selectinload(Job.company), selectinload(Job.locations))
            )
        )
        .scalars()
        .first()
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    provenance = (
        (
            await session.execute(
                select(SourceJobRecord)
                .join(JobSourceLink, JobSourceLink.source_job_record_id == SourceJobRecord.id)
                .where(JobSourceLink.job_id == job_id)
                .options(selectinload(SourceJobRecord.source))
            )
        )
        .scalars()
        .all()
    )

    summary = to_summary(job)
    return JobDetailOut(
        **summary.model_dump(),
        description_text=job.description_text,
        description_html=job.description_html,
        sources=[
            JobSourceOut(
                source_name=record.source.name,
                source_job_id=record.source_job_id,
                canonical_url=record.canonical_url,
                first_seen_at=record.first_seen_at,
                last_seen_at=record.last_seen_at,
            )
            for record in provenance
        ],
    )
