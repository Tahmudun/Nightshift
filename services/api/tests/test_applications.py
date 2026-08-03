"""The write layer: no change without an event.

The rule these tests exist to hold is that a state change and its event are one
transaction. A stage that moved with no event is a history with a hole in it,
and holes are invisible — which is why every test here asserts on the event
rather than only on the column.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationPriority,
    ApplicationStage,
    EventActor,
    JobStatus,
    TransitionClass,
)
from nightshift.db.models import Application, ApplicationEvent, Company, Job, User
from nightshift.domain.applications import (
    ApplicationArchivedError,
    SystemMayNotSetStageError,
    add_note,
    change_stage,
    save_job,
    schedule_interview,
    set_archived,
    update_details,
)
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


async def _a_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.test")
    session.add(user)
    await session.flush()
    return user


async def _a_job(session: AsyncSession, title: str = "Software Engineer") -> Job:
    company = Company(canonical_name="Example Inc.", normalized_name=str(uuid.uuid4()))
    session.add(company)
    await session.flush()
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.casefold(),
        status=JobStatus.OPEN,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(job)
    await session.flush()
    return job


async def _events(session: AsyncSession, application: Application) -> list[ApplicationEvent]:
    return list(
        (
            await session.execute(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == application.id)
                .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
            )
        )
        .scalars()
        .all()
    )


async def test_saving_creates_an_application_and_one_event(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    job = await _a_job(db_session)

    application, created = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    assert created is True
    assert application.current_stage is ApplicationStage.SAVED
    events = await _events(db_session, application)
    assert [e.event_type for e in events] == [ApplicationEventType.SAVED]
    assert events[0].actor is EventActor.USER
    assert events[0].to_stage is ApplicationStage.SAVED
    assert events[0].from_stage is None
    assert events[0].transition_class is TransitionClass.ADVANCE


async def test_saving_twice_is_idempotent(db_session: AsyncSession) -> None:
    """A double click is not a second pipeline entry, and not a second event."""
    user = await _a_user(db_session)
    job = await _a_job(db_session)

    first, created_first = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)
    second, created_second = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    total = (await db_session.execute(select(func.count()).select_from(Application))).scalar_one()
    assert total == 1
    assert len(await _events(db_session, first)) == 1


async def test_a_stage_change_records_its_classification(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    event = await change_stage(
        db_session,
        application=application,
        to_stage=ApplicationStage.OFFER,
        actor=EventActor.USER,
        now=NOW,
    )

    assert application.current_stage is ApplicationStage.OFFER
    # Read the row back rather than trusting the returned object. The returned
    # event is constructed in memory and carries the right fields whether or
    # not it was ever written — dropping `session.add` from `change_stage`
    # leaves every assertion on `event` passing, which is precisely the hole
    # this test exists to close.
    stored = await _events(db_session, application)
    assert [e.event_type for e in stored] == [
        ApplicationEventType.SAVED,
        ApplicationEventType.STAGE_CHANGED,
    ]
    assert stored[-1].id == event.id
    assert stored[-1].from_stage is ApplicationStage.SAVED
    assert stored[-1].to_stage is ApplicationStage.OFFER
    # Five stages skipped. The machine records that rather than refusing it.
    assert stored[-1].transition_class is TransitionClass.CORRECTION


async def test_the_system_may_not_move_a_stage(db_session: AsyncSession) -> None:
    """Invariant I5, refused in Python before the database ever sees it."""
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    with pytest.raises(SystemMayNotSetStageError):
        await change_stage(
            db_session,
            application=application,
            to_stage=ApplicationStage.CLOSED,
            actor=EventActor.SYSTEM,
            now=NOW,
        )
    assert application.current_stage is ApplicationStage.SAVED


async def test_recording_an_application_stores_when_and_where(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    applied_at = NOW + timedelta(hours=2)
    event = await change_stage(
        db_session,
        application=application,
        to_stage=ApplicationStage.APPLIED,
        actor=EventActor.USER,
        now=NOW,
        applied_at=applied_at,
        application_url="https://boards.example.test/apply/1",
    )

    assert application.applied_at == applied_at
    assert application.application_url == "https://boards.example.test/apply/1"
    # One click, one event. The details ride on the transition rather than
    # producing a second row that says the same thing.
    assert event.payload["application_url"] == "https://boards.example.test/apply/1"
    assert len(await _events(db_session, application)) == 2


async def test_a_note_is_an_event_not_a_column(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    await add_note(db_session, application=application, body="Referred by Sam", now=NOW)
    await add_note(db_session, application=application, body="Recruiter called", now=NOW)

    notes = [
        e
        for e in await _events(db_session, application)
        if e.event_type is ApplicationEventType.NOTE_ADDED
    ]
    assert [n.body for n in notes] == ["Referred by Sam", "Recruiter called"]
    # Both survive. A `notes` column would have kept only the second.
    assert not hasattr(application, "notes")


async def test_an_interview_is_scheduled_in_the_future(db_session: AsyncSession) -> None:
    """`occurred_at` is world time, not write time, and may be ahead of now."""
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    when = NOW + timedelta(days=6)
    event = await schedule_interview(
        db_session, application=application, scheduled_for=when, now=NOW
    )

    assert event.event_type is ApplicationEventType.INTERVIEW_SCHEDULED
    assert event.occurred_at == when
    assert event.created_at is not None
    # Scheduling an interview does not move the stage. The user does that.
    assert application.current_stage is ApplicationStage.SAVED


async def test_updating_details_records_only_what_changed(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    event = await update_details(
        db_session,
        application=application,
        changes={"priority": ApplicationPriority.HIGH, "next_action_at": NOW},
        now=NOW,
    )

    assert event is not None
    assert application.priority is ApplicationPriority.HIGH
    assert set(event.payload["changed"]) == {"priority", "next_action_at"}


async def test_updating_nothing_writes_nothing(db_session: AsyncSession) -> None:
    """A no-op PATCH must not manufacture history."""
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    event = await update_details(db_session, application=application, changes={}, now=NOW)

    assert event is None
    assert len(await _events(db_session, application)) == 1


async def test_archive_and_restore_both_leave_a_trace(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    await set_archived(db_session, application=application, archived=True, now=NOW)
    assert application.archived_at == NOW

    await set_archived(db_session, application=application, archived=False, now=NOW)
    assert application.archived_at is None

    kinds = [e.event_type for e in await _events(db_session, application)]
    assert kinds == [
        ApplicationEventType.SAVED,
        ApplicationEventType.ARCHIVED,
        ApplicationEventType.RESTORED,
    ]


async def test_events_written_in_one_transaction_keep_their_order(
    db_session: AsyncSession,
) -> None:
    """`created_at` must distinguish two writes inside one transaction.

    Postgres's `now()` is the *transaction* timestamp: every row written in one
    transaction gets the same value, so a timeline ordered by it falls back to
    the tiebreak, and the tiebreak is a random UUID. This is asserted rather
    than assumed because it is invisible — the rows are all there, in an order
    that looks plausible and is wrong. `clock_timestamp()` is what makes it
    true, and this test is what stops somebody restoring `now()` for symmetry
    with the other tables.
    """
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)
    await add_note(db_session, application=application, body="first", now=NOW)
    await add_note(db_session, application=application, body="second", now=NOW)

    events = await _events(db_session, application)
    stamps = [e.created_at for e in events]
    assert len(set(stamps)) == len(stamps)
    assert stamps == sorted(stamps)
    assert [e.body for e in events] == [None, "first", "second"]


async def test_an_archived_application_does_not_move(db_session: AsyncSession) -> None:
    """Restore first. Otherwise a stage change silently edits a hidden row."""
    user = await _a_user(db_session)
    job = await _a_job(db_session)
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)
    await set_archived(db_session, application=application, archived=True, now=NOW)

    with pytest.raises(ApplicationArchivedError):
        await change_stage(
            db_session,
            application=application,
            to_stage=ApplicationStage.APPLIED,
            actor=EventActor.USER,
            now=NOW,
        )
