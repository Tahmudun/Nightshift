"""The daily queue.

Routes validate and delegate (CLAUDE.md §3). Every rule lives in
``nightshift.domain.queue``; this module reads the clock, calls one function,
and shapes the answer. There is no write route here and §7.3 says there is not
to be one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import CurrentUserId
from nightshift.api.schemas import (
    DailyQueueOut,
    DeferredQueueRowOut,
    QueueRowOut,
    QueueSectionBlindSpotOut,
    QueueSectionOut,
    QueueThresholdsOut,
)
from nightshift.db.session import get_db_session
from nightshift.db.types import utcnow
from nightshift.domain.queue import (
    FOLLOW_UP_SILENT_DAYS,
    INTERVIEW_HORIZON_DAYS,
    ROW_CAP,
    STALE_SAVED_DAYS,
    QueueSectionKey,
    build_queue,
)

router = APIRouter(prefix="/queue", tags=["queue"])

#: Rendered as headings. Kept beside the keys rather than in TypeScript so the
#: API is self-describing and the page cannot invent a fifth section.
SECTION_TITLES: dict[QueueSectionKey, str] = {
    QueueSectionKey.FOLLOW_UP: "Follow up",
    QueueSectionKey.INTERVIEWS_APPROACHING: "Interviews approaching",
    QueueSectionKey.STALE_SAVED: "Saved and going quiet",
    QueueSectionKey.CLOSED_WHILE_SAVED: "Closed while you were tracking it",
    QueueSectionKey.BEST_NEW_INTERNSHIPS: "New internships worth a look",
}

#: I7: the rows PRODUCT-SPEC §10.4 asks for that this system cannot compute
#: honestly yet. Named on the page with the reason, because an empty section
#: claims "you have none of these" and that is a different, false statement.
#: `command-center.md` §7.
#:
#: **Best new internships left this tuple at M3d Task 7** and is a real section
#: now. Its old reason — *"'best' is a ranking, and there is no match score
#: behind it yet"* — was true when written and stopped being true, which is the
#: failure mode the remaining entries are checked against: a deferral is a claim
#: with a date on it, and one that outlives its cause is a false statement the
#: page keeps making.
DEFERRED_ROWS: tuple[DeferredQueueRowOut, ...] = (
    DeferredQueueRowOut(
        name="High-match roles closing soon",
        blocked_on="milestone 3",
        reason=(
            "needs both a match score and a closing date. Most sources publish no "
            "deadline at all, so even the second half is often unknowable."
        ),
    ),
    DeferredQueueRowOut(
        name="Resume mismatch warnings",
        blocked_on="milestone 3",
        reason=(
            "needs requirement extraction and the evidence graph, so that a warning "
            "can point at the specific gap rather than assert one."
        ),
    ),
    DeferredQueueRowOut(
        name="The one thing to do today",
        blocked_on="milestone 3",
        reason=(
            "ranking across every row above. It is the most useful line on this page "
            "and the least honest to fake, so it waits."
        ),
    ),
)


@router.get("", response_model=DailyQueueOut)
async def get_queue(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> DailyQueueOut:
    """What to look at today, and what this page still cannot tell you."""
    now = utcnow()
    queue = await build_queue(session, user_id=user_id, now=now)
    return DailyQueueOut(
        generated_at=now,
        sections=[
            QueueSectionOut(
                key=section.key,
                title=SECTION_TITLES[section.key],
                rows=[
                    QueueRowOut(
                        application_id=row.application_id,
                        job_id=row.job_id,
                        job_title=row.job_title,
                        company_name=row.company_name,
                        current_stage=row.current_stage,
                        at=row.at,
                        because=row.because,
                        eligibility=row.eligibility,
                    )
                    for row in section.rows
                ],
                total=section.total,
                blind_spots=[
                    QueueSectionBlindSpotOut(name=spot.name, count=spot.count, because=spot.because)
                    for spot in section.blind_spots
                ],
                note=section.note,
            )
            for section in queue.sections
        ],
        total_rows=queue.total_rows,
        deferred_rows=list(DEFERRED_ROWS),
        thresholds=QueueThresholdsOut(
            follow_up_silent_days=FOLLOW_UP_SILENT_DAYS,
            stale_saved_days=STALE_SAVED_DAYS,
            interview_horizon_days=INTERVIEW_HORIZON_DAYS,
            row_cap=ROW_CAP,
        ),
    )
