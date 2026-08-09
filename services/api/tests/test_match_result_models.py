"""The guards on a score: every one of them shown able to fail.

`matching.md` §4.3 puts two of these in the database rather than in code review,
and the M3c plan gives the reason: the code that breaks them is code doing its
job correctly. A scorer that awards 12 points for skill overlap and writes no
evidence row is not malfunctioning — it is a scorer somebody wrote before the
evidence part, and every test in the suite goes on passing.

**Why every test here calls `SET CONSTRAINTS ALL IMMEDIATE`.** The evidence
guard is a deferrable constraint trigger, so it runs at commit; this suite rolls
back and never commits, which would mean the guard never fired in a single test
and the whole file asserted nothing. Forcing it is also how it is shown to fail:
the statement raises when the transaction's state is wrong and returns when it
is right, so both directions are observed rather than assumed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    EligibilityState,
    EvidenceSource,
    JobTextField,
    MatchComponent,
    ProficiencyLevel,
    RequirementKind,
    RequirementNecessity,
    SkillSourceType,
)
from nightshift.db.models import (
    Job,
    JobRequirement,
    MatchEvidence,
    MatchResult,
    User,
    UserProject,
    UserSkill,
)
from tests.conftest import make_job_with_text, requires_db

# The session-scoped loop is required, not stylistic — see
# test_job_requirement_models.py, which hit this first.
pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

DESCRIPTION = "We need strong Python and a track record of shipping distributed systems."


async def _user(session: AsyncSession) -> User:
    """A user of this test's own. `users` is not truncated by `db_session`."""
    user = User(email=f"scorer-{uuid.uuid4().hex[:12]}@example.test")
    session.add(user)
    await session.flush()
    return user


async def _job(session: AsyncSession, description: str = DESCRIPTION) -> Job:
    return await make_job_with_text(session, description)


def _result(user: User, job: Job, **overrides: Any) -> MatchResult:
    """A score whose parts add up. Overrides are what each test is about."""
    fields: dict[str, Any] = {
        "user_id": user.id,
        "job_id": job.id,
        "overall_score": 0,
        "eligibility_status": EligibilityState.UNCERTAIN,
        "role_score": 0,
        "skill_score": 0,
        "project_evidence_score": 0,
        "location_score": 0,
        "freshness_score": 0,
        "priority_score": 0,
        "penalty_score": 0,
        # Added with the column at `0017_match_score_denominator`. 100 — every
        # component assessable — because these tests are about the guards, not
        # about §5.1.1: a smaller denominator would make
        # `a_score_never_exceeds_what_was_assessed` the thing that fires in
        # tests naming a different constraint, which is a test whose failure
        # message lies about what broke. `test_match_recompute.py` is where the
        # denominator is exercised against real scores.
        "assessed_out_of": 100,
        "ruleset_version": "1+test",
    }
    fields.update(overrides)
    return MatchResult(**fields)


def _skill_evidence(result: MatchResult, *, points: int = 12, **overrides: Any) -> MatchEvidence:
    """A well-formed `skill` row: both spans quoted, offsets into DESCRIPTION."""
    start = DESCRIPTION.index("Python")
    fields: dict[str, Any] = {
        "match_result_id": result.id,
        "component": MatchComponent.SKILL,
        "job_span_text": "Python",
        # Added with the column at `0017_match_score_denominator`: the span
        # travels as text, field and both offsets, and the quoting trigger reads
        # the field to know which string of `jobs` to check against.
        "job_span_field": JobTextField.DESCRIPTION_TEXT,
        "job_char_start": start,
        "job_char_end": start + len("Python"),
        "user_span_text": "Python",
        "proposed_by": EvidenceSource.RULE,
        "points": points,
    }
    fields.update(overrides)
    return MatchEvidence(**fields)


async def _commit_check(session: AsyncSession) -> None:
    """Run the deferred guards now, as `COMMIT` would — then defer them again.

    The restoration is not tidiness. `SET CONSTRAINTS ALL IMMEDIATE` holds for
    the **rest of the transaction**, so a test that checks, then mutates, then
    checks again is running the second half in immediate mode — and the tests
    that delete an evidence row after a passing check were measured raising on
    the `DELETE` statement itself rather than at the end. That is a different
    guard from the one this file claims to exercise: it would pass while the
    deferred behaviour real commits depend on was never observed.
    """
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


async def _match_result_count(session: AsyncSession, **where: Any) -> int:
    query = select(func.count()).select_from(MatchResult)
    for column, value in where.items():
        query = query.where(getattr(MatchResult, column) == value)
    return int((await session.execute(query)).scalar_one())


# ---------------------------------------------------------------------------
# Guard 1 — a component with no evidence is not a component
# ---------------------------------------------------------------------------


async def test_a_score_with_its_evidence_commits(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    db_session.add(_skill_evidence(result))
    await db_session.flush()

    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 1


async def test_a_positive_component_with_no_evidence_cannot_be_committed(
    db_session: AsyncSession,
) -> None:
    """The guard, shown able to fail on the realistic mistake.

    Not a corrupted row and not a hand-written violation of a rule nobody would
    break — this is a scorer that awards points for skill overlap and has not
    written the evidence half yet. Every other constraint on the table is
    satisfied: the components are non-negative, the total is its parts, the
    eligibility state is real. Only the evidence is missing, and that is exactly
    the row invariant I4 exists to refuse.
    """
    user = await _user(db_session)
    job = await _job(db_session)
    db_session.add(_result(user, job, skill_score=12, overall_score=12))
    await db_session.flush()

    with pytest.raises(DBAPIError, match="has no skill evidence row"):
        await _commit_check(db_session)


async def test_the_guard_names_the_component_and_the_score_it_is_missing(
    db_session: AsyncSession,
) -> None:
    """A guard whose message does not say what is wrong sends the reader to the
    trigger source to find out, which is the moment most people disable it."""
    user = await _user(db_session)
    job = await _job(db_session)
    db_session.add(_result(user, job, project_evidence_score=7, overall_score=7))
    await db_session.flush()

    with pytest.raises(DBAPIError, match=r"scores 7 for project and has no project evidence row"):
        await _commit_check(db_session)


async def test_deleting_the_last_evidence_row_for_a_component_is_refused(
    db_session: AsyncSession,
) -> None:
    """The same violation from the other side.

    A guard that only watches `match_results` cannot see this: the score is
    never touched, so its trigger never queues. This is why there are two.
    """
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    evidence = _skill_evidence(result)
    db_session.add(evidence)
    await db_session.flush()
    await _commit_check(db_session)

    await db_session.delete(evidence)
    await db_session.flush()

    with pytest.raises(DBAPIError, match="has no skill evidence row"):
        await _commit_check(db_session)


async def test_a_second_evidence_row_may_be_deleted(db_session: AsyncSession) -> None:
    """The guard asserts *at least one*, and a rule that fires on the wrong
    condition is as bad as one that never fires."""
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    keep = _skill_evidence(result, points=8)
    drop = _skill_evidence(result, points=4)
    db_session.add_all([keep, drop])
    await db_session.flush()

    await db_session.delete(drop)
    await db_session.flush()
    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 1


async def test_a_zero_component_needs_no_evidence(db_session: AsyncSession) -> None:
    """A job the person has no skill overlap with scores zero for skill and says
    so. Requiring an evidence row for nothing would mean inventing one."""
    user = await _user(db_session)
    job = await _job(db_session)
    db_session.add(_result(user, job, freshness_score=10, overall_score=10))
    await db_session.flush()
    db_session.add(
        MatchEvidence(
            match_result_id=(await db_session.execute(select(MatchResult.id))).scalar_one(),
            component=MatchComponent.FRESHNESS,
            compared={"last_seen_at": "2026-08-09", "days": 0},
            points=10,
        )
    )
    await db_session.flush()

    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 1


async def test_a_score_deleted_in_the_same_transaction_raises_nothing(
    db_session: AsyncSession,
) -> None:
    """A deferred trigger fires at commit with the record it was queued with, so
    a function trusting `NEW` would raise about a row that no longer exists."""
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    await db_session.delete(result)
    await db_session.flush()

    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 0


# ---------------------------------------------------------------------------
# Guard 2 — a claim about a person quotes both sides
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "component",
    [MatchComponent.ROLE, MatchComponent.SKILL, MatchComponent.PROJECT],
)
async def test_a_claim_about_the_person_with_no_user_span_is_refused(
    db_session: AsyncSession, component: MatchComponent
) -> None:
    """§2.1's three components, each shown able to fail rather than one standing
    in for the others — a CHECK listing two of three names passes this test in
    its single-component form and ships the third unguarded."""
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    db_session.add(_skill_evidence(result, component=component, user_span_text=None))

    with pytest.raises(IntegrityError, match="a_person_claim_quotes_both_sides"):
        await db_session.flush()


async def test_a_claim_about_the_person_with_no_job_span_is_refused(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    db_session.add(
        _skill_evidence(result, job_span_text=None, job_char_start=None, job_char_end=None)
    )

    with pytest.raises(IntegrityError, match="a_person_claim_quotes_both_sides"):
        await db_session.flush()


async def test_an_exempt_component_may_not_carry_a_user_span(
    db_session: AsyncSession,
) -> None:
    """The half the first constraint did not cover, and this test is what found
    it.

    The original was one biconditional — `component IN (role, skill, project) =
    (both spans non-null)` — which reads like it covers both directions and does
    not. For a `freshness` row carrying a user-side span and no job span, both
    sides evaluate false, the equality holds, and the row is accepted: a
    quotation of somebody's own words filed under a component that makes no
    claim about them. Written as a passing test first, it failed, and the second
    constraint is the result.
    """
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, freshness_score=10, overall_score=10)
    db_session.add(result)
    await db_session.flush()
    db_session.add(
        MatchEvidence(
            match_result_id=result.id,
            component=MatchComponent.FRESHNESS,
            user_span_text="Python",
            points=10,
        )
    )

    with pytest.raises(IntegrityError, match="only_a_person_claim_quotes_a_person"):
        await db_session.flush()


async def test_an_exempt_component_may_still_quote_the_posting(
    db_session: AsyncSession,
) -> None:
    """Only the *user* side is restricted, and the reason is what the two sides
    mean. The priority component reads the posting's own seniority; quoting the
    sentence it read makes it more auditable, not less. A constraint that
    stripped every span from the exempt three would push those rows back to a
    JSON summary of what they compared and nothing to check it against.
    """
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, priority_score=10, overall_score=10)
    db_session.add(result)
    await db_session.flush()
    start = DESCRIPTION.index("Python")
    db_session.add(
        MatchEvidence(
            match_result_id=result.id,
            component=MatchComponent.PRIORITY,
            job_span_text="Python",
            job_span_field=JobTextField.DESCRIPTION_TEXT,
            job_char_start=start,
            job_char_end=start + len("Python"),
            points=10,
        )
    )
    await db_session.flush()
    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 1


async def test_an_exempt_component_records_what_it_compared(
    db_session: AsyncSession,
) -> None:
    """Exempt from quoting a span is not exempt from being inspectable (I4)."""
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, location_score=10, overall_score=10)
    db_session.add(result)
    await db_session.flush()
    db_session.add(
        MatchEvidence(
            match_result_id=result.id,
            component=MatchComponent.LOCATION,
            compared={"job": "New York, NY", "preference": "hybrid"},
            points=10,
        )
    )
    await db_session.flush()
    await _commit_check(db_session)

    stored = (
        await db_session.execute(
            select(MatchEvidence.compared).where(MatchEvidence.match_result_id == result.id)
        )
    ).scalar_one()
    assert stored == {"job": "New York, NY", "preference": "hybrid"}


# ---------------------------------------------------------------------------
# Guard 3 — the job-side span literally quotes the description
# ---------------------------------------------------------------------------


async def test_a_span_off_by_one_character_is_refused(db_session: AsyncSession) -> None:
    """Shifting the offset by one is the whole test.

    The row still claims `job_span_text = "Python"`, the offsets are still
    inside the description, and the numbers still look plausible in a debugger.
    The only thing wrong is that they point at different characters than the
    words claim — which is what a quoted span silently drifting looks like, and
    is unreadable from the row itself.
    """
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    start = DESCRIPTION.index("Python")
    db_session.add(
        _skill_evidence(result, job_char_start=start + 1, job_char_end=start + 1 + len("Python"))
    )

    with pytest.raises(DBAPIError, match="does not quote the job description"):
        await db_session.flush()


async def test_a_span_running_past_the_description_is_refused(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    db_session.add(
        _skill_evidence(
            result, job_char_start=len(DESCRIPTION) - 2, job_char_end=len(DESCRIPTION) + 40
        )
    )

    with pytest.raises(DBAPIError, match="runs past"):
        await db_session.flush()


# ---------------------------------------------------------------------------
# The total is its parts
# ---------------------------------------------------------------------------


async def test_a_total_that_is_not_its_parts_is_refused(db_session: AsyncSession) -> None:
    """Without this, "every score decomposes" is a property of whichever
    function last wrote the row rather than of the row."""
    user = await _user(db_session)
    job = await _job(db_session)
    db_session.add(_result(user, job, skill_score=12, overall_score=40))

    with pytest.raises(IntegrityError, match="the_total_is_its_parts"):
        await db_session.flush()


async def test_a_penalty_below_the_components_floors_at_zero(
    db_session: AsyncSession,
) -> None:
    """Components can reach 100 and penalties -55, so arithmetic can go negative
    where meaning cannot. The floor is in the constraint, so a scorer that
    stores -3 is refused rather than displayed."""
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=5, penalty_score=-25, overall_score=0)
    db_session.add(result)
    await db_session.flush()
    db_session.add(_skill_evidence(result, points=5))
    await db_session.flush()
    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 1


async def test_a_penalty_that_adds_points_is_refused(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    job = await _job(db_session)
    db_session.add(_result(user, job, penalty_score=5, overall_score=5))

    with pytest.raises(IntegrityError, match="a_penalty_never_adds"):
        await db_session.flush()


# ---------------------------------------------------------------------------
# A score dies with its inputs
# ---------------------------------------------------------------------------


async def test_rewriting_a_description_deletes_the_scores_for_that_job(
    db_session: AsyncSession,
) -> None:
    """The evidence rows hold character offsets into the old text. Keeping the
    score would mean keeping a quotation of characters that have moved."""
    user = await _user(db_session)
    job = await _job(db_session)
    other_job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    untouched = _result(user, other_job, freshness_score=10, overall_score=10)
    db_session.add_all([result, untouched])
    await db_session.flush()
    db_session.add(_skill_evidence(result))
    db_session.add(
        MatchEvidence(match_result_id=untouched.id, component=MatchComponent.FRESHNESS, points=10)
    )
    await db_session.flush()

    job.description_text = DESCRIPTION.replace("Python", "Rust")
    await db_session.flush()
    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 0
    assert await _match_result_count(db_session, job_id=other_job.id) == 1


async def test_a_description_rewritten_to_the_same_text_keeps_the_score(
    db_session: AsyncSession,
) -> None:
    """A re-poll of an unchanged board writes the same text back. Throwing away
    every score in the corpus on every poll is a rescore storm, which is the
    same `IS DISTINCT FROM` reasoning M3a's requirements trigger carries."""
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    db_session.add(_skill_evidence(result))
    await db_session.flush()

    await db_session.execute(
        text("UPDATE jobs SET description_text = :value WHERE id = :id"),
        {"value": DESCRIPTION, "id": job.id},
    )
    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 1


async def test_ingestion_rewriting_a_description_does_not_fail_at_commit(
    db_session: AsyncSession,
) -> None:
    """The interaction these triggers exist for, asserted end to end.

    `_apply_normalized_fields()` rewrites `description_text` on every re-poll of
    a changed job. That fires M3a's trigger, which deletes `job_requirements`,
    which cascades to `match_evidence` — and without a trigger deleting the
    score too, the transaction ends with a positive component and no evidence
    and **ingestion fails at commit**. Reproduced before the trigger existed.
    """
    user = await _user(db_session)
    job = await _job(db_session)
    start = DESCRIPTION.index("Python")
    requirement = JobRequirement(
        job_id=job.id,
        kind=RequirementKind.TECHNOLOGY,
        value="Python",
        raw_text="Python",
        char_start=start,
        char_end=start + len("Python"),
        necessity=RequirementNecessity.REQUIRED,
        extractor_version="test",
    )
    db_session.add(requirement)
    await db_session.flush()
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    db_session.add(_skill_evidence(result, job_requirement_id=requirement.id))
    await db_session.flush()

    await db_session.execute(
        text("UPDATE jobs SET description_text = :value WHERE id = :id"),
        {"value": "An entirely different posting about Rust.", "id": job.id},
    )
    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 0


async def test_re_extracting_requirements_deletes_the_scores_for_that_job(
    db_session: AsyncSession,
) -> None:
    """A requirement row appearing or vanishing changes what the score was
    computed against, even when the description did not move."""
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    db_session.add(_skill_evidence(result))
    await db_session.flush()

    start = DESCRIPTION.index("Python")
    db_session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.TECHNOLOGY,
            value="Python",
            raw_text="Python",
            char_start=start,
            char_end=start + len("Python"),
            necessity=RequirementNecessity.REQUIRED,
            extractor_version="test",
        )
    )
    await db_session.flush()
    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 0


async def test_deleting_a_confirmed_skill_deletes_that_person_s_scores(
    db_session: AsyncSession,
) -> None:
    """The evidence quotes the skill. A score outliving the fact it rests on is
    the I2 failure one layer down: a claim about a person with nothing behind
    it."""
    user = await _user(db_session)
    job = await _job(db_session)
    skill = UserSkill(
        user_id=user.id,
        name="Python",
        normalized_name="python",
        skill_id="Python",
        proficiency_level=ProficiencyLevel.UNSPECIFIED,
        source_type=SkillSourceType.MANUAL,
    )
    db_session.add(skill)
    await db_session.flush()
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    db_session.add(_skill_evidence(result, user_skill_id=skill.id))
    await db_session.flush()
    await _commit_check(db_session)

    await db_session.delete(skill)
    await db_session.flush()
    await _commit_check(db_session)

    assert await _match_result_count(db_session, user_id=user.id) == 0


async def test_editing_a_project_deletes_that_person_s_scores(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    job = await _job(db_session)
    project = UserProject(user_id=user.id, name="Sharded work queue", evidence="Built it in Rust")
    db_session.add(project)
    await db_session.flush()
    result = _result(user, job, skill_score=12, overall_score=12)
    db_session.add(result)
    await db_session.flush()
    db_session.add(_skill_evidence(result))
    await db_session.flush()
    await _commit_check(db_session)

    project.evidence = "Built it in Go"
    await db_session.flush()
    await _commit_check(db_session)

    assert await _match_result_count(db_session, user_id=user.id) == 0


async def test_one_person_s_change_does_not_delete_another_person_s_scores(
    db_session: AsyncSession,
) -> None:
    """A trigger that deletes by the wrong key passes every test above."""
    user = await _user(db_session)
    other = await _user(db_session)
    job = await _job(db_session)
    mine = _result(user, job, freshness_score=10, overall_score=10)
    theirs = _result(other, job, freshness_score=10, overall_score=10)
    db_session.add_all([mine, theirs])
    await db_session.flush()
    for row in (mine, theirs):
        db_session.add(
            MatchEvidence(match_result_id=row.id, component=MatchComponent.FRESHNESS, points=10)
        )
    skill = UserSkill(
        user_id=user.id,
        name="Python",
        normalized_name="python",
        skill_id="Python",
        proficiency_level=ProficiencyLevel.UNSPECIFIED,
        source_type=SkillSourceType.MANUAL,
    )
    db_session.add(skill)
    await db_session.flush()

    await db_session.delete(skill)
    await db_session.flush()
    await _commit_check(db_session)

    assert await _match_result_count(db_session, user_id=user.id) == 0
    assert await _match_result_count(db_session, user_id=other.id) == 1


# ---------------------------------------------------------------------------
# The version, and what it is for
# ---------------------------------------------------------------------------


async def test_two_ruleset_versions_coexist_for_one_person_and_job(
    db_session: AsyncSession,
) -> None:
    """§4.2's uniqueness is on (user, job, ruleset_version), not on (user, job).

    A version bump computes alongside what it is being compared against rather
    than overwriting it, which is what makes "what did this change do to the
    corpus" answerable at all.
    """
    user = await _user(db_session)
    job = await _job(db_session)
    for version in ("1+2026-08-09.1", "2+2026-08-09.1"):
        row = _result(user, job, freshness_score=10, overall_score=10, ruleset_version=version)
        db_session.add(row)
        await db_session.flush()
        db_session.add(
            MatchEvidence(match_result_id=row.id, component=MatchComponent.FRESHNESS, points=10)
        )
    await db_session.flush()
    await _commit_check(db_session)

    assert await _match_result_count(db_session, job_id=job.id) == 2


async def test_the_same_ruleset_version_cannot_be_scored_twice(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    job = await _job(db_session)
    db_session.add(_result(user, job, freshness_score=10, overall_score=10))
    await db_session.flush()
    db_session.add(_result(user, job, freshness_score=10, overall_score=10))

    with pytest.raises(IntegrityError, match="uq_match_results_user_job_ruleset"):
        await db_session.flush()


async def test_created_at_is_stored_in_utc(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    job = await _job(db_session)
    result = _result(user, job, freshness_score=10, overall_score=10)
    db_session.add(result)
    await db_session.flush()
    evidence = MatchEvidence(
        match_result_id=result.id, component=MatchComponent.FRESHNESS, points=10
    )
    db_session.add(evidence)
    await db_session.flush()
    await db_session.refresh(evidence)

    assert evidence.created_at.tzinfo is not None
    assert evidence.created_at.astimezone(UTC) <= datetime.now(tz=UTC)
