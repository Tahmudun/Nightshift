"""The fetch → preserve → normalize → persist → dedupe → age pipeline.

M0 shaped this module so that M1b could add steps rather than restructure it,
and that is what happened: raw payloads were already preserved and canonical
rows already reachable only through ``job_source_links``, so dedupe became a
step at the end of the create branch and freshness a step at the end of the run.

Policy lives in two pure modules and not here. :mod:`nightshift.domain.dedupe`
decides whether two jobs are one, and :mod:`nightshift.domain.freshness` decides
what state a job should be in; both take values and return verdicts. This module
is the translation layer that reads rows, asks them, and writes the answer down.
Keeping it that way is what makes the state machine and the merge rules testable
without a database.

Invariant I3 is the load-bearing rule here. A board that failed contributes
nothing: no state change, no closure, and — the part that is easy to get wrong —
no counter movement either, because a miss counter that ticks during an outage
closes jobs three polls later with nothing in the data explaining why. The guard
is structural: ``apply_freshness`` is given only the boards that answered, and
there is no argument by which a caller can ask for the others.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import (
    BoardRef,
    FetchOutcome,
    JobSourceAdapter,
    NormalizedSourceJob,
    RawJob,
    TwoPhaseJobSourceAdapter,
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
    JobEmbedding,
    JobLocation,
    JobMergeEvent,
    JobSourceLink,
    JobStatusEvent,
    Source,
    SourceJobRecord,
)
from nightshift.db.types import utcnow
from nightshift.domain.applications import record_listing_closed
from nightshift.domain.companies import normalize_company_name
from nightshift.domain.dedupe import (
    DEDUPE_RULESET_VERSION,
    DedupeCandidate,
    DedupeVerdict,
    compare,
    location_key,
)
from nightshift.domain.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_NAME,
    default_embedder,
)
from nightshift.domain.freshness import RecordObservation, decide_job_status

log = structlog.get_logger(__name__)

# The reason on the first link a job ever gets. Full confidence, because the
# claim it makes is only "this job came from this record" — not "these two
# records are the same job", which is the claim dedupe has to earn and which
# writes its own reason over this one on merge.
SOLE_RECORD_REASON = "sole_source_record"
SOLE_RECORD_CONFIDENCE = 1.0


@dataclass(slots=True)
class IngestionStats:
    """Counters for one run. Mirrors the ``ingestion_runs`` columns."""

    fetched: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    failed: int = 0
    # Jobs that transitioned to `closed` during this run (ADR 0009). Only ever
    # non-zero for boards that answered — see apply_freshness.
    closed: int = 0
    #: Boards that answered at all, including with a 304. "Did this source
    #: respond" is what this measures, and it is what `status` is derived from.
    boards_ok: list[str] = field(default_factory=list)
    #: Boards that answered with an actual listing. **Only these may age
    #: records.** A 304 board is in `boards_ok` but not here: it responded
    #: successfully and described nothing, so ageing its records against a run
    #: it never enumerated would close every posting on it.
    boards_listed: list[str] = field(default_factory=list)
    #: Boards that answered 304. Polled successfully, wrote nothing, cost one
    #: request and no body.
    not_modified: list[str] = field(default_factory=list)
    boards_failed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    #: The ETag each board served, for the caller to store against it. Carried
    #: on the stats rather than returned separately because the caller already
    #: has to hold these, and a second return value is a second thing to forget.
    etags: dict[str, str | None] = field(default_factory=dict)

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
    """Insert-or-fetch, atomically.

    Check-then-insert races the moment worker concurrency exceeds one, which
    ADR 0007's queue-driven polling makes routine. `ON CONFLICT DO NOTHING`
    followed by a read is one statement plus one read rather than a
    read-then-write window, and it never raises on the loser of the race.
    """
    stmt = (
        pg_insert(Source)
        .values(name=name, source_type=source_type, base_url=base_url)
        .on_conflict_do_nothing(index_elements=[Source.name])
    )
    await session.execute(stmt)
    source = (await session.execute(select(Source).where(Source.name == name))).scalar_one()
    return source


async def get_or_create_company(session: AsyncSession, display_name: str) -> Company:
    """Insert-or-fetch, atomically, keyed on the normalized name.

    `normalized_name` is the identity column and it is unique, so the conflict
    target is the thing that actually decides whether two strings are the same
    employer. `canonical_name` is display text and is deliberately not part of
    the key: "Moody's" and "Moodys" are one company (see test_companies.py).
    """
    normalized = normalize_company_name(display_name)
    stmt = (
        pg_insert(Company)
        .values(canonical_name=display_name.strip(), normalized_name=normalized)
        .on_conflict_do_nothing(index_elements=[Company.normalized_name])
    )
    await session.execute(stmt)
    company = (
        await session.execute(select(Company).where(Company.normalized_name == normalized))
    ).scalar_one()
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
            source_updated_at=normalized.source_updated_at,
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
                match_confidence=SOLE_RECORD_CONFIDENCE,
                link_reason=SOLE_RECORD_REASON,
            )
        )
        await session.flush()
        await _store_embedding(session, job)

        # Dedupe runs only on creation. An existing record already resolves to
        # its canonical job through the link table, and re-running the matcher
        # on every poll is how a settled merge starts oscillating between two
        # jobs — and how the audit table fills with the same decision forever.
        duplicate = await find_duplicate(session, job=job)
        if duplicate is not None:
            existing_job, verdict = duplicate
            log.info(
                "job_merged",
                winner=str(existing_job.id),
                loser=str(job.id),
                reason=verdict.reason,
                confidence=verdict.confidence,
            )
            await merge_jobs(session, winner=existing_job, loser=job, verdict=verdict)
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
    record.source_updated_at = normalized.source_updated_at

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


async def _canonical_url_of(session: AsyncSession, job: Job) -> str | None:
    """The URL of any source record describing this job.

    Any, not all: after a merge a job has several, and they are by construction
    the URLs that made it one job. Layer 1 only needs one to match.
    """
    return (
        await session.execute(
            select(SourceJobRecord.canonical_url)
            .join(JobSourceLink, JobSourceLink.source_job_record_id == SourceJobRecord.id)
            .where(JobSourceLink.job_id == job.id, SourceJobRecord.canonical_url.is_not(None))
            .limit(1)
        )
    ).scalar_one_or_none()


async def _candidate_for(session: AsyncSession, job: Job) -> DedupeCandidate:
    """Flatten a canonical job into a comparison candidate.

    Both sides of every comparison are built by this one function, from the
    database, so the two candidates cannot be constructed differently. An
    earlier draft took one side's URL from the incoming payload and the other's
    from storage, which made ``compare`` asymmetric through its inputs even
    though the function itself is symmetric.
    """
    location_rows = (
        await session.execute(
            select(JobLocation.city, JobLocation.state, JobLocation.country).where(
                JobLocation.job_id == job.id
            )
        )
    ).all()
    embedding = (
        await session.execute(select(JobEmbedding.embedding).where(JobEmbedding.job_id == job.id))
    ).scalar_one_or_none()

    return DedupeCandidate(
        # The company UUID, not its name: identity is already resolved by
        # get_or_create_company, and re-deciding it here could disagree.
        company_key=str(job.company_id),
        canonical_url=await _canonical_url_of(session, job),
        normalized_title=job.normalized_title,
        employment_type=job.employment_type,
        location_keys=frozenset(
            location_key(city, state, country) for city, state, country in location_rows
        ),
        description_hash=job.canonical_description_hash or "",
        description=job.description_text,
        embedding=tuple(embedding) if embedding is not None else None,
    )


async def _store_embedding(session: AsyncSession, job: Job) -> None:
    """Embed a job's description, skipping unchanged ones.

    Keyed on the description hash, so a re-poll of an unchanged posting does no
    model work. Without that check every poll would re-embed the whole corpus,
    which is the difference between dedupe costing nothing on a quiet day and
    costing everything.
    """
    if not job.description_text:
        return

    source_hash = job.canonical_description_hash or ""
    existing = (
        await session.execute(select(JobEmbedding).where(JobEmbedding.job_id == job.id))
    ).scalar_one_or_none()
    if existing is not None and existing.source_hash == source_hash:
        return

    vector = list(default_embedder().embed([job.description_text])[0])
    if existing is None:
        session.add(
            JobEmbedding(
                job_id=job.id,
                model_name=EMBEDDING_MODEL_NAME,
                dimension=EMBEDDING_DIMENSION,
                embedding=vector,
                source_hash=source_hash,
            )
        )
    else:
        existing.embedding = vector
        existing.source_hash = source_hash
        existing.model_name = EMBEDDING_MODEL_NAME
        existing.dimension = EMBEDDING_DIMENSION
    await session.flush()


async def find_duplicate(session: AsyncSession, *, job: Job) -> tuple[Job, DedupeVerdict] | None:
    """Find an existing job that ``job`` duplicates, within the same company.

    Blocking by company is a correctness rule before it is a performance one:
    merging across employers is never right, and there is no code path here
    that can compare two companies' postings.

    Linear in the company's job count. Fine at thousands; it will not be at
    M1c's scale, and the fix then is a blocking index on
    (company_id, normalized_title) — not now, because building for a load
    nobody has measured is its own mistake (CLAUDE.md §8).
    """
    others = (
        (
            await session.execute(
                select(Job).where(Job.company_id == job.company_id, Job.id != job.id)
            )
        )
        .scalars()
        .all()
    )
    if not others:
        return None

    candidate = await _candidate_for(session, job)
    for other in others:
        verdict = compare(candidate, await _candidate_for(session, other))
        if verdict.merge:
            return other, verdict
    return None


async def _absorb_locations(session: AsyncSession, *, winner: Job, loser: Job) -> None:
    """Move locations the loser named and the winner did not.

    Two cross-posted listings of one role can name different sets of offices —
    one board says "Washington, DC", the other says "Washington, DC" and
    "Austin, TX". They share a location, so they merge, and without this the
    loser's rows cascade away with it and the canonical job silently
    under-reports where the role is. A user filtering for Austin would never
    see it, at the exact moment two sources agree the job exists there.

    Deduplicated on the parsed (city, state, country) key rather than on
    ``raw_text``: "New York, NY" and "New York, NY (HQ)" are the same office
    written twice, and keeping both would turn one place into two.

    Moved rows are never primary. The winner already has one, and A2 lets order
    carry meaning for sorting only — so a second primary would be a claim
    neither posting made.
    """
    existing = {
        location_key(city, state, country)
        for city, state, country in (
            await session.execute(
                select(JobLocation.city, JobLocation.state, JobLocation.country).where(
                    JobLocation.job_id == winner.id
                )
            )
        ).all()
    }

    loser_rows = (
        (await session.execute(select(JobLocation).where(JobLocation.job_id == loser.id)))
        .scalars()
        .all()
    )
    moved = False
    for row in loser_rows:
        key = location_key(row.city, row.state, row.country)
        if key in existing:
            continue
        existing.add(key)
        row.job_id = winner.id
        row.is_primary = False
        moved = True

    if moved:
        await session.flush()
        # The loser is about to be deleted, and Job.locations cascades
        # delete-orphan. Expiring the collection stops SQLAlchemy deleting the
        # rows we just reassigned along with it.
        session.expire(loser, ["locations"])
        session.expire(winner, ["locations"])


async def merge_jobs(
    session: AsyncSession, *, winner: Job, loser: Job, verdict: DedupeVerdict
) -> None:
    """Fold ``loser`` into ``winner``, preserving every provenance edge.

    Reversibility does not depend on the snapshot written here. Canonical jobs
    are derived from ``source_job_records.raw_payload``, which is preserved
    verbatim, so any merge can be undone by re-deriving. The event exists to
    make the decision auditable and an un-merge cheap — not because the data
    could otherwise be lost.

    **Both rows are locked first, in primary-key order.** M1d makes this
    reachable: ADR 0007 gives every board its own job, so two polls can run at
    once and each can decide that postings A and B are the same opening —
    typically in *opposite* directions, because each worker names the winner
    from its own board's perspective. Unlocked, they interleave and each deletes
    the other's winner.

    The ordering is what prevents a deadlock rather than merely detecting one.
    Locking in the order the caller happened to pass means two workers can each
    hold the row the other is waiting for; sorting by primary key means whoever
    gets there first holds both, and the other simply queues. Verified: without
    it, ``tests/test_merge_concurrency.py`` reproduces a real
    ``DeadlockDetectedError`` from Postgres.

    Acquired as two statements rather than one ``IN`` clause with ``ORDER BY``,
    because a single statement's lock acquisition order follows the query plan
    and is not guaranteed to follow the sort.
    """
    for job_id in sorted([winner.id, loser.id]):
        still_there = (
            await session.execute(select(Job).where(Job.id == job_id).with_for_update())
        ).scalar_one_or_none()
        if still_there is None:
            # Another worker merged this pair and deleted one of them while we
            # were queueing for the lock. Nothing to do, and emphatically not an
            # error: the outcome we wanted has already happened.
            log.info(
                "merge_already_applied",
                winner=str(winner.id),
                loser=str(loser.id),
                missing=str(job_id),
            )
            return

    session.add(
        JobMergeEvent(
            winner_job_id=winner.id,
            loser_job_id=loser.id,
            loser_snapshot={
                "title": loser.title,
                "normalized_title": loser.normalized_title,
                "canonical_description_hash": loser.canonical_description_hash,
                "company_id": str(loser.company_id),
                "first_seen_at": loser.first_seen_at.isoformat(),
                "status": loser.status.value,
            },
            reason=verdict.reason,
            match_confidence=verdict.confidence,
            ruleset_version=DEDUPE_RULESET_VERSION,
        )
    )

    links = (
        (await session.execute(select(JobSourceLink).where(JobSourceLink.job_id == loser.id)))
        .scalars()
        .all()
    )
    for link in links:
        link.job_id = winner.id
        link.match_confidence = verdict.confidence
        link.link_reason = verdict.reason

    # The winner keeps the earlier discovery date: it is the same opening, and
    # the earlier sighting is the true one. Overwriting it with the later of the
    # two would make every merge look like a brand-new posting.
    winner.first_seen_at = min(winner.first_seen_at, loser.first_seen_at)
    winner.last_seen_at = max(winner.last_seen_at, loser.last_seen_at)

    await session.flush()
    # Before the delete, not after: the loser's location rows cascade with it.
    await _absorb_locations(session, winner=winner, loser=loser)
    await session.delete(loser)
    await session.flush()


async def mark_listed(
    session: AsyncSession,
    *,
    source: Source,
    token: str,
    source_job_ids: Sequence[str],
    now: datetime,
) -> int:
    """Record that these postings were on the board, without re-reading them.

    This is the seam between ADR 0007's two phases, and the reason M1d does not
    close every unchanged posting on every Greenhouse board.

    :func:`apply_freshness` ages any record whose ``last_seen_at`` is older than
    the run, reasoning that persisting a posting sets it to ``now`` so anything
    older was absent from the payload. That reasoning holds only while every
    listed posting is also persisted. Under phase 2 it is false by design: an
    unchanged posting is deliberately never refetched, so it would look absent
    and take a miss on every single poll.

    "The board listed it" is the fact that keeps a posting open. "We refetched
    its content and read it" is a different and stronger fact, and it belongs to
    ``last_verified_at`` — which this function deliberately does not touch, so
    the distinction the schema already draws is preserved rather than blurred.

    Returns the number of records updated.
    """
    if not source_job_ids:
        return 0

    # `session.execute` is typed as returning `Result`, but an UPDATE always
    # yields a `CursorResult`, which is where `rowcount` lives. The cast states
    # that rather than reaching for `getattr`, which would silently return 0 if
    # the statement type ever changed.
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            update(SourceJobRecord)
            .where(
                SourceJobRecord.source_id == source.id,
                SourceJobRecord.source_company_key == token,
                SourceJobRecord.source_job_id.in_(list(source_job_ids)),
            )
            .values(
                last_seen_at=now,
                consecutive_misses=0,
                source_status=SourceStatus.ACTIVE,
            )
        ),
    )
    return int(result.rowcount or 0)


async def _known_posting_count(session: AsyncSession, *, source: Source, token: str) -> int:
    """How many postings we already hold for this board.

    Zero means this board has never been ingested, which is the one case
    ADR 0007 lets us use ``content=true`` for. Counting rows rather than
    consulting a "has this board been polled" flag on purpose: the question is
    whether there is anything to diff *against*, and an emptied-then-refilled
    board genuinely has nothing.
    """
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(SourceJobRecord)
                .where(
                    SourceJobRecord.source_id == source.id,
                    SourceJobRecord.source_company_key == token,
                )
            )
        ).scalar_one()
    )


async def _postings_needing_content(
    session: AsyncSession, *, source: Source, outcome: FetchOutcome
) -> list[str]:
    """Which listed postings must be refetched: new ones, and changed ones.

    Only reached for a two-phase provider. Greenhouse publishes ``updated_at``
    on its listing, which is what makes this diff possible; Lever and Ashby
    publish no such field and need none, because their board response already
    carries every posting in full.

    Every ambiguous case resolves towards refetching. A posting we have never
    seen, one whose stored timestamp is NULL, and one whose listing carries no
    timestamp are all refetched, because the cost of being wrong in that
    direction is one request, while the cost of being wrong in the other is
    never seeing a change at all.
    """
    known = {
        row.source_job_id: row.source_updated_at
        for row in (
            await session.execute(
                select(
                    SourceJobRecord.source_job_id,
                    SourceJobRecord.source_updated_at,
                ).where(
                    SourceJobRecord.source_id == source.id,
                    SourceJobRecord.source_company_key == outcome.board.token,
                )
            )
        ).all()
    }

    needed: list[str] = []
    for posting in outcome.listed:
        stored = known.get(posting.source_job_id)
        if posting.source_job_id not in known or stored is None:
            needed.append(posting.source_job_id)
        elif posting.source_updated_at is None or posting.source_updated_at > stored:
            needed.append(posting.source_job_id)
    return needed


async def apply_freshness(
    session: AsyncSession,
    *,
    source: Source,
    polled_tokens: Sequence[str],
    run: IngestionRun,
    now: datetime,
) -> int:
    """Age every record on the boards that answered, then re-decide their jobs.

    ``polled_tokens`` carries only the boards whose fetch succeeded, and that
    argument is where invariant I3 lives in this function. A board that failed
    is not in the list, so none of its records are aged and none of its jobs
    are re-decided. There is deliberately no parameter by which a caller could
    ask for a failed board to be processed anyway — the guard is structural,
    not a condition someone can forget to write.

    Returns the number of jobs that newly became ``closed``.
    """
    if not polled_tokens:
        return 0

    tokens = list(polled_tokens)

    # A record on a board that answered, which this run did not touch, was not
    # in the response. `last_seen_at < now` is the test for that: persisting a
    # posting sets it to `now`, so anything older was absent from the payload.
    stale_records = (
        (
            await session.execute(
                select(SourceJobRecord).where(
                    SourceJobRecord.source_id == source.id,
                    SourceJobRecord.source_company_key.in_(tokens),
                    SourceJobRecord.last_seen_at < now,
                )
            )
        )
        .scalars()
        .all()
    )
    for record in stale_records:
        record.consecutive_misses += 1
        record.source_status = SourceStatus.MISSING
    await session.flush()

    # Re-decide every job reachable from this source's polled boards, not only
    # the ones that just went missing: a job whose second source vanished has
    # not changed itself, but its verdict may have.
    jobs = (
        (
            await session.execute(
                select(Job)
                .join(JobSourceLink, JobSourceLink.job_id == Job.id)
                .join(
                    SourceJobRecord,
                    SourceJobRecord.id == JobSourceLink.source_job_record_id,
                )
                .where(
                    SourceJobRecord.source_id == source.id,
                    SourceJobRecord.source_company_key.in_(tokens),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )

    closed = 0
    for job in jobs:
        # Every record describing this job, across all sources — not only the
        # one being polled. A job listed by two boards is missing only when
        # both stop listing it, and that is decided in freshness.py.
        observations = (
            await session.execute(
                select(SourceJobRecord.consecutive_misses, SourceJobRecord.last_seen_at)
                .join(
                    JobSourceLink,
                    JobSourceLink.source_job_record_id == SourceJobRecord.id,
                )
                .where(JobSourceLink.job_id == job.id)
            )
        ).all()

        decision = decide_job_status(
            current=job.status,
            records=[
                RecordObservation(consecutive_misses=misses, last_seen_at=last_seen)
                for misses, last_seen in observations
            ],
            board_last_success_at=source.last_success_at,
            now=now,
        )
        if decision.status is job.status:
            # Not a transition. Writing a row per poll would bury the real
            # transitions under thousands of no-ops.
            continue

        session.add(
            JobStatusEvent(
                job_id=job.id,
                from_status=job.status,
                to_status=decision.status,
                reason=decision.reason,
                ingestion_run_id=run.id,
                observed_misses=min((m for m, _ in observations), default=None),
            )
        )
        job.status = decision.status
        # The `closed_at_matches_status` check constraint pairs these two, so a
        # buggy transition is a database error rather than a silent one.
        job.closed_at = now if decision.status is JobStatus.CLOSED else None
        if decision.status is JobStatus.CLOSED:
            closed += 1
            # I5: the person tracking this role finds out; the system does not
            # decide for them. `record_listing_closed` writes an event with a
            # `system` actor, which the database will not let carry a stage.
            await record_listing_closed(session, job_id=job.id, now=now, reason=decision.reason)

    await session.flush()
    return closed


async def ingest_boards(
    session: AsyncSession,
    adapter: JobSourceAdapter,
    boards: Sequence[BoardRef],
    *,
    source: Source,
    now: datetime | None = None,
    etags: Mapping[str, str | None] | None = None,
) -> tuple[IngestionRun, IngestionStats]:
    """Poll every board and persist what came back.

    The run row is created before any fetch and closed after the last one, so an
    ingestion that crashes leaves a ``running`` row rather than no evidence at
    all — §2.6 requires source reliability to be visible, which means visible on
    the bad days too.

    ``etags`` maps board token to the ETag last served for it. Absent or None
    means poll unconditionally, which is right for a board nobody has seen and
    for a caller that does not track them (``make seed``, the fixture path).
    Whatever each board serves back comes out on ``stats.etags``.
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
        outcome = await adapter.fetch_board(board, etag=etags.get(board.token) if etags else None)
        if not outcome.ok:
            # I3: we learned nothing. No listing state changes, nothing closes,
            # and — crucially — no miss counter moves. See apply_freshness.
            stats.boards_failed.append(board.token)
            stats.errors.append(f"{board.ats}:{board.token}: {outcome.error}")
            source.last_failure_at = timestamp
            log.warning("ingest_board_failed", board=board.token, error=outcome.error)
            continue

        stats.boards_ok.append(board.token)
        # Set before apply_freshness reads it, or the first poll of a new source
        # would decide `unverified` on a board that just answered.
        source.last_success_at = timestamp
        stats.etags[board.token] = outcome.etag

        if outcome.not_modified:
            # I3 at the level ADR 0007 introduced. The listing is byte-identical
            # to the copy we already parsed, so every posting we know about is
            # still listed and nothing about them has changed. Nothing is
            # written and — critically — this board is kept out of
            # `boards_listed`, because ageing its records against a timestamp
            # the board never wrote would close the whole board.
            stats.not_modified.append(board.token)
            log.info("ingest_board_not_modified", board=board.token)
            continue

        stats.boards_listed.append(board.token)

        # Every posting the board listed is still open, whether or not its
        # content is refetched below. This is the line that stops phase 2 from
        # closing every unchanged posting — see mark_listed.
        await mark_listed(
            session,
            source=source,
            token=board.token,
            source_job_ids=outcome.listed_source_job_ids,
            now=timestamp,
        )

        if adapter.is_two_phase:
            # The flag declares intent; the Protocol is only structural, so it
            # answers True for anything that happens to have both method names
            # — including a single-phase test stub that implements them for
            # convenience. Gating on the flag and *then* narrowing means a
            # provider cannot be dragged into phase 2 by accident, and a
            # provider that claims two phases without implementing them fails
            # loudly here instead of silently ingesting nothing.
            if not isinstance(adapter, TwoPhaseJobSourceAdapter):
                raise TypeError(
                    f"{type(adapter).__name__} sets is_two_phase but does not implement "
                    "fetch_postings and fetch_full_board"
                )
            known = await _known_posting_count(session, source=source, token=board.token)
            if known == 0 and outcome.listed:
                # First ingestion of this board. ADR 0007 reserves content=true
                # for exactly this: nothing is stored, so every posting counts
                # as changed, and phase 2 would mean one request each — 429 of
                # them on Datadog, to fetch what one request returns. The
                # listing above is not wasted; it is where the ETag future polls
                # revalidate against comes from, and it costs 33 KB once.
                full = await adapter.fetch_full_board(board)
                if full.ok:
                    outcome = outcome.model_copy(update={"jobs": full.jobs})
                else:
                    # I3: the cheap listing succeeded, so the postings are known
                    # to exist and have already been marked listed. Only their
                    # content is missing. Nothing closes.
                    stats.failed += len(outcome.listed)
                    stats.errors.append(
                        f"{board.ats}:{board.token}: first ingestion fetch failed: {full.error}"
                    )
                    log.warning("first_ingestion_failed", board=board.token, error=full.error)
                    continue
            else:
                changed = await _postings_needing_content(session, source=source, outcome=outcome)
                fetched, failed_ids = await adapter.fetch_postings(board, changed)
                for job_id in failed_ids:
                    # A posting that failed to fetch was still on the listing, so
                    # it is still open. Counted and surfaced, never aged (I3).
                    stats.failed += 1
                    stats.errors.append(f"{board.ats}:{board.token}: fetch posting {job_id}")
                outcome = outcome.model_copy(update={"jobs": fetched})

        await _persist_outcome(session, adapter, outcome, source=source, stats=stats, now=timestamp)

    # Only the boards that answered *with a listing*. A failed board contributes
    # no evidence; a board that answered 304 contributes no *new* evidence, and
    # ageing its records against a run it never described would close all of them.
    stats.closed = await apply_freshness(
        session, source=source, polled_tokens=stats.boards_listed, run=run, now=timestamp
    )

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
            normalized = adapter.normalize(raw_job, outcome.board)
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
