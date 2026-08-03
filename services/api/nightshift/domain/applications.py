"""Application tracking: the stage machine, and (from Task 3) its writes.

The machine does not block. PRODUCT-SPEC §10.2 requires that the user can
always set and correct a stage, and ``saved -> offer`` is a real thing that
happens to real people with referrals. So every transition is permitted and
every transition is *classified*, and the classification lands on the event.

What is enforced instead is invariant I5: only a user moves a stage. That rule
lives in three places on purpose — this module raises, the API requires it, and
the database refuses it with a check constraint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationStage,
    EventActor,
    TransitionClass,
)
from nightshift.db.models import Application, ApplicationEvent

#: The default forward order. Terminal stages are deliberately absent: they are
#: outcomes rather than steps, reachable from anywhere.
STAGE_ORDER: tuple[ApplicationStage, ...] = (
    ApplicationStage.DISCOVERED,
    ApplicationStage.SAVED,
    ApplicationStage.PREPARING,
    ApplicationStage.APPLIED,
    ApplicationStage.ASSESSMENT,
    ApplicationStage.INTERVIEW,
    ApplicationStage.OFFER,
)

TERMINAL_STAGES: frozenset[ApplicationStage] = frozenset(
    {
        ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
        ApplicationStage.CLOSED,
    }
)

_POSITION = {stage: index for index, stage in enumerate(STAGE_ORDER)}


class SameStageError(ValueError):
    """Raised when asked to classify a stage change that changes nothing."""


def classify_transition(
    from_stage: ApplicationStage, to_stage: ApplicationStage
) -> TransitionClass:
    """Classify a stage change. Never refuses one; only describes it.

    ``reopen`` beats every other rule: leaving a terminal stage is the fact
    worth recording, whatever the destination.
    """
    if from_stage is to_stage:
        raise SameStageError(f"{from_stage.value} is already the current stage")

    if from_stage in TERMINAL_STAGES:
        return TransitionClass.REOPEN

    if to_stage in TERMINAL_STAGES:
        # An outcome is the natural end of any stage, not a skipped step.
        return TransitionClass.ADVANCE

    if _POSITION[to_stage] == _POSITION[from_stage] + 1:
        return TransitionClass.ADVANCE

    # Backward, or forward past a stage that never happened. Both are the user
    # correcting the record, which is exactly what §10.2 asks us to allow.
    return TransitionClass.CORRECTION


class SystemMayNotSetStageError(PermissionError):
    """Invariant I5. Nothing but a user moves an application's stage."""


class ApplicationArchivedError(ValueError):
    """Restore before changing an archived application."""


def _event(
    application: Application,
    *,
    event_type: ApplicationEventType,
    actor: EventActor,
    occurred_at: datetime,
    from_stage: ApplicationStage | None = None,
    to_stage: ApplicationStage | None = None,
    transition_class: TransitionClass | None = None,
    body: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ApplicationEvent:
    """One constructor, so no write path can forget a field.

    Everything here goes through it, which is why "no change without an event"
    is checkable by reading one file.
    """
    return ApplicationEvent(
        application_id=application.id,
        event_type=event_type,
        actor=actor,
        occurred_at=occurred_at,
        from_stage=from_stage,
        to_stage=to_stage,
        transition_class=transition_class,
        body=body,
        payload=payload or {},
    )


async def save_job(
    session: AsyncSession, *, user_id: UUID, job_id: UUID, now: datetime
) -> tuple[Application, bool]:
    """Save a job, or return the application that already tracks it.

    Idempotent by lookup rather than by exception: a second click is a normal
    thing for a person to do and must not be an error, and must not write a
    second ``saved`` event either.
    """
    existing = (
        await session.execute(
            select(Application).where(Application.user_id == user_id, Application.job_id == job_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    application = Application(user_id=user_id, job_id=job_id, current_stage=ApplicationStage.SAVED)
    session.add(application)
    await session.flush()
    session.add(
        _event(
            application,
            event_type=ApplicationEventType.SAVED,
            actor=EventActor.USER,
            occurred_at=now,
            # from_stage is null: it came from nothing, exactly as
            # JobStatusEvent.from_status is null on a job's first event.
            to_stage=ApplicationStage.SAVED,
            transition_class=TransitionClass.ADVANCE,
        )
    )
    await session.flush()
    return application, True


async def change_stage(
    session: AsyncSession,
    *,
    application: Application,
    to_stage: ApplicationStage,
    actor: EventActor,
    now: datetime,
    note: str | None = None,
    applied_at: datetime | None = None,
    application_url: str | None = None,
) -> ApplicationEvent:
    """Move a stage, classify the move, and record it. Never refuses the move.

    Refuses two things that are not the move: a system actor (I5), and an
    archived application (restore is one click and makes the change visible).
    """
    if actor is not EventActor.USER:
        raise SystemMayNotSetStageError(
            "only a user may set an application stage; the system may record a fact"
        )
    if application.archived_at is not None:
        raise ApplicationArchivedError("restore this application before changing it")

    from_stage = application.current_stage
    transition = classify_transition(from_stage, to_stage)

    payload: dict[str, Any] = {}
    if applied_at is not None:
        application.applied_at = applied_at
        payload["applied_at"] = applied_at.isoformat()
    if application_url is not None:
        application.application_url = application_url
        payload["application_url"] = application_url

    application.current_stage = to_stage
    event = _event(
        application,
        event_type=ApplicationEventType.STAGE_CHANGED,
        actor=actor,
        occurred_at=now,
        from_stage=from_stage,
        to_stage=to_stage,
        transition_class=transition,
        body=note,
        payload=payload,
    )
    session.add(event)
    await session.flush()
    return event


async def add_note(
    session: AsyncSession,
    *,
    application: Application,
    body: str,
    now: datetime,
    occurred_at: datetime | None = None,
) -> ApplicationEvent:
    event = _event(
        application,
        event_type=ApplicationEventType.NOTE_ADDED,
        actor=EventActor.USER,
        occurred_at=occurred_at or now,
        body=body,
    )
    session.add(event)
    await session.flush()
    return event


async def schedule_interview(
    session: AsyncSession,
    *,
    application: Application,
    scheduled_for: datetime,
    now: datetime,
    body: str | None = None,
) -> ApplicationEvent:
    """Record an interview at a time, without moving the stage.

    ``occurred_at`` is the interview, not the click. M2d's "interviews
    approaching" row is a query over exactly this column.
    """
    event = _event(
        application,
        event_type=ApplicationEventType.INTERVIEW_SCHEDULED,
        actor=EventActor.USER,
        occurred_at=scheduled_for,
        body=body,
        payload={"recorded_at": now.isoformat()},
    )
    session.add(event)
    await session.flush()
    return event


#: Columns `update_details` is allowed to set. An allow-list rather than
#: `setattr` on anything: `current_stage` and `archived_at` have their own
#: functions precisely because they carry rules, and a generic patch route
#: would route around both.
UPDATABLE_FIELDS = frozenset(
    {"priority", "next_action_at", "application_url", "source_of_application", "applied_at"}
)


async def update_details(
    session: AsyncSession,
    *,
    application: Application,
    changes: dict[str, Any],
    now: datetime,
) -> ApplicationEvent | None:
    """Apply an allow-listed patch. Returns None when nothing changed.

    A no-op PATCH must not manufacture history — the same reason
    ``apply_freshness`` skips a decision that changes no status.
    """
    unknown = set(changes) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"not updatable here: {sorted(unknown)}")
    if application.archived_at is not None:
        raise ApplicationArchivedError("restore this application before changing it")

    changed = [field for field, value in changes.items() if getattr(application, field) != value]
    if not changed:
        return None
    for field in changed:
        setattr(application, field, changes[field])

    event = _event(
        application,
        event_type=ApplicationEventType.DETAIL_UPDATED,
        actor=EventActor.USER,
        occurred_at=now,
        payload={"changed": sorted(changed)},
    )
    session.add(event)
    await session.flush()
    return event


async def set_archived(
    session: AsyncSession, *, application: Application, archived: bool, now: datetime
) -> ApplicationEvent:
    """Archive or restore. The only removal this product has.

    Deleting is not offered because it is not possible: the events cascade, and
    the append-only trigger refuses the cascade. See
    ``test_an_application_cannot_be_deleted_either``.
    """
    application.archived_at = now if archived else None
    event = _event(
        application,
        event_type=(ApplicationEventType.ARCHIVED if archived else ApplicationEventType.RESTORED),
        actor=EventActor.USER,
        occurred_at=now,
    )
    session.add(event)
    await session.flush()
    return event


async def record_listing_closed(
    session: AsyncSession, *, job_id: UUID, now: datetime, reason: str
) -> int:
    """Tell every live application tracking this job that its listing closed.

    A fact about the world, recorded with a ``system`` actor. The stage does not
    move, and cannot: ``application_events`` has a check constraint refusing a
    ``to_stage`` from any actor but ``user`` (invariant I5). The UI surfaces a
    prompt; the person decides.

    Archived applications are skipped — a notification about a role somebody put
    away is noise, and noise is what makes real prompts get ignored.

    Returns how many applications were notified, so the caller can report it.
    """
    applications = (
        (
            await session.execute(
                select(Application).where(
                    Application.job_id == job_id, Application.archived_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    for application in applications:
        session.add(
            _event(
                application,
                event_type=ApplicationEventType.LISTING_CLOSED,
                actor=EventActor.SYSTEM,
                occurred_at=now,
                body=f"the source stopped listing this role: {reason}",
            )
        )
    await session.flush()
    return len(applications)
