"""How often a board is polled, derived from what its postings said.

ADR 0007 and ``docs/architecture/conditional-polling.md`` §8.

    hot   the board has an open NYC posting, or had one seen in the last 30 days
    warm  every other pollable board

**Derived, never declared.** ``nyc_presence`` exists in the registry YAML and is
deliberately not read here: it is a human's guess recorded once, while the
postings are the current truth. ``board-discovery.md`` §16 anticipates deleting
that field, and a test asserts nothing in the polling path consults it so the
deletion stays a cleanup rather than a behaviour change.

The threshold is **one posting**. A company's first NYC role is precisely the
event the product promises to catch the day it happens, so requiring two would
mean missing the one that matters most.

Nothing here geocodes. Recognising that a posting says "Brooklyn" is not knowing
where the building is (I1); this decides a polling interval and never places a
point.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import BoardTier, JobStatus
from nightshift.db.models import Job, JobLocation, JobSourceLink, SourceJobRecord
from nightshift.domain.locations import NYC_CITY_NAMES

#: How long an employer stays "an NYC employer" after their last NYC posting
#: closes. Thirty days, because demoting the instant a role closes would mean
#: catching their next one up to a day late — and a company that hired in New
#: York last week will very likely hire there again.
NYC_WINDOW: Final[timedelta] = timedelta(days=30)


async def derive_tier(
    session: AsyncSession,
    *,
    source_id: uuid.UUID,
    token: str,
    now: datetime,
) -> BoardTier:
    """Which tier this board belongs in, according to its own postings.

    Reads ``job_locations`` through the provenance chain — link table, raw
    record — rather than from anything denormalised onto the board. The link
    table is how a canonical job traces back to the board that listed it, and
    reaching for the answer any other way is what breaks after a merge, when one
    job carries records from several boards.

    Counts a posting when it is open, **or** when we last saw it inside
    :data:`NYC_WINDOW`. An open posting is evidence now, however old; a closed
    one is evidence that fades.
    """
    cutoff = now - NYC_WINDOW

    has_nyc = (
        await session.execute(
            select(func.count())
            .select_from(JobLocation)
            .join(Job, Job.id == JobLocation.job_id)
            .join(JobSourceLink, JobSourceLink.job_id == Job.id)
            .join(
                SourceJobRecord,
                SourceJobRecord.id == JobSourceLink.source_job_record_id,
            )
            .where(
                SourceJobRecord.source_id == source_id,
                SourceJobRecord.source_company_key == token,
                func.lower(JobLocation.city).in_(NYC_CITY_NAMES),
                or_(Job.status != JobStatus.CLOSED, Job.last_seen_at >= cutoff),
            )
            .limit(1)
        )
    ).scalar_one()

    return BoardTier.HOT if has_nyc else BoardTier.WARM
