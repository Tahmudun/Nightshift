"""The daily queue: four rows, and the boundaries that decide who is in them.

Every threshold here is tested at three points — one day inside, exactly on,
and one day outside. An off-by-one in this file shows a person the wrong jobs
and looks completely plausible while doing it, which is why the boundary cases
are the point of the file rather than an extra.

``now`` is passed in everywhere. A query function that read the clock itself
could not be tested at a boundary at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationStage,
    EligibilityState,
    EventActor,
    InternshipSeason,
    JobStatus,
    Seniority,
    TransitionClass,
)
from nightshift.db.models import Application, ApplicationEvent, Company, Job, User
from nightshift.domain.queue import (
    FOLLOW_UP_SILENT_DAYS,
    INTERVIEW_HORIZON_DAYS,
    NEW_INTERNSHIP_DAYS,
    ROW_CAP,
    STALE_SAVED_DAYS,
    DailyQueue,
    QueueSection,
    QueueSectionKey,
    build_queue,
)
from tests.conftest import requires_db, store_score

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)

#: Every job in this file carries it, so a stored score has a real span to quote.
DESCRIPTION = "We need strong Python and PostgreSQL for a team in New York."


async def _a_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.test")
    session.add(user)
    await session.flush()
    return user


async def _a_job(
    session: AsyncSession,
    *,
    title: str = "Software Engineer",
    status: JobStatus = JobStatus.OPEN,
    seniority: Seniority | None = None,
    first_seen_at: datetime = NOW,
    internship_season: InternshipSeason | None = None,
    internship_year: int | None = None,
) -> Job:
    """A job, with ``closed_at`` kept consistent with ``status``.

    ``ck_jobs_closed_at_matches_status`` is a biconditional — a closed job has a
    closure timestamp and an open one does not (I3). A helper that set the
    status alone could not insert a closed job at all, which is the schema
    doing its job and worth stating rather than working around.

    ``description_text`` is always set because M3d Task 7's rows carry scores,
    and the evidence-quoting trigger checks the characters of a real string.
    """
    company = Company(canonical_name="Example Inc.", normalized_name=str(uuid.uuid4()))
    session.add(company)
    await session.flush()
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.casefold(),
        description_text=DESCRIPTION,
        status=status,
        closed_at=NOW - timedelta(days=1) if status is JobStatus.CLOSED else None,
        seniority=seniority,
        internship_season=internship_season,
        internship_year=internship_year,
        first_seen_at=first_seen_at,
        last_seen_at=NOW,
    )
    session.add(job)
    await session.flush()
    return job


async def _an_application(
    session: AsyncSession,
    *,
    user: User,
    job: Job,
    stage: ApplicationStage = ApplicationStage.SAVED,
    next_action_at: datetime | None = None,
    archived_at: datetime | None = None,
    saved_at: datetime = NOW,
) -> Application:
    """An application with its one ``saved`` event, as ``save_job`` would leave it."""
    application = Application(
        user_id=user.id,
        job_id=job.id,
        current_stage=stage,
        next_action_at=next_action_at,
        archived_at=archived_at,
    )
    session.add(application)
    await session.flush()
    session.add(
        ApplicationEvent(
            application_id=application.id,
            event_type=ApplicationEventType.SAVED,
            actor=EventActor.USER,
            occurred_at=saved_at,
            to_stage=ApplicationStage.SAVED,
            transition_class=TransitionClass.ADVANCE,
        )
    )
    await session.flush()
    return application


async def _an_event(
    session: AsyncSession,
    *,
    application: Application,
    event_type: ApplicationEventType,
    actor: EventActor,
    occurred_at: datetime,
) -> ApplicationEvent:
    event = ApplicationEvent(
        application_id=application.id,
        event_type=event_type,
        actor=actor,
        occurred_at=occurred_at,
    )
    session.add(event)
    await session.flush()
    return event


def _section(queue: DailyQueue, key: QueueSectionKey) -> QueueSection:
    return {section.key: section for section in queue.sections}[key]


def _ids(queue: DailyQueue, key: QueueSectionKey) -> set[uuid.UUID]:
    return {row.application_id for row in _section(queue, key).rows}


# --- Follow up -------------------------------------------------------------


async def test_a_due_next_action_is_a_follow_up(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        next_action_at=NOW - timedelta(hours=1),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id in _ids(queue, QueueSectionKey.FOLLOW_UP)


async def test_a_future_next_action_is_not_a_follow_up_yet(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        next_action_at=NOW + timedelta(days=1),
        saved_at=NOW,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.FOLLOW_UP)


@pytest.mark.parametrize(
    ("days_silent", "expected"),
    [
        (FOLLOW_UP_SILENT_DAYS - 1, False),
        (FOLLOW_UP_SILENT_DAYS, True),
        (FOLLOW_UP_SILENT_DAYS + 1, True),
    ],
)
async def test_the_follow_up_boundary(
    db_session: AsyncSession, days_silent: int, expected: bool
) -> None:
    """Exactly seven days of silence counts. Six does not."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=days_silent),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert (application.id in _ids(queue, QueueSectionKey.FOLLOW_UP)) is expected


async def test_an_assessment_with_a_date_is_a_follow_up(db_session: AsyncSession) -> None:
    """§7.1: assessments fold in here rather than getting their own row."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.ASSESSMENT,
        next_action_at=NOW - timedelta(hours=2),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id in _ids(queue, QueueSectionKey.FOLLOW_UP)


async def test_a_rejected_application_is_never_a_follow_up(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.REJECTED,
        next_action_at=NOW - timedelta(days=30),
        saved_at=NOW - timedelta(days=90),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.FOLLOW_UP)


async def test_a_system_event_does_not_count_as_activity(db_session: AsyncSession) -> None:
    """The load-bearing filter on the whole page (§7.2).

    A ``listing_closed`` written by the poller is not the user touching the job.
    If it counted, a closing listing would silently make its application look
    freshly handled and drop it out of the queue that exists to surface it.
    """
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=30),
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.LISTING_CLOSED,
        actor=EventActor.SYSTEM,
        occurred_at=NOW,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id in _ids(queue, QueueSectionKey.FOLLOW_UP)


async def test_a_user_note_does_count_as_activity(db_session: AsyncSession) -> None:
    """The other half of the same filter — without this, the test above would
    pass on a function that ignored events entirely."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=30),
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.NOTE_ADDED,
        actor=EventActor.USER,
        occurred_at=NOW - timedelta(days=1),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.FOLLOW_UP)


# --- Interviews approaching ------------------------------------------------


@pytest.mark.parametrize(
    ("days_ahead", "expected"),
    [(-1, False), (1, True), (INTERVIEW_HORIZON_DAYS, True), (INTERVIEW_HORIZON_DAYS + 1, False)],
)
async def test_the_interview_horizon(
    db_session: AsyncSession, days_ahead: int, expected: bool
) -> None:
    """Yesterday's interview is history, not a queue row."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.INTERVIEW,
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.INTERVIEW_SCHEDULED,
        actor=EventActor.USER,
        occurred_at=NOW + timedelta(days=days_ahead),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert (application.id in _ids(queue, QueueSectionKey.INTERVIEWS_APPROACHING)) is expected


async def test_two_interviews_are_two_rows_soonest_first(db_session: AsyncSession) -> None:
    """One application, two scheduled times. Both are real appointments."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.INTERVIEW,
    )
    for days in (5, 2):
        await _an_event(
            db_session,
            application=application,
            event_type=ApplicationEventType.INTERVIEW_SCHEDULED,
            actor=EventActor.USER,
            occurred_at=NOW + timedelta(days=days),
        )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    rows = _section(queue, QueueSectionKey.INTERVIEWS_APPROACHING).rows
    assert len(rows) == 2
    assert rows[0].at is not None
    assert rows[1].at is not None
    assert rows[0].at < rows[1].at


# --- Stale saved -----------------------------------------------------------


@pytest.mark.parametrize(
    ("days_old", "expected"),
    [(STALE_SAVED_DAYS - 1, False), (STALE_SAVED_DAYS, True), (STALE_SAVED_DAYS + 1, True)],
)
async def test_the_stale_saved_boundary(
    db_session: AsyncSession, days_old: int, expected: bool
) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.SAVED,
        saved_at=NOW - timedelta(days=days_old),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert (application.id in _ids(queue, QueueSectionKey.STALE_SAVED)) is expected


async def test_an_applied_job_is_not_stale_saved(db_session: AsyncSession) -> None:
    """It moved on. Follow up is the row that covers it now."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=90),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.STALE_SAVED)


# --- Closed while saved ----------------------------------------------------


async def test_a_closed_listing_surfaces(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.APPLIED,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id in _ids(queue, QueueSectionKey.CLOSED_WHILE_SAVED)


async def test_a_possibly_stale_listing_does_not_surface(db_session: AsyncSession) -> None:
    """I3. A source that went quiet is not a job that closed, and the queue
    must not tell the user it is."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.POSSIBLY_STALE),
        stage=ApplicationStage.APPLIED,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.CLOSED_WHILE_SAVED)


async def test_a_reopened_listing_leaves_the_queue(db_session: AsyncSession) -> None:
    """§7.2: membership is read from the job's *current* status, not from the
    ``listing_closed`` event. Reading the event would pin a reopened role here
    forever."""
    user = await _a_user(db_session)
    job = await _a_job(db_session, status=JobStatus.CLOSED)
    application = await _an_application(
        db_session, user=user, job=job, stage=ApplicationStage.APPLIED
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.LISTING_CLOSED,
        actor=EventActor.SYSTEM,
        occurred_at=NOW - timedelta(days=2),
    )
    # Reopening clears the closure timestamp with the status, because
    # `ck_jobs_closed_at_matches_status` is a biconditional and would refuse
    # the row otherwise.
    job.status = JobStatus.OPEN
    job.closed_at = None
    await db_session.flush()

    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.CLOSED_WHILE_SAVED)


async def test_a_withdrawn_application_ignores_its_closed_listing(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.WITHDRAWN,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert application.id not in _ids(queue, QueueSectionKey.CLOSED_WHILE_SAVED)


# --- Best new internships --------------------------------------------------
#
# M3d Task 7. The first section whose rows are *jobs* rather than applications,
# and the first that depends on a stored score. Two failure modes are specific
# to it and both are silent: a posting the classifier could not read vanishing
# without trace, and a posting the sweep has not reached vanishing the same way.
# Neither looks like anything from outside — the row is simply shorter.


async def _an_internship(
    session: AsyncSession,
    *,
    user: User,
    title: str = "Software Engineer Internship",
    overall: int = 60,
    out_of: int = 100,
    state: EligibilityState = EligibilityState.ELIGIBLE,
    first_seen_at: datetime = NOW,
    status: JobStatus = JobStatus.OPEN,
    season: InternshipSeason | None = None,
    year: int | None = None,
) -> Job:
    """An open internship this user has a current-version score for."""
    job = await _a_job(
        session,
        title=title,
        status=status,
        seniority=Seniority.INTERNSHIP,
        first_seen_at=first_seen_at,
        internship_season=season,
        internship_year=year,
    )
    await store_score(session, user=user, job=job, overall=overall, out_of=out_of, state=state)
    return job


def _job_ids(queue: DailyQueue, key: QueueSectionKey) -> list[uuid.UUID]:
    """In order. The internship row is a ranking, so position is the assertion."""
    return [row.job_id for row in _section(queue, key).rows]


async def test_a_scored_internship_is_offered(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    job = await _an_internship(db_session, user=user)
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert job.id in _job_ids(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS)


async def test_a_non_internship_is_not_offered_however_well_it_scores(
    db_session: AsyncSession,
) -> None:
    """The row filters on ``seniority``, which is the only column that carries
    internship-ness — there is no ``jobs.is_internship``."""
    user = await _a_user(db_session)
    job = await _a_job(db_session, title="Senior Engineer", seniority=Seniority.SENIOR)
    await store_score(
        db_session, user=user, job=job, overall=95, out_of=100, state=EligibilityState.ELIGIBLE
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert job.id not in _job_ids(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS)


@pytest.mark.parametrize(
    ("days_old", "expected"),
    [
        (NEW_INTERNSHIP_DAYS - 1, True),
        (NEW_INTERNSHIP_DAYS, True),
        (NEW_INTERNSHIP_DAYS + 1, False),
    ],
)
async def test_the_new_internship_boundary(
    db_session: AsyncSession, days_old: int, expected: bool
) -> None:
    """ "New" is a claim with a date behind it. Exactly fourteen days old still
    counts; fifteen does not."""
    user = await _a_user(db_session)
    job = await _an_internship(db_session, user=user, first_seen_at=NOW - timedelta(days=days_old))
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert (job.id in _job_ids(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS)) is expected


async def test_a_closed_internship_is_not_offered(db_session: AsyncSession) -> None:
    """I3 is what makes ``status`` trustworthy enough to filter on, and a queue
    row pointing at a role nobody can apply to is the row wasting itself."""
    user = await _a_user(db_session)
    job = await _an_internship(db_session, user=user, status=JobStatus.CLOSED)
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert job.id not in _job_ids(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS)


async def test_an_internship_you_already_track_is_not_offered_again(
    db_session: AsyncSession,
) -> None:
    """Including an archived one: archiving is how a person says *not this*, and
    a suggestion row that re-offers it is the page arguing with them."""
    user = await _a_user(db_session)
    tracked = await _an_internship(db_session, user=user, title="Tracked Internship")
    archived = await _an_internship(db_session, user=user, title="Archived Internship")
    await _an_application(db_session, user=user, job=tracked)
    await _an_application(db_session, user=user, job=archived, archived_at=NOW)
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    offered = _job_ids(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS)
    assert tracked.id not in offered
    assert archived.id not in offered


async def test_internships_are_ordered_by_band_before_score(db_session: AsyncSession) -> None:
    """The same compromise the ranked list makes (`matching.md` §5.3): the band
    is the outer sort, the score orders inside it. A better-scoring posting that
    states something the reader does not meet does not lead this row."""
    user = await _a_user(db_session)
    high_but_ineligible = await _an_internship(
        db_session,
        user=user,
        title="Ineligible Internship",
        overall=95,
        state=EligibilityState.INELIGIBLE,
    )
    low_but_eligible = await _an_internship(
        db_session,
        user=user,
        title="Eligible Internship",
        overall=30,
        state=EligibilityState.ELIGIBLE,
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    offered = _job_ids(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS)
    assert offered.index(low_but_eligible.id) < offered.index(high_but_ineligible.id)


async def test_inside_a_band_the_order_is_the_fraction_not_the_total(
    db_session: AsyncSession,
) -> None:
    """§5.1.1, and the reason this row does not write its own ORDER BY: 40 of 50
    beats 45 of 100, and sorting on the totals puts them the other way round."""
    user = await _a_user(db_session)
    bigger_total = await _an_internship(
        db_session, user=user, title="Forty-five of a hundred", overall=45, out_of=100
    )
    better_share = await _an_internship(
        db_session, user=user, title="Forty of fifty", overall=40, out_of=50
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    offered = _job_ids(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS)
    assert offered.index(better_share.id) < offered.index(bigger_total.id)


def _blind_spot(queue: DailyQueue, key: QueueSectionKey, name: str) -> int:
    """How many a section reported it could not see, by name.

    Looked up by name rather than by position, and every spot is reported even
    at zero — "nothing was hidden from this row" is a statement worth being able
    to make, and a spot that appears only when non-zero cannot make it.
    """
    return next(spot.count for spot in _section(queue, key).blind_spots if spot.name == name)


async def test_an_unscored_internship_is_counted_rather_than_dropped(
    db_session: AsyncSession,
) -> None:
    """The M2d closure-state failure wearing new clothes: a row that silently
    shows fewer items because the worker is behind."""
    user = await _a_user(db_session)
    await _a_job(db_session, title="Unscored Internship", seniority=Seniority.INTERNSHIP)
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert _section(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS).rows == ()
    assert _blind_spot(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS, "not_yet_scored") == 1


async def test_a_posting_whose_level_could_not_be_read_is_counted_not_hidden(
    db_session: AsyncSession,
) -> None:
    """A posting at ``unclear`` might be an internship, and one the classifier
    never saw carries ``NULL``. The row cannot include either and must not
    pretend they do not exist — the plan's own words."""
    user = await _a_user(db_session)
    for seniority in (Seniority.UNCLEAR, None):
        job = await _a_job(db_session, title="Ambiguous", seniority=seniority)
        await store_score(
            db_session, user=user, job=job, overall=70, out_of=100, state=EligibilityState.ELIGIBLE
        )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert _blind_spot(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS, "level_not_read") == 2


async def test_a_blind_spot_counts_only_inside_the_rows_own_window(
    db_session: AsyncSession,
) -> None:
    """A count taken over a wider window than the row's own is a denominator
    that does not belong to it, and it reads as a bigger gap than there is."""
    user = await _a_user(db_session)
    await _a_job(
        db_session,
        title="Old and unreadable",
        seniority=Seniority.UNCLEAR,
        first_seen_at=NOW - timedelta(days=NEW_INTERNSHIP_DAYS + 1),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    section = _section(queue, QueueSectionKey.BEST_NEW_INTERNSHIPS)
    assert [spot.count for spot in section.blind_spots] == [0, 0]


async def test_an_internship_row_names_a_state_and_never_its_score(
    db_session: AsyncSession,
) -> None:
    """I4: a bare number in the UI is a bug, and this row has no room for a
    breakdown. The eligibility state is a verdict with a quoted sentence behind
    it on the job page, so that is what travels — never the score it was ranked
    on, and never a share of one."""
    user = await _a_user(db_session)
    await _an_internship(
        db_session,
        user=user,
        overall=63,
        state=EligibilityState.UNCERTAIN,
        season=InternshipSeason.SUMMER,
    )
    row = _section(
        await build_queue(db_session, user_id=user.id, now=NOW),
        QueueSectionKey.BEST_NEW_INTERNSHIPS,
    ).rows[0]
    assert row.eligibility is EligibilityState.UNCERTAIN
    assert "63" not in row.because
    assert "%" not in row.because


async def test_an_internship_row_states_its_season_when_the_posting_did(
    db_session: AsyncSession,
) -> None:
    """Two of nineteen internships in the recorded corpus state a year and no
    season, so absence is normal and must not read as a claim."""
    user = await _a_user(db_session)
    await _an_internship(db_session, user=user, season=InternshipSeason.SUMMER, year=2027)
    section = _section(
        await build_queue(db_session, user_id=user.id, now=NOW),
        QueueSectionKey.BEST_NEW_INTERNSHIPS,
    )
    assert "summer 2027" in section.rows[0].because


async def test_an_internship_row_has_no_application_behind_it(
    db_session: AsyncSession,
) -> None:
    """The row links to the posting, not to an application, because there is no
    application — offering one is the whole point of the row."""
    user = await _a_user(db_session)
    await _an_internship(db_session, user=user)
    section = _section(
        await build_queue(db_session, user_id=user.id, now=NOW),
        QueueSectionKey.BEST_NEW_INTERNSHIPS,
    )
    assert section.rows[0].application_id is None
    assert section.rows[0].current_stage is None


# --- Rules that hold across every section ----------------------------------


async def test_an_archived_application_is_in_no_section(db_session: AsyncSession) -> None:
    """§7.2, and the bug M2b already shipped once from the other direction."""
    user = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.APPLIED,
        next_action_at=NOW - timedelta(days=5),
        saved_at=NOW - timedelta(days=90),
        archived_at=NOW - timedelta(days=1),
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.INTERVIEW_SCHEDULED,
        actor=EventActor.USER,
        occurred_at=NOW + timedelta(days=2),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    for key in QueueSectionKey:
        assert application.id not in _ids(queue, key), key


async def test_another_users_application_is_in_no_section(db_session: AsyncSession) -> None:
    """A3. Every query filters on user_id, including the ones reaching events
    through a join."""
    mine = await _a_user(db_session)
    theirs = await _a_user(db_session)
    application = await _an_application(
        db_session,
        user=theirs,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.APPLIED,
        next_action_at=NOW - timedelta(days=5),
        saved_at=NOW - timedelta(days=90),
    )
    await _an_event(
        db_session,
        application=application,
        event_type=ApplicationEventType.INTERVIEW_SCHEDULED,
        actor=EventActor.USER,
        occurred_at=NOW + timedelta(days=2),
    )
    queue = await build_queue(db_session, user_id=mine.id, now=NOW)
    assert queue.total_rows == 0


async def test_every_row_says_why_it_is_there(db_session: AsyncSession) -> None:
    """I4's spirit: no bare signal. A row with an empty reason is a bug."""
    user = await _a_user(db_session)
    await _an_application(
        db_session,
        user=user,
        job=await _a_job(db_session, status=JobStatus.CLOSED),
        stage=ApplicationStage.APPLIED,
        saved_at=NOW - timedelta(days=90),
    )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert queue.total_rows > 0
    for section in queue.sections:
        for row in section.rows:
            assert row.because.strip()
            assert row.job_title.strip()
            assert row.company_name.strip()


async def test_a_section_is_capped_and_says_how_many_it_capped(
    db_session: AsyncSession,
) -> None:
    """Unbounded render work is CLAUDE.md §8's anti-pattern, and it applies to
    a list as much as to a map. ``total`` is the honest count behind the cap."""
    user = await _a_user(db_session)
    for index in range(ROW_CAP + 3):
        await _an_application(
            db_session,
            user=user,
            job=await _a_job(db_session, title=f"Engineer {index}"),
            stage=ApplicationStage.SAVED,
            saved_at=NOW - timedelta(days=STALE_SAVED_DAYS + 1),
        )
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    section = _section(queue, QueueSectionKey.STALE_SAVED)
    assert len(section.rows) == ROW_CAP
    assert section.total == ROW_CAP + 3


async def test_an_empty_queue_is_four_empty_sections_not_an_error(
    db_session: AsyncSession,
) -> None:
    """A user with nothing to do gets a well-formed answer. The page needs the
    section list to render "nothing today" honestly."""
    user = await _a_user(db_session)
    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    assert len(queue.sections) == len(QueueSectionKey)
    assert queue.total_rows == 0
