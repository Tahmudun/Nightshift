"""Manual capture routes: paste, review, confirm.

Routes validate and delegate (CLAUDE.md §3). Every rule worth arguing about is
in `nightshift.domain.capture`; this module turns HTTP into those calls and
back.

Three of them, and the shape is the point:

    POST /capture              -> stores the paste, returns a *proposal*
    POST /capture/{id}/confirm -> the person's own values become a job
    POST /capture/{id}/discard -> nothing becomes anything

There is deliberately no ``POST /capture?confirm=true``. A one-shot endpoint
that parses and commits in the same request is the whole of this milestone's
risk in one convenience: it makes the parser's reading indistinguishable from a
person's decision, at exactly the point where the difference decides whether a
job lands on the right building. The two-step is the feature.

Every route is scoped to ``CurrentUserId``. A capture is somebody's own record
of their own action, and one person may not confirm, read, or discard another
person's paste — asserted in `tests/test_capture_routes.py` rather than left to
this file's good intentions.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import CurrentUserId
from nightshift.api.schemas import (
    AssistantQuoteOut,
    CaptureConfirmIn,
    CaptureIn,
    CaptureListOut,
    CaptureOut,
    CaptureProposalOut,
    CorpusCheckOut,
    CorpusMatchOut,
)
from nightshift.db.base import CaptureStatus
from nightshift.db.models import CapturedPosting
from nightshift.db.session import get_db_session
from nightshift.db.types import utcnow
from nightshift.domain.capture import (
    CaptureAlreadyDecidedError,
    capture_origin,
    capture_paste,
    confirm_capture,
    discard_capture,
    employment_type_for_title,
)
from nightshift.domain.capture_assist import AssistantProposal
from nightshift.domain.capture_matches import CorpusCheck, check_corpus

router = APIRouter(prefix="/capture", tags=["capture"])

MAX_LIMIT = 200


def _corpus_out(check: CorpusCheck | None) -> CorpusCheckOut | None:
    if check is None:
        return None
    return CorpusCheckOut(
        checked=check.checked,
        why_not=check.why_not,
        matches=[
            CorpusMatchOut(
                job_id=match.job_id,
                title=match.title,
                company_name=match.company_name,
                status=match.status,
                reason=match.reason,
            )
            for match in check.matches
        ],
    )


def _to_out(
    capture: CapturedPosting,
    *,
    already_existed: bool = False,
    corpus_check: CorpusCheck | None = None,
) -> CaptureOut:
    return CaptureOut(
        already_existed=already_existed,
        corpus_check=_corpus_out(corpus_check),
        id=capture.id,
        status=capture.status,
        source_url=capture.source_url,
        origin=capture_origin(capture.source_url),
        raw_text=capture.raw_text,
        proposed=CaptureProposalOut(
            title=capture.proposed_title,
            company_name=capture.proposed_company_name,
            location_text=capture.proposed_location_text,
            # Derived rather than stored — a column could disagree with the
            # title sitting beside it in the form. This read `None` in the
            # first draft, which left the internship detection working,
            # unit-tested, and invisible to every person who used the form.
            employment_type=employment_type_for_title(capture.proposed_title),
        ),
        parser_version=capture.parser_version,
        # ``None`` rather than an object of nulls when the assistant said
        # nothing: a client can then distinguish "no assistant was involved"
        # from "the assistant quoted nothing that survived the rule", and only
        # the second is worth telling the reader about.
        assistant=_assistant_out(capture),
        assistant_rejected_fields=list(capture.assistant_rejected_fields),
        job_id=capture.job_id,
        created_at=capture.created_at,
        decided_at=capture.decided_at,
    )


def _assistant_out(capture: CapturedPosting) -> AssistantQuoteOut | None:
    quoted = (
        capture.assistant_title,
        capture.assistant_company_name,
        capture.assistant_location_text,
    )
    if not any(quoted) and not capture.assistant_rejected_fields:
        return None
    return AssistantQuoteOut(
        title=capture.assistant_title,
        company_name=capture.assistant_company_name,
        location_text=capture.assistant_location_text,
    )


async def _own_capture(
    session: AsyncSession, *, capture_id: UUID, user_id: UUID
) -> CapturedPosting:
    """Fetch a capture, or 404.

    Scoped by ``user_id`` in the query rather than fetched-then-checked, so a
    capture belonging to somebody else is indistinguishable from one that does
    not exist. A 403 here would confirm the id is real, which is a small leak
    and an entirely avoidable one.
    """
    capture = (
        await session.execute(
            select(CapturedPosting).where(
                CapturedPosting.id == capture_id,
                CapturedPosting.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if capture is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="capture not found")
    return capture


async def _corpus_for(session: AsyncSession, capture: CapturedPosting) -> CorpusCheck | None:
    """What the corpus already holds that this capture appears to be.

    Searched with the assistant's quote first and the parser's reading second.
    This is the one place an assistant value outranks a parser value, and it is
    safe here only because it steers a *search* — a wrong company finds
    nothing, and finding nothing is what an unassisted capture would have done
    anyway. ADR 0039 §4.

    Run on every response that shows a **pending** capture to a person, and on
    none that show a decided one. Not because it is expensive, but because it
    is a fact about the corpus *now*: it is worth answering while a decision is
    open and it is not a property of a row somebody already decided. That is
    also why nothing caches it.
    """
    if capture.status is not CaptureStatus.PENDING:
        return None
    return await check_corpus(
        session,
        title=capture.assistant_title or capture.proposed_title,
        company_name=capture.assistant_company_name or capture.proposed_company_name,
        source_url=capture.source_url,
    )


@router.post("", response_model=CaptureOut, status_code=status.HTTP_201_CREATED)
async def capture_posting(
    payload: CaptureIn,
    user_id: CurrentUserId,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    response: Response,
) -> CaptureOut:
    """Store a paste and read what can be read from it. Creates no job.

    **201 for a new proposal, 200 for one that already existed.** The status
    code is set here rather than declared on the decorator because the route
    does not know which it is until the domain has looked; the decorator's
    value is the default and the documented one.
    """
    outcome = await capture_paste(
        session,
        user_id=user_id,
        raw_text=payload.raw_text,
        source_url=payload.source_url,
        assistant=(
            AssistantProposal(
                title=payload.assistant.title,
                company_name=payload.assistant.company_name,
                location_text=payload.assistant.location_text,
            )
            if payload.assistant is not None
            else None
        ),
    )
    await session.commit()
    if not outcome.created:
        response.status_code = status.HTTP_200_OK

    stored = outcome.capture
    return _to_out(
        stored,
        already_existed=not outcome.created,
        corpus_check=await _corpus_for(session, stored),
    )


@router.get("", response_model=CaptureListOut)
async def list_captures(
    user_id: CurrentUserId,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    capture_status: Annotated[CaptureStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> CaptureListOut:
    query = select(CapturedPosting).where(CapturedPosting.user_id == user_id)
    count_query = (
        select(func.count()).select_from(CapturedPosting).where(CapturedPosting.user_id == user_id)
    )
    if capture_status is not None:
        query = query.where(CapturedPosting.status == capture_status)
        count_query = count_query.where(CapturedPosting.status == capture_status)

    rows = (
        (await session.execute(query.order_by(CapturedPosting.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    total = (await session.execute(count_query)).scalar_one()
    # No corpus check on a list row, and the omission is deliberate: it is one
    # query per row, and a queue is a list of things to open rather than a
    # place to decide. ``GET /capture/{id}`` runs it for the row that gets
    # opened, which is where the duplicate warning has to be read anyway.
    return CaptureListOut(captures=[_to_out(row) for row in rows], total=total)


@router.get("/{capture_id}", response_model=CaptureOut)
async def get_capture(
    capture_id: UUID,
    user_id: CurrentUserId,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CaptureOut:
    """One capture, with the duplicate check a reader needs to decide.

    **The corpus check is computed here as well as on the paste.** A capture
    made through the MCP server is read for the first time by this route — the
    person who reviews it never saw the paste response — so returning the
    proposal without it would leave ADR 0039 §4 holding only for whoever
    pasted the text into this browser. See ``_corpus_for``.
    """
    capture = await _own_capture(session, capture_id=capture_id, user_id=user_id)
    return _to_out(capture, corpus_check=await _corpus_for(session, capture))


@router.post("/{capture_id}/confirm", response_model=CaptureOut)
async def confirm(
    capture_id: UUID,
    payload: CaptureConfirmIn,
    user_id: CurrentUserId,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CaptureOut:
    """Turn an approved capture into a real job.

    The body is what the person approved. It is not defaulted from the
    proposal — a client that wants the proposed values has to send them, which
    means the request itself records that somebody looked.
    """
    capture = await _own_capture(session, capture_id=capture_id, user_id=user_id)
    try:
        await confirm_capture(
            session,
            capture=capture,
            title=payload.title,
            company_name=payload.company_name,
            location_text=payload.location_text,
            employment_type=payload.employment_type,
            now=utcnow(),
        )
    except CaptureAlreadyDecidedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    return _to_out(capture)


@router.post("/{capture_id}/discard", response_model=CaptureOut)
async def discard(
    capture_id: UUID,
    user_id: CurrentUserId,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CaptureOut:
    capture = await _own_capture(session, capture_id=capture_id, user_id=user_id)
    try:
        await discard_capture(session, capture=capture, now=utcnow())
    except CaptureAlreadyDecidedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    return _to_out(capture)
