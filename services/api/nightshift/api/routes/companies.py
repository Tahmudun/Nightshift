"""Company read routes.

A job's employer should be somewhere you can go, not just a string on a row.

Counts are by closure state rather than a single total, for the same reason
``/jobs/admin`` breaks them out: a company page showing only open roles makes
the closure machine invisible, and the closure machine is the part of this
system most likely to be quietly wrong.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.schemas import (
    CompanyDetailOut,
    CompanyListOut,
    CompanyRowOut,
    JobStatusCounts,
)
from nightshift.db.models import Company, Job
from nightshift.db.session import get_db_session

router = APIRouter(prefix="/companies", tags=["companies"])

MAX_LIMIT = 200


@router.get("", response_model=CompanyListOut)
async def list_companies(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    q: Annotated[str | None, Query(description="Company name substring")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CompanyListOut:
    """Every employer we have ingested a role from, with how many.

    A blank ``q`` is not a filter — same rule as the job search. An empty box
    that returns nothing is a search page that looks broken and is.
    """
    filters: list[ColumnElement[bool]] = []
    if q and q.strip():
        filters.append(func.lower(Company.canonical_name).contains(q.strip().lower()))

    total = (
        await session.execute(select(func.count()).select_from(Company).where(*filters))
    ).scalar_one()

    rows = (
        await session.execute(
            select(Company, func.count(Job.id))
            .outerjoin(Job, Job.company_id == Company.id)
            .where(*filters)
            .group_by(Company.id)
            # Name then id: pagination has to be stable, and two employers can
            # share a display name while normalization keeps them apart.
            .order_by(Company.canonical_name, Company.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return CompanyListOut(
        items=[
            CompanyRowOut(
                id=company.id,
                canonical_name=company.canonical_name,
                website=company.website,
                job_count=job_count,
            )
            for company, job_count in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{company_id}", response_model=CompanyDetailOut)
async def get_company(
    company_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CompanyDetailOut:
    company = (
        await session.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if company is None:
        # 404 rather than an empty company: "this employer has no roles" and
        # "this employer does not exist" are different answers and must not
        # look alike.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="company not found")

    counted = (
        await session.execute(
            select(Job.status, func.count())
            .where(Job.company_id == company_id)
            .group_by(Job.status)
        )
    ).all()

    first_seen = (
        await session.execute(
            select(func.min(Job.first_seen_at)).where(Job.company_id == company_id)
        )
    ).scalar_one_or_none()

    return CompanyDetailOut(
        id=company.id,
        canonical_name=company.canonical_name,
        website=company.website,
        # JobStatusCounts defaults every state to 0, so a state with no jobs is
        # an explicit zero rather than a missing key.
        job_status_counts=JobStatusCounts(**{state.value: count for state, count in counted}),
        first_seen_at=first_seen,
    )
