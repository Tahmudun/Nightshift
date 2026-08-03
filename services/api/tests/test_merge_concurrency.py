"""Two workers merging the same pair. M1d, and M1b's carried defect.

The M1b review named this as the one thing M1d must not inherit unnoticed, and
M1d is exactly what makes it reachable: ADR 0007 gives every board its own ARQ
job, so two polls can run at once and each can independently decide that
postings A and B are the same opening.

Without a lock, both transactions read both rows, each writes a merge event,
each re-points the other's links, and each deletes the other's winner. The pair
vanishes, or one transaction raises on a row that is already gone. Neither
outcome is recoverable from the canonical tables — only from the raw records.

**This file does not use the ``db_session`` fixture.** That fixture holds one
transaction and rolls it back, which is the right isolation for every other
test and precisely wrong here: two sessions inside one transaction cannot
contend, so the race under test could not occur. These tests commit, contend
for real, and clean up after themselves.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from nightshift.db.base import JobStatus
from nightshift.db.models import (
    Company,
    Job,
    JobMergeEvent,
    JobSourceLink,
    Source,
    SourceJobRecord,
)
from nightshift.db.types import utcnow
from nightshift.domain.dedupe import DedupeVerdict
from nightshift.domain.ingestion import merge_jobs
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

VERDICT = DedupeVerdict(merge=True, reason="identical_content", confidence=1.0)


async def _seed_pair(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Two jobs, each with its own raw record and link. Committed.

    Returns ``(company_id, job_a_id, job_b_id)``. Committed rather than held in
    a transaction because the two contending sessions below have to be able to
    see them.
    """
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    marker = uuid.uuid4().hex[:8]
    now = utcnow()

    async with maker() as session, session.begin():
        company = Company(
            canonical_name=f"Acme {marker}", normalized_name=f"acme concurrency {marker}"
        )
        session.add(company)
        source = Source(name=f"concurrency_{marker}", source_type="ats_lever")
        session.add(source)
        await session.flush()

        job_ids: list[uuid.UUID] = []
        for n in range(2):
            job = Job(
                company_id=company.id,
                title="Engineer",
                normalized_title="engineer",
                first_seen_at=now,
                last_seen_at=now,
                status=JobStatus.OPEN,
            )
            session.add(job)
            await session.flush()

            record = SourceJobRecord(
                source_id=source.id,
                source_job_id=f"{marker}-{n}",
                source_company_key="acme",
                raw_payload={"id": f"{marker}-{n}"},
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(record)
            await session.flush()

            session.add(
                JobSourceLink(
                    job_id=job.id,
                    source_job_record_id=record.id,
                    match_confidence=1.0,
                    link_reason="sole_source_record",
                )
            )
            job_ids.append(job.id)

    return company.id, job_ids[0], job_ids[1]


async def _cleanup(engine: AsyncEngine, company_id: uuid.UUID) -> None:
    """Remove what this test committed, so the next one starts clean.

    ``TRUNCATE`` rather than ``DELETE``, and not for speed: ``job_merge_events``
    is append-only, enforced by a row trigger (CLAUDE.md §7), so a ``DELETE``
    against it is refused — including the cascade from deleting a job. That
    refusal is M1b's guarantee working exactly as intended, and the right answer
    is to stop trying to delete rather than to weaken the trigger.

    The same table list ``conftest`` truncates, imported rather than retyped so
    a table added to one is added to both.
    """
    from tests.conftest import _INGESTION_TABLES

    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        await session.execute(text(f"TRUNCATE TABLE {', '.join(_INGESTION_TABLES)}"))


async def _merge_in_its_own_transaction(
    engine: AsyncEngine, winner_id: uuid.UUID, loser_id: uuid.UUID
) -> None:
    maker = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        winner = await session.get(Job, winner_id)
        loser = await session.get(Job, loser_id)
        if winner is None or loser is None:
            # The other worker got there first and deleted one of them. Nothing
            # to do, and emphatically not an error.
            return
        await merge_jobs(session, winner=winner, loser=loser, verdict=VERDICT)


class TestConcurrentMerges:
    async def test_two_workers_merging_the_same_pair_leave_one_survivor(
        self, db_engine: AsyncEngine
    ) -> None:
        """The defect M1b carried and M1d makes reachable.

        Both transactions decide A and B are duplicates, in opposite
        directions — which is the realistic case, because each worker picks the
        winner from its own board's perspective.
        """
        company_id, job_a, job_b = await _seed_pair(db_engine)
        try:
            results = await asyncio.gather(
                _merge_in_its_own_transaction(db_engine, job_a, job_b),
                _merge_in_its_own_transaction(db_engine, job_b, job_a),
                return_exceptions=True,
            )

            maker = async_sessionmaker(bind=db_engine, expire_on_commit=False)
            async with maker() as session:
                survivors = (
                    (await session.execute(select(Job).where(Job.id.in_([job_a, job_b]))))
                    .scalars()
                    .all()
                )
                links = (
                    (
                        await session.execute(
                            select(JobSourceLink).where(JobSourceLink.job_id.in_([job_a, job_b]))
                        )
                    )
                    .scalars()
                    .all()
                )

            failures = [r for r in results if isinstance(r, BaseException)]
            assert not failures, f"a merge raised: {failures}"
            assert len(survivors) == 1, (
                f"expected exactly one survivor, got {len(survivors)} — "
                "both workers deleted the other's winner"
            )
            assert len(links) == 2, (
                "the survivor must carry both source links; a lost link is a "
                "canonical job that no longer traces to a raw record"
            )
        finally:
            await _cleanup(db_engine, company_id)

    async def test_the_second_merge_is_a_no_op_not_a_crash(self, db_engine: AsyncEngine) -> None:
        """Sequentially, which is what the losing worker experiences after the
        winner commits: the pair is already merged and one row is gone."""
        company_id, job_a, job_b = await _seed_pair(db_engine)
        try:
            await _merge_in_its_own_transaction(db_engine, job_a, job_b)
            await _merge_in_its_own_transaction(db_engine, job_a, job_b)  # must not raise

            maker = async_sessionmaker(bind=db_engine, expire_on_commit=False)
            async with maker() as session:
                survivors = (
                    (await session.execute(select(Job).where(Job.id.in_([job_a, job_b]))))
                    .scalars()
                    .all()
                )
                events = (
                    (
                        await session.execute(
                            select(JobMergeEvent).where(JobMergeEvent.winner_job_id == job_a)
                        )
                    )
                    .scalars()
                    .all()
                )

            assert len(survivors) == 1
            assert len(events) == 1, "a repeated merge must not write a second audit row"
        finally:
            await _cleanup(db_engine, company_id)

    async def test_merging_three_ways_still_leaves_one(self, db_engine: AsyncEngine) -> None:
        """Three workers, three orderings. Deterministic lock ordering is what
        stops two of them each holding the row the other wants."""
        company_id, job_a, job_b = await _seed_pair(db_engine)
        try:
            results = await asyncio.gather(
                _merge_in_its_own_transaction(db_engine, job_a, job_b),
                _merge_in_its_own_transaction(db_engine, job_b, job_a),
                _merge_in_its_own_transaction(db_engine, job_a, job_b),
                return_exceptions=True,
            )

            maker = async_sessionmaker(bind=db_engine, expire_on_commit=False)
            async with maker() as session:
                survivors = (
                    (await session.execute(select(Job).where(Job.id.in_([job_a, job_b]))))
                    .scalars()
                    .all()
                )

            deadlocks = [
                r for r in results if isinstance(r, BaseException) and "deadlock" in str(r).lower()
            ]
            assert not deadlocks, f"lock ordering failed: {deadlocks}"
            assert len(survivors) == 1
        finally:
            await _cleanup(db_engine, company_id)
