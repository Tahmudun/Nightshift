"""The daily queue: the questions this system can answer honestly today.

Read ``docs/architecture/command-center.md`` §7 before changing anything here.
§7.1 records why assessments do not have their own row, §7.2 records the three
rules that decide whether the page tells the truth, and §7.3 records that this
module has no write path and is not to grow one.

Everything here is a read. ``build_queue`` is called once per page load and runs
independent queries rather than one clever join — they answer different
questions, they are separately indexable, and a join producing all of them would
be the kind of query nobody can change safely later.

``now`` is a parameter, never ``utcnow()`` read inside. Every threshold in this
file is a boundary somebody will get wrong eventually, and a function that
reads its own clock cannot be tested at one.

**M3d Task 7 added the first sections backed by a match score**, and with them
two shapes the original four did not need:

* A row is not always about an application. ``best_new_internships`` offers
  postings the reader is *not* tracking, so ``application_id`` is nullable and
  the page links to the job instead.
* A section can have a blind spot. A row computed from scores shows fewer items
  when the sweep is behind, and it shows fewer items when the classifier could
  not read a posting — both look identical to having less to do. Each such
  section counts what it could not see and says so (``BlindSpot``).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.db.base import (
    ApplicationEventType,
    ApplicationStage,
    EligibilityState,
    EventActor,
    JobStatus,
    RequirementNecessity,
    Seniority,
)
from nightshift.db.models import Application, ApplicationEvent, Company, Job, MatchResult
from nightshift.domain.matching import band_rank, coverage_weighted_rank, unmet_requirements
from nightshift.domain.matching_weights import load_weights

#: Decided by the human on 2026-08-04 (`command-center.md` §7). A week is when
#: silence after applying starts to mean something; three weeks of a saved job
#: untouched is genuinely stale; two weeks is far enough ahead to prepare for
#: an interview and near enough that it is still this month's problem.
FOLLOW_UP_SILENT_DAYS = 7
STALE_SAVED_DAYS = 21
INTERVIEW_HORIZON_DAYS = 14

#: How recently a posting must have been first seen to count as *new* in the
#: internship row (M3d Task 7). A fortnight is the same horizon the interview
#: section uses, and for the same reason: far enough out to be worth acting on,
#: near enough to still be this month's problem. "New" is a claim with a date
#: behind it, and the date is ``jobs.first_seen_at`` — when *this system* first
#: saw the posting, which is not when the employer published it. Nothing in the
#: corpus carries a publication date, so this is the honest available fact and
#: the row says "first listed" rather than "posted".
NEW_INTERNSHIP_DAYS = 14

#: Rows per section. The count before the cap travels with it, so the page can
#: say "and 6 more" rather than quietly truncating.
ROW_CAP = 20

#: Applied and now waiting on somebody else. Silence in these stages is the
#: thing worth surfacing. ``assessment`` is here because §7.1 folds assessments
#: into follow-up rather than giving them a row of their own.
AWAITING_STAGES: tuple[ApplicationStage, ...] = (
    ApplicationStage.APPLIED,
    ApplicationStage.ASSESSMENT,
    ApplicationStage.INTERVIEW,
)

#: Over, one way or another. Nothing in these stages belongs in a queue of
#: things to do today — including ``offer``, which is a decision rather than a
#: chase, and which the pipeline already shows prominently.
TERMINAL_STAGES: tuple[ApplicationStage, ...] = (
    ApplicationStage.REJECTED,
    ApplicationStage.WITHDRAWN,
    ApplicationStage.CLOSED,
)


class QueueSectionKey(enum.StrEnum):
    """The sections, in the order the page renders them. Deliberately not a
    database enum — this is a shape of the API, not a stored value, and nothing
    persists it.

    Declaration order is render order, and it is a product decision rather than
    a historical accident: the four M2d sections are things already waiting on
    the reader, and the M3d rows are suggestions, so the suggestions come last.
    """

    FOLLOW_UP = "follow_up"
    INTERVIEWS_APPROACHING = "interviews_approaching"
    STALE_SAVED = "stale_saved"
    CLOSED_WHILE_SAVED = "closed_while_saved"
    REQUIREMENT_GAPS = "requirement_gaps"
    BEST_NEW_INTERNSHIPS = "best_new_internships"


@dataclass(frozen=True, slots=True)
class QueueRow:
    """One thing to look at, and the sentence saying why.

    ``at`` is the date the row is *about* — the follow-up date, the interview
    time, the day it went quiet, the day a posting was first seen. It is read
    from a column, never invented, and it is None when the section has no
    meaningful date (I1's habit applied to time rather than to place).

    ``application_id`` and ``current_stage`` are None together, on exactly the
    sections that offer a posting the reader is not tracking. The page links to
    the job in that case; there is no application to link to and inventing one
    would be I5's irreversible action taken by a list.

    ``eligibility`` is the only score-derived thing a row carries, and it is a
    *state* rather than a number. I4 forbids a bare score, and a queue row has
    no room for the breakdown that would make one legitimate — the job page has
    it, quoted sentence and all, one click away.
    """

    application_id: UUID | None
    job_id: UUID
    job_title: str
    company_name: str
    current_stage: ApplicationStage | None
    at: datetime | None
    because: str
    eligibility: EligibilityState | None = None


@dataclass(frozen=True, slots=True)
class BlindSpot:
    """What a section could not see, counted and named.

    Every section that has one reports it at every load, **including when the
    count is zero** — "nothing was hidden from this row" is a statement worth
    being able to make, and a spot that appears only when non-zero cannot make
    it. `command-center.md` §7 and the coverage page make the same move.

    ``name`` is a stable slug the page keys off; ``because`` is the sentence a
    person reads. A count with no sentence is the failure this exists to stop.
    """

    name: str
    count: int
    because: str


@dataclass(frozen=True, slots=True)
class QueueSection:
    key: QueueSectionKey
    rows: tuple[QueueRow, ...]
    #: Before the cap. ``len(rows) < total`` is how the page knows to say so.
    total: int
    #: What this section could not see. Empty for the four M2d sections, which
    #: read committed application state and can see all of it.
    blind_spots: tuple[BlindSpot, ...] = ()
    #: One sentence about the section as a whole, where the rows cannot carry
    #: it. None where the title says everything.
    note: str | None = field(default=None)


@dataclass(frozen=True, slots=True)
class DailyQueue:
    sections: tuple[QueueSection, ...]
    total_rows: int


def _last_user_activity() -> Any:
    """The most recent event *the user caused*, per application.

    §7.2, and the load-bearing filter on this page. ``application_events`` holds
    system events too — ``record_listing_closed`` writes one — and a system
    event is not somebody touching their application. If it counted here, a
    listing going closed would make its application look freshly handled and
    drop it out of the very queue that exists to surface it. Mutation-checked
    by ``test_a_system_event_does_not_count_as_activity``.
    """
    return (
        select(
            ApplicationEvent.application_id.label("application_id"),
            func.max(ApplicationEvent.occurred_at).label("last_at"),
        )
        .where(ApplicationEvent.actor == EventActor.USER)
        .group_by(ApplicationEvent.application_id)
        .subquery()
    )


def _live(user_id: UUID) -> list[Any]:
    """Filters every section shares: this user's, not archived, not over.

    Archived exclusion is §7.2's second rule, and M2b shipped the same bug from
    the other direction — an archived application rendered as unsaved and
    saving it changed nothing.
    """
    return [
        Application.user_id == user_id,
        Application.archived_at.is_(None),
        Application.current_stage.not_in(TERMINAL_STAGES),
    ]


def _row_columns() -> list[Any]:
    """The columns every section selects, in one place so they cannot drift."""
    return [
        Application.id,
        Application.job_id,
        Job.title,
        Company.canonical_name,
        Application.current_stage,
    ]


def _joined(stmt: Select[Any]) -> Select[Any]:
    return stmt.join(Job, Job.id == Application.job_id).join(Company, Company.id == Job.company_id)


def _follow_up_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Due by date, or silent past the threshold.

    Two branches, one row per application — an application matching both is
    still one thing to do. ``coalesce`` falls back to the application's own
    creation time so an application with no user event is surfaced rather than
    silently skipped; ``save_job`` always writes one today, and being wrong in
    the direction of showing too much is the right way to be wrong here.
    """
    activity = _last_user_activity()
    silent_since = now - timedelta(days=FOLLOW_UP_SILENT_DAYS)
    last_at = func.coalesce(activity.c.last_at, Application.created_at)
    return (
        _joined(select(*_row_columns(), Application.next_action_at, last_at.label("last_at")))
        .outerjoin(activity, activity.c.application_id == Application.id)
        .where(
            *_live(user_id),
            or_(
                and_(
                    Application.next_action_at.is_not(None),
                    Application.next_action_at <= now,
                ),
                and_(
                    Application.current_stage.in_(AWAITING_STAGES),
                    last_at <= silent_since,
                ),
            ),
        )
        # Most overdue first: a date we were given beats one we inferred.
        .order_by(func.coalesce(Application.next_action_at, last_at), Application.id)
    )


def _interviews_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Scheduled times inside the horizon. One row per interview, not per
    application — two interviews are two appointments to prepare for."""
    horizon = now + timedelta(days=INTERVIEW_HORIZON_DAYS)
    return (
        _joined(select(*_row_columns(), ApplicationEvent.occurred_at))
        .join(ApplicationEvent, ApplicationEvent.application_id == Application.id)
        .where(
            *_live(user_id),
            ApplicationEvent.event_type == ApplicationEventType.INTERVIEW_SCHEDULED,
            ApplicationEvent.occurred_at > now,
            ApplicationEvent.occurred_at <= horizon,
        )
        .order_by(ApplicationEvent.occurred_at, Application.id)
    )


def _stale_saved_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Still at ``saved``, untouched past the threshold."""
    activity = _last_user_activity()
    stale_since = now - timedelta(days=STALE_SAVED_DAYS)
    last_at = func.coalesce(activity.c.last_at, Application.created_at)
    return (
        _joined(select(*_row_columns(), last_at.label("last_at")))
        .outerjoin(activity, activity.c.application_id == Application.id)
        .where(
            *_live(user_id),
            Application.current_stage == ApplicationStage.SAVED,
            last_at <= stale_since,
        )
        # Stalest first.
        .order_by(last_at, Application.id)
    )


def _closed_while_saved_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """The listing is closed *right now*.

    §7.2's third rule: membership comes from ``jobs.status``, not from the
    ``listing_closed`` event, so a role that closed and reopened leaves this
    section instead of sitting in it permanently. ``now`` is unused and that is
    deliberate — the signature matches its three siblings so ``queue_selects``
    can hold them in one dict.
    """
    del now
    return (
        _joined(select(*_row_columns(), Job.last_seen_at))
        .where(*_live(user_id), Job.status == JobStatus.CLOSED)
        .order_by(Job.last_seen_at.desc(), Application.id)
    )


def _already_touched(user_id: UUID) -> Any:
    """Every job this person has an application for, archived or not.

    Archived is included deliberately. Archiving is how somebody says *not this
    one*, and a suggestion row that re-offers an archived posting is the page
    arguing with them. It is the one place in this module where an archived
    application still counts for something, and it counts in the direction of
    showing less rather than more.
    """
    return select(Application.job_id).where(Application.user_id == user_id).scalar_subquery()


def _current_score(user_id: UUID) -> Any:
    """The join condition for this person's score at the version now in force.

    A row at an older ``ruleset_version`` is not a stale score to be shown with a
    caveat — `MatchResult`'s own docstring says it is never served. So it does
    not join, and the posting lands in the ``not_yet_scored`` blind spot with the
    ones that were never scored at all. Both are the same thing to a reader: the
    page cannot rank this yet.
    """
    return and_(
        MatchResult.job_id == Job.id,
        MatchResult.user_id == user_id,
        MatchResult.ruleset_version == load_weights().ruleset_version,
    )


def _new_postings(now: datetime) -> list[Any]:
    """Open, and first seen inside the window. Shared by the row and its blind
    spots, so a count can never be taken over a wider corpus than the rows were.
    """
    return [
        Job.status == JobStatus.OPEN,
        Job.first_seen_at >= now - timedelta(days=NEW_INTERNSHIP_DAYS),
    ]


def _internships_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Recent internships this person has a current score for and is not tracking.

    **The ordering is imported, not written here** — `matching.band_rank` and
    `matching.coverage_weighted_rank`, the same two clauses `/matches` sorts on.
    Two surfaces ranking the same rows by two clauses is a difference nobody can
    see from either page, and M3d Task 6 chose this one by measurement.

    There is no ``jobs.is_internship``. Internship-ness is carried by
    ``seniority``, with ``internship_season`` and ``internship_year`` gated on
    it, so this filters on the level and the two season columns are read only for
    the sentence. A posting at ``unclear`` or ``NULL`` is not silently excluded:
    it is absent from the rows and counted in ``level_not_read``.
    """
    return (
        select(
            Job.id.label("job_id"),
            Job.title,
            Company.canonical_name,
            Job.first_seen_at,
            Job.internship_season,
            Job.internship_year,
            MatchResult.eligibility_status,
        )
        .join(Company, Company.id == Job.company_id)
        .join(MatchResult, _current_score(user_id))
        .where(
            *_new_postings(now),
            Job.seniority == Seniority.INTERNSHIP,
            Job.id.not_in(_already_touched(user_id)),
        )
        .order_by(
            band_rank(),
            coverage_weighted_rank().desc().nulls_last(),
            MatchResult.overall_score.desc(),
            Job.first_seen_at,
            Job.id,
        )
    )


def _gaps_select(*, user_id: UUID, now: datetime) -> Select[Any]:
    """Live applications with a current score, and everything a gap needs.

    Entities rather than columns, because the difference is taken in Python by
    `matching.unmet_requirements` against the *stored* evidence graph. Doing it
    in SQL would be a second derivation of a list the job page already computes
    one way, and the two would agree almost always — which is the failure that
    is impossible to notice.

    Bounded by one person's live applications, so loading them all and counting
    in Python is honest arithmetic rather than a scale problem. `command-center`
    §7's cap still applies to what is *rendered*.

    ``now`` is unused; the signature matches its siblings so ``queue_selects``
    can hold them in one dict.
    """
    del now
    return (
        select(Application, Job, Company.canonical_name, MatchResult)
        .join(Job, Job.id == Application.job_id)
        .join(Company, Company.id == Job.company_id)
        .join(MatchResult, _current_score(user_id))
        .where(*_live(user_id))
        .options(selectinload(MatchResult.evidence), selectinload(Job.requirements))
        .order_by(Application.id)
    )


def queue_selects(*, user_id: UUID, now: datetime) -> dict[QueueSectionKey, Select[Any]]:
    """Exactly what ``build_queue`` runs, exposed for the query-plan test.

    Task 2 asserts each of these is servable by an index. It matters that it
    reads the real statements rather than a copy that can drift out of step.
    """
    return {
        QueueSectionKey.FOLLOW_UP: _follow_up_select(user_id=user_id, now=now),
        QueueSectionKey.INTERVIEWS_APPROACHING: _interviews_select(user_id=user_id, now=now),
        QueueSectionKey.STALE_SAVED: _stale_saved_select(user_id=user_id, now=now),
        QueueSectionKey.CLOSED_WHILE_SAVED: _closed_while_saved_select(user_id=user_id, now=now),
        QueueSectionKey.REQUIREMENT_GAPS: _gaps_select(user_id=user_id, now=now),
        QueueSectionKey.BEST_NEW_INTERNSHIPS: _internships_select(user_id=user_id, now=now),
    }


def _days(a: datetime, b: datetime) -> int:
    return max((a - b).days, 0)


def _when(days: int) -> str:
    """A day count in words. ``0 days ago`` is not a thing anybody says, and a
    row that says it reads as a rendering bug rather than as today."""
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def _term(row: Any) -> str:
    """*summer 2027*, *summer*, *2027*, or nothing.

    Eleven of the recorded corpus's nineteen internships state no season and
    nine state no year, so absence is the common case and must not read as a
    claim: the sentence simply says less. Never assembled from a default —
    inventing a season is I1's failure applied to a calendar.
    """
    parts = [row.internship_season.value if row.internship_season else None, row.internship_year]
    stated = " ".join(str(part) for part in parts if part is not None)
    return f" for {stated}" if stated else ""


def _because(key: QueueSectionKey, *, row: Any, now: datetime) -> str:
    """One plain sentence per row, derived from the same data the query filtered
    on. Never a score and never a share of one — I4 forbids showing a number
    without the breakdown behind it, and a row here has nowhere to put one."""
    if key is QueueSectionKey.FOLLOW_UP:
        if row.next_action_at is not None and row.next_action_at <= now:
            return f"you set a next action for {row.next_action_at:%-d %b}"
        return f"no activity from you in {_days(now, row.last_at)} days"
    if key is QueueSectionKey.INTERVIEWS_APPROACHING:
        return f"interview scheduled for {row.occurred_at:%-d %b}"
    if key is QueueSectionKey.STALE_SAVED:
        return f"saved {_days(now, row.last_at)} days ago and untouched since"
    if key is QueueSectionKey.BEST_NEW_INTERNSHIPS:
        return f"internship{_term(row)}, first listed {_when(_days(now, row.first_seen_at))}"
    return "the source stopped listing this role"


def _at(key: QueueSectionKey, row: Any) -> datetime | None:
    if key is QueueSectionKey.FOLLOW_UP:
        at: datetime | None = row.next_action_at or row.last_at
        return at
    if key is QueueSectionKey.INTERVIEWS_APPROACHING:
        occurred_at: datetime = row.occurred_at
        return occurred_at
    if key is QueueSectionKey.STALE_SAVED:
        last_at: datetime = row.last_at
        return last_at
    if key is QueueSectionKey.BEST_NEW_INTERNSHIPS:
        first_seen_at: datetime = row.first_seen_at
        return first_seen_at
    last_seen_at: datetime = row.last_seen_at
    return last_seen_at


def _to_application_row(key: QueueSectionKey, *, row: Any, now: datetime) -> QueueRow:
    """A row about something the reader is already tracking."""
    return QueueRow(
        application_id=row.id,
        job_id=row.job_id,
        job_title=row.title,
        company_name=row.canonical_name,
        current_stage=row.current_stage,
        at=_at(key, row),
        because=_because(key, row=row, now=now),
    )


def _to_offered_row(key: QueueSectionKey, *, row: Any, now: datetime) -> QueueRow:
    """A row about a posting the reader is *not* tracking.

    No ``application_id`` and no stage, because neither exists — offering the
    posting is the point. The eligibility state travels so the page can say what
    band the suggestion came out of; the score it was ranked on does not.
    """
    return QueueRow(
        application_id=None,
        job_id=row.job_id,
        job_title=row.title,
        company_name=row.canonical_name,
        current_stage=None,
        at=_at(key, row),
        because=_because(key, row=row, now=now),
        eligibility=row.eligibility_status,
    )


async def _count(session: AsyncSession, stmt: Select[Any]) -> int:
    """``order_by(None)`` strips the sort before counting — Postgres allows it
    inside the subquery, but sorting rows nobody reads is wasted work."""
    return int(
        (
            await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
        ).scalar_one()
    )


async def _build_section(
    session: AsyncSession,
    *,
    key: QueueSectionKey,
    stmt: Select[Any],
    now: datetime,
    to_row: Any = _to_application_row,
    blind_spots: tuple[BlindSpot, ...] = (),
    note: str | None = None,
) -> QueueSection:
    """Count first, then take the capped page.

    Two queries rather than a window function, because the count must be the
    honest total and ``len(rows)`` after a LIMIT is not it.
    """
    total = await _count(session, stmt)
    result = (await session.execute(stmt.limit(ROW_CAP))).all()
    rows = tuple(to_row(key, row=row, now=now) for row in result)
    return QueueSection(key=key, rows=rows, total=total, blind_spots=blind_spots, note=note)


#: What the internship row cannot see, and what a person should read when the
#: count is not zero. Both are counted over `_new_postings` — the row's own
#: window — because a count taken over a wider corpus is a denominator that does
#: not belong to the row and reads as a bigger gap than there is.
_INTERNSHIP_BLIND_SPOTS: tuple[tuple[str, str], ...] = (
    (
        "not_yet_scored",
        "recent internships with no score yet, so nothing here can rank them. They are not "
        "worse matches — they are unread ones, and they arrive as the sweep reaches them.",
    ),
    (
        "level_not_read",
        "recent postings whose level could not be read from the title. Some of them are "
        "probably internships. This row cannot tell, so it does not guess either way.",
    ),
)

_INTERNSHIP_NOTE = (
    "Internships first listed in the last {days} days that you are not already tracking, in "
    "the order the ranked list would put them: what each posting states you meet first, best "
    "match inside that. No score is shown here — open one for the breakdown behind it."
)


async def _internship_blind_spots(
    session: AsyncSession, *, user_id: UUID, now: datetime
) -> tuple[BlindSpot, ...]:
    """The two counts, taken against the same window the rows were.

    Both exclude postings the reader already tracks, for the same reason the row
    does: a posting they have already decided about is not something this row
    failed to show them.
    """
    untouched = (*_new_postings(now), Job.id.not_in(_already_touched(user_id)))
    unscored = (
        select(func.count())
        .select_from(Job)
        .outerjoin(MatchResult, _current_score(user_id))
        .where(*untouched, Job.seniority == Seniority.INTERNSHIP, MatchResult.id.is_(None))
    )
    unread = (
        select(func.count())
        .select_from(Job)
        .where(*untouched, or_(Job.seniority.is_(None), Job.seniority == Seniority.UNCLEAR))
    )
    counts = [(await session.execute(stmt)).scalar_one() for stmt in (unscored, unread)]
    return tuple(
        BlindSpot(name=name, count=int(count), because=because)
        for (name, because), count in zip(_INTERNSHIP_BLIND_SPOTS, counts, strict=True)
    )


#: PRODUCT-SPEC §10.4 calls this row *"resume mismatch warnings"* and it is not
#: called that here, on purpose. The list is differenced against `user_skills` —
#: what this person confirmed — and never against `resume_extractions`, which
#: are proposals a file appears to make. Shipping it under the old name would be
#: ADR 0019's defect arriving by the front door: a true statement about a
#: database rendered as a false one about a document.
#:
#: The word *resume* is therefore absent from this sentence and a test asserts
#: it stays absent.
_GAPS_NOTE = (
    "What these postings state they require that nothing in your confirmed skills answers. "
    "Read from your profile, never from a file you uploaded — an extracted line is a "
    "proposal until you confirm it. Only hard requirements are here: a nice-to-have you "
    "lack is not a warning, and treating it as one reports shortfalls against somebody "
    "who is qualified."
)

_GAPS_BLIND_SPOT = (
    "roles you are tracking that have no score yet, so there is no evidence graph to "
    "difference against. That is not the same as having nothing missing."
)


def _gap_sentence(values: list[str]) -> str:
    """The asks, named. A count with no names is the unexplained number I4 is
    about, one level up from a score."""
    shown = ", ".join(values[:3])
    rest = len(values) - 3
    tail = f", and {rest} more" if rest > 0 else ""
    answers = "it" if len(values) == 1 else "them"
    return f"asks for {shown}{tail} — nothing you have confirmed answers {answers}"


async def _build_requirement_gaps(
    session: AsyncSession, *, user_id: UUID, stmt: Select[Any], now: datetime
) -> QueueSection:
    """Tracked roles with an unanswered hard requirement, worst shortfall first.

    ``at`` is None on every row and that is the honest value: a gap is not an
    event and has no date. I1's habit applied to time.
    """
    del now
    gapped: list[tuple[int, QueueRow]] = []
    for application, job, company_name, result in (await session.execute(stmt)).all():
        values = [
            requirement.value
            for requirement in unmet_requirements(result, job.requirements)
            if requirement.necessity is RequirementNecessity.REQUIRED
        ]
        if not values:
            continue
        gapped.append(
            (
                len(values),
                QueueRow(
                    application_id=application.id,
                    job_id=job.id,
                    job_title=job.title,
                    company_name=company_name,
                    current_stage=application.current_stage,
                    at=None,
                    because=_gap_sentence(values),
                    eligibility=result.eligibility_status,
                ),
            )
        )
    # Worst shortfall first, then by id so a reload cannot reorder two equal rows.
    gapped.sort(key=lambda pair: (-pair[0], str(pair[1].application_id)))

    unscored = (
        select(func.count())
        .select_from(Application)
        .join(Job, Job.id == Application.job_id)
        .outerjoin(MatchResult, _current_score(user_id))
        .where(*_live(user_id), MatchResult.id.is_(None))
    )
    return QueueSection(
        key=QueueSectionKey.REQUIREMENT_GAPS,
        rows=tuple(row for _, row in gapped[:ROW_CAP]),
        total=len(gapped),
        blind_spots=(
            BlindSpot(
                name="not_yet_scored",
                count=int((await session.execute(unscored)).scalar_one()),
                because=_GAPS_BLIND_SPOT,
            ),
        ),
        note=_GAPS_NOTE,
    )


async def build_queue(session: AsyncSession, *, user_id: UUID, now: datetime) -> DailyQueue:
    """Every section, in the order the page renders them.

    Sections are independent, so a role can legitimately appear in two of them
    — a closed listing you also owe a follow-up on is two different facts about
    the same job, and collapsing them would hide one.

    The order comes from ``QueueSectionKey`` rather than from the order things
    are built in, so adding a section cannot silently reorder the page.
    """
    selects = queue_selects(user_id=user_id, now=now)
    built: dict[QueueSectionKey, QueueSection] = {}
    for key, stmt in selects.items():
        if key is QueueSectionKey.REQUIREMENT_GAPS:
            built[key] = await _build_requirement_gaps(session, user_id=user_id, stmt=stmt, now=now)
        elif key is QueueSectionKey.BEST_NEW_INTERNSHIPS:
            built[key] = await _build_section(
                session,
                key=key,
                stmt=stmt,
                now=now,
                to_row=_to_offered_row,
                blind_spots=await _internship_blind_spots(session, user_id=user_id, now=now),
                note=_INTERNSHIP_NOTE.format(days=NEW_INTERNSHIP_DAYS),
            )
        else:
            built[key] = await _build_section(session, key=key, stmt=stmt, now=now)
    sections = tuple(built[key] for key in QueueSectionKey)
    return DailyQueue(sections=sections, total_rows=sum(section.total for section in sections))
