"""What the map is allowed to draw.

One route, and it exists because the renderer asks a question no other endpoint
answers: *for every open role, where — if anywhere — does it stand?* The
decision itself is in ``nightshift.domain.placement``; this validates, joins and
serialises, per `CLAUDE.md` §3.

**The counts ship with the signals rather than being counted by the client.**
`city.md` §4.7 asks the product to say what it cannot place, not only what it
can, and on this corpus the honest answer is "all of them". A map that has to
derive that by filtering an array is a map one refactor away from quietly
dropping the sentence.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.api.schemas import (
    CitySignalOut,
    CitySignalsOut,
    PlacementCounts,
    PlacementOut,
)
from nightshift.db.base import JobStatus
from nightshift.db.models import Job
from nightshift.db.session import get_db_session
from nightshift.domain.placement import (
    Placement,
    PlacementKind,
    primary_offices,
    resolve_placement,
)

router = APIRouter(prefix="/city", tags=["city"])

#: A ceiling rather than a page. The map draws the whole corpus at once — that
#: is what instancing is for — so paging it would mean a city that fills in as
#: you scroll something that does not scroll. The cap is here because an
#: unbounded query is a bug waiting for a bigger database, and the response says
#: when it bites instead of silently showing a partial city.
MAX_SIGNALS = 5_000

#: `city.md` §6 gives a closed listing a fading afterimage, which belongs to the
#: session that watched it close rather than to a cold load. A closed role
#: arriving on first paint would be an afterimage of something the viewer never
#: saw.
_DEFAULT_STATUSES = (JobStatus.OPEN, JobStatus.POSSIBLY_STALE, JobStatus.UNVERIFIED)


def _to_placement(placement: Placement) -> PlacementOut:
    return PlacementOut(
        kind=placement.kind,
        latitude=placement.latitude,
        longitude=placement.longitude,
        building_id=placement.building_id,
        location_confidence=placement.location_confidence,
        resolution_method=placement.resolution_method,
        stated=placement.stated,
        inherited=placement.inherited,
        office_label=placement.office_label,
        office_address=placement.office_address,
    )


@router.get("/signals", response_model=CitySignalsOut)
async def city_signals(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    include_closed: Annotated[
        bool, Query(description="Include closed listings, for the Analyze archive view")
    ] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_SIGNALS)] = MAX_SIGNALS,
) -> CitySignalsOut:
    """Every role the city can show, each with its placement resolved.

    Two queries, whatever the corpus size: the jobs with their locations and
    companies eager-loaded, then one lookup of every confirmed primary office.
    A lazy relationship per job would be thousands of round trips to answer a
    question about twenty-odd employers.
    """
    statuses = list(JobStatus) if include_closed else list(_DEFAULT_STATUSES)

    total = (
        await session.execute(select(func.count()).select_from(Job).where(Job.status.in_(statuses)))
    ).scalar_one()

    jobs = (
        (
            await session.execute(
                select(Job)
                .where(Job.status.in_(statuses))
                .options(selectinload(Job.locations), selectinload(Job.company))
                # Stable across calls, so two loads of the same city produce the
                # same instance buffer in the same order. A renderer diffing
                # against its previous frame gets a no-op instead of a reshuffle.
                .order_by(Job.first_seen_at.desc(), Job.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    offices = await primary_offices(session, [job.company_id for job in jobs])

    counts = PlacementCounts(total=len(jobs))
    signals: list[CitySignalOut] = []
    for job in jobs:
        placement = resolve_placement(job, office=offices.get(job.company_id))
        if placement.kind is PlacementKind.BUILDING:
            counts.building += 1
        elif placement.kind is PlacementKind.AREA:
            counts.area += 1
        else:
            counts.unresolved += 1

        signals.append(
            CitySignalOut(
                job_id=job.id,
                title=job.title,
                company_id=job.company_id,
                company_name=job.company.canonical_name,
                employment_type=job.employment_type,
                remote_policy=job.remote_policy,
                status=job.status,
                first_seen_at=job.first_seen_at,
                placement=_to_placement(placement),
            )
        )

    return CitySignalsOut(
        signals=signals,
        counts=counts,
        limit=limit,
        truncated=total > len(jobs),
    )
