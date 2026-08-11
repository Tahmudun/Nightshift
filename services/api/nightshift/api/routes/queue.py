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
    QueueSectionKey.TODAYS_ONE_THING: "If you do one thing today",
    QueueSectionKey.FOLLOW_UP: "Follow up",
    QueueSectionKey.INTERVIEWS_APPROACHING: "Interviews approaching",
    QueueSectionKey.STALE_SAVED: "Saved and going quiet",
    QueueSectionKey.CLOSED_WHILE_SAVED: "Closed while you were tracking it",
    QueueSectionKey.REQUIREMENT_GAPS: "Gaps on roles you are tracking",
    QueueSectionKey.BEST_NEW_INTERNSHIPS: "New internships worth a look",
}

#: I7: the rows PRODUCT-SPEC §10.4 asks for that this system cannot compute
#: honestly yet. Named on the page with the reason, because an empty section
#: claims "you have none of these" and that is a different, false statement.
#: `command-center.md` §7.
#:
#: **Three rows left this tuple at M3d Task 7** and are real sections now: best
#: new internships, resume mismatch warnings — the second under a different
#: name, `command-center.md` §7.4 — and the one thing to do today. Their old
#: reasons were true when written and stopped being true, which is the failure
#: mode the one remaining entry is checked against: a deferral is a claim with a
#: date on it, and one that outlives its cause is a false statement the page
#: keeps making.
#:
#: The one below survives M3 and its `blocked_on` **changed**. It said
#: *"milestone 3"* and blamed the absent score; the score now exists and the row
#: is still impossible, because most sources publish no deadline at all (A10)
#: and Datadog's registry note says that board publishes none. Leaving it
#: reading "milestone 3" after M3 closes would be a false statement with a date
#: on it — the exact thing this tuple exists to avoid.
DEFERRED_ROWS: tuple[DeferredQueueRowOut, ...] = (
    DeferredQueueRowOut(
        name="High-match roles closing soon",
        blocked_on="the sources",
        reason=(
            "needs a closing date, and almost nothing publishes one. Most boards state "
            "no application deadline at all and one of the sources in this registry "
            "states none ever, so this row would rank the small, unrepresentative "
            "slice that happens to give a date and silently omit everything else."
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
