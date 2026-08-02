"""The three tables M1b adds, and the guarantees they are supposed to carry.

The append-only assertions are the point of this file. ``job_status_events`` is
what makes a closure auditable after the job reopens, and an append-only table
enforced by convention is a comment with extra syntax. CLAUDE.md §7 requires a
trigger, so these tests attempt the mutation and expect the database to refuse.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import JobStatus
from nightshift.db.models import Company, Job, JobMergeEvent, JobStatusEvent
from tests.conftest import requires_db

# The session-scoped loop is required, not stylistic: `db_engine` and
# `db_session` are session-scoped, and a function-scoped loop tears itself down
# underneath them. The symptom is an "another operation is in progress" error
# raised from the teardown rollback, which masks whatever the test actually did.
pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


async def _a_job(session: AsyncSession) -> Job:
    company = Company(canonical_name="Acme", normalized_name=f"acme {uuid.uuid4().hex[:8]}")
    session.add(company)
    await session.flush()
    now = datetime.now(tz=UTC)
    job = Job(
        company_id=company.id,
        title="Engineer",
        normalized_title="engineer",
        first_seen_at=now,
        last_seen_at=now,
        status=JobStatus.OPEN,
    )
    session.add(job)
    await session.flush()
    return job


async def test_status_event_can_be_inserted(db_session: AsyncSession) -> None:
    job = await _a_job(db_session)
    db_session.add(
        JobStatusEvent(
            job_id=job.id,
            from_status=JobStatus.OPEN,
            to_status=JobStatus.POSSIBLY_STALE,
            reason="missed 3 consecutive polls",
        )
    )
    await db_session.flush()
    rows = (
        (await db_session.execute(select(JobStatusEvent).where(JobStatusEvent.job_id == job.id)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].to_status is JobStatus.POSSIBLY_STALE
    assert rows[0].from_status is JobStatus.OPEN


async def test_the_first_event_of_a_life_may_have_no_prior_state(
    db_session: AsyncSession,
) -> None:
    """``from_status`` is nullable on purpose: a newly created job transitioned
    from nothing, and writing ``open -> open`` would be a fabricated event."""
    job = await _a_job(db_session)
    db_session.add(
        JobStatusEvent(job_id=job.id, from_status=None, to_status=JobStatus.OPEN, reason="created")
    )
    await db_session.flush()
    row = (
        await db_session.execute(select(JobStatusEvent).where(JobStatusEvent.job_id == job.id))
    ).scalar_one()
    assert row.from_status is None


async def test_status_events_cannot_be_updated(db_session: AsyncSession) -> None:
    """Append-only, enforced by trigger rather than by good intentions."""
    job = await _a_job(db_session)
    db_session.add(
        JobStatusEvent(job_id=job.id, from_status=None, to_status=JobStatus.OPEN, reason="created")
    )
    await db_session.flush()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("UPDATE job_status_events SET reason = 'rewritten' WHERE job_id = :j"),
            {"j": job.id},
        )


async def test_status_events_cannot_be_deleted(db_session: AsyncSession) -> None:
    job = await _a_job(db_session)
    db_session.add(
        JobStatusEvent(job_id=job.id, from_status=None, to_status=JobStatus.OPEN, reason="created")
    )
    await db_session.flush()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("DELETE FROM job_status_events WHERE job_id = :j"), {"j": job.id}
        )


async def test_merge_events_cannot_be_updated(db_session: AsyncSession) -> None:
    winner = await _a_job(db_session)
    db_session.add(
        JobMergeEvent(
            winner_job_id=winner.id,
            loser_job_id=uuid.uuid4(),
            loser_snapshot={"title": "Engineer"},
            reason="identical_content",
            match_confidence=0.99,
            ruleset_version="1",
        )
    )
    await db_session.flush()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("UPDATE job_merge_events SET reason = 'rewritten' WHERE winner_job_id = :w"),
            {"w": winner.id},
        )


async def test_merge_event_keeps_the_loser_id_without_a_foreign_key(
    db_session: AsyncSession,
) -> None:
    """The loser row is gone after a merge, so an FK would be unsatisfiable.

    Reversibility comes from the preserved raw payloads, not from this row —
    but the row has to survive the deletion of what it describes, which is why
    ``loser_job_id`` is a plain uuid column.
    """
    winner = await _a_job(db_session)
    vanished = uuid.uuid4()
    db_session.add(
        JobMergeEvent(
            winner_job_id=winner.id,
            loser_job_id=vanished,
            loser_snapshot={"title": "Engineer"},
            reason="same_canonical_url",
            match_confidence=1.0,
            ruleset_version="1",
        )
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            select(JobMergeEvent).where(JobMergeEvent.loser_job_id == vanished)
        )
    ).scalar_one()
    assert row.ruleset_version == "1"
    assert row.loser_snapshot == {"title": "Engineer"}


async def test_a_job_cannot_be_merged_into_itself(db_session: AsyncSession) -> None:
    """A self-merge would delete the winner. The constraint is cheap insurance
    against a candidate-generation bug that stops excluding ``Job.id``."""
    winner = await _a_job(db_session)
    db_session.add(
        JobMergeEvent(
            winner_job_id=winner.id,
            loser_job_id=winner.id,
            loser_snapshot={},
            reason="same_canonical_url",
            match_confidence=1.0,
            ruleset_version="1",
        )
    )
    with pytest.raises(DBAPIError):
        await db_session.flush()


async def test_merge_confidence_must_be_a_probability(db_session: AsyncSession) -> None:
    winner = await _a_job(db_session)
    db_session.add(
        JobMergeEvent(
            winner_job_id=winner.id,
            loser_job_id=uuid.uuid4(),
            loser_snapshot={},
            reason="similar_description",
            match_confidence=1.5,
            ruleset_version="1",
        )
    )
    with pytest.raises(DBAPIError):
        await db_session.flush()
