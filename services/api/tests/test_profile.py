"""Promotion across the boundary, and everything that must not cross it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import ExtractionKind, ExtractionStatus, ResumeSourceKind
from nightshift.db.models import Resume, ResumeExtraction, User, UserProject, UserSkill
from nightshift.domain import profile
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
RESUME_TEXT = (Path(__file__).parent / "fixtures" / "resumes" / "nadia_okonkwo.txt").read_text(
    encoding="utf-8"
)
PROSE_TEXT = (Path(__file__).parent / "fixtures" / "resumes" / "prose_only.txt").read_text(
    encoding="utf-8"
)


async def _a_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.test", display_name="Test User")
    session.add(user)
    await session.flush()
    return user


async def _a_resume_with_proposals(
    session: AsyncSession, user: User, text: str = RESUME_TEXT
) -> tuple[Resume, list[ResumeExtraction]]:
    resume, _ = await profile.create_resume(
        session,
        user_id=user.id,
        name="my resume",
        source_kind=ResumeSourceKind.PASTE,
        original_filename=None,
        text=text,
    )
    proposals = await profile.propose_from_resume(session, resume=resume)
    return resume, proposals


async def _count(session: AsyncSession, model: type, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).select_from(model).where(model.user_id == user_id)
            )
        ).scalar_one()
    )


async def test_pasting_a_resume_confirms_nothing(db_session: AsyncSession) -> None:
    """Invariant I2, stated as a test. Everything else in this file is detail."""
    user = await _a_user(db_session)
    _, proposals = await _a_resume_with_proposals(db_session, user)

    assert proposals, "the fixture resume should propose something"
    assert all(p.status is ExtractionStatus.PENDING for p in proposals)
    assert await _count(db_session, UserSkill, user.id) == 0
    assert await _count(db_session, UserProject, user.id) == 0
    assert (user.graduation_year, user.degree, user.school) == (None, None, None)


async def test_confirming_a_skill_creates_exactly_that_skill(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    resume, proposals = await _a_resume_with_proposals(db_session, user)
    python = next(p for p in proposals if p.value.get("name") == "Python")

    result = await profile.confirm_extractions(
        db_session,
        user_id=user.id,
        resume_id=resume.id,
        decisions={python.id: "confirm"},
        now=NOW,
    )

    assert (result.confirmed, result.skills_added) == (1, 1)
    skills = (
        (await db_session.execute(select(UserSkill).where(UserSkill.user_id == user.id)))
        .scalars()
        .all()
    )
    assert [skill.name for skill in skills] == ["Python"]
    assert skills[0].source_reference == (
        f"resume:{resume.id}#{python.char_start}-{python.char_end}"
    )
    assert python.status is ExtractionStatus.CONFIRMED
    assert python.decided_at == NOW


async def test_rejecting_a_proposal_writes_nothing_but_the_decision(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    resume, proposals = await _a_resume_with_proposals(db_session, user)
    go = next(p for p in proposals if p.value.get("name") == "Go")

    result = await profile.confirm_extractions(
        db_session, user_id=user.id, resume_id=resume.id, decisions={go.id: "reject"}, now=NOW
    )

    assert (result.confirmed, result.rejected) == (0, 1)
    assert go.status is ExtractionStatus.REJECTED
    assert go.decided_at == NOW
    assert await _count(db_session, UserSkill, user.id) == 0


async def test_confirming_a_graduation_sets_a_year_and_a_month_and_no_day(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    resume, proposals = await _a_resume_with_proposals(db_session, user)
    graduation = next(p for p in proposals if p.kind is ExtractionKind.GRADUATION)

    result = await profile.confirm_extractions(
        db_session,
        user_id=user.id,
        resume_id=resume.id,
        decisions={graduation.id: "confirm"},
        now=NOW,
    )

    assert (user.graduation_year, user.graduation_month) == (2027, 5)
    assert "graduation_year" in result.profile_fields_set
    # There is no day to check, which is the point (I1).
    assert not hasattr(user, "graduation_date")


async def test_confirming_a_project_stores_its_bullets_as_evidence(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    resume, proposals = await _a_resume_with_proposals(db_session, user)
    project = next(p for p in proposals if p.kind is ExtractionKind.PROJECT)

    await profile.confirm_extractions(
        db_session,
        user_id=user.id,
        resume_id=resume.id,
        decisions={project.id: "confirm"},
        now=NOW,
    )

    stored = (
        (await db_session.execute(select(UserProject).where(UserProject.user_id == user.id)))
        .scalars()
        .one()
    )
    assert stored.name == "Transit Delay Tracker"
    assert "MTA real-time feeds" in (stored.evidence or "")


async def test_confirming_twice_is_idempotent(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    resume, proposals = await _a_resume_with_proposals(db_session, user)
    python = next(p for p in proposals if p.value.get("name") == "Python")

    first = await profile.confirm_extractions(
        db_session, user_id=user.id, resume_id=resume.id, decisions={python.id: "confirm"}, now=NOW
    )
    second = await profile.confirm_extractions(
        db_session, user_id=user.id, resume_id=resume.id, decisions={python.id: "confirm"}, now=NOW
    )

    assert (first.confirmed, first.skipped) == (1, 0)
    assert (second.confirmed, second.skipped) == (0, 1)
    assert await _count(db_session, UserSkill, user.id) == 1


async def test_re_uploading_the_same_resume_returns_the_same_row(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    first, created_first = await profile.create_resume(
        db_session,
        user_id=user.id,
        name="one",
        source_kind=ResumeSourceKind.PASTE,
        original_filename=None,
        text=RESUME_TEXT,
    )
    proposals = await profile.propose_from_resume(db_session, resume=first)
    second, created_second = await profile.create_resume(
        db_session,
        user_id=user.id,
        name="two",
        source_kind=ResumeSourceKind.PDF,
        original_filename="resume.pdf",
        text=RESUME_TEXT,
    )
    again = await profile.propose_from_resume(db_session, resume=second)

    assert (created_first, created_second) == (True, False)
    assert first.id == second.id
    assert len(again) == len(proposals), "proposals must not be duplicated on re-upload"


async def test_a_changed_resume_is_a_new_row(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    first, _ = await profile.create_resume(
        db_session,
        user_id=user.id,
        name="one",
        source_kind=ResumeSourceKind.PASTE,
        original_filename=None,
        text=RESUME_TEXT,
    )
    second, created = await profile.create_resume(
        db_session,
        user_id=user.id,
        name="two",
        source_kind=ResumeSourceKind.PASTE,
        original_filename=None,
        text=RESUME_TEXT + "\nRust\n",
    )
    assert created is True
    assert first.id != second.id
    assert second.is_default is False, "only the first resume defaults"


async def test_a_proposal_from_another_users_resume_cannot_be_confirmed(
    db_session: AsyncSession,
) -> None:
    """A3: every query filters on user_id, and this is what proves it is real."""
    owner = await _a_user(db_session)
    intruder = await _a_user(db_session)
    resume, proposals = await _a_resume_with_proposals(db_session, owner)
    target = proposals[0]

    with pytest.raises(profile.ExtractionNotFoundError):
        await profile.confirm_extractions(
            db_session,
            user_id=intruder.id,
            resume_id=resume.id,
            decisions={target.id: "confirm"},
            now=NOW,
        )

    assert await _count(db_session, UserSkill, intruder.id) == 0
    assert await _count(db_session, UserSkill, owner.id) == 0
    assert target.status is ExtractionStatus.PENDING


async def test_a_proposal_from_another_resume_of_the_same_user_is_refused(
    db_session: AsyncSession,
) -> None:
    """The resume filter is not decoration: it is what makes the confirm
    screen's promise ("these proposals, from this file") true."""
    user = await _a_user(db_session)
    resume_one, proposals = await _a_resume_with_proposals(db_session, user)
    resume_two, _ = await profile.create_resume(
        db_session,
        user_id=user.id,
        name="other",
        source_kind=ResumeSourceKind.PASTE,
        original_filename=None,
        text=PROSE_TEXT,
    )

    with pytest.raises(profile.ExtractionNotFoundError):
        await profile.confirm_extractions(
            db_session,
            user_id=user.id,
            resume_id=resume_two.id,
            decisions={proposals[0].id: "confirm"},
            now=NOW,
        )
    assert resume_one.id != resume_two.id


async def test_a_resume_that_proves_nothing_produces_no_proposals(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    _, proposals = await _a_resume_with_proposals(db_session, user, text=PROSE_TEXT)
    assert proposals == []


async def test_deleting_a_resume_leaves_confirmed_skills_alone(
    db_session: AsyncSession,
) -> None:
    user = await _a_user(db_session)
    resume, proposals = await _a_resume_with_proposals(db_session, user)
    python = next(p for p in proposals if p.value.get("name") == "Python")
    await profile.confirm_extractions(
        db_session, user_id=user.id, resume_id=resume.id, decisions={python.id: "confirm"}, now=NOW
    )

    assert await profile.delete_resume(db_session, user_id=user.id, resume_id=resume.id) is True
    assert await _count(db_session, UserSkill, user.id) == 1
    assert await _count(db_session, ResumeExtraction, user.id) == 0


async def test_manual_skill_entry_does_not_need_a_resume(db_session: AsyncSession) -> None:
    """§6.2's manual path, and where "nothing could be proven" sends people."""
    user = await _a_user(db_session)
    skill = await profile.add_skill(db_session, user_id=user.id, name="  Rust ")
    assert skill.name == "Rust"
    assert skill.source_reference == "manual"
    assert await profile.remove_skill(db_session, user_id=user.id, skill_id=skill.id) is True
    assert await _count(db_session, UserSkill, user.id) == 0


async def test_a_patch_touches_only_what_it_names(db_session: AsyncSession) -> None:
    user = await _a_user(db_session)
    await profile.update_profile(
        db_session,
        user_id=user.id,
        patch=profile.ProfilePatch.from_mapping({"school": "Hunter College"}),
    )
    await profile.update_profile(
        db_session,
        user_id=user.id,
        patch=profile.ProfilePatch.from_mapping({"minimum_salary": 90000}),
    )
    assert (user.school, user.minimum_salary) == ("Hunter College", 90000)


async def test_a_patch_can_clear_a_field(db_session: AsyncSession) -> None:
    """Otherwise "remove my minimum salary" is unexpressible."""
    user = await _a_user(db_session)
    await profile.update_profile(
        db_session,
        user_id=user.id,
        patch=profile.ProfilePatch.from_mapping({"minimum_salary": 90000}),
    )
    await profile.update_profile(
        db_session,
        user_id=user.id,
        patch=profile.ProfilePatch.from_mapping({"minimum_salary": None}),
    )
    assert user.minimum_salary is None


async def test_a_patch_naming_an_unknown_field_is_refused() -> None:
    with pytest.raises(profile.UnknownProfileFieldError):
        profile.ProfilePatch.from_mapping({"is_admin": True})
