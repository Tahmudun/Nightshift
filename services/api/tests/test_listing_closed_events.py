"""A closing listing informs the user. It does not move their application.

This is §3's last paragraph and invariant I5 in one place. The failure mode it
guards against is quiet and plausible: ingestion "helpfully" setting a tracked
application to `closed` because the posting went away. That would be a system
actor making a judgement about somebody's job search — the person may well have
an interview next week for a role that was taken off the board.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationStage,
    EventActor,
    JobStatus,
)
from nightshift.db.models import Application, ApplicationEvent, Company, Job, User
from nightshift.domain.applications import record_listing_closed, save_job, set_archived
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


async def _tracked(session: AsyncSession) -> tuple[Application, Job]:
    user = User(email=f"{uuid.uuid4()}@example.test")
    company = Company(canonical_name="Example Inc.", normalized_name=str(uuid.uuid4()))
    session.add_all([user, company])
    await session.flush()
    job = Job(
        company_id=company.id,
        title="Software Engineer",
        normalized_title="software engineer",
        status=JobStatus.OPEN,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(job)
    await session.flush()
    application, _ = await save_job(session, user_id=user.id, job_id=job.id, now=NOW)
    return application, job


async def test_a_closing_listing_writes_an_event(db_session: AsyncSession) -> None:
    application, job = await _tracked(db_session)

    notified = await record_listing_closed(
        db_session, job_id=job.id, now=NOW, reason="3 misses over 8 days"
    )

    assert notified == 1
    event = (
        await db_session.execute(
            select(ApplicationEvent).where(
                ApplicationEvent.application_id == application.id,
                ApplicationEvent.event_type == ApplicationEventType.LISTING_CLOSED,
            )
        )
    ).scalar_one()
    assert event.actor is EventActor.SYSTEM
    assert event.to_stage is None
    assert event.body is not None and "3 misses" in event.body


async def test_a_closing_listing_does_not_move_the_stage(db_session: AsyncSession) -> None:
    """The assertion this whole task exists for."""
    application, job = await _tracked(db_session)
    before = application.current_stage

    await record_listing_closed(db_session, job_id=job.id, now=NOW, reason="closed")

    await db_session.refresh(application)
    assert application.current_stage is before is ApplicationStage.SAVED
    assert application.archived_at is None


async def test_an_archived_application_is_not_notified(db_session: AsyncSession) -> None:
    """Nobody wants a notification about a role they put away last month."""
    application, job = await _tracked(db_session)
    await set_archived(db_session, application=application, archived=True, now=NOW)

    notified = await record_listing_closed(db_session, job_id=job.id, now=NOW, reason="closed")

    assert notified == 0


async def test_a_job_nobody_tracks_notifies_nobody(db_session: AsyncSession) -> None:
    company = Company(canonical_name="Example Inc.", normalized_name=str(uuid.uuid4()))
    db_session.add(company)
    await db_session.flush()
    job = Job(
        company_id=company.id,
        title="Untracked",
        normalized_title="untracked",
        status=JobStatus.OPEN,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    db_session.add(job)
    await db_session.flush()

    assert await record_listing_closed(db_session, job_id=job.id, now=NOW, reason="x") == 0


async def test_the_ingestion_pipeline_notifies_on_a_real_closure(
    db_session: AsyncSession,
) -> None:
    """End to end through `apply_freshness`, not through the helper.

    A helper that is correct and never called is the failure this test exists
    to catch — and it is the exact shape of M1d's finding 9, where the pipeline
    had never been run against Greenhouse at all and nothing went red.

    Drives closure through `test_closure_pipeline._poll`, the same helper that
    file's own tests use: an empty-but-successful board poll, which is real
    evidence of absence and deliberately not the same as a failed fetch.
    Repeated past both ADR 0009 thresholds (three misses **and** seven elapsed
    days), it closes the job for real.
    """
    # These three are private to that module. Importing them is deliberate: a
    # second way to drive a closure is a second thing that can drift from the
    # closure rules.
    from tests.test_closure_pipeline import _outcome, _payload, _poll

    user = User(email=f"{uuid.uuid4()}@example.test")
    db_session.add(user)
    await db_session.flush()

    await _poll(db_session, _outcome(_payload()), NOW)
    # order_by, so the job this test tracks is the same one on every run.
    job = (await db_session.execute(select(Job).order_by(Job.id).limit(1))).scalars().one()
    application, _ = await save_job(db_session, user_id=user.id, job_id=job.id, now=NOW)

    for day in (4, 8, 12):
        await _poll(db_session, _outcome([]), NOW + timedelta(days=day))

    await db_session.refresh(job)
    await db_session.refresh(application)
    assert job.status is JobStatus.CLOSED
    # The listing closed. The application did not.
    assert application.current_stage is ApplicationStage.SAVED

    kinds = [
        event.event_type
        for event in (
            await db_session.execute(
                select(ApplicationEvent).where(ApplicationEvent.application_id == application.id)
            )
        )
        .scalars()
        .all()
    ]
    assert ApplicationEventType.LISTING_CLOSED in kinds
