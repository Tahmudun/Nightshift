"""Resume intake and the confirmation step.

Two intake shapes, two routes. Sniffing the content type in one handler would
put the decision "is this a paste or a file" inside the code path that must not
be wrong, so a paste and an upload are separate doors into the same three calls:
read the text, create the resume, propose from it.

**Proposing is not confirming.** Everything these routes write lands in
`resume_extractions`, which is the pending side of invariant I2. The only route
here that can change a fact about a person is `POST /resumes/{id}/confirm`, and
all it does is hand a person's decisions to `domain/profile.py`.

The uploaded bytes are read in memory and never written anywhere (§13). What
survives is the filename, a hash of the extracted text, and the text itself.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import CurrentUserId
from nightshift.api.schemas import (
    ConfirmationOut,
    ConfirmIn,
    ExtractionCounts,
    ExtractionOut,
    ResumeDetailOut,
    ResumeListOut,
    ResumeOut,
    ResumePasteIn,
    ResumePatchIn,
)
from nightshift.db.base import ResumeSourceKind
from nightshift.db.models import Resume, ResumeExtraction
from nightshift.db.session import get_db_session
from nightshift.db.types import utcnow
from nightshift.domain.profile import (
    ExtractionNotFoundError,
    InvalidProfileError,
    confirm_extractions,
    create_resume,
    delete_resume,
    propose_from_resume,
    update_resume,
)
from nightshift.domain.resume_text import (
    MAX_UPLOAD_BYTES,
    ResumeTextError,
    UnsupportedResumeFormatError,
    format_for_filename,
    normalize_text,
    read_resume_bytes,
)

router = APIRouter(prefix="/resumes", tags=["resumes"])


async def _load(session: AsyncSession, resume_id: UUID, user_id: UUID) -> Resume:
    """One loader, so no route can forget the user filter (A3)."""
    resume = (
        (
            await session.execute(
                select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
            )
        )
        .scalars()
        .first()
    )
    if resume is None:
        # 404 rather than 403: whether a resume exists is another user's
        # business, and this is the most personal row the project holds.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resume not found")
    return resume


async def _counts(session: AsyncSession, resume_id: UUID) -> ExtractionCounts:
    rows = (
        await session.execute(
            select(ResumeExtraction.status, func.count())
            .where(ResumeExtraction.resume_id == resume_id)
            .group_by(ResumeExtraction.status)
        )
    ).all()
    return ExtractionCounts(**{value.value: count for value, count in rows})


def _to_out(resume: Resume, counts: ExtractionCounts) -> ResumeOut:
    return ResumeOut(
        id=resume.id,
        name=resume.name,
        variant_type=resume.variant_type,
        source_kind=resume.source_kind,
        original_filename=resume.original_filename,
        content_hash=resume.content_hash,
        is_default=resume.is_default,
        extraction_counts=counts,
        created_at=resume.created_at,
        updated_at=resume.updated_at,
    )


async def _to_detail(session: AsyncSession, resume: Resume) -> ResumeDetailOut:
    extractions = (
        (
            await session.execute(
                select(ResumeExtraction)
                .where(ResumeExtraction.resume_id == resume.id)
                # Reading order, so the confirmation screen walks the page the
                # way a person reads it rather than the way Postgres returns it.
                .order_by(ResumeExtraction.char_start, ResumeExtraction.char_end)
            )
        )
        .scalars()
        .all()
    )
    return ResumeDetailOut(
        **_to_out(resume, await _counts(session, resume.id)).model_dump(),
        parsed_text=resume.parsed_text,
        extractions=[ExtractionOut.model_validate(row) for row in extractions],
        # I7: "this file proved nothing" is a result worth stating. The screen
        # says so and offers the manual form; it never fills a field to look
        # like it worked.
        nothing_proven=not extractions,
    )


async def _intake(
    session: AsyncSession,
    *,
    user_id: UUID,
    name: str,
    text: str,
    source_kind: ResumeSourceKind,
    original_filename: str | None,
    response: Response,
) -> ResumeDetailOut:
    """The one path both intake shapes end in, so there is one thing to be wrong.

    201 when this text was new, 200 when the same text is already on file.
    Re-uploading a resume is a normal thing for a person to do, and it must not
    strand the decisions they already made against it.
    """
    resume, created = await create_resume(
        session,
        user_id=user_id,
        name=name,
        source_kind=source_kind,
        original_filename=original_filename,
        text=text,
    )
    await propose_from_resume(session, resume=resume)
    await session.commit()
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return await _to_detail(session, await _load(session, resume.id, user_id))


@router.post("/paste", response_model=ResumeDetailOut, status_code=status.HTTP_201_CREATED)
async def paste_resume(
    payload: ResumePasteIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
    response: Response,
) -> ResumeDetailOut:
    """Paste the text. The route the upload control offers as the way around
    any format we cannot read."""
    text = normalize_text(payload.text)
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That is empty. Paste the text of your resume.",
        )
    return await _intake(
        session,
        user_id=user_id,
        name=payload.name,
        text=text,
        source_kind=ResumeSourceKind.PASTE,
        original_filename=None,
        response=response,
    )


@router.post("/upload", response_model=ResumeDetailOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
    response: Response,
    file: Annotated[UploadFile, File()],
    name: Annotated[str | None, Form()] = None,
) -> ResumeDetailOut:
    """A PDF or a `.txt`. Anything else is refused by name (415).

    Reading one byte past the limit is deliberate: it is how the size check
    below can be decisive without pulling an arbitrarily large body into memory
    first.
    """
    filename = file.filename or ""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    try:
        source_kind = ResumeSourceKind(format_for_filename(filename))
        text = read_resume_bytes(data=data, filename=filename)
    except UnsupportedResumeFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=exc.user_message
        ) from exc
    except ResumeTextError as exc:
        # 422, not 500: the file is the problem and the message says how to
        # get past it. `command-center.md` §6.2 — failure is stated, never filled.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.user_message
        ) from exc

    return await _intake(
        session,
        user_id=user_id,
        name=name or filename or "Uploaded resume",
        text=text,
        source_kind=source_kind,
        original_filename=filename or None,
        response=response,
    )


@router.get("", response_model=ResumeListOut)
async def list_resumes(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ResumeListOut:
    resumes = (
        (
            await session.execute(
                select(Resume)
                .where(Resume.user_id == user_id)
                # id breaks ties: a paste and an upload in the same second
                # otherwise order differently on each read.
                .order_by(Resume.created_at.desc(), Resume.id)
            )
        )
        .scalars()
        .all()
    )
    counted = (
        await session.execute(
            select(ResumeExtraction.resume_id, ResumeExtraction.status, func.count())
            .where(ResumeExtraction.user_id == user_id)
            .group_by(ResumeExtraction.resume_id, ResumeExtraction.status)
        )
    ).all()
    per_resume: dict[UUID, dict[str, int]] = {}
    for resume_id, extraction_status, count in counted:
        per_resume.setdefault(resume_id, {})[extraction_status.value] = count

    return ResumeListOut(
        items=[
            _to_out(resume, ExtractionCounts(**per_resume.get(resume.id, {}))) for resume in resumes
        ],
        total=len(resumes),
    )


@router.get("/{resume_id}", response_model=ResumeDetailOut)
async def get_resume(
    resume_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ResumeDetailOut:
    return await _to_detail(session, await _load(session, resume_id, user_id))


@router.patch("/{resume_id}", response_model=ResumeDetailOut)
async def patch_resume(
    resume_id: UUID,
    payload: ResumePatchIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ResumeDetailOut:
    resume = await _load(session, resume_id, user_id)
    try:
        await update_resume(
            session,
            resume=resume,
            name=payload.name,
            variant_type=payload.variant_type,
            is_default=payload.is_default,
        )
    except InvalidProfileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await session.commit()
    return await _to_detail(session, await _load(session, resume_id, user_id))


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_resume(
    resume_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> Response:
    """Delete the resume and its proposals. **Confirmed facts survive.**

    Stated here because a reader will otherwise assume the opposite: a skill a
    person confirmed belongs to the person, not to the file it arrived in. Any
    application pointing at this resume keeps its row and loses only the
    pointer (`ondelete="SET NULL"`).
    """
    if not await delete_resume(session, user_id=user_id, resume_id=resume_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resume not found")
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{resume_id}/confirm", response_model=ConfirmationOut)
async def confirm(
    resume_id: UUID,
    payload: ConfirmIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> ConfirmationOut:
    """The click that makes a proposal a fact. The only one in the product.

    A duplicate id in the body would silently drop a decision, so it is refused
    rather than deduplicated — two different answers for one proposal is a
    confused form, not a request to guess which one was meant.
    """
    await _load(session, resume_id, user_id)
    decisions = {row.extraction_id: row.decision for row in payload.decisions}
    if len(decisions) != len(payload.decisions):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="one decision per proposal; the same id was sent twice",
        )

    try:
        result = await confirm_extractions(
            session,
            user_id=user_id,
            resume_id=resume_id,
            decisions=decisions,
            now=utcnow(),
        )
    except ExtractionNotFoundError as exc:
        # Nothing partial. The domain raises before writing a row, so a request
        # naming one unknown proposal confirms none of the known ones either.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return ConfirmationOut(
        confirmed=result.confirmed,
        rejected=result.rejected,
        skipped=result.skipped,
        skills_added=result.skills_added,
        projects_added=result.projects_added,
        profile_fields_set=list(result.profile_fields_set),
    )
