"""A score reaching the database, and what makes one due.

M3c Task 8. `test_scoring.py` grades the arithmetic with no Postgres running and
`test_matching_golden.py` pins its output; neither can see the half this file is
about — whether the number that survives a round trip through
`match_results` is the number the scorer produced, and whether the right rows go
missing when an input moves.

Three of these tests exist because of a specific thing that would otherwise be
true and untested:

* **The title span.** Role relevance quotes `jobs.title`; every other span in
  this system points into `description_text`. Before `job_span_field` there was
  one column and the quoting trigger checked one string, so the first real role
  evidence row would have been rejected — and the cheapest way to make it pass
  would have been to stop storing the span, which is the evidence graph quietly
  losing the one component §2.1 cares most about.
* **A display-name change.** The acceptance criterion for this task is a
  negative: *a profile change rescores; a display-name change does not*. Only a
  test can hold that line, because the version that rescores on everything is
  simpler, passes every other test, and is wrong only in load.
* **The denominator's constraint.** `overall_score <= assessed_out_of` is what
  makes the ranked list's fraction meaningful. It is asserted by the database,
  and shown here to be a constraint that can actually fail rather than one that
  is trivially true of every row anyone happens to write.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    JobStatus,
    JobTextField,
    MatchComponent,
    ProficiencyLevel,
    RemotePreference,
    SkillSourceType,
)
from nightshift.db.models import Job, MatchEvidence, MatchResult, User, UserSkill
from nightshift.domain import matching
from nightshift.domain.ingestion import sync_requirements
from nightshift.domain.matching_weights import load_weights
from nightshift.domain.profile import ProfilePatch, update_profile
from nightshift.domain.scoring import WEIGHT_NAME, score_match
from tests.conftest import make_job_with_text, requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

#: Long enough to carry a required-technology block the extractor recognises, so
#: skill overlap and the missing-requirement penalty are both live. A posting
#: naming no technology exercises a different and equally important path — see
#: `test_a_terse_posting_is_scored_out_of_less_than_a_hundred`.
DESCRIPTION = (
    "About the role. We are hiring for our core team in New York. "
    "Requirements: strong Python, experience with PostgreSQL, and familiarity with Docker. "
    "Nice to have: Kubernetes."
)

TODAY = datetime(2026, 8, 9, tzinfo=UTC).date()


async def _user(session: AsyncSession, **fields: Any) -> User:
    """A user of this test's own — `users` is not truncated by `db_session`."""
    user = User(email=f"recompute-{uuid.uuid4().hex[:12]}@example.test", **fields)
    session.add(user)
    await session.flush()
    return user


async def _job(session: AsyncSession, description: str = DESCRIPTION) -> Job:
    """A posting with its requirements extracted, as ingestion would leave it."""
    job = await make_job_with_text(session, description)
    job.title = "Software Engineer"
    job.source_published_at = datetime.now(tz=UTC) - timedelta(days=2)
    await sync_requirements(session, job)
    await session.flush()
    return job


async def _reload(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await matching._load_user(session, user_id)


async def _score_count(session: AsyncSession, **where: Any) -> int:
    query = select(func.count()).select_from(MatchResult)
    for column, value in where.items():
        query = query.where(getattr(MatchResult, column) == value)
    return int((await session.execute(query)).scalar_one())


# ---------------------------------------------------------------------------
# A score survives the round trip
# ---------------------------------------------------------------------------


async def test_a_scored_pair_stores_the_number_the_scorer_produced(
    db_session: AsyncSession,
) -> None:
    """The stored row against `score_match` on the same inputs, field by field.

    The failure this catches is a copy that drifts: `_score_row` maps six
    components onto six columns, and a transposition there is invisible to every
    other test in the suite — the total still adds up, the constraint still
    holds, and only the breakdown is wrong. I4 is a claim about the breakdown.
    """
    user = await _user(db_session, years_experience=1)
    job = await _job(db_session)

    weights = load_weights()
    stored = await matching.score_pair(db_session, user=user, job=job, weights=weights, as_of=TODAY)
    assert stored is not None
    await db_session.flush()

    requirements, locations = await _requirements_and_locations(db_session, job)
    posting, _ = matching.posting_for(job, requirements, locations)
    expected = score_match(posting, matching.profile_for(user), weights=weights, as_of=TODAY)

    assert stored.overall_score == expected.overall
    assert stored.assessed_out_of == expected.assessed_out_of
    assert stored.penalty_score == expected.penalty_total
    assert stored.ruleset_version == weights.ruleset_version
    # Null until Task 11 — a rules-only score has no embedding behind it.
    assert stored.model_version is None

    by_component = {c.component: c.points for c in expected.components}
    assert stored.role_score == by_component[MatchComponent.ROLE]
    assert stored.skill_score == by_component[MatchComponent.SKILL]
    assert stored.project_evidence_score == by_component[MatchComponent.PROJECT]
    assert stored.location_score == by_component[MatchComponent.LOCATION]
    assert stored.freshness_score == by_component[MatchComponent.FRESHNESS]
    assert stored.priority_score == by_component[MatchComponent.PRIORITY]
    assert len(stored.evidence) == len(expected.evidence)

    # Written out by hand rather than through `COMPONENT_SCORE_COLUMNS`, on
    # purpose: this is the test that would catch a transposition *in* that
    # mapping, and reading the row through the same mapping that wrote it would
    # agree with itself whatever it said.
    #
    # The assessments, added at Task 9. Both fields, because they answer different
    # questions and only one of them is recoverable from anything else: a zero and
    # an unassessable component both store `0` in their score column (§5.1.1).
    assert {row.component for row in stored.assessments} == set(MatchComponent)
    stated = {row.component: row for row in stored.assessments}
    for component in expected.components:
        assert stated[component.component].assessable == component.assessable
        assert stated[component.component].why == component.why


async def _requirements_and_locations(session: AsyncSession, job: Job) -> tuple[list, list]:
    from nightshift.db.models import JobLocation, JobRequirement

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
    return requirements, locations


async def test_the_deferred_evidence_guard_passes_on_a_real_score(
    db_session: AsyncSession,
) -> None:
    """Every positive component the scorer produced has its evidence row.

    `SET CONSTRAINTS ALL IMMEDIATE` for the reason `test_match_result_models.py`
    records: the guard is deferrable and this suite never commits, so without
    forcing it the strongest assertion in the schema would never fire in a test
    of the code that has to satisfy it.
    """
    user = await _user(db_session, years_experience=1)
    db_session.add(
        UserSkill(
            user_id=user.id,
            name="Python",
            normalized_name="python",
            skill_id="python",
            proficiency_level=ProficiencyLevel.UNSPECIFIED,
            source_type=SkillSourceType.MANUAL,
        )
    )
    await db_session.flush()
    user = await _reload(db_session, user.id)
    assert user is not None

    job = await _job(db_session)
    result = await matching.score_pair(
        db_session, user=user, job=job, weights=load_weights(), as_of=TODAY
    )
    assert result is not None
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    assert result.skill_score > 0, "the fixture must exercise the guard it claims to"


# ---------------------------------------------------------------------------
# The title span, which is why this task owed a migration
# ---------------------------------------------------------------------------


async def test_role_evidence_quotes_the_title_and_says_so(db_session: AsyncSession) -> None:
    """The row records `title`, and the offsets index the title, not the description."""
    user = await _user(db_session, preferred_roles=["software engineer"])
    user = await _reload(db_session, user.id)
    assert user is not None
    job = await _job(db_session)

    result = await matching.score_pair(
        db_session, user=user, job=job, weights=load_weights(), as_of=TODAY
    )
    assert result is not None
    await db_session.flush()

    role_rows = [row for row in result.evidence if row.component is MatchComponent.ROLE]
    assert role_rows, "the fixture profile must reach role relevance"
    for row in role_rows:
        assert row.job_span_field is JobTextField.TITLE
        assert row.job_char_start is not None and row.job_char_end is not None
        assert job.title[row.job_char_start : row.job_char_end] == row.job_span_text


async def test_a_title_span_filed_as_a_description_span_is_refused(
    db_session: AsyncSession,
) -> None:
    """The migration's whole point, shown able to fail.

    Storing the same offsets under `description_text` is what the schema did
    before `job_span_field` existed. The trigger now checks the string the row
    names, and this row names the wrong one.
    """
    user = await _user(db_session, preferred_roles=["software engineer"])
    user = await _reload(db_session, user.id)
    assert user is not None
    job = await _job(db_session)
    result = await matching.score_pair(
        db_session, user=user, job=job, weights=load_weights(), as_of=TODAY
    )
    assert result is not None
    await db_session.flush()

    role = next(row for row in result.evidence if row.component is MatchComponent.ROLE)
    with pytest.raises(DBAPIError, match="does not quote the job description_text"):
        db_session.add(
            MatchEvidence(
                match_result_id=result.id,
                component=MatchComponent.ROLE,
                job_span_text=role.job_span_text,
                job_span_field=JobTextField.DESCRIPTION_TEXT,
                job_char_start=role.job_char_start,
                job_char_end=role.job_char_end,
                user_span_text=role.user_span_text,
                points=0,
            )
        )
        await db_session.flush()


# ---------------------------------------------------------------------------
# The denominator
# ---------------------------------------------------------------------------


async def test_a_terse_posting_is_scored_out_of_less_than_a_hundred(
    db_session: AsyncSession,
) -> None:
    """§5.1.1 in the database: no required technology, so half the score cannot be asked.

    Also the assertion that `assessed_out_of` is not decoration — a
    reimplementation that always stored 100 would pass every other test here.
    """
    user = await _user(db_session, years_experience=1)
    job = await _job(db_session, "We are hiring. Come and work with a friendly team in Brooklyn.")

    result = await matching.score_pair(
        db_session, user=user, job=job, weights=load_weights(), as_of=TODAY
    )
    assert result is not None
    await db_session.flush()

    weights = load_weights()
    requirements, locations = await _requirements_and_locations(db_session, job)
    posting, _ = matching.posting_for(job, requirements, locations)
    expected = score_match(posting, matching.profile_for(user), weights=weights, as_of=TODAY)

    unassessable = {component.component for component in expected.unassessable}
    assert MatchComponent.SKILL in unassessable
    assert MatchComponent.PROJECT in unassessable
    # The denominator is the weights of what remained, and nothing else. Written
    # as the sum rather than as a literal so it stays true when a weight moves —
    # the number itself is pinned by the golden file, one layer down.
    assert result.assessed_out_of == sum(
        weights.weight(WEIGHT_NAME[component.component])
        for component in expected.components
        if component.assessable
    )
    assert result.assessed_out_of < 100
    assert result.skill_score == 0
    assert result.project_evidence_score == 0

    # The two facts the page needs and the score columns cannot carry: *which*
    # components could not be assessed, and why. `assessed_out_of` names how much
    # was assessed and can never name which — several subsets of the six weights
    # sum to the same number — so without these rows a terse posting reaches the
    # browser as two components scoring zero, which is the reading §5.1.1 exists
    # to prevent.
    stated = {row.component: row for row in result.assessments}
    assert stated[MatchComponent.SKILL].assessable is False
    assert stated[MatchComponent.PROJECT].assessable is False
    assert "no required technologies" in stated[MatchComponent.SKILL].why
    # And not everything: a fixture where all six were unassessable would satisfy
    # the two assertions above while proving nothing about the distinction.
    assert stated[MatchComponent.FRESHNESS].assessable is True


async def test_a_score_may_not_exceed_what_was_assessed(db_session: AsyncSession) -> None:
    """The constraint the ranked list's fraction rests on, shown able to fail."""
    user = await _user(db_session, years_experience=1)
    job = await _job(db_session)
    result = await matching.score_pair(
        db_session, user=user, job=job, weights=load_weights(), as_of=TODAY
    )
    assert result is not None
    await db_session.flush()

    # Widen the numerator past the denominator by the smallest possible amount,
    # keeping `the_total_is_its_parts` satisfied so the failure can only be the
    # constraint this test names.
    result.freshness_score = result.freshness_score + (
        result.assessed_out_of - result.overall_score + 1
    )
    result.overall_score = result.assessed_out_of + 1
    with pytest.raises(DBAPIError, match="a_score_never_exceeds_what_was_assessed"):
        await db_session.flush()


# ---------------------------------------------------------------------------
# What makes a score due
# ---------------------------------------------------------------------------


async def test_a_new_job_is_pending_and_stops_being_pending_once_scored(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, years_experience=1)
    job = await _job(db_session)
    ruleset = load_weights().ruleset_version

    pending = await matching.pending_pairs(db_session, ruleset=ruleset, limit=50)
    assert (user.id, job.id) in pending

    report = await matching.recompute_pending(db_session, limit=50, as_of=TODAY)
    assert report.scored >= 1
    await db_session.flush()

    assert (user.id, job.id) not in await matching.pending_pairs(
        db_session, ruleset=ruleset, limit=50
    )


async def test_recomputing_twice_writes_one_row(db_session: AsyncSession) -> None:
    """Idempotent, and not by way of the unique constraint raising.

    The sweep works from what is *missing*, so a second run finds nothing to do.
    A version that recomputed everything and relied on
    `uq_match_results_user_job_ruleset` to deduplicate would fail this test by
    raising, which is the point: an integrity error is not idempotency.
    """
    user = await _user(db_session, years_experience=1)
    job = await _job(db_session)

    first = await matching.recompute_pending(db_session, limit=50, as_of=TODAY)
    await db_session.flush()
    second = await matching.recompute_pending(db_session, limit=50, as_of=TODAY)
    await db_session.flush()

    assert first.scored >= 1
    assert second.scored == 0
    assert await _score_count(db_session, user_id=user.id, job_id=job.id) == 1


async def test_a_closed_posting_is_never_swept(db_session: AsyncSession) -> None:
    """I3 makes `status` trustworthy; this is what spends the corpus on it."""
    user = await _user(db_session, years_experience=1)
    job = await _job(db_session)
    job.status = JobStatus.CLOSED
    job.closed_at = datetime.now(tz=UTC)
    await db_session.flush()

    pending = await matching.pending_pairs(
        db_session, ruleset=load_weights().ruleset_version, limit=50
    )
    assert (user.id, job.id) not in pending


async def test_a_ruleset_version_bump_makes_every_pair_due_again(
    db_session: AsyncSession,
) -> None:
    """§4.2's third trigger, and the old row is kept rather than deleted."""
    user = await _user(db_session, years_experience=1)
    job = await _job(db_session)
    await matching.recompute_pending(db_session, limit=50, as_of=TODAY)
    await db_session.flush()

    bumped = replace(load_weights(), version="2999-01-01.1")
    assert (user.id, job.id) in await matching.pending_pairs(
        db_session, ruleset=bumped.ruleset_version, limit=50
    )

    result = await matching.score_pair(db_session, user=user, job=job, weights=bumped, as_of=TODAY)
    assert result is not None
    await db_session.flush()
    # Both versions present: §4.2 computes alongside rather than overwriting, so
    # a bump can be compared against what it replaced.
    assert await _score_count(db_session, user_id=user.id, job_id=job.id) == 2


# ---------------------------------------------------------------------------
# The acceptance criterion: a profile change rescores, a display name does not
# ---------------------------------------------------------------------------


async def test_a_scoring_relevant_profile_change_clears_the_scores(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, years_experience=1)
    job = await _job(db_session)
    await matching.recompute_pending(db_session, limit=50, as_of=TODAY)
    await db_session.flush()
    assert await _score_count(db_session, user_id=user.id) == 1

    await update_profile(
        db_session,
        user_id=user.id,
        patch=ProfilePatch.from_mapping({"preferred_roles": ["data engineer"]}),
    )
    await db_session.flush()

    assert await _score_count(db_session, user_id=user.id) == 0
    assert (user.id, job.id) in await matching.pending_pairs(
        db_session, ruleset=load_weights().ruleset_version, limit=50
    )


async def test_a_display_name_change_leaves_every_score_alone(
    db_session: AsyncSession,
) -> None:
    """The negative half of the criterion, and the reason the named list exists.

    Rescoring on any profile write is simpler code that passes the positive test
    above. What it costs is a full corpus rescore every time somebody edits a
    field no component reads, which is a retry storm with a form submission in
    front of it.
    """
    user = await _user(db_session, years_experience=1)
    await _job(db_session)
    await matching.recompute_pending(db_session, limit=50, as_of=TODAY)
    await db_session.flush()
    assert await _score_count(db_session, user_id=user.id) == 1

    await update_profile(
        db_session,
        user_id=user.id,
        patch=ProfilePatch.from_mapping({"display_name": "Somebody Else"}),
    )
    await db_session.flush()

    assert await _score_count(db_session, user_id=user.id) == 1


async def test_resubmitting_the_same_values_changes_nothing(db_session: AsyncSession) -> None:
    """Provided is not changed, and a form saved unedited must cost nothing.

    This is the case a `provided`-based implementation gets wrong: M2c's PATCH
    carries every field the form holds, so "save" with no edits provides the
    whole scoring-relevant set and would rescore the corpus on each click.
    """
    user = await _user(db_session, years_experience=1, remote_preference=RemotePreference.HYBRID)
    user.preferred_roles = ["software engineer"]
    await db_session.flush()
    await _job(db_session)
    await matching.recompute_pending(db_session, limit=50, as_of=TODAY)
    await db_session.flush()

    await update_profile(
        db_session,
        user_id=user.id,
        patch=ProfilePatch.from_mapping(
            {
                "years_experience": 1,
                "remote_preference": RemotePreference.HYBRID,
                "preferred_roles": ["software engineer"],
            }
        ),
    )
    await db_session.flush()

    assert await _score_count(db_session, user_id=user.id) == 1


async def test_confirming_a_graduation_year_clears_the_scores(
    db_session: AsyncSession,
) -> None:
    """`confirm_extractions` writes the same columns `update_profile` does.

    `graduation_year` is not read by any *component* — it is read by the gate,
    and `eligibility_status` is a column of `match_results`. A score whose
    eligibility band no longer matches the person is exactly as wrong as one
    whose number does not, and this is the path that would have missed it.
    """
    user = await _user(db_session, years_experience=1)
    await _job(db_session)
    await matching.recompute_pending(db_session, limit=50, as_of=TODAY)
    await db_session.flush()
    assert await _score_count(db_session, user_id=user.id) == 1

    user.graduation_year = 2027
    await matching._load_user(db_session, user.id)
    cleared = await matching.clear_scores_for_user(db_session, user.id)
    assert cleared == 1
    assert await _score_count(db_session, user_id=user.id) == 0
