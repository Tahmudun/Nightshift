"""Job read routes.

Routes validate and delegate (CLAUDE.md §3). The mapping from ORM rows to
response models lives in ``to_summary`` / ``_to_detail`` here because it is
serialisation, not domain logic; anything that makes a *decision* about a job
belongs in ``nightshift.domain``.

``to_summary`` is public rather than underscored because
``routes/applications.py`` reuses it: one row, one serialiser. Two mappings of
the same row drift, and they drift silently.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.api.deps import CurrentUserId
from nightshift.api.schemas import (
    CompanyOut,
    DeferredComponentOut,
    DeferredFilterOut,
    EligibilityBlockerOut,
    EligibilityOut,
    EligibilityUnknownOut,
    JobAdminListOut,
    JobAdminRowOut,
    JobDetailOut,
    JobListOut,
    JobLocationOut,
    JobRequirementOut,
    JobSourceOut,
    JobStatusCounts,
    JobStatusEventOut,
    JobSummaryOut,
    MatchComponentOut,
    MatchEvidenceOut,
    MatchOut,
    MatchPenaltyOut,
    SalaryOut,
    UnmetRequirementOut,
)
from nightshift.db.base import (
    EmploymentType,
    InternshipSeason,
    JobStatus,
    LocationConfidence,
    MatchComponent,
    PenaltyName,
    RemotePolicy,
)
from nightshift.db.models import (
    Company,
    Job,
    JobLocation,
    JobMergeEvent,
    JobRequirement,
    JobSourceLink,
    JobStatusEvent,
    MatchResult,
    SourceJobRecord,
    User,
)
from nightshift.db.session import get_db_session
from nightshift.domain.eligibility import evaluate, profile_from_user
from nightshift.domain.eligibility_reading import read_posting
from nightshift.domain.matching import (
    COMPONENT_SCORE_COLUMNS,
    current_result_for,
    unmet_requirements,
)
from nightshift.domain.matching_weights import load_weights
from nightshift.domain.requirement_extraction import RequirementProposal
from nightshift.domain.scoring import DEFERRED_COMPONENTS, WEIGHT_NAME, score_fraction
from nightshift.domain.search import (
    DEFERRED_FILTERS,
    JobSearchQuery,
    build_filters,
    salary_excluded_filter,
    season_excluded_filter,
    skill_excluded_filter,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

MAX_LIMIT = 100


def _to_salary(job: Job) -> SalaryOut:
    """A10: never present an absent salary as a zero or an omitted field."""
    provided = job.salary_min is not None or job.salary_max is not None
    if not provided:
        return SalaryOut(provided=False)
    return SalaryOut(
        provided=True,
        minimum=float(job.salary_min) if job.salary_min is not None else None,
        maximum=float(job.salary_max) if job.salary_max is not None else None,
        currency=job.salary_currency,
        period=job.salary_period,
    )


def _to_location(row: JobLocation) -> JobLocationOut:
    return JobLocationOut(
        id=row.id,
        raw_text=row.raw_text,
        city=row.city,
        state=row.state,
        country=row.country,
        latitude=float(row.latitude) if row.latitude is not None else None,
        longitude=float(row.longitude) if row.longitude is not None else None,
        # I1: the confidence travels with the coordinates, always, in both
        # directions. There is no serialisation path that emits one without the
        # other.
        location_confidence=row.location_confidence,
        resolution_method=row.resolution_method,
        is_primary=row.is_primary,
    )


def to_summary(job: Job) -> JobSummaryOut:
    return JobSummaryOut(
        id=job.id,
        title=job.title,
        company=CompanyOut(
            id=job.company.id,
            canonical_name=job.company.canonical_name,
            website=job.company.website,
        ),
        employment_type=job.employment_type,
        remote_policy=job.remote_policy,
        status=job.status,
        locations=[_to_location(row) for row in job.locations],
        salary=_to_salary(job),
        source_published_at=job.source_published_at,
        source_updated_at=job.source_updated_at,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        application_deadline=job.application_deadline,
    )


@router.get("", response_model=JobListOut)
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    q: Annotated[str | None, Query(description="Full-text search over the job title")] = None,
    include_description: Annotated[
        bool, Query(description="Widen `q` to search descriptions as well as titles")
    ] = False,
    company: Annotated[str | None, Query(description="Filter by company name substring")] = None,
    city: Annotated[str | None, Query(description="City exactly as the source wrote it")] = None,
    employment_type: Annotated[EmploymentType | None, Query()] = None,
    remote_policy: Annotated[RemotePolicy | None, Query()] = None,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    confidence: Annotated[
        LocationConfidence | None,
        Query(description="Only jobs with at least one location at this confidence"),
    ] = None,
    source: Annotated[str | None, Query(description="Source name substring")] = None,
    first_seen_after: Annotated[datetime | None, Query()] = None,
    salary_at_least: Annotated[float | None, Query(ge=0)] = None,
    skill: Annotated[
        str | None,
        Query(
            description=(
                "A technology the posting names. Resolved through data/skills.yaml, "
                "so 'GCP' finds postings stored as 'Google Cloud'. Incomplete: see "
                "excluded_no_requirements."
            )
        ),
    ] = None,
    internship_season: Annotated[
        InternshipSeason | None,
        Query(description="Only internships whose title states this season"),
    ] = None,
    internship_year: Annotated[
        int | None,
        Query(ge=2000, description="Only internships whose title states this year"),
    ] = None,
) -> JobListOut:
    """Search canonical jobs, most-recently-seen first.

    Ordering is recency, not relevance. PRODUCT-SPEC §24's ranking is M3 work
    and depends on the match score, so ranking by a relevance number here would
    be inventing half of it.
    """
    query = JobSearchQuery(
        q=q,
        include_description=include_description,
        company=company,
        city=city,
        employment_type=employment_type,
        remote_policy=remote_policy,
        job_status=job_status,
        confidence=confidence,
        source=source,
        first_seen_after=first_seen_after,
        salary_at_least=salary_at_least,
        skill=skill,
        internship_season=internship_season,
        internship_year=internship_year,
    )
    filters = build_filters(query)

    total = (
        await session.execute(select(func.count()).select_from(Job).where(*filters))
    ).scalar_one()

    # What the salary floor necessarily removed, counted against the *other*
    # filters so the number describes this result set rather than the corpus.
    excluded_no_salary = 0
    if query.salary_at_least is not None:
        without_salary = build_filters(query.model_copy(update={"salary_at_least": None}))
        excluded_no_salary = (
            await session.execute(
                select(func.count())
                .select_from(Job)
                .where(*without_salary, salary_excluded_filter())
            )
        ).scalar_one()

    # The same shape for the two filters M3b turned on. Each counts what its own
    # filter could not have matched, against the *other* filters, so the number
    # describes this result rather than the whole corpus.
    #
    # Both are computed only when their filter is in play. A count nobody asked
    # for is a query nobody needed, and a caveat shown beside an unfiltered
    # result is noise that teaches people to ignore caveats.
    excluded_no_requirements = 0
    if query.skill and query.skill.strip():
        without_skill = build_filters(query.model_copy(update={"skill": None}))
        excluded_no_requirements = (
            await session.execute(
                select(func.count()).select_from(Job).where(*without_skill, skill_excluded_filter())
            )
        ).scalar_one()

    excluded_no_season = 0
    if query.internship_season is not None or query.internship_year is not None:
        without_season = build_filters(
            query.model_copy(update={"internship_season": None, "internship_year": None})
        )
        excluded_no_season = (
            await session.execute(
                select(func.count())
                .select_from(Job)
                .where(*without_season, season_excluded_filter(query))
            )
        ).scalar_one()

    rows = (
        (
            await session.execute(
                select(Job)
                .where(*filters)
                .options(selectinload(Job.company), selectinload(Job.locations))
                # Deterministic: id breaks ties so pagination cannot skip or repeat
                # a row when several jobs share a last_seen_at, which they always do
                # because a whole board is ingested with one timestamp.
                .order_by(Job.last_seen_at.desc(), Job.id)
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return JobListOut(
        items=[to_summary(job) for job in rows],
        total=total,
        limit=limit,
        offset=offset,
        excluded_no_salary=excluded_no_salary,
        excluded_no_requirements=excluded_no_requirements,
        excluded_no_season=excluded_no_season,
        deferred_filters=[
            DeferredFilterOut(name=e.name, blocked_on=e.blocked_on, reason=e.reason)
            for e in DEFERRED_FILTERS
        ],
    )


@router.get("/admin", response_model=JobAdminListOut)
async def list_jobs_for_admin(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobAdminListOut:
    """Operational view of the canonical job table.

    Declared before ``/{job_id}`` deliberately: FastAPI matches in declaration
    order, so the other way round this path resolves as a job whose id is the
    string "admin" and returns 422.

    Includes closed jobs by default, unlike the user-facing list. Hiding them
    here would make the closure machine unobservable — which is the one thing
    this view exists to prevent.
    """
    counted = (await session.execute(select(Job.status, func.count()).group_by(Job.status))).all()
    status_counts = JobStatusCounts(**{state.value: count for state, count in counted})

    filters = [Job.status == job_status] if job_status is not None else []

    total = (
        await session.execute(select(func.count()).select_from(Job).where(*filters))
    ).scalar_one()

    rows = (
        await session.execute(
            select(
                Job,
                Company.canonical_name,
                func.count(func.distinct(JobSourceLink.id)),
                func.count(func.distinct(JobLocation.id)),
                func.count(func.distinct(JobMergeEvent.id)),
            )
            .join(Company, Company.id == Job.company_id)
            .outerjoin(JobSourceLink, JobSourceLink.job_id == Job.id)
            .outerjoin(JobLocation, JobLocation.job_id == Job.id)
            .outerjoin(JobMergeEvent, JobMergeEvent.winner_job_id == Job.id)
            .where(*filters)
            .group_by(Job.id, Company.canonical_name)
            # id breaks ties, as in list_jobs: a whole board shares one
            # last_seen_at, so without it pagination can skip or repeat a row.
            .order_by(Job.last_seen_at.desc(), Job.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return JobAdminListOut(
        items=[
            JobAdminRowOut(
                id=job.id,
                title=job.title,
                company_name=company_name,
                status=job.status,
                first_seen_at=job.first_seen_at,
                last_seen_at=job.last_seen_at,
                closed_at=job.closed_at,
                source_count=source_count,
                location_count=location_count,
                merge_count=merge_count,
            )
            for job, company_name, source_count, location_count, merge_count in rows
        ],
        total=total,
        status_counts=status_counts,
    )


@router.get("/{job_id}/history", response_model=list[JobStatusEventOut])
async def job_history(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[JobStatusEventOut]:
    """Every transition this job has been through, oldest first.

    This is the answer to "why did this job disappear?", and it survives the job
    reopening — which is the whole reason ``job_status_events`` is append-only.
    A reposted job has ``closed_at`` back to null, so the column that showed the
    closure is gone and only these rows remain.
    """
    exists = (await session.execute(select(Job.id).where(Job.id == job_id))).scalar_one_or_none()
    if exists is None:
        # 404 rather than an empty list: "this job has no transitions" and "this
        # job does not exist" are different answers and must not look alike.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    events = (
        (
            await session.execute(
                select(JobStatusEvent)
                .where(JobStatusEvent.job_id == job_id)
                .order_by(JobStatusEvent.created_at, JobStatusEvent.id)
            )
        )
        .scalars()
        .all()
    )
    return [JobStatusEventOut.model_validate(event) for event in events]


@router.get("/{job_id}", response_model=JobDetailOut)
async def get_job(
    job_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    user_id: CurrentUserId,
) -> JobDetailOut:
    job = (
        (
            await session.execute(
                select(Job)
                .where(Job.id == job_id)
                .options(
                    selectinload(Job.company),
                    selectinload(Job.locations),
                    selectinload(Job.requirements),
                )
            )
        )
        .scalars()
        .first()
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")

    provenance = (
        (
            await session.execute(
                select(SourceJobRecord)
                .join(JobSourceLink, JobSourceLink.source_job_record_id == SourceJobRecord.id)
                .where(JobSourceLink.job_id == job_id)
                .options(selectinload(SourceJobRecord.source))
            )
        )
        .scalars()
        .all()
    )

    requirements = sorted(job.requirements, key=lambda r: (r.char_start, r.char_end))
    summary = to_summary(job)
    eligibility = await _eligibility_for(session, user_id=user_id, requirements=requirements)
    stored = await current_result_for(session, user_id=user_id, job_id=job_id)
    return JobDetailOut(
        **summary.model_dump(),
        description_text=job.description_text,
        description_html=job.description_html,
        requirements=[
            JobRequirementOut(
                kind=row.kind,
                value=row.value,
                raw_text=row.raw_text,
                char_start=row.char_start,
                char_end=row.char_end,
                necessity=row.necessity,
                has_equivalence=row.has_equivalence,
            )
            for row in requirements
        ],
        # Read off the rows rather than from the module constant: a job whose
        # rows predate an extractor bump must report the version that actually
        # produced them, and a job nobody has read must report nothing at all.
        requirements_extractor_version=(
            requirements[0].extractor_version if requirements else None
        ),
        eligibility=eligibility,
        match=to_match(stored),
        # Null rather than empty without a score: there are no evidence rows to
        # difference against, and `[]` there reads as "you meet everything" —
        # a claim about a person computed from nothing.
        unmet_requirements=(
            [
                UnmetRequirementOut(
                    kind=row.kind,
                    value=row.value,
                    raw_text=row.raw_text,
                    char_start=row.char_start,
                    char_end=row.char_end,
                    necessity=row.necessity,
                    has_equivalence=row.has_equivalence,
                )
                for row in unmet_requirements(stored, requirements)
            ]
            if stored is not None
            else None
        ),
        sources=[
            JobSourceOut(
                source_name=record.source.name,
                source_job_id=record.source_job_id,
                canonical_url=record.canonical_url,
                first_seen_at=record.first_seen_at,
                last_seen_at=record.last_seen_at,
            )
            for record in provenance
        ],
    )


def to_match(result: MatchResult | None) -> MatchOut | None:
    """A stored score as its own breakdown. Serialisation, and nothing more.

    Public rather than underscored because `routes/matches.py` reuses it, for the
    reason `to_summary` is: one row, one serialiser. Two mappings of the same row
    drift, and a drifted breakdown is I4's failure with every constraint still
    green.

    Every number here was written by `domain/matching.py`; nothing is recomputed.
    Re-running the scorer to fill in a field would be a second derivation of the
    same claim, which is what `matching.posting_for` is written about — and here
    it would produce a breakdown that can disagree with the total printed above
    it, while looking entirely plausible.

    The one thing read from outside the row is each component's `weight`, out of
    `data/matching.yaml`. That is safe precisely because `current_result_for`
    already refused any row whose `ruleset_version` is not the current one: the
    weights file *is* the data half of that version, so the numbers this reads and
    the numbers that produced the row are the same numbers by construction.
    """
    if result is None:
        return None

    weights = load_weights()
    assessed = {row.component: row for row in result.assessments}
    evidence: dict[MatchComponent, list[MatchEvidenceOut]] = {}
    for row in result.evidence:
        evidence.setdefault(row.component, []).append(
            MatchEvidenceOut(
                component=row.component,
                points=row.points,
                job_span_text=row.job_span_text,
                job_span_field=row.job_span_field,
                job_char_start=row.job_char_start,
                job_char_end=row.job_char_end,
                user_span_text=row.user_span_text,
                user_skill_id=row.user_skill_id,
                user_project_id=row.user_project_id,
                compared=row.compared,
                proposed_by=row.proposed_by,
                job_requirement_id=row.job_requirement_id,
            )
        )

    return MatchOut(
        overall_score=result.overall_score,
        assessed_out_of=result.assessed_out_of,
        # The same rule the pure scorer applies before the row exists, so a pair
        # nothing could be assessed on reads as `null` on both sides of the
        # database rather than as a zero on one of them.
        fraction=score_fraction(result.overall_score, result.assessed_out_of),
        eligibility_status=result.eligibility_status,
        # Iterating the enum rather than the stored rows or the column mapping:
        # the order the page renders is the domain's order, not a property of a
        # dict literal, and a missing assessment raises here rather than silently
        # shortening the breakdown. The database asserts the same count at commit,
        # so this is the second net and not the only one.
        components=[
            MatchComponentOut(
                component=component,
                points=getattr(result, COMPONENT_SCORE_COLUMNS[component]),
                weight=weights.weight(WEIGHT_NAME[component]),
                assessable=assessed[component].assessable,
                why=assessed[component].why,
                evidence=evidence.get(component, []),
            )
            for component in MatchComponent
        ],
        penalty_score=result.penalty_score,
        # In `PenaltyName` order rather than the rows' insertion order, so two
        # scores print their penalties in the same sequence and a reader comparing
        # two postings is comparing the same lines. The database asserts both rows
        # exist, so the lookup cannot come up short.
        penalties=[
            MatchPenaltyOut(
                name=penalty.name,
                points=penalty.points,
                applicable=penalty.applicable,
                why=penalty.why,
                compared=penalty.compared,
            )
            for penalty in sorted(
                result.penalties, key=lambda row: list(PenaltyName).index(row.name)
            )
        ],
        deferred_components=[
            DeferredComponentOut(
                name=deferred.name,
                weight=deferred.weight,
                blocked_on=deferred.blocked_on,
                reason=deferred.reason,
            )
            for deferred in DEFERRED_COMPONENTS
        ],
        ruleset_version=result.ruleset_version,
        model_version=result.model_version,
        computed_at=result.created_at,
    )


async def _eligibility_for(
    session: AsyncSession, *, user_id: UUID, requirements: Sequence[JobRequirement]
) -> EligibilityOut | None:
    """The gate's verdict for this person and this posting, computed on read.

    Returns `None` when the posting has no extracted requirements at all.
    A verdict derived from an unread posting would say `eligible` to everything,
    which is a claim about a person based on nothing — and indistinguishable, on
    the page, from a posting that genuinely asks for nothing. The two are
    different and the null is what keeps them apart, exactly as
    `requirements_extractor_version` already does one field up.

    Nothing is written. `matching.md` §4.2 puts the stored verdict in M3c, and a
    stored one goes stale the moment somebody edits their graduation year.
    """
    if not requirements:
        return None

    user = (await session.execute(select(User).where(User.id == user_id))).scalars().first()
    if user is None:
        return None

    reading = read_posting(
        [
            RequirementProposal(
                kind=row.kind.value,
                value=row.value,
                raw_text=row.raw_text,
                char_start=row.char_start,
                char_end=row.char_end,
                necessity=row.necessity.value,
                has_equivalence=row.has_equivalence,
            )
            for row in requirements
        ]
    )
    verdict = evaluate(reading, profile_from_user(user))
    return EligibilityOut(
        state=verdict.state.value,
        blockers=[
            EligibilityBlockerOut(
                dimension=blocker.dimension,
                outcome=blocker.outcome,
                posting_says=blocker.posting_says,
                char_start=blocker.posting_span[0] if blocker.posting_span else None,
                char_end=blocker.posting_span[1] if blocker.posting_span else None,
                profile_says=blocker.profile_says,
                why=blocker.why,
            )
            for blocker in verdict.blockers
        ],
        unknowns=[
            EligibilityUnknownOut(
                dimension=unknown.dimension,
                profile_field=unknown.profile_field,
                why=unknown.why,
            )
            for unknown in verdict.unknowns
        ],
        gate_version=verdict.gate_version,
    )
