"""The tracking tables, asserted against a live database.

Three of these are the only reason the invariants hold. The append-only
trigger, the actor check constraint, and the impossibility of deleting an
application are each demonstrated *by attempting the violation and catching the
error* — a constraint nobody has watched reject something is a comment with
extra syntax (milestone-0 review, F3).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
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
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


async def _a_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.test", display_name="Test User")
    session.add(user)
    await session.flush()
    return user


async def _a_job(session: AsyncSession) -> Job:
    company = Company(canonical_name="Example Inc.", normalized_name=str(uuid.uuid4()))
    session.add(company)
    await session.flush()
    job = Job(
        company_id=company.id,
        title="Software Engineer",
        # NOT NULL on `jobs`. The plan's helper omitted it and every test in
        # this file failed on the same insert.
        normalized_title="software engineer",
        status=JobStatus.OPEN,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(job)
    await session.flush()
    return job


async def _an_application(session: AsyncSession) -> Application:
    user = await _a_user(session)
    job = await _a_job(session)
    application = Application(user_id=user.id, job_id=job.id)
    session.add(application)
    await session.flush()
    return application


async def test_a_new_application_starts_at_saved(db_session: AsyncSession) -> None:
    """Not `discovered`. In M2 nothing enters the pipeline without a click."""
    application = await _an_application(db_session)
    assert application.current_stage is ApplicationStage.SAVED
    assert application.priority is ApplicationPriority.NORMAL
    assert application.archived_at is None
    assert application.applied_at is None


async def test_one_application_per_user_and_job(db_session: AsyncSession) -> None:
    """Saving twice must not create a second pipeline entry for one role."""
    first = await _an_application(db_session)
    db_session.add(Application(user_id=first.user_id, job_id=first.job_id))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_events_cannot_be_updated(db_session: AsyncSession) -> None:
    application = await _an_application(db_session)
    db_session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.SAVED,
            actor=EventActor.USER,
            occurred_at=NOW,
        )
    )
    await db_session.flush()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("UPDATE application_events SET body = 'rewritten' WHERE application_id = :a"),
            {"a": application.id},
        )


async def test_events_cannot_be_deleted(db_session: AsyncSession) -> None:
    application = await _an_application(db_session)
    db_session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.SAVED,
            actor=EventActor.USER,
            occurred_at=NOW,
        )
    )
    await db_session.flush()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("DELETE FROM application_events WHERE application_id = :a"),
            {"a": application.id},
        )


async def test_an_application_cannot_be_deleted_either(db_session: AsyncSession) -> None:
    """A consequence worth stating rather than discovering.

    ``application_events.application_id`` is ``ON DELETE CASCADE``, and a
    cascading delete fires the child table's row trigger. So deleting an
    application means deleting its events, which the database refuses. History
    is therefore not merely append-only — it is undeletable through the row it
    hangs from. Archive is the reversible path; there is no other.
    """
    application = await _an_application(db_session)
    db_session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.SAVED,
            actor=EventActor.USER,
            occurred_at=NOW,
        )
    )
    await db_session.flush()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("DELETE FROM applications WHERE id = :a"), {"a": application.id}
        )


async def test_a_system_actor_may_not_move_a_stage(db_session: AsyncSession) -> None:
    """Invariant I5, as a check constraint.

    Ingestion may record that a listing closed. It may not decide that your
    application is closed. The distinction is the whole of §3's last paragraph,
    and here it is a database error rather than a code review.
    """
    application = await _an_application(db_session)
    db_session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.STAGE_CHANGED,
            actor=EventActor.SYSTEM,
            occurred_at=NOW,
            from_stage=ApplicationStage.SAVED,
            to_stage=ApplicationStage.CLOSED,
            transition_class=TransitionClass.ADVANCE,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_system_actor_may_still_record_a_fact(db_session: AsyncSession) -> None:
    """The other half of the constraint: it must not block `listing_closed`."""
    application = await _an_application(db_session)
    db_session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.LISTING_CLOSED,
            actor=EventActor.SYSTEM,
            occurred_at=NOW,
            body="the source stopped listing this role",
        )
    )
    await db_session.flush()

    stored = (
        await db_session.execute(
            select(ApplicationEvent).where(ApplicationEvent.application_id == application.id)
        )
    ).scalar_one()
    assert stored.to_stage is None


async def test_stage_fields_travel_together(db_session: AsyncSession) -> None:
    """A `to_stage` with no classification is a half-recorded transition."""
    application = await _an_application(db_session)
    db_session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.STAGE_CHANGED,
            actor=EventActor.USER,
            occurred_at=NOW,
            from_stage=ApplicationStage.SAVED,
            to_stage=ApplicationStage.APPLIED,
            transition_class=None,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
