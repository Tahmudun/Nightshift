"""The schema half of invariant I2: what the database itself refuses.

The span-quoting trigger is the reason this slice can promise that a highlight
and a claim never disagree. It is demonstrated here *by attempting the
violation and catching the error* — a constraint nobody has watched reject
something is a comment with extra syntax (milestone-0 review, F3).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ExtractionKind,
    ExtractionStatus,
    ResumeSourceKind,
    SkillSourceType,
)
from nightshift.db.models import Resume, ResumeExtraction, User, UserSkill
from nightshift.domain.resume_text import RESUME_FORMATS
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

#: "Python" is at 8..14 and "Docker" at 19..25.
PARSED = "Skills: Python and Docker.\n"


async def _a_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.test", display_name="Test User")
    session.add(user)
    await session.flush()
    return user


async def _a_resume(session: AsyncSession, user: User) -> Resume:
    resume = Resume(
        user_id=user.id,
        name="test resume",
        source_kind=ResumeSourceKind.PASTE,
        parsed_text=PARSED,
        content_hash=uuid.uuid4().hex,
    )
    session.add(resume)
    await session.flush()
    return resume


def _proposal(user: User, resume: Resume, **overrides: object) -> ResumeExtraction:
    fields: dict[str, object] = {
        "user_id": user.id,
        "resume_id": resume.id,
        "kind": ExtractionKind.SKILL,
        "value": {"name": "Python"},
        "char_start": 8,
        "char_end": 14,
        "quoted_text": "Python",
        "extractor_version": "test",
    }
    fields.update(overrides)
    return ResumeExtraction(**fields)  # type: ignore[arg-type]


async def test_a_span_that_quotes_the_text_is_accepted(db_session: AsyncSession) -> None:
    """The positive case, first. A trigger that refuses everything is worse
    than no trigger, and one off-by-one in `substring` produces exactly that."""
    user = await _a_user(db_session)
    resume = await _a_resume(db_session, user)
    db_session.add(_proposal(user, resume))
    await db_session.flush()  # must not raise


async def test_a_proposal_must_quote_the_resume_text(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    resume = await _a_resume(db_session, user)
    # The text at 8..14 is "Python", not "Rust".
    db_session.add(_proposal(user, resume, value={"name": "Rust"}, quoted_text="Rust"))
    with pytest.raises(DBAPIError, match="does not quote"):
        await db_session.flush()


async def test_a_proposal_whose_span_runs_past_the_text_is_refused(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    resume = await _a_resume(db_session, user)
    db_session.add(
        _proposal(user, resume, char_start=0, char_end=len(PARSED) + 50, quoted_text=PARSED)
    )
    with pytest.raises(DBAPIError, match="runs past"):
        await db_session.flush()


async def test_a_proposal_with_an_empty_span_is_refused(db_session: AsyncSession) -> None:
    """ "A proposal with no span is unrepresentable" (command-center.md §6.1)."""
    user = await _a_user(db_session)
    resume = await _a_resume(db_session, user)
    db_session.add(_proposal(user, resume, char_start=8, char_end=8, quoted_text=""))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_proposal_with_a_negative_span_is_refused(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    resume = await _a_resume(db_session, user)
    db_session.add(_proposal(user, resume, char_start=-4, char_end=2, quoted_text="Sk"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_decided_proposal_must_carry_the_time_it_was_decided(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    resume = await _a_resume(db_session, user)
    db_session.add(_proposal(user, resume, status=ExtractionStatus.CONFIRMED))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_confirmed_skill_cannot_be_marked_pending(db_session: AsyncSession) -> None:
    """`user_skills` holds confirmed facts. A pending one belongs elsewhere."""
    user = await _a_user(db_session)
    db_session.add(
        UserSkill(
            user_id=user.id,
            name="Python",
            normalized_name="python",
            source_type=SkillSourceType.INFERRED_PENDING_CONFIRMATION,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_skill_per_user_per_name(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    for _ in range(2):
        db_session.add(
            UserSkill(
                user_id=user.id,
                name="Python",
                normalized_name="python",
                source_type=SkillSourceType.MANUAL,
            )
        )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_a_graduation_month_requires_a_year(db_session: AsyncSession) -> None:
    """A month with no year is not a date, it is a fragment (I1)."""
    user = await _a_user(db_session)
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("UPDATE users SET graduation_month = 5, graduation_year = NULL WHERE id = :id"),
            {"id": user.id},
        )


async def test_a_graduation_month_must_be_a_month(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    with pytest.raises(DBAPIError):
        await db_session.execute(
            text("UPDATE users SET graduation_month = 13, graduation_year = 2027 WHERE id = :id"),
            {"id": user.id},
        )


async def test_deleting_a_resume_takes_its_proposals_and_leaves_confirmed_facts(
    db_session: AsyncSession,
) -> None:
    """A confirmed fact belongs to the person, not to the file it came from."""
    user = await _a_user(db_session)
    resume = await _a_resume(db_session, user)
    db_session.add(_proposal(user, resume))
    db_session.add(
        UserSkill(
            user_id=user.id,
            name="Python",
            normalized_name="python",
            source_type=SkillSourceType.RESUME,
            source_reference=f"resume:{resume.id}#8-14",
        )
    )
    await db_session.flush()

    await db_session.delete(resume)
    await db_session.flush()

    proposals = (
        await db_session.execute(
            text("SELECT count(*) FROM resume_extractions WHERE user_id = :id"), {"id": user.id}
        )
    ).scalar_one()
    skills = (
        await db_session.execute(
            text("SELECT count(*) FROM user_skills WHERE user_id = :id"), {"id": user.id}
        )
    ).scalar_one()
    assert (proposals, skills) == (0, 1)


async def test_the_enum_and_the_reader_agree_on_format_names() -> None:
    """A drift here would store a `source_kind` nothing can read back.

    Async only because this module's `pytestmark` says so; it touches nothing.
    """
    assert {kind.value for kind in ResumeSourceKind} == set(RESUME_FORMATS)
