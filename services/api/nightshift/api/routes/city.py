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

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated
from uuid import UUID

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
from nightshift.db.models import Job, JobSourceLink, Source, SourceJobRecord
from nightshift.db.session import get_db_session
from nightshift.domain.capture import CAPTURE_SOURCE_NAME
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


async def _last_verified(
    session: AsyncSession, job_ids: Sequence[UUID]
) -> dict[UUID, datetime | None]:
    """When each job's own posting was last checked, for the jobs where it was.

    One grouped query rather than a relationship per job, for the same reason
    ``primary_offices`` is one lookup: this runs over the whole corpus at once.

    ``max`` across a job's source records is the meaningful aggregate — a role
    merged from three boards is as verified as its most recently verified
    record. Jobs absent from the result have never been verified at all, and the
    caller's ``.get`` turns that into ``None`` rather than into a date.
    """
    if not job_ids:
        return {}
    rows = await session.execute(
        select(JobSourceLink.job_id, func.max(SourceJobRecord.last_verified_at))
        .join(SourceJobRecord, SourceJobRecord.id == JobSourceLink.source_job_record_id)
        .where(JobSourceLink.job_id.in_(job_ids))
        .group_by(JobSourceLink.job_id)
    )
    return dict(rows.all())  # type: ignore[arg-type]


async def _captured(session: AsyncSession, job_ids: Sequence[UUID]) -> set[UUID]:
    """Which of these roles a person pasted in, rather than a poller finding.

    One query for the whole corpus, for the same reason ``_last_verified`` is
    one: this runs over every signal on the map at once.

    The fact is read off the source a confirmed capture is attributed to
    (``manual_capture``, `domain/capture.py`), which is where it was written
    down — it is not derived from the posting's text. That distinction is ADR
    0039 §5: *whether* a posting arrived by hand is recorded, *which website*
    it came from is not, and this answers only the first question.

    A set rather than a dict of booleans, so a job absent from the join is
    simply not in it. A polled role has no ``manual_capture`` record and never
    appears here, which is what makes the caller's ``in`` correct by default
    rather than dependent on a fallback.
    """
    if not job_ids:
        return set()
    rows = await session.execute(
        select(JobSourceLink.job_id)
        .join(SourceJobRecord, SourceJobRecord.id == JobSourceLink.source_job_record_id)
        .join(Source, Source.id == SourceJobRecord.source_id)
        .where(JobSourceLink.job_id.in_(job_ids), Source.name == CAPTURE_SOURCE_NAME)
        .distinct()
    )
    return set(rows.scalars().all())


@router.get("/signals", response_model=CitySignalsOut)
async def city_signals(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    include_closed: Annotated[
        bool, Query(description="Include closed listings, for the Analyze archive view")
    ] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_SIGNALS)] = MAX_SIGNALS,
) -> CitySignalsOut:
    """Every role the city can show, each with its placement resolved.

    **A fixed number of queries whatever the corpus size**, which is the
    property that matters and the one a count in a docstring stops describing
    the moment somebody adds a field. Today it is five: the total, the jobs with
    their locations and companies eager-loaded, then one lookup each for the
    confirmed primary offices, the last-verified dates, and which roles were
    captured by hand.

    Each of the last three is one grouped query over the whole corpus rather
    than a lazy relationship per job, which would be thousands of round trips to
    answer a question about twenty-odd employers. Adding a per-signal fact means
    adding a fourth lookup in that shape — not a `selectinload` that looks
    cheaper and is not.
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
    verified = await _last_verified(session, [job.id for job in jobs])
    captured = await _captured(session, [job.id for job in jobs])

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
                last_seen_at=job.last_seen_at,
                last_verified_at=verified.get(job.id),
                application_deadline=job.application_deadline,
                captured=job.id in captured,
                placement=_to_placement(placement),
            )
        )

    return CitySignalsOut(
        signals=signals,
        counts=counts,
        limit=limit,
        truncated=total > len(jobs),
    )
