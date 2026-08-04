"""Profile routes — the confirmed side of the I2 boundary.

Routes validate and delegate (CLAUDE.md §3): every write here goes through
`nightshift.domain.profile`, which is the only module allowed to touch
`users`, `user_skills` or `user_projects`. `tests/test_nothing_infers.py`
asserts that at the source level, so a convenient shortcut in this file would
turn a test red rather than quietly cross the boundary.

Nothing in this module infers anything. A field is null until a person fills
it, and `DEFERRED_PROFILE_FIELDS` names the ones that will stay null on purpose.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.api.deps import CurrentUserId
from nightshift.api.schemas import (
    DeferredProfileFieldOut,
    ProfileOut,
    ProfilePatchIn,
    ProjectIn,
    SkillIn,
    UserProjectOut,
    UserSkillOut,
)
from nightshift.db.models import User
from nightshift.db.session import get_db_session
from nightshift.domain.profile import (
    InvalidProfileError,
    ProfilePatch,
    UnknownProfileFieldError,
    UserNotFoundError,
    add_project,
    add_skill,
    remove_project,
    remove_skill,
    update_profile,
)

router = APIRouter(prefix="/profile", tags=["profile"])

#: I7: what this profile will not learn from a file, named on the page.
DEFERRED_PROFILE_FIELDS: tuple[DeferredProfileFieldOut, ...] = (
    DeferredProfileFieldOut(
        name="Skill proficiency from a resume",
        blocked_on="never",
        reason="a resume cannot show how well someone knows a thing, so the "
        "level is yours to set and nothing infers it (I2)",
    ),
    DeferredProfileFieldOut(
        name="Work authorization from a resume",
        blocked_on="never",
        reason="a claim about legal status is confirmed in a form, never read "
        "off a page — the extractor has no rule that could produce one",
    ),
    DeferredProfileFieldOut(
        name="Skill taxonomy and aliases",
        blocked_on="M3",
        reason="M2c matches a starter vocabulary in data/skills.yaml; the "
        "taxonomy proper, with its evidence graph, is M3's",
    ),
    DeferredProfileFieldOut(
        name=".docx upload",
        blocked_on="unscheduled",
        reason="one parser at a time in the slice with the most invariant "
        "risk; paste the text instead",
    ),
)


async def _load(session: AsyncSession, user_id: UUID) -> User:
    """One loader, so no route can forget the user filter (A3)."""
    user = (
        (
            await session.execute(
                select(User)
                .where(User.id == user_id)
                .options(selectinload(User.skills), selectinload(User.projects))
            )
        )
        .scalars()
        .first()
    )
    if user is None:
        # A3: the id comes from a dependency, so this is a misconfigured
        # deployment rather than a bad request. Said plainly instead of 500ing.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no profile for the current user",
        )
    return user


def _to_out(user: User) -> ProfileOut:
    return ProfileOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        timezone=user.timezone,
        graduation_year=user.graduation_year,
        graduation_month=user.graduation_month,
        degree=user.degree,
        school=user.school,
        work_authorization=user.work_authorization,
        home_location_text=user.home_location_text,
        remote_preference=user.remote_preference,
        minimum_salary=user.minimum_salary,
        preferred_roles=list(user.preferred_roles),
        preferred_locations=list(user.preferred_locations),
        skills=[
            UserSkillOut.model_validate(skill)
            for skill in sorted(user.skills, key=lambda row: row.normalized_name)
        ],
        projects=[
            UserProjectOut.model_validate(project)
            for project in sorted(user.projects, key=lambda row: row.name)
        ],
        deferred_fields=list(DEFERRED_PROFILE_FIELDS),
    )


@router.get("", response_model=ProfileOut)
async def get_profile(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ProfileOut:
    return _to_out(await _load(session, user_id))


@router.patch("", response_model=ProfileOut)
async def patch_profile(
    payload: ProfilePatchIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ProfileOut:
    """The manual path. Every field here was typed by the person it describes.

    `exclude_unset` is what makes an explicit null mean "clear" and an absent
    key mean "leave alone" — without it, clearing a graduation year is
    impossible and the bug looks like a UI problem.
    """
    try:
        patch = ProfilePatch.from_mapping(payload.model_dump(exclude_unset=True))
        await update_profile(session, user_id=user_id, patch=patch)
    except (InvalidProfileError, UnknownProfileFieldError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no profile for the current user"
        ) from exc
    await session.commit()
    return _to_out(await _load(session, user_id))


@router.post("/skills", response_model=UserSkillOut, status_code=status.HTTP_201_CREATED)
async def post_skill(
    payload: SkillIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> UserSkillOut:
    try:
        skill = await add_skill(
            session,
            user_id=user_id,
            name=payload.name,
            proficiency_level=payload.proficiency_level,
        )
    except InvalidProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await session.commit()
    return UserSkillOut.model_validate(skill)


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> Response:
    if not await remove_skill(session, user_id=user_id, skill_id=skill_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="skill not found")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects", response_model=UserProjectOut, status_code=status.HTTP_201_CREATED)
async def post_project(
    payload: ProjectIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> UserProjectOut:
    try:
        project = await add_project(
            session,
            user_id=user_id,
            name=payload.name,
            summary=payload.summary,
            evidence=payload.evidence,
            repository_url=payload.repository_url,
            demo_url=payload.demo_url,
            technologies=payload.technologies,
            status=payload.status,
        )
    except InvalidProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await session.commit()
    return UserProjectOut.model_validate(project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> Response:
    if not await remove_project(session, user_id=user_id, project_id=project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
