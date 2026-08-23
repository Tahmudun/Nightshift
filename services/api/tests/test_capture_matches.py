"""Does Nightshift already hold the job somebody is about to capture?

M5d / ADR 0039 §4. The corpus polls thousands of board tokens first-hand, so
most NYC tech postings a reader finds on LinkedIn are **already in it** — with
a match score, a location Nightshift trusts and a source it can go back to.
Capturing one of those is worse than useless: it costs a review, and it
produces a thinner second record of a job already held.

This is advisory and it is not ``dedupe.compare``. Nothing is merged, no
``job_merge_event`` is written, and the reader decides. The merge comparator
would need an employment type, a location set and a description hash that a
paste does not honestly have.

The test that matters most is the last one: **when there is nothing to check
with, the answer is "not checked", never an empty list.** An empty list reads
as "no duplicates", and presenting silence as evidence is the I3 failure in a
new place.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import JobStatus
from nightshift.db.models import Job
from nightshift.domain.capture_matches import check_corpus
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


async def _job(
    session: AsyncSession,
    *,
    company: str,
    title: str,
    status: JobStatus = JobStatus.OPEN,
) -> Job:
    """A canonical job under a real company, normalised the way ingestion does."""
    from nightshift.adapters.greenhouse import normalize_title
    from nightshift.domain.ingestion import get_or_create_company

    # The real upsert, not a fresh Company each time: `normalized_name` is
    # unique, and the check under test looks companies up by exactly that
    # value. A randomised name would make every lookup miss and every test
    # here pass for the wrong reason.
    row = await get_or_create_company(session, company)

    now = datetime.now(tz=UTC)
    job = Job(
        company_id=row.id,
        title=title,
        normalized_title=normalize_title(title),
        first_seen_at=now,
        last_seen_at=now,
        status=status,
        closed_at=now if status is JobStatus.CLOSED else None,
    )
    session.add(job)
    await session.flush()
    return job


@pytest_asyncio.fixture(loop_scope="session")
async def existing(db_session: AsyncSession) -> Job:
    return await _job(db_session, company="Ramp", title="Staff Backend Engineer")


async def test_the_same_company_and_title_is_named(db_session: AsyncSession, existing: Job) -> None:
    check = await check_corpus(
        db_session,
        title="Staff Backend Engineer",
        company_name="Ramp",
        source_url=None,
    )
    assert check.checked is True
    assert check.why_not is None
    assert [m.job_id for m in check.matches] == [existing.id]
    assert check.matches[0].reason == "same_company_and_title"
    assert check.matches[0].company_name == "Ramp"
    assert check.matches[0].status is JobStatus.OPEN


async def test_normalisation_is_the_ingestion_pipeline_s_own(
    db_session: AsyncSession, existing: Job
) -> None:
    """ "ramp" and "Ramp, Inc." are the same employer to the rest of this system.

    Reusing ``normalize_company_name`` and ``normalize_title`` rather than
    writing a second reading means this check and the corpus agree by
    construction. A private normaliser here would drift and the symptom would
    be a duplicate warning that stops firing.
    """
    check = await check_corpus(
        db_session,
        title="  STAFF   BACKEND ENGINEER ",
        company_name="ramp",
        source_url=None,
    )
    assert [m.job_id for m in check.matches] == [existing.id]


async def test_the_same_title_at_another_company_is_not_a_match(
    db_session: AsyncSession, existing: Job
) -> None:
    """The precision half. Titles repeat across the whole industry."""
    check = await check_corpus(
        db_session,
        title="Staff Backend Engineer",
        company_name="Datadog",
        source_url=None,
    )
    assert check.checked is True
    assert check.matches == ()


async def test_another_title_at_the_same_company_is_not_a_match(
    db_session: AsyncSession, existing: Job
) -> None:
    check = await check_corpus(
        db_session, title="Product Designer", company_name="Ramp", source_url=None
    )
    assert check.matches == ()


async def test_a_closed_job_is_returned_and_says_so(db_session: AsyncSession) -> None:
    """The reader needs this one more than the open ones, not less.

    Somebody capturing a role Nightshift already knows has closed is about to
    spend an evening on it. Hiding closed matches to keep the warning "clean"
    would withhold the single most useful thing this check can say.
    """
    closed = await _job(
        db_session,
        company="Datadog",
        title="Senior Platform Engineer",
        status=JobStatus.CLOSED,
    )
    check = await check_corpus(
        db_session, title="Senior Platform Engineer", company_name="Datadog", source_url=None
    )
    assert [m.job_id for m in check.matches] == [closed.id]
    assert check.matches[0].status is JobStatus.CLOSED


async def test_an_open_job_is_reported_before_a_closed_one(db_session: AsyncSession) -> None:
    """Two records of one opening: the live one is the one to act on."""
    company = "Stripe"
    title = "Infrastructure Engineer"
    await _job(db_session, company=company, title=title, status=JobStatus.CLOSED)
    open_row = await _job(db_session, company=company, title=title, status=JobStatus.OPEN)

    check = await check_corpus(db_session, title=title, company_name=company, source_url=None)
    assert len(check.matches) == 2
    assert check.matches[0].job_id == open_row.id
    assert check.matches[0].status is JobStatus.OPEN


async def test_without_a_company_the_answer_is_not_checked(db_session: AsyncSession) -> None:
    """The test this module exists for.

    An empty ``matches`` on an unchecked capture reads as "no duplicates". That
    is silence presented as evidence — I3's failure, in a new place — and it is
    the difference between a reader trusting this check and a reader being
    quietly misled by it.
    """
    check = await check_corpus(
        db_session, title="Staff Backend Engineer", company_name=None, source_url=None
    )
    assert check.checked is False
    assert check.matches == ()
    assert check.why_not is not None
    assert "company" in check.why_not


async def test_without_a_title_the_answer_is_not_checked(db_session: AsyncSession) -> None:
    check = await check_corpus(db_session, title=None, company_name="Ramp", source_url=None)
    assert check.checked is False
    assert check.why_not is not None
    assert "title" in check.why_not


async def test_a_url_can_answer_when_the_text_cannot(db_session: AsyncSession) -> None:
    """The rule that fires when the reader pastes the employer's own ATS link.

    It is narrow — a LinkedIn URL will never equal a Greenhouse one — and it is
    the only rule that works when the parser read nothing, which is exactly the
    case where the other rule is unavailable.
    """
    from nightshift.db.base import SourceType
    from nightshift.db.models import JobSourceLink, SourceJobRecord
    from nightshift.domain.ingestion import get_or_create_source

    url = "https://boards.greenhouse.io/ramp/jobs/1234567?gh_src=abcd"
    job = await _job(db_session, company="Ramp", title="Data Engineer")
    source = await get_or_create_source(
        db_session, name="greenhouse", source_type=SourceType.ATS_GREENHOUSE, base_url=None
    )
    now = datetime.now(tz=UTC)
    record = SourceJobRecord(
        source_id=source.id,
        source_job_id=f"gh-{uuid.uuid4().hex[:8]}",
        source_company_key="ramp",
        canonical_url=url,
        raw_payload={},
        description_hash="0" * 64,
        first_seen_at=now,
        last_seen_at=now,
    )
    db_session.add(record)
    await db_session.flush()
    db_session.add(
        JobSourceLink(
            job_id=job.id,
            source_job_record_id=record.id,
            match_confidence=1.0,
            link_reason="test",
        )
    )
    await db_session.flush()

    check = await check_corpus(
        db_session,
        title=None,
        company_name=None,
        source_url="https://boards.greenhouse.io/ramp/jobs/1234567?utm_source=linkedin",
    )
    assert check.checked is True
    assert [m.job_id for m in check.matches] == [job.id]
    assert check.matches[0].reason == "same_url"
