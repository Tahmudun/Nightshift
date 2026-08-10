"""Where the score meets the database: assembly, persistence, and what makes one due.

`matching.md` §4.2, §4.3, §5.1.2, and M3c Task 8. `scoring.py` is pure and
imports no ORM on purpose — it is the thing that has to be mutation-tested and
graded against 60 postings with no Postgres running. This module is the other
half: it reads the rows, hands `scoring.py` plain dataclasses, and writes what
comes back.

## Three things become due, and only one of them is an event this code raises

§4.2 names three triggers: a new or changed job, a profile change, and a ruleset
version bump. They are **not** three mechanisms here, and collapsing two of them
into one was a deliberate call:

* **A new or changed job** already deletes the affected scores. Four triggers
  written at Task 2 watch `jobs.description_text`, `job_requirements`,
  `user_skills` and `user_projects`, and they are not optional — without them
  ingestion cannot commit at all. A job with no current-version row is therefore
  what "due" means, and a brand-new job reaches that state by never having had
  one.
* **A ruleset version bump** reaches the same state by a different route:
  `ruleset_version` is part of the uniqueness key, so after a bump no row
  matches the current version and every pair is due again. Old rows are kept
  rather than deleted — §4.2 wants a version computed *alongside* what it is
  being compared against.
* **A profile change** is the one this module has to raise itself, because no
  database trigger can see it: `users.preferred_roles` moving changes six
  components' inputs and touches none of the four watched tables.

So `pending_pairs` is the sweep that serves the first two, and
`clear_scores_for_user` is what a profile change calls. Both end in the same
place — a pair with no current-version row — which means there is exactly one
code path that computes a score, not three that can drift.

**Why a sweep rather than an enqueue from the request handler.** The plan said
"the task is enqueued". Doing the invalidation inside the PATCH's own
transaction is strictly more durable than enqueueing beside it: the delete
commits with the change that caused it or neither happens, whereas an enqueue
after commit is lost if Redis is unreachable at that instant, and the score then
stays wrong with nothing recording that it should not be. It also needs no ARQ
pool in the API process, which is a dependency the web tier does not otherwise
have. What it costs is latency — a score reads as not-yet-computed until the
sweep runs, rather than for the second an enqueue would take. That is the right
side to err on: not-yet-computed is true, and a number computed against a
profile the person just replaced is not.

## The trap in "any profile change"

§4.2's wording is *any profile change*, and taken literally it is a retry storm
waiting for a demo. M2c's `PATCH /profile` is one endpoint writing fifteen
columns, and most of them no component reads. Rescoring the corpus because
somebody fixed the spelling of their display name is work with no output.

`SCORING_RELEVANT_PROFILE_COLUMNS` below is the named set, and it is checked
against `User.__table__` by `test_nothing_infers.py` the same way
`PROFILE_COLUMNS` is — because that hand-maintained list is precisely the thing
that quietly stopped describing what it named at M3b, and a second list of the
same kind will do it again if nothing watches.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, delete, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.db.base import EligibilityState, JobStatus, MatchComponent
from nightshift.db.models import (
    Job,
    JobLocation,
    JobRequirement,
    MatchComponentAssessment,
    MatchEvidence,
    MatchPenalty,
    MatchResult,
    User,
)
from nightshift.db.types import utcnow
from nightshift.domain.eligibility import evaluate, profile_from_user
from nightshift.domain.eligibility_reading import read_posting
from nightshift.domain.matching_weights import MatchingWeights, load_weights
from nightshift.domain.requirement_extraction import RequirementProposal
from nightshift.domain.role_classification import classify_role
from nightshift.domain.scoring import (
    ConfirmedProject,
    ConfirmedSkill,
    Evidence,
    JobLocationForScoring,
    MatchScore,
    PostingForScoring,
    ScoringProfile,
    score_match,
)

log = structlog.get_logger(__name__)

#: The columns on `users` a stored `match_results` row depends on. A change to
#: one of these makes every score for that person wrong; a change to anything
#: else makes none of them wrong.
#:
#: Two sources, and both belong here because both are *on the row*:
#:
#: * What `scoring.ScoringProfile` reads — `preferred_roles`,
#:   `preferred_locations`, `remote_preference`, `years_experience`.
#: * What `eligibility.SeekerProfile` reads, because `eligibility_status` is a
#:   column of `match_results` (§5.2 keeps it beside the number and out of it,
#:   which is a statement about the arithmetic, not about what is stored).
#:
#: Left out deliberately, and each one is a claim that can be checked: `school`
#: is read by neither; `home_location_text` is not read by the location
#: component, which compares the posting against `preferred_locations` and
#: `remote_preference`; `minimum_salary` belongs to the compensation component
#: §5.1 defers. `display_name` and `timezone` are not profile facts at all —
#: `test_nothing_infers.py` classifies those.
SCORING_RELEVANT_PROFILE_COLUMNS = (
    "graduation_year",
    "graduation_month",
    "degree",
    "work_authorization",
    "years_experience",
    "is_enrolled",
    "remote_preference",
    "preferred_roles",
    "preferred_locations",
)

#: Profile columns a score does not read. Together with the tuple above this
#: partitions `PROFILE_COLUMNS`, and the parity test asserts exactly that — so a
#: new profile column cannot land without somebody deciding which side it is on.
#: Getting it wrong in this direction is the expensive one: a column listed here
#: that a component starts reading produces a score that never updates and never
#: errors.
NOT_SCORING_RELEVANT_PROFILE_COLUMNS = (
    "school",
    "home_location_text",
    "minimum_salary",
)


#: Which column on `match_results` holds which component's points.
#:
#: One mapping rather than two, because both directions of the copy exist: this
#: module writes the columns and the job route reads them back to rebuild the
#: breakdown. A transposition in either is invisible — the total still adds up,
#: every constraint still holds, and only the decomposition is wrong, which is the
#: one thing I4 is a claim about. `test_nothing_infers.py` guards it beside the
#: other two hand-maintained lists: every component has an entry, every entry is a
#: real column, and no two components share one.
COMPONENT_SCORE_COLUMNS: Mapping[MatchComponent, str] = {
    MatchComponent.ROLE: "role_score",
    MatchComponent.SKILL: "skill_score",
    MatchComponent.PROJECT: "project_evidence_score",
    MatchComponent.LOCATION: "location_score",
    MatchComponent.FRESHNESS: "freshness_score",
    MatchComponent.PRIORITY: "priority_score",
}


@dataclass(frozen=True)
class RecomputeReport:
    """What a recompute run did, in numbers a log line and a test can both read."""

    scored: int
    #: Postings skipped because there was nothing to read. Counted rather than
    #: silently dropped: a sweep reporting `scored=0` and a sweep reporting
    #: `scored=0, skipped=3000` are different situations and one of them is a
    #: bug.
    skipped: int
    ruleset: str


def _identity(kind: str, value: str, char_start: int) -> tuple[str, str, int]:
    """What `uq_job_requirements_span` already treats as one requirement.

    Used to hand an `Evidence` row back the id of the `job_requirements` row it
    came from. `RequirementProposal` carries no id — it is the extractor's
    output shape and predates the table — so the join is on the tuple the
    database itself considers unique rather than on object identity, which does
    not survive the round trip through `scoring.py`.
    """
    return (kind, value, char_start)


def _proposals(
    requirements: Sequence[JobRequirement],
) -> tuple[tuple[RequirementProposal, ...], dict[tuple[str, str, int], uuid.UUID]]:
    """Stored requirement rows as the extractor's own dataclass, plus their ids.

    **Read from the table, never re-extracted here.** Re-running the extractor
    would produce proposals that no `job_requirements` row corresponds to
    whenever the two versions differ, and `match_evidence.job_requirement_id`
    would then be null on rows that plainly have a requirement behind them —
    evidence that cannot be traced back, which is the whole point of the column.
    """
    proposals: list[RequirementProposal] = []
    ids: dict[tuple[str, str, int], uuid.UUID] = {}
    for row in requirements:
        proposals.append(
            RequirementProposal(
                kind=row.kind.value,
                value=row.value,
                raw_text=row.raw_text,
                char_start=row.char_start,
                char_end=row.char_end,
                necessity=row.necessity.value,
                has_equivalence=row.has_equivalence,
            )
        )
        ids[_identity(row.kind.value, row.value, row.char_start)] = row.id
    return tuple(proposals), ids


def posting_for(
    job: Job,
    requirements: Sequence[JobRequirement],
    locations: Sequence[JobLocation],
) -> tuple[PostingForScoring, dict[tuple[str, str, int], uuid.UUID]]:
    """Assemble what the scorer reads from rows that are already loaded.

    **The role family is re-classified rather than read from `jobs.role_family`,
    and that is not an oversight.** The classifier's *span* is not a stored
    column, and role relevance owes a quoted span (§2.1). Pairing a stored
    family with a freshly computed span would mean the words in the evidence row
    and the family they justify came from two different runs of the rules, which
    is the second-derivation failure `TextSpan`'s own docstring was written
    about: they agree until a classifier version moves without a re-ingestion,
    and then the row quotes text that produced a different answer.

    It also keeps this function and the golden test's corpus assembly the same
    shape, which is what makes the committed golden file a description of what
    production does rather than of what a test does.
    """
    proposals, ids = _proposals(requirements)
    text = job.description_text or ""
    reading = read_posting(list(proposals))
    years = reading.min_years_experience
    classification = classify_role(
        job.title,
        description=text,
        years=years if isinstance(years, int) else None,
    )
    posting = PostingForScoring(
        title=job.title,
        description_text=text,
        role_family=classification.role_family,
        role_family_span=classification.family_span,
        seniority=classification.seniority,
        requirements=proposals,
        locations=tuple(
            JobLocationForScoring(city=row.city, region=row.state) for row in locations
        ),
        remote_policy=job.remote_policy.value if job.remote_policy else None,
        source_published_at=(
            job.source_published_at.date() if job.source_published_at is not None else None
        ),
    )
    return posting, ids


def profile_for(user: User) -> ScoringProfile:
    """A `users` row and its confirmed children as the scorer's own dataclass.

    Only confirmed facts reach here (I2). `user.skills` and `user.projects` are
    `user_skills` and `user_projects`, which `domain/profile.py` is the sole
    writer of; `resume_extractions` holds proposals and is not read anywhere in
    this module.
    """
    return ScoringProfile(
        skills=tuple(
            ConfirmedSkill(name=row.name, taxonomy_id=row.skill_id, user_skill_id=row.id)
            for row in user.skills
        ),
        projects=tuple(
            ConfirmedProject(
                name=row.name,
                technologies=tuple(row.technologies or ()),
                evidence=row.evidence,
                user_project_id=row.id,
            )
            for row in user.projects
        ),
        preferred_roles=tuple(user.preferred_roles or ()),
        preferred_locations=tuple(user.preferred_locations or ()),
        remote_preference=user.remote_preference.value if user.remote_preference else None,
        years_experience=user.years_experience,
    )


def _eligibility_for(user: User, proposals: Sequence[RequirementProposal]) -> EligibilityState:
    """The gate's verdict, stored beside the score and never folded into it (§5.2).

    A posting with no extracted requirements reaches `uncertain` rather than
    `eligible`. The jobs route returns `None` for that case and the page shows
    nothing; this column is `NOT NULL`, so the honest value here is the state
    that means *we did not learn enough to say* — which is what an unread
    posting is. Reading it as `eligible` would be a claim about a person based on
    a posting nobody parsed.
    """
    if not proposals:
        return EligibilityState.UNCERTAIN
    return evaluate(read_posting(list(proposals)), profile_from_user(user)).state


def _score_row(
    *,
    user: User,
    job: Job,
    score: MatchScore,
    eligibility: EligibilityState,
    ruleset: str,
    requirement_ids: dict[tuple[str, str, int], uuid.UUID],
) -> MatchResult:
    """One `match_results` row and its two sets of children, unsaved.

    The component columns are filled through `COMPONENT_SCORE_COLUMNS` rather
    than from the tuple's order. `MatchScore.__post_init__` already refuses a
    tuple that is not exactly the six, so this cannot silently write a zero for a
    missing one — but reading by position would make the mapping between a
    component and its column a fact about two files agreeing on an order, and
    that is the shape of thing this project keeps finding out of date.
    """
    points = {component.component: component.points for component in score.components}
    result = MatchResult(
        user_id=user.id,
        job_id=job.id,
        overall_score=score.overall,
        assessed_out_of=score.assessed_out_of,
        eligibility_status=eligibility,
        **{column: points[component] for component, column in COMPONENT_SCORE_COLUMNS.items()},
        penalty_score=score.penalty_total,
        # Null until Task 11. A rules-only score has no embedding behind it and
        # naming one here would make `proposed_by` unauditable.
        model_version=None,
        ruleset_version=ruleset,
    )
    result.evidence = [
        _evidence_row(row, requirement_ids=requirement_ids) for row in score.evidence
    ]
    # All six, assessable or not. The database asserts the count at commit
    # (`match_results_components_are_assessed`), so a component quietly left
    # without a statement is a failed transaction rather than a page rendering
    # five of six with nothing looking wrong.
    result.assessments = [
        MatchComponentAssessment(
            component=component.component,
            assessable=component.assessable,
            why=component.why,
        )
        for component in score.components
    ]
    # Both, applicable or not. §4.2 keeps `penalty_score` as one column and this
    # does not reopen that — it records what the column is made of, which §4.2
    # itself calls the explanation's business and nothing then carried. The
    # database asserts at commit that these sum to the column
    # (`match_results_penalties_are_accounted_for`), so the split cannot drift
    # from the total it decomposes.
    result.penalties = [
        MatchPenalty(
            name=penalty.name,
            points=penalty.points,
            applicable=penalty.applicable,
            why=penalty.why,
            compared=dict(penalty.compared),
        )
        for penalty in score.penalties
    ]
    return result


def _evidence_row(
    row: Evidence, *, requirement_ids: dict[tuple[str, str, int], uuid.UUID]
) -> MatchEvidence:
    """A field copy, deliberately. `Evidence` mirrors this table's columns.

    The one thing that is a lookup rather than a copy is `job_requirement_id`,
    and it resolves to `None` when the evidence points at a span that is no
    requirement row — which is legal today for the exempt components and is the
    shape Task 11's embedding proposals will arrive in.
    """
    requirement = row.requirement
    requirement_id = (
        requirement_ids.get(_identity(requirement.kind, requirement.value, requirement.char_start))
        if requirement is not None
        else None
    )
    return MatchEvidence(
        component=row.component,
        points=row.points,
        job_requirement_id=requirement_id,
        job_span_text=row.job_span_text,
        job_span_field=row.job_span_field,
        job_char_start=row.job_char_start,
        job_char_end=row.job_char_end,
        user_skill_id=row.user_skill_id,
        user_project_id=row.user_project_id,
        user_span_text=row.user_span_text,
        compared=dict(row.compared),
        proposed_by=row.proposed_by,
    )


async def _load_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """The person and both sets of confirmed facts, in one round trip.

    `selectinload` rather than lazy access, because the sweep loads one user and
    scores thousands of postings against them: a lazy `user.skills` inside that
    loop is a query per posting, and under an async session it is not a slow
    query but a `MissingGreenlet`.
    """
    return (
        await session.execute(
            select(User)
            .options(selectinload(User.skills), selectinload(User.projects))
            .where(User.id == user_id)
        )
    ).scalar_one_or_none()


async def score_pair(
    session: AsyncSession,
    *,
    user: User,
    job: Job,
    weights: MatchingWeights,
    as_of: date,
) -> MatchResult | None:
    """Score one (person, posting) pair and add the row. Does not commit.

    Returns `None` for a posting with no description text, and that is a refusal
    rather than a zero. Skill overlap and project evidence read a requirement
    list that is extracted from the description, so a posting without one cannot
    produce either — and the three components that remain would be scored out of
    a denominator that says the other three *were* assessable, which is exactly
    the false statement §5.1.1 exists to prevent. The pair reads as
    not-yet-computed, which is true of it.
    """
    if not job.description_text:
        return None

    # `profile_for` is sync and walks `user.skills` and `user.projects`, so a
    # user this session loaded without them raises `MissingGreenlet` — a lazy
    # load from inside sync code — rather than returning an empty profile. That
    # is the better of the two failures and still a trap: the caller that hits it
    # is whoever loads a `User` for some other purpose and passes it here,
    # which is every route Task 9 adds. Loading what is missing costs one query
    # and only when something is actually missing; `_load_user` below leaves
    # nothing to do.
    unloaded = {"skills", "projects"} & inspect(user).unloaded
    if unloaded:
        await session.refresh(user, sorted(unloaded))

    requirements = list(
        (
            await session.execute(
                select(JobRequirement)
                .where(JobRequirement.job_id == job.id)
                .order_by(JobRequirement.char_start, JobRequirement.id)
            )
        )
        .scalars()
        .all()
    )
    locations = list(
        (await session.execute(select(JobLocation).where(JobLocation.job_id == job.id)))
        .scalars()
        .all()
    )
    posting, requirement_ids = posting_for(job, requirements, locations)
    score = score_match(posting, profile_for(user), weights=weights, as_of=as_of)
    row = _score_row(
        user=user,
        job=job,
        score=score,
        eligibility=_eligibility_for(user, posting.requirements),
        ruleset=weights.ruleset_version,
        requirement_ids=requirement_ids,
    )
    session.add(row)
    return row


async def current_result_for(
    session: AsyncSession, *, user_id: uuid.UUID, job_id: uuid.UUID
) -> MatchResult | None:
    """This pair's score **at the current ruleset version**, or `None`.

    `None` means *not yet computed*, and it is the only other answer this
    function has. There is deliberately no third state for "computed under rules
    that no longer exist", because the page has nothing true to do with one: a
    number produced by arithmetic that has since changed is not a worse score, it
    is not a score (§4.2, *a stale result is never silently served*).

    **The version is a filter, not a sort.** §4.2 keeps old-version rows on
    purpose — a bump computes alongside what it replaced, so the comparison is
    possible — which means `match_results` legitimately holds several rows for one
    pair, and the newest is not necessarily the current one either: the sweep
    processes a bump in batches, so a row written a minute ago can carry the old
    version while a row written last week carries the new one only after its batch
    lands. Any query that reaches for the latest row, or the highest score, or the
    only row it can find, therefore serves exactly the rows this function exists
    to refuse. It compares `ruleset_version` to `load_weights()` and nothing else.

    Both children are eager-loaded because every caller needs both: a score with
    its evidence left behind is I4's bare number, and one with its assessments
    left behind cannot tell a component that scored zero from one nobody could
    ask (§5.1.1).
    """
    ruleset = load_weights().ruleset_version
    return (
        await session.execute(
            select(MatchResult)
            .where(
                MatchResult.user_id == user_id,
                MatchResult.job_id == job_id,
                MatchResult.ruleset_version == ruleset,
            )
            .options(
                selectinload(MatchResult.evidence),
                selectinload(MatchResult.assessments),
                selectinload(MatchResult.penalties),
            )
        )
    ).scalar_one_or_none()


async def pending_pairs(
    session: AsyncSession, *, ruleset: str, limit: int
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """(user, job) pairs with no score at the current ruleset version.

    This one query is both the "new or changed job" trigger and the "ruleset
    version bump" trigger, and it is the same query for both because after the
    database triggers have done their work the two situations are indeterminable
    from the outside — which is the point. There is no event to miss and no
    queue to lose: absence of a row *is* the work item, and it is durable.

    Only open jobs. Scoring a closed posting spends the corpus on rows the
    ranked list filters out, and I3 is what makes `status` trustworthy enough to
    filter on: a source outage does not close anything.

    Ordered so that a bounded sweep makes progress rather than re-examining the
    same slice — `limit` is a batch size, not a cap on the work.
    """
    rows = await session.execute(
        select(User.id, Job.id)
        .join(Job, Job.status == JobStatus.OPEN)
        .outerjoin(
            MatchResult,
            (MatchResult.user_id == User.id)
            & (MatchResult.job_id == Job.id)
            & (MatchResult.ruleset_version == ruleset),
        )
        .where(MatchResult.id.is_(None))
        .order_by(User.id, Job.first_seen_at, Job.id)
        .limit(limit)
    )
    return [(user_id, job_id) for user_id, job_id in rows.all()]


async def recompute_pending(
    session: AsyncSession, *, limit: int = 500, as_of: date | None = None
) -> RecomputeReport:
    """Score one batch of due pairs. The sweep behind two of the three triggers.

    Bounded on purpose. An unbounded rescore after a version bump is one
    transaction holding thousands of rows, and a failure anywhere in it discards
    every score it computed — the shape of a retry storm this plan named in
    advance. A batch commits what it finished and the next tick continues.
    """
    weights = load_weights()
    ruleset = weights.ruleset_version
    today = as_of or utcnow().date()
    pairs = await pending_pairs(session, ruleset=ruleset, limit=limit)

    scored = 0
    skipped = 0
    users: dict[uuid.UUID, User | None] = {}
    for user_id, job_id in pairs:
        if user_id not in users:
            users[user_id] = await _load_user(session, user_id)
        user = users[user_id]
        job = await session.get(Job, job_id)
        if user is None or job is None:
            skipped += 1
            continue
        if await score_pair(session, user=user, job=job, weights=weights, as_of=today) is None:
            skipped += 1
            continue
        scored += 1

    log.info("match_results_recomputed", scored=scored, skipped=skipped, ruleset=ruleset)
    return RecomputeReport(scored=scored, skipped=skipped, ruleset=ruleset)


async def clear_scores_for_user(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Delete this person's scores, every version. What a profile change calls.

    **Every version, not only the current one.** §4.2 keeps old-version rows so a
    ruleset bump can be compared against what preceded it, and that comparison is
    only meaningful when the *person* held still. A row scored against a profile
    that has since been replaced is not a baseline, it is a different experiment
    with the same label.

    Deletion rather than recomputation, for §4.2's reason and one more: this runs
    inside the request's transaction, and scoring the corpus there would put a
    multi-second job in the path of a form submission.
    """
    # `session.execute` is typed as returning `Result`; a DELETE always yields a
    # `CursorResult`, which is where `rowcount` lives. The same cast, and the
    # same reason, as `ingestion._mark_seen`.
    result = cast(
        "CursorResult[Any]",
        await session.execute(delete(MatchResult).where(MatchResult.user_id == user_id)),
    )
    deleted = int(result.rowcount or 0)
    if deleted:
        log.info("match_results_cleared", user_id=str(user_id), deleted=deleted)
    return deleted
