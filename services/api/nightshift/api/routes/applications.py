"""Application tracking routes.

Routes validate and delegate (CLAUDE.md §3): every state change goes through
`nightshift.domain.applications`, which is where the rules are and where the
events are written. Nothing here mutates a model directly.

Invariant I5 governs this whole module. There is no route that submits an
application to an employer, and `tests/test_nothing_applies.py` asserts the
system has no outbound write path at all.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.api.deps import CurrentUserId
from nightshift.api.routes.jobs import to_summary
from nightshift.api.schemas import (
    ApplicationDetailOut,
    ApplicationEventOut,
    ApplicationListOut,
    ApplicationOut,
    ApplicationPatchIn,
    ApplicationStageCounts,
    DeferredApplicationFieldOut,
    InterviewIn,
    NoteIn,
    SaveJobIn,
    StageChangeIn,
)
from nightshift.db.base import ApplicationStage, EventActor
from nightshift.db.models import Application, ApplicationEvent, Job, Resume
from nightshift.db.session import get_db_session
from nightshift.db.types import utcnow
from nightshift.domain.applications import (
    ApplicationArchivedError,
    SameStageError,
    add_note,
    change_stage,
    save_job,
    schedule_interview,
    set_archived,
    update_details,
)

router = APIRouter(prefix="/applications", tags=["applications"])

MAX_LIMIT = 200

#: I7: what tracking cannot record yet, named on the page rather than hidden.
DEFERRED_FIELDS: tuple[DeferredApplicationFieldOut, ...] = (
    DeferredApplicationFieldOut(
        name="Contacts",
        blocked_on="unscheduled",
        reason="a contact is a person and needs its own table; the M2 design "
        "does not place it in this slice",
    ),
    DeferredApplicationFieldOut(
        name="Match score and eligibility",
        blocked_on="M3",
        reason="a score with no breakdown behind it is a bug, and an invented "
        "one is worse (invariant I4)",
    ),
)


async def _load(session: AsyncSession, application_id: UUID, user_id: UUID) -> Application:
    """One loader, so no route can forget the user filter (A3)."""
    application = (
        (
            await session.execute(
                select(Application)
                .where(Application.id == application_id, Application.user_id == user_id)
                .options(
                    selectinload(Application.job).selectinload(Job.company),
                    selectinload(Application.job).selectinload(Job.locations),
                    selectinload(Application.events),
                )
            )
        )
        .scalars()
        .first()
    )
    if application is None:
        # 404 rather than 403: whether an application exists is itself another
        # user's business.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="application not found")
    return application


def _to_out(application: Application) -> ApplicationOut:
    return ApplicationOut(
        id=application.id,
        job=to_summary(application.job),
        current_stage=application.current_stage,
        priority=application.priority,
        applied_at=application.applied_at,
        next_action_at=application.next_action_at,
        application_url=application.application_url,
        source_of_application=application.source_of_application,
        selected_resume_id=application.selected_resume_id,
        archived_at=application.archived_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


async def _to_detail(session: AsyncSession, application: Application) -> ApplicationDetailOut:
    events = (
        (
            await session.execute(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == application.id)
                # created_at, not occurred_at: this is the history of what was
                # recorded, and an interview scheduled for next month must not
                # sort ahead of the note written about it today.
                .order_by(ApplicationEvent.created_at, ApplicationEvent.id)
            )
        )
        .scalars()
        .all()
    )
    return ApplicationDetailOut(
        **_to_out(application).model_dump(),
        events=[ApplicationEventOut.model_validate(event) for event in events],
    )


@router.post("", response_model=ApplicationOut)
async def save(
    payload: SaveJobIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
    response: Response,
) -> ApplicationOut:
    """Save a job. 201 when it created the row, 200 when it already existed.

    Idempotent on purpose: a second click is a normal thing for a person to do.
    The status code is the only place the two outcomes differ, which is what
    lets `make verify` be run twice without its assertions changing.
    """
    job = (
        (
            await session.execute(
                select(Job)
                .where(Job.id == payload.job_id)
                .options(selectinload(Job.company), selectinload(Job.locations))
            )
        )
        .scalars()
        .first()
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    application, created = await save_job(session, user_id=user_id, job_id=job.id, now=utcnow())
    await session.commit()
    application.job = job
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return _to_out(application)


@router.get("", response_model=ApplicationListOut)
async def list_applications(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
    stage: Annotated[ApplicationStage | None, Query()] = None,
    archived: Annotated[bool, Query(description="Include archived applications")] = False,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ApplicationListOut:
    """The pipeline, newest first, archived excluded unless asked for."""
    filters = [Application.user_id == user_id]
    if not archived:
        filters.append(Application.archived_at.is_(None))
    if stage is not None:
        filters.append(Application.current_stage == stage)

    total = (
        await session.execute(select(func.count()).select_from(Application).where(*filters))
    ).scalar_one()

    # Counted over the same archived scope as the list, so the tabs and the
    # rows agree. Counting the whole table here would show a stage tab with a
    # number and an empty list behind it.
    count_filters = [Application.user_id == user_id]
    if not archived:
        count_filters.append(Application.archived_at.is_(None))
    counted = (
        await session.execute(
            select(Application.current_stage, func.count())
            .where(*count_filters)
            .group_by(Application.current_stage)
        )
    ).all()

    archived_count = (
        await session.execute(
            select(func.count())
            .select_from(Application)
            .where(Application.user_id == user_id, Application.archived_at.is_not(None))
        )
    ).scalar_one()

    rows = (
        (
            await session.execute(
                select(Application)
                .where(*filters)
                .options(
                    selectinload(Application.job).selectinload(Job.company),
                    selectinload(Application.job).selectinload(Job.locations),
                )
                # id breaks ties: several applications share a created_at when
                # somebody saves a page of results in one sitting.
                .order_by(Application.created_at.desc(), Application.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return ApplicationListOut(
        items=[_to_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        stage_counts=ApplicationStageCounts(
            **{stage_value.value: count for stage_value, count in counted}
        ),
        archived_count=archived_count,
        deferred_fields=list(DEFERRED_FIELDS),
    )


@router.get("/{application_id}", response_model=ApplicationDetailOut)
async def get_application(
    application_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ApplicationDetailOut:
    return await _to_detail(session, await _load(session, application_id, user_id))


@router.patch("/{application_id}/stage", response_model=ApplicationDetailOut)
async def set_stage(
    application_id: UUID,
    payload: StageChangeIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ApplicationDetailOut:
    """Move a stage. Never refused for being the wrong move — see §3.

    409 for a stage the application is already at, and for an archived one.
    Neither is the machine disagreeing about the user's job search; both are
    requests that would record something untrue.
    """
    application = await _load(session, application_id, user_id)
    try:
        await change_stage(
            session,
            application=application,
            to_stage=payload.to_stage,
            actor=EventActor.USER,
            now=utcnow(),
            note=payload.note,
            applied_at=payload.applied_at,
            application_url=payload.application_url,
        )
    except SameStageError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ApplicationArchivedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    return await _to_detail(session, await _load(session, application_id, user_id))


@router.post(
    "/{application_id}/notes",
    response_model=ApplicationEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_note(
    application_id: UUID,
    payload: NoteIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ApplicationEventOut:
    application = await _load(session, application_id, user_id)
    event = await add_note(
        session,
        application=application,
        body=payload.body,
        now=utcnow(),
        occurred_at=payload.occurred_at,
    )
    await session.commit()
    return ApplicationEventOut.model_validate(event)


@router.post(
    "/{application_id}/interviews",
    response_model=ApplicationEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_interview(
    application_id: UUID,
    payload: InterviewIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ApplicationEventOut:
    """Record an interview time. Deliberately does not move the stage (I5)."""
    application = await _load(session, application_id, user_id)
    event = await schedule_interview(
        session,
        application=application,
        scheduled_for=payload.scheduled_for,
        now=utcnow(),
        body=payload.body,
    )
    await session.commit()
    return ApplicationEventOut.model_validate(event)


@router.patch("/{application_id}", response_model=ApplicationDetailOut)
async def patch_application(
    application_id: UUID,
    payload: ApplicationPatchIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ApplicationDetailOut:
    application = await _load(session, application_id, user_id)
    # Only the keys the client actually sent. `exclude_unset` is what makes an
    # explicit null mean "clear" and an absent key mean "leave alone".
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True)

    # A3: the foreign key would happily accept a stranger's resume id, and every
    # later read of this application would then leak it. Checked here rather
    # than trusted, and 404 rather than 403 for the same reason `_load` is.
    selected = changes.get("selected_resume_id")
    if selected is not None:
        owned = (
            await session.execute(
                select(Resume.id).where(Resume.id == selected, Resume.user_id == user_id)
            )
        ).first()
        if owned is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resume not found")

    try:
        await update_details(session, application=application, changes=changes, now=utcnow())
    except ApplicationArchivedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    return await _to_detail(session, await _load(session, application_id, user_id))


@router.post("/{application_id}/archive", response_model=ApplicationDetailOut)
async def archive(
    application_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ApplicationDetailOut:
    """Archive. There is no delete, and that is a property of the schema.

    `application_events` is append-only by trigger, the events cascade from
    this row, and a cascading delete fires that trigger. So an application
    cannot be deleted even by a direct SQL statement.
    """
    application = await _load(session, application_id, user_id)
    await set_archived(session, application=application, archived=True, now=utcnow())
    await session.commit()
    return await _to_detail(session, await _load(session, application_id, user_id))


@router.post("/{application_id}/restore", response_model=ApplicationDetailOut)
async def restore(
    application_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ApplicationDetailOut:
    application = await _load(session, application_id, user_id)
    await set_archived(session, application=application, archived=False, now=utcnow())
    await session.commit()
    return await _to_detail(session, await _load(session, application_id, user_id))
