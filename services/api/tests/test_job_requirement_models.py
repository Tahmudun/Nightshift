"""The span trigger, and the constraints around it.

`resume_extractions` has the same guard for the same reason: a requirement
nobody can trace back to a sentence is not auditable, and one whose span quotes
different words than it claims is worse than none at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import JobStatus, RequirementKind, RequirementNecessity
from nightshift.db.models import Company, Job, JobRequirement
from tests.conftest import requires_db

# The session-scoped loop is required, not stylistic: `db_engine` and
# `db_session` are session-scoped, and a function-scoped loop tears itself
# down underneath them (see test_models_canonical_spine.py, which hit this
# first).
pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


async def _requirement_count(session: AsyncSession, job_id: object) -> int:
    from sqlalchemy import func, select

    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(JobRequirement)
                .where(JobRequirement.job_id == job_id)
            )
        ).scalar_one()
    )


async def _job_with_text(session: AsyncSession, text: str) -> Job:
    """Build a canonical job carrying `text` as its description.

    `tests/test_models_canonical_spine.py` builds its jobs with a private,
    module-local `_a_job` helper (no shared `make_job` exists anywhere in the
    suite — checked before writing this). This mirrors that helper's shape
    (company + job, no source record needed since `Job.company_id` is the
    only required foreign key) and adds the one field this file needs:
    `description_text`, which the span trigger reads.
    """
    company = Company(canonical_name="Acme", normalized_name=f"acme {uuid.uuid4().hex[:8]}")
    session.add(company)
    await session.flush()
    now = datetime.now(tz=UTC)
    job = Job(
        company_id=company.id,
        title="Engineer",
        normalized_title="engineer",
        description_text=text,
        first_seen_at=now,
        last_seen_at=now,
        status=JobStatus.OPEN,
    )
    session.add(job)
    await session.flush()
    return job


async def test_a_requirement_quoting_its_span_is_accepted(
    db_session: AsyncSession,
) -> None:
    text = "You will need Kotlin and an Android SDK background."
    job = await _job_with_text(db_session, text)
    start = text.index("Kotlin")
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=start,
            char_end=start + len("Kotlin"),
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    await db_session.flush()


async def test_a_span_that_quotes_the_wrong_words_is_refused(
    db_session: AsyncSession,
) -> None:
    """One character of drift and the highlight disagrees with the claim."""
    text = "You will need Kotlin and an Android SDK background."
    job = await _job_with_text(db_session, text)
    start = text.index("Kotlin")
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=start + 1,  # off by one
            char_end=start + 1 + len("Kotlin"),
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    with pytest.raises(DBAPIError, match="does not quote"):
        await db_session.flush()


async def test_a_span_running_past_the_description_is_refused(
    db_session: AsyncSession,
) -> None:
    text = "Kotlin."
    job = await _job_with_text(db_session, text)
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=0,
            char_end=9999,
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    with pytest.raises(DBAPIError, match="runs past"):
        await db_session.flush()


async def test_rewriting_the_description_clears_its_requirements(
    db_session: AsyncSession,
) -> None:
    """The span trigger cannot see the parent change. This is what does.

    Reproduced before it was fixed: a requirement quoting "Kotlin" at the right
    offsets, then a description rewrite, and the row pointed at ``'ent wo'``
    while still claiming ``raw_text='Kotlin'``. Ingestion rewrites this column
    on every re-poll of a known job, so it is a live path, not a dormant one.
    """
    text = "You will need Kotlin and an Android SDK background."
    job = await _job_with_text(db_session, text)
    start = text.index("Kotlin")
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=start,
            char_end=start + len("Kotlin"),
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    await db_session.flush()
    assert await _requirement_count(db_session, job.id) == 1

    job.description_text = "Totally different words now, no framework named."
    await db_session.flush()

    assert await _requirement_count(db_session, job.id) == 0


async def test_rewriting_an_unrelated_column_keeps_the_requirements(
    db_session: AsyncSession,
) -> None:
    """Only the column the spans point into may clear them."""
    text = "You will need Kotlin and an Android SDK background."
    job = await _job_with_text(db_session, text)
    start = text.index("Kotlin")
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=start,
            char_end=start + len("Kotlin"),
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    await db_session.flush()

    job.title = "A different title entirely"
    await db_session.flush()

    assert await _requirement_count(db_session, job.id) == 1


async def test_rewriting_the_description_to_the_same_text_keeps_them(
    db_session: AsyncSession,
) -> None:
    """Re-ingestion assigns the column whether or not the board changed it.

    ``IS DISTINCT FROM`` is what stops every poll of an unchanged board
    throwing away work the extractor would only have to redo.
    """
    text = "You will need Kotlin and an Android SDK background."
    job = await _job_with_text(db_session, text)
    start = text.index("Kotlin")
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=start,
            char_end=start + len("Kotlin"),
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    await db_session.flush()

    job.description_text = text  # the same words, assigned again
    await db_session.flush()

    assert await _requirement_count(db_session, job.id) == 1


async def test_an_inverted_span_is_refused(db_session: AsyncSession) -> None:
    text = "Kotlin."
    job = await _job_with_text(db_session, text)
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Kotlin",
            raw_text="Kotlin",
            char_start=6,
            char_end=2,
            necessity=RequirementNecessity.REQUIRED,
            has_equivalence=False,
            extractor_version="m3a.1",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
