"""Manual capture: what the parser may claim, and what only a person may.

Two rules carry this module, and every test here exists to hold one of them.

1. **Nothing a parser produced reaches ``jobs``.** The confirmation is the only
   route, and the schema — not a code path — is what enforces it.
2. **A posting has one identity, whoever pasted it.** Two people capturing the
   same opening get one job, because the id is derived from content rather than
   from the capture or the user.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    CaptureStatus,
    EmploymentType,
    JobStatus,
    LocationConfidence,
    SourceType,
)
from nightshift.db.models import CapturedPosting, Company, Job, JobLocation, User
from nightshift.domain.capture import (
    CaptureAlreadyDecidedError,
    capture_source_job_id,
    confirm_capture,
    create_capture,
    discard_capture,
    propose,
)
from tests.conftest import requires_db

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)

# A realistic LinkedIn-shaped paste: title, then "Employer · Location (Policy)".
LINKEDIN_PASTE = """Senior Software Engineer, Platform
Datadog · New York, NY (Hybrid)

About the job
We are looking for a platform engineer to work on our ingestion pipeline.
Requirements: Python, Kubernetes, and 5 years of experience.
"""


# --------------------------------------------------------------------------
# The parser. No database — these are pure.
# --------------------------------------------------------------------------


def test_it_reads_a_linkedin_shaped_paste() -> None:
    proposal = propose(LINKEDIN_PASTE)
    assert proposal.title == "Senior Software Engineer, Platform"
    assert proposal.company_name == "Datadog"
    assert proposal.location_text == "New York, NY (Hybrid)"


def test_it_proposes_nothing_for_an_empty_paste() -> None:
    assert propose("   \n\n  ") == propose("")


def test_it_declines_a_title_that_is_a_paragraph() -> None:
    """A long first line is prose, not a job title, and seeding the form with
    it would be worse than seeding nothing."""
    proposal = propose("x" * 500 + "\nDatadog")
    assert proposal.title is None


def test_it_declines_a_url_as_a_title_or_company() -> None:
    proposal = propose("https://example.com/jobs/1\nwww.example.com")
    assert proposal.title is None
    assert proposal.company_name is None


@pytest.mark.parametrize(
    "line",
    [
        # A bare token the location parser was taught to refuse outright.
        "Multiple Locations",
        # The one that broke the first draft of this parser. Any comma makes
        # `parse_location_segment` claim a city ("Platform"), so a
        # confidence-only test proposed a *job title* as the location. What
        # separates this from a real place is that nothing recognised — no
        # state, no country, no known NYC name — came back with it.
        "Senior Software Engineer, Platform",
        # Same failure, one line down: a company with a legal suffix.
        "Acme, Inc.",
        # A work policy is not a place.
        "Hybrid",
    ],
)
def test_it_declines_anything_with_no_recognised_place_in_it(line: str) -> None:
    assert propose(f"Software Engineer\nAcme\n{line}").location_text is None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("New York, NY", "New York, NY"),
        ("San Francisco, CA", "San Francisco, CA"),
        ("London, United Kingdom", "London, United Kingdom"),
        # ADR 0008's enumerated NYC names, which providers write without a state.
        ("Brooklyn", "Brooklyn"),
    ],
)
def test_it_reads_a_place_that_names_something_recognised(line: str, expected: str) -> None:
    assert propose(f"Software Engineer\nAcme\n{line}").location_text == expected


def test_it_reads_remote_as_a_location() -> None:
    proposal = propose("Software Engineer\nAcme · Remote")
    assert proposal.location_text == "Remote"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Software Engineer Intern", EmploymentType.INTERNSHIP),
        ("Summer 2027 Internship, Backend", EmploymentType.INTERNSHIP),
        # The two words that make a naive substring check wrong, and both are
        # real title words.
        ("Internal Tools Engineer", None),
        ("International Payments Engineer", None),
        ("Staff Software Engineer", None),
    ],
)
def test_internship_detection_is_word_boundaried(
    title: str, expected: EmploymentType | None
) -> None:
    assert propose(f"{title}\nAcme").employment_type is expected


# --------------------------------------------------------------------------
# Identity. Also pure, and the reason two users do not double the corpus.
# --------------------------------------------------------------------------


def test_the_same_posting_has_one_id_however_it_was_typed() -> None:
    """Company and title normalisation feed the id, so cosmetic differences in
    what two people typed do not fork the corpus."""
    first = capture_source_job_id(
        company_name="Datadog, Inc.", title="Senior  Engineer", description="body"
    )
    second = capture_source_job_id(
        company_name="datadog", title="Senior Engineer", description="body"
    )
    assert first == second


def test_a_different_employer_is_a_different_posting() -> None:
    assert capture_source_job_id(
        company_name="Datadog", title="Engineer", description="body"
    ) != capture_source_job_id(company_name="Ramp", title="Engineer", description="body")


# --------------------------------------------------------------------------
# The database rules.
# --------------------------------------------------------------------------

pytestmark_db = [requires_db, pytest.mark.asyncio(loop_scope="session")]


async def _a_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", display_name="Test Person")
    session.add(user)
    await session.flush()
    return user


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_a_capture_creates_no_job_until_it_is_confirmed(db_session: AsyncSession) -> None:
    """Rule 1, at the level a person can see it."""
    user = await _a_user(db_session)
    capture = await create_capture(
        db_session, user_id=user.id, raw_text=LINKEDIN_PASTE, source_url=None
    )

    assert capture.status is CaptureStatus.PENDING
    assert capture.job_id is None
    assert capture.decided_at is None
    # The proposal was stored, and it is not a fact yet.
    assert capture.proposed_company_name == "Datadog"
    assert (await db_session.execute(select(func.count()).select_from(Job))).scalar_one() == 0


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_the_schema_refuses_a_pending_capture_that_carries_a_job(
    db_session: AsyncSession,
) -> None:
    """Rule 1, at the level no code path can get around.

    This is the test that makes the guarantee structural. If it ever passes
    without raising, `confirmed_rows_carry_a_job` has been dropped and a parser
    bug can reach the corpus.
    """
    user = await _a_user(db_session)
    company = Company(canonical_name="Acme", normalized_name="acme")
    db_session.add(company)
    await db_session.flush()
    job = Job(
        company_id=company.id,
        title="Engineer",
        normalized_title="engineer",
        first_seen_at=NOW,
        last_seen_at=NOW,
        status=JobStatus.OPEN,
        employment_type=EmploymentType.UNKNOWN,
    )
    db_session.add(job)
    await db_session.flush()

    db_session.add(
        CapturedPosting(
            user_id=user.id,
            raw_text="anything",
            status=CaptureStatus.PENDING,
            parser_version="1",
            job_id=job.id,
        )
    )
    with pytest.raises(IntegrityError, match="confirmed_rows_carry_a_job"):
        await db_session.flush()
    await db_session.rollback()


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_confirming_creates_a_real_job_through_the_real_pipeline(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    capture = await create_capture(
        db_session,
        user_id=user.id,
        raw_text=LINKEDIN_PASTE,
        source_url="https://example.com/jobs/1",
    )

    job = await confirm_capture(
        db_session,
        capture=capture,
        title="Senior Software Engineer, Platform",
        company_name="Datadog",
        location_text="New York, NY",
        employment_type=EmploymentType.FULL_TIME,
        now=NOW,
    )

    assert capture.status is CaptureStatus.CONFIRMED
    assert capture.job_id == job.id
    assert capture.decided_at == NOW
    assert job.title == "Senior Software Engineer, Platform"

    # It went through normalisation and location parsing, not around them.
    locations = (
        (await db_session.execute(select(JobLocation).where(JobLocation.job_id == job.id)))
        .scalars()
        .all()
    )
    assert [loc.city for loc in locations] == ["New York"]
    # I1: a captured posting names a city and no street, so it earns exactly
    # `city_only` and nothing better.
    assert locations[0].location_confidence is LocationConfidence.CITY_ONLY


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_capturing_the_same_posting_twice_creates_one_job(
    db_session: AsyncSession,
) -> None:
    """Rule 2, and the property that makes capture safe to encourage."""
    first_user = await _a_user(db_session)
    second_user = await _a_user(db_session)

    fields = {
        "title": "Senior Software Engineer, Platform",
        "company_name": "Datadog",
        "location_text": "New York, NY",
        "employment_type": EmploymentType.FULL_TIME,
    }

    first_capture = await create_capture(
        db_session, user_id=first_user.id, raw_text=LINKEDIN_PASTE, source_url=None
    )
    first_job = await confirm_capture(db_session, capture=first_capture, now=NOW, **fields)

    # A different person, a different capture row, the same posting — and
    # deliberately a different tracking URL, because the id must not key on it.
    second_capture = await create_capture(
        db_session,
        user_id=second_user.id,
        raw_text=LINKEDIN_PASTE,
        source_url="https://example.com/jobs/1?refId=abc123",
    )
    second_job = await confirm_capture(db_session, capture=second_capture, now=NOW, **fields)

    assert first_job.id == second_job.id
    assert (await db_session.execute(select(func.count()).select_from(Job))).scalar_one() == 1
    # Both captures are real, separate, user-owned records of a real action.
    assert first_capture.id != second_capture.id
    assert first_capture.user_id != second_capture.user_id


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_a_decision_is_made_once(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    capture = await create_capture(
        db_session, user_id=user.id, raw_text=LINKEDIN_PASTE, source_url=None
    )
    await confirm_capture(
        db_session,
        capture=capture,
        title="Engineer",
        company_name="Datadog",
        location_text="New York, NY",
        employment_type=EmploymentType.FULL_TIME,
        now=NOW,
    )

    with pytest.raises(CaptureAlreadyDecidedError):
        await confirm_capture(
            db_session,
            capture=capture,
            title="Engineer",
            company_name="Datadog",
            location_text="New York, NY",
            employment_type=EmploymentType.FULL_TIME,
            now=NOW,
        )
    with pytest.raises(CaptureAlreadyDecidedError):
        await discard_capture(db_session, capture=capture, now=NOW)


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_discarding_creates_nothing_and_keeps_the_record(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    capture = await create_capture(
        db_session, user_id=user.id, raw_text=LINKEDIN_PASTE, source_url=None
    )
    await discard_capture(db_session, capture=capture, now=NOW)

    assert capture.status is CaptureStatus.DISCARDED
    assert capture.job_id is None
    assert capture.decided_at == NOW
    assert (await db_session.execute(select(func.count()).select_from(Job))).scalar_one() == 0


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_a_capture_follows_its_job_through_a_dedupe_merge(
    db_session: AsyncSession,
) -> None:
    """The defect this test was written for was found by reading, not by failing.

    ``captured_postings.job_id`` is ``ON DELETE SET NULL`` under a constraint
    that a confirmed row must carry a job. ``merge_jobs`` deletes the loser. So
    a capture whose job loses a merge does not merely lose its link — the null
    trips ``confirmed_rows_carry_a_job`` and the *merge itself* aborts, which
    would have taken down ordinary polling of any board that happened to
    duplicate something somebody had pasted.

    Remove the re-pointing loop in ``merge_jobs`` and this goes red with an
    IntegrityError rather than an assertion, which is the shape of the bug.
    """
    from nightshift.domain.dedupe import DedupeVerdict
    from nightshift.domain.ingestion import merge_jobs

    user = await _a_user(db_session)
    company = Company(canonical_name="Acme", normalized_name="acme")
    db_session.add(company)
    await db_session.flush()

    capture = await create_capture(
        db_session, user_id=user.id, raw_text=LINKEDIN_PASTE, source_url=None
    )
    loser = await confirm_capture(
        db_session,
        capture=capture,
        title="Engineer",
        company_name="Acme",
        location_text="New York, NY",
        employment_type=EmploymentType.FULL_TIME,
        now=NOW,
    )

    winner = Job(
        company_id=company.id,
        title="Engineer",
        normalized_title="engineer",
        first_seen_at=NOW,
        last_seen_at=NOW,
        status=JobStatus.OPEN,
        employment_type=EmploymentType.UNKNOWN,
    )
    db_session.add(winner)
    await db_session.flush()

    await merge_jobs(
        db_session,
        winner=winner,
        loser=loser,
        verdict=DedupeVerdict(merge=True, reason="same_title", confidence=1.0),
    )

    await db_session.refresh(capture)
    assert capture.job_id == winner.id
    assert capture.status is CaptureStatus.CONFIRMED


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_a_captured_job_is_attributed_to_a_source_that_says_so(
    db_session: AsyncSession,
) -> None:
    """I7. A captured posting must never be indistinguishable from a polled one."""
    from nightshift.db.models import JobSourceLink, Source, SourceJobRecord

    user = await _a_user(db_session)
    capture = await create_capture(
        db_session, user_id=user.id, raw_text=LINKEDIN_PASTE, source_url=None
    )
    job = await confirm_capture(
        db_session,
        capture=capture,
        title="Engineer",
        company_name="Datadog",
        location_text="New York, NY",
        employment_type=EmploymentType.FULL_TIME,
        now=NOW,
    )

    source = (
        await db_session.execute(
            select(Source)
            .join(SourceJobRecord, SourceJobRecord.source_id == Source.id)
            .join(JobSourceLink, JobSourceLink.source_job_record_id == SourceJobRecord.id)
            .where(JobSourceLink.job_id == job.id)
        )
    ).scalar_one()
    assert source.source_type is SourceType.MANUAL_CAPTURE

    # And the paste survives verbatim, so a parser fix is a backfill.
    record = (
        await db_session.execute(
            select(SourceJobRecord)
            .join(JobSourceLink, JobSourceLink.source_job_record_id == SourceJobRecord.id)
            .where(JobSourceLink.job_id == job.id)
        )
    ).scalar_one()
    assert record.raw_payload["captured"]["raw_text"] == LINKEDIN_PASTE
