"""Requirements follow the description, and re-ingestion does not multiply them.

A requirement's span is an offset into `jobs.description_text`. That makes the
two inseparable: the moment the text moves, every row derived from the old text
is either rejected by the trigger or — worse — still accepted while quoting
different words. So the rows are replaced wholesale rather than diffed, and
these tests are the proof that they are.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.models import JobRequirement
from nightshift.domain.ingestion import sync_requirements
from tests.conftest import make_job_with_text, requires_db

# Session-scoped loop, for the reason recorded in test_job_requirement_models.py:
# `db_engine` and `db_session` are session-scoped and a function-scoped loop
# tears itself down underneath them.
pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

_TEXT = "WHAT YOU'LL NEED Proficiency in Kotlin. NICE TO HAVES React."


async def _count(session: AsyncSession, job_id: object) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(JobRequirement)
                .where(JobRequirement.job_id == job_id)
            )
        ).scalar_one()
    )


async def _rows(session: AsyncSession, job_id: object) -> list[JobRequirement]:
    return list(
        (
            await session.execute(
                select(JobRequirement)
                .where(JobRequirement.job_id == job_id)
                .order_by(JobRequirement.char_start, JobRequirement.value)
            )
        )
        .scalars()
        .all()
    )


async def test_syncing_twice_produces_the_same_rows(db_session: AsyncSession) -> None:
    """M1's idempotency criterion, applied to a new table."""
    job = await make_job_with_text(db_session, _TEXT)
    first = await sync_requirements(db_session, job)
    await db_session.flush()
    second = await sync_requirements(db_session, job)
    await db_session.flush()

    assert first == second
    assert first > 0, "a description with two headings and two skills must yield rows"
    assert await _count(db_session, job.id) == first


async def test_syncing_twice_stores_the_same_values(db_session: AsyncSession) -> None:
    """Equal counts are not equal rows. Compare what is actually stored."""
    job = await make_job_with_text(db_session, _TEXT)
    await sync_requirements(db_session, job)
    await db_session.flush()
    before = [
        (r.kind, r.value, r.char_start, r.char_end, r.necessity)
        for r in await _rows(db_session, job.id)
    ]

    await sync_requirements(db_session, job)
    await db_session.flush()
    after = [
        (r.kind, r.value, r.char_start, r.char_end, r.necessity)
        for r in await _rows(db_session, job.id)
    ]

    assert before == after


async def test_changing_the_description_replaces_the_requirements(
    db_session: AsyncSession,
) -> None:
    """Stale spans point at characters that have moved. They must not survive.

    The guard that holds this up is the database's, not this function's:
    `jobs_description_change_clears_requirements` (Task 5) clears the rows on
    the UPDATE itself. Measured — removing the delete from `sync_requirements`
    leaves this test green. It is kept because it asserts the end state a
    caller depends on, whichever layer produces it.
    """
    job = await make_job_with_text(db_session, _TEXT)
    await sync_requirements(db_session, job)
    await db_session.flush()

    job.description_text = "REQUIREMENTS Proficiency in Python."
    await sync_requirements(db_session, job)
    await db_session.flush()

    rows = await _rows(db_session, job.id)
    assert {r.value for r in rows if r.kind.value == "technology"} == {"Python"}
    assert job.description_text is not None
    for row in rows:
        assert job.description_text[row.char_start : row.char_end] == row.raw_text


async def test_a_job_with_no_description_gets_no_requirements(
    db_session: AsyncSession,
) -> None:
    """Not an error, and not a zero-requirement claim either — just no rows."""
    job = await make_job_with_text(db_session, None)
    assert await sync_requirements(db_session, job) == 0
    assert await _count(db_session, job.id) == 0


async def test_losing_a_description_clears_the_requirements(
    db_session: AsyncSession,
) -> None:
    """The dangerous direction: text goes away, spans point at nothing.

    Also the database's guard rather than this function's — `NULL IS DISTINCT
    FROM 'text'` is true, so the trigger fires on a description being cleared
    exactly as it does on one being edited. Asserted here because "the text is
    gone" is the case a reader most expects to have been forgotten.
    """
    job = await make_job_with_text(db_session, _TEXT)
    assert await sync_requirements(db_session, job) > 0
    await db_session.flush()

    job.description_text = None
    assert await sync_requirements(db_session, job) == 0
    await db_session.flush()
    assert await _count(db_session, job.id) == 0


async def test_every_stored_row_quotes_its_own_span(db_session: AsyncSession) -> None:
    """The trigger enforces this. Asserting it here proves the trigger ran."""
    job = await make_job_with_text(db_session, _TEXT)
    await sync_requirements(db_session, job)
    await db_session.flush()

    for row in await _rows(db_session, job.id):
        assert _TEXT[row.char_start : row.char_end] == row.raw_text
