"""Job read routes.

Routes validate and delegate (CLAUDE.md §3). The mapping from ORM rows to
response models lives in ``_to_summary`` / ``_to_detail`` here because it is
serialisation, not domain logic; anything that makes a *decision* about a job
belongs in ``nightshift.domain``.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.api.schemas import (
    CompanyOut,
    JobDetailOut,
    JobListOut,
    JobLocationOut,
    JobSourceOut,
    JobSummaryOut,
    SalaryOut,
)
from nightshift.db.base import JobStatus, LocationConfidence
from nightshift.db.models import Company, Job, JobLocation, JobSourceLink, SourceJobRecord
from nightshift.db.session import get_db_session

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


def _to_summary(job: Job) -> JobSummaryOut:
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
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    company: Annotated[str | None, Query(description="Filter by company name substring")] = None,
    confidence: Annotated[
        LocationConfidence | None,
        Query(description="Only jobs with at least one location at this confidence"),
    ] = None,
) -> JobListOut:
    """List canonical jobs, newest-seen first."""
    filters = []
    if job_status is not None:
        filters.append(Job.status == job_status)
    if company:
        filters.append(
            Job.company.has(func.lower(Company.canonical_name).contains(company.lower()))
        )
    if confidence is not None:
        filters.append(
            Job.id.in_(
                select(JobLocation.job_id).where(JobLocation.location_confidence == confidence)
            )
        )

    total = (
        await session.execute(select(func.count()).select_from(Job).where(*filters))
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
        items=[_to_summary(job) for job in rows], total=total, limit=limit, offset=offset
    )


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

    summary = _to_summary(job)
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
