"""The daily queue: four questions this system can answer honestly today.

Read ``docs/architecture/command-center.md`` §7 before changing anything here.
§7.1 records why assessments do not have their own row, §7.2 records the three
rules that decide whether the page tells the truth, and §7.3 records that this
module has no write path and is not to grow one.

Everything here is a read. ``build_queue`` is called once per page load and runs
four independent queries rather than one clever join — they answer four
different questions, they are separately indexable, and a join producing all
four would be the kind of query nobody can change safely later.

``now`` is a parameter, never ``utcnow()`` read inside. Every threshold in this
file is a boundary somebody will get wrong eventually, and a function that
reads its own clock cannot be tested at one.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationStage,
    EventActor,
    JobStatus,
)
from nightshift.db.models import Application, ApplicationEvent, Company, Job

#: Decided by the human on 2026-08-04 (`command-center.md` §7). A week is when
#: silence after applying starts to mean something; three weeks of a saved job
#: untouched is genuinely stale; two weeks is far enough ahead to prepare for
#: an interview and near enough that it is still this month's problem.
FOLLOW_UP_SILENT_DAYS = 7
STALE_SAVED_DAYS = 21
INTERVIEW_HORIZON_DAYS = 14

#: Rows per section. The count before the cap travels with it, so the page can
#: say "and 6 more" rather than quietly truncating.
ROW_CAP = 20

#: Applied and now waiting on somebody else. Silence in these stages is the
#: thing worth surfacing. ``assessment`` is here because §7.1 folds assessments
#: into follow-up rather than giving them a row of their own.
AWAITING_STAGES: tuple[ApplicationStage, ...] = (
    ApplicationStage.APPLIED,
    ApplicationStage.ASSESSMENT,
    ApplicationStage.INTERVIEW,
)

#: Over, one way or another. Nothing in these stages belongs in a queue of
#: things to do today — including ``offer``, which is a decision rather than a
#: chase, and which the pipeline already shows prominently.
TERMINAL_STAGES: tuple[ApplicationStage, ...] = (
    ApplicationStage.REJECTED,
    ApplicationStage.WITHDRAWN,
    ApplicationStage.CLOSED,
)


class QueueSectionKey(enum.StrEnum):
    """The four sections. Deliberately not a database enum — this is a shape of
    the API, not a stored value, and nothing persists it."""

    FOLLOW_UP = "follow_up"
    INTERVIEWS_APPROACHING = "interviews_approaching"
    STALE_SAVED = "stale_saved"
    CLOSED_WHILE_SAVED = "closed_while_saved"


@dataclass(frozen=True, slots=True)
class QueueRow:
    """One thing to look at, and the sentence saying why.

    ``at`` is the date the row is *about* — the follow-up date, the interview
    time, the day it went quiet. It is read from a column, never invented, and
    it is None when the section has no meaningful date (I1's habit applied to
    time rather than to place).
    """

    application_id: UUID
    job_id: UUID
    job_title: str
    company_name: str
    current_stage: ApplicationStage
    at: datetime | None
    because: str


@dataclass(frozen=True, slots=True)
class QueueSection:
    key: QueueSectionKey
    rows: tuple[QueueRow, ...]
    #: Before the cap. ``len(rows) < total`` is how the page knows to say so.
    total: int


@dataclass(frozen=True, slots=True)
class DailyQueue:
    sections: tuple[QueueSection, ...]
    total_rows: int


def _last_user_activity() -> Any:
    """The most recent event *the user caused*, per application.

    §7.2, and the load-bearing filter on this page. ``application_events`` holds
    system events too — ``record_listing_closed`` writes one — and a system
    event is not somebody touching their application. If it counted here, a
    listing going closed would make its application look freshly handled and
    drop it out of the very queue that exists to surface it. Mutation-checked
    by ``test_a_system_event_does_not_count_as_activity``.
    """
    return (
        select(
            ApplicationEvent.application_id.label("application_id"),
            func.max(ApplicationEvent.occurred_at).label("last_at"),
        )
        .where(ApplicationEvent.actor == EventActor.USER)
        .group_by(ApplicationEvent.application_id)
        .subquery()
    )


def _live(user_id: UUID) -> list[Any]:
    """Filters every section shares: this user's, not archived, not over.

    Archived exclusion is §7.2's second rule, and M2b shipped the same bug from
    the other direction — an archived application rendered as unsaved and
    saving it changed nothing.
    """
    return [
        Application.user_id == user_id,
        Application.archived_at.is_(None),
        Application.current_stage.not_in(TERMINAL_STAGES),
    ]


def _row_columns() -> list[Any]:
    """The columns every section selects, in one place so they cannot drift."""
    return [
        Application.id,
        Application.job_id,
        Job.title,
        Company.canonical_name,
        Application.current_stage,
    ]


def _joined(stmt: Select[Any]) -> Select[Any]:
    return stmt.join(Job, Job.id == Application.job_id).join(Company, Company.id == Job.company_id)


def _follow_up_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Due by date, or silent past the threshold.

    Two branches, one row per application — an application matching both is
    still one thing to do. ``coalesce`` falls back to the application's own
    creation time so an application with no user event is surfaced rather than
    silently skipped; ``save_job`` always writes one today, and being wrong in
    the direction of showing too much is the right way to be wrong here.
    """
    activity = _last_user_activity()
    silent_since = now - timedelta(days=FOLLOW_UP_SILENT_DAYS)
    last_at = func.coalesce(activity.c.last_at, Application.created_at)
    return (
        _joined(select(*_row_columns(), Application.next_action_at, last_at.label("last_at")))
        .outerjoin(activity, activity.c.application_id == Application.id)
        .where(
            *_live(user_id),
            or_(
                and_(
                    Application.next_action_at.is_not(None),
                    Application.next_action_at <= now,
                ),
                and_(
                    Application.current_stage.in_(AWAITING_STAGES),
                    last_at <= silent_since,
                ),
            ),
        )
        # Most overdue first: a date we were given beats one we inferred.
        .order_by(func.coalesce(Application.next_action_at, last_at), Application.id)
    )


def _interviews_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Scheduled times inside the horizon. One row per interview, not per
    application — two interviews are two appointments to prepare for."""
    horizon = now + timedelta(days=INTERVIEW_HORIZON_DAYS)
    return (
        _joined(select(*_row_columns(), ApplicationEvent.occurred_at))
        .join(ApplicationEvent, ApplicationEvent.application_id == Application.id)
        .where(
            *_live(user_id),
            ApplicationEvent.event_type == ApplicationEventType.INTERVIEW_SCHEDULED,
            ApplicationEvent.occurred_at > now,
            ApplicationEvent.occurred_at <= horizon,
        )
        .order_by(ApplicationEvent.occurred_at, Application.id)
    )


def _stale_saved_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Still at ``saved``, untouched past the threshold."""
    activity = _last_user_activity()
    stale_since = now - timedelta(days=STALE_SAVED_DAYS)
    last_at = func.coalesce(activity.c.last_at, Application.created_at)
    return (
        _joined(select(*_row_columns(), last_at.label("last_at")))
        .outerjoin(activity, activity.c.application_id == Application.id)
        .where(
            *_live(user_id),
            Application.current_stage == ApplicationStage.SAVED,
            last_at <= stale_since,
        )
        # Stalest first.
        .order_by(last_at, Application.id)
    )


def _closed_while_saved_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """The listing is closed *right now*.

    §7.2's third rule: membership comes from ``jobs.status``, not from the
    ``listing_closed`` event, so a role that closed and reopened leaves this
    section instead of sitting in it permanently. ``now`` is unused and that is
    deliberate — the signature matches its three siblings so ``queue_selects``
    can hold them in one dict.
    """
    del now
    return (
        _joined(select(*_row_columns(), Job.last_seen_at))
        .where(*_live(user_id), Job.status == JobStatus.CLOSED)
        .order_by(Job.last_seen_at.desc(), Application.id)
    )


def queue_selects(*, user_id: UUID, now: datetime) -> dict[QueueSectionKey, Select[Any]]:
    """Exactly what ``build_queue`` runs, exposed for the query-plan test.

    Task 2 asserts each of these is servable by an index. It matters that it
    reads the real statements rather than a copy that can drift out of step.
    """
    return {
        QueueSectionKey.FOLLOW_UP: _follow_up_select(user_id=user_id, now=now),
        QueueSectionKey.INTERVIEWS_APPROACHING: _interviews_select(user_id=user_id, now=now),
        QueueSectionKey.STALE_SAVED: _stale_saved_select(user_id=user_id, now=now),
        QueueSectionKey.CLOSED_WHILE_SAVED: _closed_while_saved_select(user_id=user_id, now=now),
    }


def _days(a: datetime, b: datetime) -> int:
    return max((a - b).days, 0)


def _because(key: QueueSectionKey, *, row: Any, now: datetime) -> str:
    """One plain sentence per row, derived from the same data the query filtered
    on. Never a score and never a ranking — those are M3's, and I4 forbids
    showing one without a breakdown behind it."""
    if key is QueueSectionKey.FOLLOW_UP:
        if row.next_action_at is not None and row.next_action_at <= now:
            return f"you set a next action for {row.next_action_at:%-d %b}"
        return f"no activity from you in {_days(now, row.last_at)} days"
    if key is QueueSectionKey.INTERVIEWS_APPROACHING:
        return f"interview scheduled for {row.occurred_at:%-d %b}"
    if key is QueueSectionKey.STALE_SAVED:
        return f"saved {_days(now, row.last_at)} days ago and untouched since"
    return "the source stopped listing this role"


def _at(key: QueueSectionKey, row: Any) -> datetime | None:
    if key is QueueSectionKey.FOLLOW_UP:
        at: datetime | None = row.next_action_at or row.last_at
        return at
    if key is QueueSectionKey.INTERVIEWS_APPROACHING:
        occurred_at: datetime = row.occurred_at
        return occurred_at
    if key is QueueSectionKey.STALE_SAVED:
        last_at: datetime = row.last_at
        return last_at
    last_seen_at: datetime = row.last_seen_at
    return last_seen_at


async def _build_section(
    session: AsyncSession, *, key: QueueSectionKey, stmt: Select[Any], now: datetime
) -> QueueSection:
    """Count first, then take the capped page.

    Two queries rather than a window function, because the count must be the
    honest total and ``len(rows)`` after a LIMIT is not it. ``order_by(None)``
    strips the sort before counting — Postgres allows it inside the subquery
    but sorting rows nobody reads is wasted work.
    """
    total = (
        await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
    ).scalar_one()
    result = (await session.execute(stmt.limit(ROW_CAP))).all()
    rows = tuple(
        QueueRow(
            application_id=row.id,
            job_id=row.job_id,
            job_title=row.title,
            company_name=row.canonical_name,
            current_stage=row.current_stage,
            at=_at(key, row),
            because=_because(key, row=row, now=now),
        )
        for row in result
    )
    return QueueSection(key=key, rows=rows, total=total)


async def build_queue(session: AsyncSession, *, user_id: UUID, now: datetime) -> DailyQueue:
    """Every section, in the order the page renders them.

    Sections are independent, so a role can legitimately appear in two of them
    — a closed listing you also owe a follow-up on is two different facts about
    the same job, and collapsing them would hide one.
    """
    sections = tuple(
        [
            await _build_section(session, key=key, stmt=stmt, now=now)
            for key, stmt in queue_selects(user_id=user_id, now=now).items()
        ]
    )
    return DailyQueue(sections=sections, total_rows=sum(section.total for section in sections))
