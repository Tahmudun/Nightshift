"""The one module that may turn a proposal into a confirmed fact.

Invariant I2 lives here. ``resume_extractions`` holds what a file *appears* to
say; ``users``, ``user_skills`` and ``user_projects`` hold what a person
confirmed. Promotion crosses that boundary and nothing else may
(``tests/test_nothing_infers.py`` asserts it at the source level, and the
extractor cannot even import the ORM).

Two consequences worth stating, because both are easy to undo by accident:

* **Nothing here infers.** Every write is downstream of a decision the user
  made. A resume that proves nothing produces no rows at all rather than
  half-filled ones.
* **Deleting a resume does not un-confirm anything.** A confirmed fact belongs
  to the person, not to the file it arrived in.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    ExtractionKind,
    ExtractionStatus,
    ProficiencyLevel,
    ProjectStatus,
    RemotePreference,
    ResumeSourceKind,
    ResumeVariant,
    SkillSourceType,
    WorkAuthorization,
)
from nightshift.db.models import Resume, ResumeExtraction, User, UserProject, UserSkill
from nightshift.domain.resume_extraction import EXTRACTOR_VERSION, extract_proposals
from nightshift.domain.skill_vocabulary import SkillVocabulary

Decision = Literal["confirm", "reject"]


class ProfileError(Exception):
    """Base for everything this module refuses to do."""


class UserNotFoundError(ProfileError):
    """A3: the user id comes from a dependency, so this is a bug, not input."""


class ResumeNotFoundError(ProfileError):
    pass


class ExtractionNotFoundError(ProfileError):
    """A proposal that is not this user's, or not on this resume.

    Raised rather than skipped. A silent skip would make a cross-user confirm
    look like a success, which is the shape of a data leak.
    """


class UnknownProfileFieldError(ProfileError):
    pass


class InvalidProfileError(ProfileError):
    pass


def normalize_skill_name(name: str) -> str:
    """ "PostgreSQL" and "postgresql" are one skill."""
    return " ".join(name.split()).casefold()


@dataclass(frozen=True, slots=True)
class ProfilePatch:
    """A partial update. ``provided`` is what makes clearing a field expressible.

    Without it, "set my minimum salary to nothing" and "do not touch my minimum
    salary" are the same request, and one of them silently loses data.
    """

    FIELDS: ClassVar[tuple[str, ...]] = (
        "display_name",
        "graduation_year",
        "graduation_month",
        "degree",
        "school",
        "work_authorization",
        "home_location_text",
        "remote_preference",
        "minimum_salary",
        "preferred_roles",
        "preferred_locations",
    )

    provided: frozenset[str] = field(default_factory=frozenset)
    display_name: str | None = None
    graduation_year: int | None = None
    graduation_month: int | None = None
    degree: str | None = None
    school: str | None = None
    work_authorization: WorkAuthorization = WorkAuthorization.UNSPECIFIED
    home_location_text: str | None = None
    remote_preference: RemotePreference = RemotePreference.NO_PREFERENCE
    minimum_salary: int | None = None
    preferred_roles: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> ProfilePatch:
        unknown = set(values) - set(cls.FIELDS)
        if unknown:
            raise UnknownProfileFieldError(f"not profile fields: {sorted(unknown)}")
        return cls(provided=frozenset(values), **values)


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    confirmed: int
    rejected: int
    #: Already decided before this call. Reported rather than raised, so a
    #: double-submitted form is not an error.
    skipped: int
    skills_added: int
    projects_added: int
    profile_fields_set: tuple[str, ...]


async def _load_user(session: AsyncSession, user_id: UUID) -> User:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise UserNotFoundError(str(user_id))
    return user


# ---------------------------------------------------------------------------
# Resumes and their proposals
# ---------------------------------------------------------------------------


def content_hash(text: str) -> str:
    """Over the *text*, not the file.

    So a PDF and a paste of the same content are one resume rather than two —
    the thing being identified is what the resume says, not how it arrived.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def create_resume(
    session: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    source_kind: ResumeSourceKind,
    original_filename: str | None,
    text: str,
    variant_type: ResumeVariant = ResumeVariant.CUSTOM,
) -> tuple[Resume, bool]:
    """Get-or-create by content hash. The bool is "newly created".

    Re-uploading the same resume is a no-op rather than a second row, which
    keeps a person's decisions attached to the text they were made against.
    """
    digest = content_hash(text)

    async def _find() -> Resume | None:
        return (
            await session.execute(
                select(Resume).where(Resume.user_id == user_id, Resume.content_hash == digest)
            )
        ).scalar_one_or_none()

    existing = await _find()
    if existing is not None:
        return existing, False

    has_any = (
        await session.execute(select(Resume.id).where(Resume.user_id == user_id).limit(1))
    ).first()
    resume = Resume(
        user_id=user_id,
        name=name,
        variant_type=variant_type,
        source_kind=source_kind,
        original_filename=original_filename,
        parsed_text=text,
        content_hash=digest,
        is_default=has_any is None,
    )
    try:
        # A savepoint, so losing a race costs a re-read rather than the whole
        # transaction. M2b shipped a 500 for exactly this shape of race before
        # it was fixed the same way.
        async with session.begin_nested():
            session.add(resume)
            await session.flush()
    except IntegrityError:
        raced = await _find()
        if raced is None:
            raise
        return raced, False
    return resume, True


async def propose_from_resume(
    session: AsyncSession, *, resume: Resume, vocabulary: SkillVocabulary | None = None
) -> list[ResumeExtraction]:
    """Extract and store proposals — once per resume.

    If proposals already exist they are returned untouched. Re-proposing would
    strand every decision already made against this text, and "your confirmed
    skills quietly reverted to pending" is not a behaviour worth having.
    """
    existing = list(
        (
            await session.execute(
                select(ResumeExtraction)
                .where(ResumeExtraction.resume_id == resume.id)
                .order_by(ResumeExtraction.char_start, ResumeExtraction.char_end)
            )
        )
        .scalars()
        .all()
    )
    if existing:
        return existing

    rows = [
        ResumeExtraction(
            user_id=resume.user_id,
            resume_id=resume.id,
            kind=ExtractionKind(proposal.kind),
            value=proposal.value,
            char_start=proposal.char_start,
            char_end=proposal.char_end,
            quoted_text=proposal.quoted_text,
            extractor_version=EXTRACTOR_VERSION,
        )
        for proposal in extract_proposals(resume.parsed_text, vocabulary=vocabulary)
    ]
    session.add_all(rows)
    await session.flush()
    return rows


# ---------------------------------------------------------------------------
# Promotion — the boundary crossing
# ---------------------------------------------------------------------------


async def _promote_skill(
    session: AsyncSession, *, user_id: UUID, extraction: ResumeExtraction
) -> bool:
    name = str(extraction.value["name"])
    normalized = normalize_skill_name(name)
    existing = (
        await session.execute(
            select(UserSkill).where(
                UserSkill.user_id == user_id, UserSkill.normalized_name == normalized
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    version = extraction.value.get("vocabulary_version")
    session.add(
        UserSkill(
            user_id=user_id,
            name=name,
            normalized_name=normalized,
            proficiency_level=ProficiencyLevel.UNSPECIFIED,
            source_type=SkillSourceType.RESUME,
            source_reference=(
                f"resume:{extraction.resume_id}#{extraction.char_start}-{extraction.char_end}"
            ),
            vocabulary_version=str(version) if version is not None else None,
        )
    )
    return True


async def _promote_project(
    session: AsyncSession, *, user_id: UUID, extraction: ResumeExtraction
) -> bool:
    name = str(extraction.value["name"])
    existing = (
        await session.execute(
            select(UserProject).where(UserProject.user_id == user_id, UserProject.name == name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    session.add(
        UserProject(
            user_id=user_id,
            name=name,
            evidence=str(extraction.value.get("evidence") or ""),
            status=ProjectStatus.COMPLETED,
        )
    )
    return True


async def confirm_extractions(
    session: AsyncSession,
    *,
    user_id: UUID,
    resume_id: UUID,
    decisions: Mapping[UUID, Decision],
    now: datetime,
) -> ConfirmationResult:
    """Apply a person's decisions. The only path to a confirmed fact.

    Every id must belong to this user *and* this resume; anything else raises
    before a single row is written.
    """
    rows = list(
        (
            await session.execute(
                select(ResumeExtraction).where(
                    ResumeExtraction.user_id == user_id,
                    ResumeExtraction.resume_id == resume_id,
                    ResumeExtraction.id.in_(list(decisions)),
                )
            )
        )
        .scalars()
        .all()
    )
    found = {row.id: row for row in rows}
    missing = set(decisions) - set(found)
    if missing:
        raise ExtractionNotFoundError(
            f"not this user's proposals: {sorted(str(m) for m in missing)}"
        )

    user = await _load_user(session, user_id)
    confirmed = rejected = skipped = skills_added = projects_added = 0
    fields_set: list[str] = []

    for extraction_id, decision in decisions.items():
        extraction = found[extraction_id]
        if extraction.status is not ExtractionStatus.PENDING:
            skipped += 1
            continue

        if decision == "reject":
            extraction.status = ExtractionStatus.REJECTED
            extraction.decided_at = now
            rejected += 1
            continue

        match extraction.kind:
            case ExtractionKind.SKILL:
                if await _promote_skill(session, user_id=user_id, extraction=extraction):
                    skills_added += 1
            case ExtractionKind.PROJECT:
                if await _promote_project(session, user_id=user_id, extraction=extraction):
                    projects_added += 1
            case ExtractionKind.GRADUATION:
                user.graduation_year = int(str(extraction.value["year"]))
                month = extraction.value.get("month")
                user.graduation_month = int(str(month)) if month is not None else None
                fields_set.extend(("graduation_year", "graduation_month"))
            case ExtractionKind.DEGREE:
                user.degree = str(extraction.value["degree"])
                fields_set.append("degree")
            case ExtractionKind.SCHOOL:
                user.school = str(extraction.value["school"])
                fields_set.append("school")

        extraction.status = ExtractionStatus.CONFIRMED
        extraction.decided_at = now
        confirmed += 1

    await session.flush()
    return ConfirmationResult(
        confirmed=confirmed,
        rejected=rejected,
        skipped=skipped,
        skills_added=skills_added,
        projects_added=projects_added,
        profile_fields_set=tuple(fields_set),
    )


# ---------------------------------------------------------------------------
# The manual path — §6.2's fallback, and what an empty extraction hands over to
# ---------------------------------------------------------------------------


async def update_profile(session: AsyncSession, *, user_id: UUID, patch: ProfilePatch) -> User:
    """Assign only what was provided. Every assignment is written out by name.

    Deliberately not ``setattr`` in a loop: `tests/test_nothing_infers.py`
    greps for writes to these columns, and a dynamic write is invisible to it.
    A guard that a clever refactor can slip past is not a guard.
    """
    user = await _load_user(session, user_id)
    given = patch.provided

    if "display_name" in given:
        user.display_name = patch.display_name
    if "graduation_year" in given:
        user.graduation_year = patch.graduation_year
    if "graduation_month" in given:
        user.graduation_month = patch.graduation_month
    if "degree" in given:
        user.degree = patch.degree
    if "school" in given:
        user.school = patch.school
    if "work_authorization" in given:
        user.work_authorization = patch.work_authorization
    if "home_location_text" in given:
        user.home_location_text = patch.home_location_text
    if "remote_preference" in given:
        user.remote_preference = patch.remote_preference
    if "minimum_salary" in given:
        user.minimum_salary = patch.minimum_salary
    if "preferred_roles" in given:
        user.preferred_roles = list(patch.preferred_roles)
    if "preferred_locations" in given:
        user.preferred_locations = list(patch.preferred_locations)

    if user.graduation_month is not None and user.graduation_year is None:
        # The database refuses this too. Raising here makes it a 422 with a
        # sentence rather than a 500 with a constraint name.
        raise InvalidProfileError("a graduation month needs a year")

    await session.flush()
    return user


async def add_skill(
    session: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    proficiency_level: ProficiencyLevel = ProficiencyLevel.UNSPECIFIED,
    source_type: SkillSourceType = SkillSourceType.MANUAL,
) -> UserSkill:
    """Add a skill by hand. No resume required — §6.2's manual source, and what
    "nothing could be proven from this file" hands over to."""
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidProfileError("a skill needs a name")
    normalized = normalize_skill_name(cleaned)
    existing = (
        await session.execute(
            select(UserSkill).where(
                UserSkill.user_id == user_id, UserSkill.normalized_name == normalized
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.proficiency_level = proficiency_level
        await session.flush()
        return existing

    skill = UserSkill(
        user_id=user_id,
        name=cleaned,
        normalized_name=normalized,
        proficiency_level=proficiency_level,
        source_type=source_type,
        source_reference="manual",
    )
    session.add(skill)
    await session.flush()
    return skill


async def remove_skill(session: AsyncSession, *, user_id: UUID, skill_id: UUID) -> bool:
    skill = (
        await session.execute(
            select(UserSkill).where(UserSkill.id == skill_id, UserSkill.user_id == user_id)
        )
    ).scalar_one_or_none()
    if skill is None:
        return False
    await session.delete(skill)
    await session.flush()
    return True


async def add_project(
    session: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    summary: str | None = None,
    evidence: str | None = None,
    repository_url: str | None = None,
    demo_url: str | None = None,
    technologies: Sequence[str] = (),
    status: ProjectStatus = ProjectStatus.COMPLETED,
) -> UserProject:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidProfileError("a project needs a name")
    existing = (
        await session.execute(
            select(UserProject).where(UserProject.user_id == user_id, UserProject.name == cleaned)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.summary = summary
        existing.evidence = evidence
        existing.status = status
        await session.flush()
        return existing

    project = UserProject(
        user_id=user_id,
        name=cleaned,
        summary=summary,
        evidence=evidence,
        repository_url=repository_url,
        demo_url=demo_url,
        technologies=list(technologies),
        status=status,
    )
    session.add(project)
    await session.flush()
    return project


async def remove_project(session: AsyncSession, *, user_id: UUID, project_id: UUID) -> bool:
    project = (
        await session.execute(
            select(UserProject).where(UserProject.id == project_id, UserProject.user_id == user_id)
        )
    ).scalar_one_or_none()
    if project is None:
        return False
    await session.delete(project)
    await session.flush()
    return True


async def update_resume(
    session: AsyncSession,
    *,
    resume: Resume,
    name: str | None = None,
    variant_type: ResumeVariant | None = None,
    is_default: bool | None = None,
) -> Resume:
    """Rename, retype, or make default. **Never re-reads the text.**

    Re-proposing against an edited row would strand every decision already made
    against it, and "your confirmed skills quietly reverted to pending" is not a
    behaviour worth having — the same reason ``propose_from_resume`` is
    once-only.
    """
    if name is not None:
        cleaned = " ".join(name.split())
        if not cleaned:
            raise InvalidProfileError("a resume needs a name")
        resume.name = cleaned
    if variant_type is not None:
        resume.variant_type = variant_type
    if is_default is True:
        # One default per user. Demoting the others here rather than by trigger
        # keeps the rule readable, and there is exactly one writer of it.
        others = (
            (
                await session.execute(
                    select(Resume).where(
                        Resume.user_id == resume.user_id,
                        Resume.id != resume.id,
                        Resume.is_default.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        for other in others:
            other.is_default = False
        resume.is_default = True
    elif is_default is False:
        resume.is_default = False

    await session.flush()
    return resume


async def delete_resume(session: AsyncSession, *, user_id: UUID, resume_id: UUID) -> bool:
    """Remove a resume and its proposals. **Confirmed facts are untouched.**

    A person who deletes the file keeps what they told us was true about them.
    The cascade reaches `resume_extractions` and stops there, and
    `applications.selected_resume_id` is SET NULL rather than cascading.
    """
    resume = (
        await session.execute(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        )
    ).scalar_one_or_none()
    if resume is None:
        return False
    await session.delete(resume)
    await session.flush()
    return True
