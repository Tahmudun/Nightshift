"""Source health and ingestion history.

§2.6 requires source reliability to be visible, and M1's acceptance criteria say
ingestion failures must be visible in the UI, not just the logs. These routes are
what the UI reads to satisfy that, and they exist in M0 so the honesty of the
pipeline is inspectable from the first day it produces data.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from citysignal.api.schemas import (
    IngestionRunOut,
    LocationConfidenceBreakdown,
    SourceHealthOut,
    StatsOut,
)
from citysignal.db.base import JobStatus, LocationConfidence
from citysignal.db.models import (
    Company,
    IngestionRun,
    Job,
    JobLocation,
    JobSourceLink,
    Source,
    SourceJobRecord,
)
from citysignal.db.session import get_db_session
from citysignal.domain.registry import BoardStatus, get_registry

router = APIRouter(tags=["sources"])


@router.get("/sources", response_model=list[SourceHealthOut])
async def list_source_health(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[SourceHealthOut]:
    sources = (
        (await session.execute(select(Source).order_by(Source.priority, Source.name)))
        .scalars()
        .all()
    )

    out: list[SourceHealthOut] = []
    for source in sources:
        job_count = (
            await session.execute(
                select(func.count(func.distinct(JobSourceLink.job_id)))
                .join(
                    SourceJobRecord,
                    SourceJobRecord.id == JobSourceLink.source_job_record_id,
                )
                .where(SourceJobRecord.source_id == source.id)
            )
        ).scalar_one()

        last_run = (
            (
                await session.execute(
                    select(IngestionRun)
                    .where(IngestionRun.source_id == source.id)
                    .order_by(IngestionRun.started_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

        out.append(
            SourceHealthOut(
                name=source.name,
                source_type=source.source_type.value,
                is_enabled=source.is_enabled,
                last_success_at=source.last_success_at,
                last_failure_at=source.last_failure_at,
                job_count=job_count,
                last_run_status=last_run.status if last_run else None,
                last_run_started_at=last_run.started_at if last_run else None,
                last_run_error=last_run.error_summary if last_run else None,
            )
        )
    return out


@router.get("/ingestion-runs", response_model=list[IngestionRunOut])
async def list_ingestion_runs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[IngestionRunOut]:
    """Every run, successful or not — a failed run is the interesting one."""
    runs = (
        (
            await session.execute(
                select(IngestionRun)
                .options(selectinload(IngestionRun.source))
                .order_by(IngestionRun.started_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return [
        IngestionRunOut(
            id=run.id,
            source_name=run.source.name,
            board_tokens=list(run.board_tokens),
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status,
            records_fetched=run.records_fetched,
            records_created=run.records_created,
            records_updated=run.records_updated,
            records_unchanged=run.records_unchanged,
            records_closed=run.records_closed,
            records_failed=run.records_failed,
            error_summary=run.error_summary,
        )
        for run in runs
    ]


@router.get("/stats", response_model=StatsOut)
async def stats(session: Annotated[AsyncSession, Depends(get_db_session)]) -> StatsOut:
    """Corpus counts, including the location-confidence breakdown.

    The breakdown is exposed deliberately: it makes the honesty of the data set a
    visible number. In M0 every location is ``city_only``, ``remote``, or
    ``unknown`` and ``mappable_locations`` is zero, because nothing has been
    geocoded yet — and a dashboard that quietly hid that would be the first step
    toward pretending otherwise.
    """
    total_jobs = (await session.execute(select(func.count()).select_from(Job))).scalar_one()
    open_jobs = (
        await session.execute(
            select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN)
        )
    ).scalar_one()
    total_companies = (
        await session.execute(select(func.count()).select_from(Company))
    ).scalar_one()
    total_records = (
        await session.execute(select(func.count()).select_from(SourceJobRecord))
    ).scalar_one()

    rows = (
        await session.execute(
            select(JobLocation.location_confidence, func.count()).group_by(
                JobLocation.location_confidence
            )
        )
    ).all()
    breakdown = LocationConfidenceBreakdown(
        **{LocationConfidence(confidence).value: count for confidence, count in rows}
    )

    mappable = (
        await session.execute(
            select(func.count()).select_from(JobLocation).where(JobLocation.latitude.isnot(None))
        )
    ).scalar_one()

    return StatsOut(
        total_jobs=total_jobs,
        open_jobs=open_jobs,
        total_companies=total_companies,
        total_source_records=total_records,
        location_confidence=breakdown,
        mappable_locations=mappable,
    )


@router.get("/registry")
async def board_registry() -> dict[str, object]:
    """The board registry as loaded, so A1's central data file is inspectable.

    Read-only by design. The registry is version-controlled source data and
    nothing writes to it automatically — the token resolution pipeline emits
    candidates for human review and never auto-commits.
    """
    registry = get_registry()
    return {
        "total": len(registry.boards),
        "pollable": len(registry.pollable()),
        "boards": [
            {
                "company": board.company,
                "ats": board.ats,
                "token": board.token,
                "status": board.status.value,
                "nyc_presence": board.nyc_presence,
                "verified_at": board.verified_at.isoformat() if board.verified_at else None,
                "notes": board.notes,
            }
            for board in registry.boards
        ],
        "status_counts": {
            status.value: sum(1 for b in registry.boards if b.status is status)
            for status in BoardStatus
        },
    }
