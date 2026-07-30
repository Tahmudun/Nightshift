"""The fetch → preserve → normalize → persist pipeline.

Scope: M0 creates one canonical job per source record. There is no dedupe here,
because dedupe is M1's flagship deliverable and it needs the layered-evidence
rules and fixture suite from §7.5 to be anything other than a title comparison.
What M0 does establish is the *shape* dedupe needs — raw payloads preserved,
canonical rows reached only through ``job_source_links`` — so M1 adds a merge
step rather than restructuring the pipeline.

Invariant I3 is the load-bearing rule in this module. A board that failed
contributes nothing: no state change, no closure, no counter movement beyond the
failure record itself. The only thing a failed board updates is
``sources.last_failure_at`` and the run's ``error_summary``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import (
    BoardRef,
    FetchOutcome,
    JobSourceAdapter,
    NormalizedSourceJob,
    RawJob,
)
from nightshift.db.base import (
    EmploymentType,
    IngestionRunStatus,
    JobStatus,
    RemotePolicy,
    SourceStatus,
)
from nightshift.db.models import (
    Company,
    IngestionRun,
    Job,
    JobLocation,
    JobSourceLink,
    Source,
    SourceJobRecord,
)
from nightshift.db.types import utcnow
from nightshift.domain.companies import normalize_company_name

log = structlog.get_logger(__name__)

# M0 links one raw record to one canonical job with full confidence, because the
# claim being made is only "this job came from this record" — not "these two
# records are the same job", which is the claim M1's dedupe has to earn.
M0_LINK_REASON = "sole_source_record"
M0_LINK_CONFIDENCE = 1.0


@dataclass(slots=True)
class IngestionStats:
    """Counters for one run. Mirrors the ``ingestion_runs`` columns."""

    fetched: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    # `closed` stays at zero for the whole of M0: the closure state machine is
    # an M1 deliverable, and closing a job requires evidence M0 cannot gather.
    closed: int = 0
    boards_ok: list[str] = field(default_factory=list)
    boards_failed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> IngestionRunStatus:
        if self.boards_failed and self.boards_ok:
            return IngestionRunStatus.PARTIAL
        if self.boards_failed:
            return IngestionRunStatus.FAILED
        return IngestionRunStatus.SUCCEEDED

    @property
    def error_summary(self) -> str | None:
        return "\n".join(self.errors) or None


async def get_or_create_source(
    session: AsyncSession, *, name: str, source_type: object, base_url: str | None = None
) -> Source:
    existing = (
        await session.execute(select(Source).where(Source.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    source = Source(name=name, source_type=source_type, base_url=base_url)
    session.add(source)
    await session.flush()
    return source


async def get_or_create_company(session: AsyncSession, display_name: str) -> Company:
    normalized = normalize_company_name(display_name)
    existing = (
        await session.execute(select(Company).where(Company.normalized_name == normalized))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    company = Company(canonical_name=display_name.strip(), normalized_name=normalized)
    session.add(company)
    await session.flush()
    return company


def _apply_normalized_fields(job: Job, normalized: NormalizedSourceJob) -> None:
    """Copy normalized values onto a canonical job.

    Note what is not copied: ``first_seen_at``, ``status``, and ``closed_at``.
    Those belong to our own lifecycle tracking, not to the source, and letting a
    source payload overwrite them is how a re-poll resurrects a closed job.
    """
    job.title = normalized.title
    job.normalized_title = normalized.normalized_title
    job.employment_type = normalized.employment_type
    job.remote_policy = RemotePolicy(normalized.remote_policy)
    job.description_html = normalized.description_html
    job.description_text = normalized.description_text
    job.canonical_description_hash = normalized.description_hash
    job.salary_min = normalized.salary_min
    job.salary_max = normalized.salary_max
    job.salary_currency = normalized.salary_currency
    job.salary_period = normalized.salary_period
    job.application_deadline = normalized.application_deadline
    job.source_published_at = normalized.source_published_at
    job.source_updated_at = normalized.source_updated_at


async def _replace_locations(
    session: AsyncSession, job: Job, normalized: NormalizedSourceJob
) -> None:
    """Rewrite a job's locations from the parsed source text.

    Locations are replaced only by the caller when the source's location string
    actually changed, so a stable posting keeps its rows — and, once M1 attaches
    geocoding results, keeps its resolved coordinates instead of discarding and
    re-resolving them on every poll.
    """
    existing = (
        (await session.execute(select(JobLocation).where(JobLocation.job_id == job.id)))
        .scalars()
        .all()
    )

    # Detach the denormalized pointer before deleting its target, or the FK
    # trips mid-flush.
    job.primary_location_id = None
    await session.flush()
    for row in existing:
        await session.delete(row)
    await session.flush()

    primary: JobLocation | None = None
    for parsed in normalized.locations:
        row = JobLocation(
            job_id=job.id,
            raw_text=parsed.raw_text,
            city=parsed.city,
            state=parsed.state,
            country=parsed.country,
            # I1: confidence comes from the parser and coordinates stay null.
            # There is no branch here that can populate latitude/longitude —
            # geocoding is a separate M1 stage with its own audit trail.
            location_confidence=parsed.confidence,
            resolution_method=parsed.resolution_method,
            is_primary=parsed.is_primary,
        )
        session.add(row)
        if parsed.is_primary:
            primary = row

    await session.flush()
    job.primary_location_id = primary.id if primary is not None else None
    await session.flush()


def _location_signature(normalized: NormalizedSourceJob) -> tuple[str, ...]:
    return tuple(loc.raw_text for loc in normalized.locations)


async def _existing_location_signature(session: AsyncSession, job: Job) -> tuple[str, ...]:
    rows = (
        (
            await session.execute(
                select(JobLocation.raw_text)
                .where(JobLocation.job_id == job.id)
                .order_by(JobLocation.is_primary.desc(), JobLocation.raw_text)
            )
        )
        .scalars()
        .all()
    )
    signature = tuple(rows)
    return signature


async def persist_source_job(
    session: AsyncSession,
    *,
    source: Source,
    raw_job: RawJob,
    normalized: NormalizedSourceJob,
    now: datetime,
) -> str:
    """Store one posting. Returns ``"created"``, ``"updated"``, or ``"unchanged"``.

    Idempotent by construction: keyed on ``(source_id, source_job_id)``, so
    re-ingesting the same board produces no duplicates and no spurious updates.
    """
    record = (
        await session.execute(
            select(SourceJobRecord).where(
                SourceJobRecord.source_id == source.id,
                SourceJobRecord.source_job_id == raw_job.source_job_id,
            )
        )
    ).scalar_one_or_none()

    company = await get_or_create_company(session, normalized.company_name)

    if record is None:
        record = SourceJobRecord(
            source_id=source.id,
            source_job_id=raw_job.source_job_id,
            source_company_key=raw_job.source_company_key,
            canonical_url=raw_job.canonical_url,
            raw_payload=raw_job.payload,
            raw_text=normalized.description_text,
            description_hash=normalized.description_hash,
            first_seen_at=now,
            last_seen_at=now,
            last_verified_at=now,
            source_status=SourceStatus.ACTIVE,
        )
        session.add(record)
        await session.flush()

        job = Job(
            company_id=company.id,
            first_seen_at=now,
            last_seen_at=now,
            status=JobStatus.OPEN,
            employment_type=EmploymentType.UNKNOWN,
        )
        _apply_normalized_fields(job, normalized)
        session.add(job)
        await session.flush()
        await _replace_locations(session, job, normalized)

        session.add(
            JobSourceLink(
                job_id=job.id,
                source_job_record_id=record.id,
                match_confidence=M0_LINK_CONFIDENCE,
                link_reason=M0_LINK_REASON,
            )
        )
        await session.flush()
        return "created"

    # --- existing record ---------------------------------------------------
    content_changed = record.description_hash != normalized.description_hash
    record.last_seen_at = now
    record.last_verified_at = now
    record.consecutive_misses = 0
    record.source_status = SourceStatus.ACTIVE
    record.canonical_url = raw_job.canonical_url
    record.raw_payload = raw_job.payload
    record.raw_text = normalized.description_text
    record.description_hash = normalized.description_hash

    job = await _canonical_job_for(session, record)
    job.last_seen_at = now
    job.company_id = company.id

    # Compared as sets: row order is a storage detail, and reordering the same
    # places is not a change worth discarding resolved coordinates over.
    location_changed = set(await _existing_location_signature(session, job)) != set(
        _location_signature(normalized)
    )

    field_changed = (
        job.title != normalized.title
        or job.canonical_description_hash != normalized.description_hash
        or job.salary_min != normalized.salary_min
        or job.salary_max != normalized.salary_max
        or job.source_updated_at != normalized.source_updated_at
    )

    if content_changed or field_changed:
        _apply_normalized_fields(job, normalized)
    if location_changed:
        await _replace_locations(session, job, normalized)

    await session.flush()
    return "updated" if (content_changed or field_changed or location_changed) else "unchanged"


async def _canonical_job_for(session: AsyncSession, record: SourceJobRecord) -> Job:
    """Resolve the canonical job a raw record belongs to, through the link table.

    Never by re-matching on title or URL: the link table is the provenance
    record, and reaching a canonical job any other way is how a merge silently
    comes undone.
    """
    job = (
        (
            await session.execute(
                select(Job)
                .join(JobSourceLink, JobSourceLink.job_id == Job.id)
                .where(JobSourceLink.source_job_record_id == record.id)
            )
        )
        .scalars()
        .first()
    )
    if job is None:
        raise RuntimeError(
            f"source_job_record {record.id} has no canonical job — "
            "every raw record must trace to exactly one (M1 acceptance criterion)"
        )
    return job


async def ingest_boards(
    session: AsyncSession,
    adapter: JobSourceAdapter,
    boards: Sequence[BoardRef],
    *,
    source: Source,
    now: datetime | None = None,
) -> tuple[IngestionRun, IngestionStats]:
    """Poll every board and persist what came back.

    The run row is created before any fetch and closed after the last one, so an
    ingestion that crashes leaves a ``running`` row rather than no evidence at
    all — §2.6 requires source reliability to be visible, which means visible on
    the bad days too.
    """
    timestamp = now or utcnow()
    stats = IngestionStats()

    run = IngestionRun(
        source_id=source.id,
        board_tokens=[board.token for board in boards],
        started_at=timestamp,
        status=IngestionRunStatus.RUNNING,
    )
    session.add(run)
    await session.flush()

    for board in boards:
        outcome = await adapter.fetch_board(board)
        if not outcome.ok:
            # I3: we learned nothing. No listing state changes, nothing closes.
            stats.boards_failed.append(board.token)
            stats.errors.append(f"{board.ats}:{board.token}: {outcome.error}")
            source.last_failure_at = timestamp
            log.warning("ingest_board_failed", board=board.token, error=outcome.error)
            continue

        stats.boards_ok.append(board.token)
        await _persist_outcome(session, adapter, outcome, source=source, stats=stats, now=timestamp)
        source.last_success_at = timestamp

    run.finished_at = utcnow()
    run.status = stats.status
    run.records_fetched = stats.fetched
    run.records_created = stats.created
    run.records_updated = stats.updated
    run.records_unchanged = stats.unchanged
    run.records_closed = stats.closed
    run.records_failed = stats.failed
    run.error_summary = stats.error_summary
    await session.flush()

    log.info(
        "ingest_run_finished",
        status=run.status.value,
        fetched=stats.fetched,
        created=stats.created,
        updated=stats.updated,
        unchanged=stats.unchanged,
        failed=stats.failed,
        boards_ok=len(stats.boards_ok),
        boards_failed=len(stats.boards_failed),
    )
    return run, stats


async def _persist_outcome(
    session: AsyncSession,
    adapter: JobSourceAdapter,
    outcome: FetchOutcome,
    *,
    source: Source,
    stats: IngestionStats,
    now: datetime,
) -> None:
    for raw_job in outcome.jobs:
        stats.fetched += 1
        try:
            normalized = adapter.normalize(raw_job)
        except Exception as exc:
            stats.failed += 1
            stats.errors.append(f"normalize {raw_job.source_job_id}: {exc}")
            log.warning("normalize_failed", source_job_id=raw_job.source_job_id, error=str(exc))
            continue

        try:
            # A real savepoint, so a constraint violation on one posting rolls
            # back only that posting. Without this the failed statement poisons
            # the transaction and every job after it in the board fails too.
            async with session.begin_nested():
                result = await persist_source_job(
                    session, source=source, raw_job=raw_job, normalized=normalized, now=now
                )
        except Exception as exc:
            stats.failed += 1
            stats.errors.append(f"persist {raw_job.source_job_id}: {exc}")
            log.warning("persist_failed", source_job_id=raw_job.source_job_id, error=str(exc))
            continue

        if result == "created":
            stats.created += 1
        elif result == "updated":
            stats.updated += 1
        else:
            stats.unchanged += 1
