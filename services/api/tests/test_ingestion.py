"""The fetch -> preserve -> normalize -> persist pipeline, against a real database.

Every test here needs Postgres, because the behaviour under test is
transactional: savepoints, unique constraints, FK ordering and idempotency are
not observable against a fake session. Run `make up && make migrate` first —
or, if Postgres is already up (as it is in this environment), the `db_engine`
fixture in conftest.py finds it itself; nothing here reads an env var to
decide whether to run.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, ListedPosting, RawJob
from nightshift.adapters.greenhouse import GreenhouseAdapter
from nightshift.adapters.lever import LeverAdapter
from nightshift.db.base import JobStatus, SourceStatus, SourceType
from nightshift.db.models import (
    Company,
    Job,
    JobEmbedding,
    JobLocation,
    JobSourceLink,
    JobStatusEvent,
    SourceJobRecord,
)
from nightshift.domain.ingestion import (
    get_or_create_company,
    get_or_create_source,
    ingest_boards,
)
from tests.conftest import requires_db

# `db_session` binds its asyncpg connection on the session-scoped event loop
# (conftest.db_engine), because asyncpg connections cannot cross loops. Every
# test that uses it must therefore run on that same loop, or the connection
# raises "attached to a different loop" the instant it awaits.
pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

FIXTURES = Path(__file__).parent / "fixtures"
LEVER_BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)


class _StubAdapter:
    """A real adapter with its network call replaced by a recorded outcome.

    The adapter's own normalize() runs untouched — replacing that would be
    mocking the thing under test.

    ``phase_two`` supplies what :meth:`fetch_postings` returns, so a two-phase
    provider can be exercised through the pipeline without a network. Every
    call is recorded on ``fetched_ids``, because "which postings did we
    actually ask for" is the question this milestone turns on and it is not
    visible from the resulting rows.
    """

    def __init__(
        self,
        inner: Any,
        outcome: FetchOutcome,
        *,
        two_phase: bool = False,
        phase_two: tuple[RawJob, ...] = (),
        phase_two_failures: list[str] | None = None,
        full_board_fails: bool = False,
    ) -> None:
        self._inner = inner
        self._outcome = outcome
        self._phase_two = phase_two
        self._phase_two_failures = phase_two_failures or []
        self._full_board_fails = full_board_fails
        self.source_name = inner.source_name
        self.source_type = inner.source_type
        self.parser_version = getattr(inner, "parser_version", "1")
        self.is_two_phase = two_phase
        self.fetched_ids: list[list[str]] = []
        self.seen_etags: list[str | None] = []
        self.full_board_calls = 0

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        self.seen_etags.append(etag)
        return self._outcome

    async def fetch_postings(
        self, board: BoardRef, source_job_ids: Sequence[str]
    ) -> tuple[tuple[RawJob, ...], list[str]]:
        self.fetched_ids.append(list(source_job_ids))
        wanted = set(source_job_ids)
        return (
            tuple(job for job in self._phase_two if job.source_job_id in wanted),
            [job_id for job_id in self._phase_two_failures if job_id in wanted],
        )

    async def fetch_full_board(self, board: BoardRef) -> FetchOutcome:
        """The first-ingestion path (ADR 0007). Recorded on ``full_board_calls``.

        Implemented even on stubs used for single-phase tests, because
        ``TwoPhaseJobSourceAdapter`` is a runtime-checkable Protocol and an
        adapter missing this method silently falls back to the single-phase
        branch — which is a green suite testing the wrong code path.
        """
        self.full_board_calls += 1
        if self._full_board_fails:
            return FetchOutcome(board=board, ok=False, http_status=503, error="HTTP 503")
        return FetchOutcome(board=board, ok=True, jobs=self._phase_two, http_status=200)

    def normalize(self, raw_job: RawJob, board: BoardRef) -> Any:
        # JobSourceAdapter has exactly one normalize method (raw_job, board) —
        # there is no normalize_with_board on the Protocol.
        return self._inner.normalize(raw_job, board)


def _listed_from(jobs: tuple[RawJob, ...]) -> tuple[ListedPosting, ...]:
    """What a single-phase provider reports: everything fetched was listed."""
    return tuple(
        ListedPosting(source_job_id=job.source_job_id, source_updated_at=None) for job in jobs
    )


def _lever_outcome(ok: bool = True) -> FetchOutcome:
    payload = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    jobs = tuple(
        RawJob(
            source_job_id=str(j["id"]),
            source_company_key="alloy",
            canonical_url=j.get("hostedUrl"),
            payload=j,
        )
        for j in payload
    )
    if not ok:
        return FetchOutcome(board=LEVER_BOARD, ok=False, http_status=503, error="HTTP 503")
    return FetchOutcome(
        board=LEVER_BOARD,
        ok=True,
        jobs=jobs,
        # Mirrors the real Lever adapter: single-phase, so everything fetched is
        # everything listed. Omitting this would make freshness see a board that
        # listed nothing and age every posting the same run just created.
        listed=_listed_from(jobs),
        http_status=200,
    )


async def _count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def _job_state_snapshot(session: AsyncSession) -> tuple[int, ...]:
    """The concrete form of "zero writes to job state" (design §5).

    Criterion 13 says "zero writes". A 304 *does* write one row — the board's
    own poll bookkeeping — and that is the point of polling, not a claim about
    any job. So what is asserted is that nothing describing a *job* moved:
    every table that holds job state, plus the miss counter and the closed
    count, which are the two values a silent regression would change without
    changing any row count at all.
    """
    counts = [
        await _count(session, model)
        for model in (
            SourceJobRecord,
            Job,
            JobLocation,
            JobSourceLink,
            JobStatusEvent,
            JobEmbedding,
        )
    ]
    counts.append(
        int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(SourceJobRecord.consecutive_misses), 0))
                )
            ).scalar_one()
        )
    )
    counts.append(
        int(
            (
                await session.execute(
                    select(func.count()).select_from(Job).where(Job.status == JobStatus.CLOSED)
                )
            ).scalar_one()
        )
    )
    return tuple(counts)


async def _ingest(session: AsyncSession, outcome: FetchOutcome) -> Any:
    source = await get_or_create_source(
        session, name="lever_test", source_type=SourceType.ATS_LEVER
    )
    adapter = _StubAdapter(LeverAdapter(client=None), outcome)
    return await ingest_boards(session, adapter, [LEVER_BOARD], source=source)


async def test_every_canonical_job_traces_to_a_raw_record(db_session: AsyncSession) -> None:
    """M1 acceptance criterion, asserted directly."""
    await _ingest(db_session, _lever_outcome())

    orphans = (
        await db_session.execute(
            select(func.count())
            .select_from(Job)
            .outerjoin(JobSourceLink, JobSourceLink.job_id == Job.id)
            .where(JobSourceLink.id.is_(None))
        )
    ).scalar_one()
    assert orphans == 0
    assert await _count(db_session, SourceJobRecord) == 9


async def test_reingestion_is_idempotent(db_session: AsyncSession) -> None:
    """M1 acceptance: no dupes, no spurious updates."""
    _, first = await _ingest(db_session, _lever_outcome())
    assert first.created == 9
    assert first.updated == 0

    jobs_after_first = await _count(db_session, Job)

    _, second = await _ingest(db_session, _lever_outcome())
    assert second.created == 0
    assert second.updated == 0, "a re-poll of unchanged data reported an update"
    assert second.unchanged == 9
    assert await _count(db_session, Job) == jobs_after_first


async def test_a_failed_board_closes_nothing(db_session: AsyncSession) -> None:
    """M1 acceptance: simulated source outage closes zero jobs (I3)."""
    await _ingest(db_session, _lever_outcome())
    open_before = int(
        (
            await db_session.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN)
            )
        ).scalar_one()
    )
    assert open_before == 9

    _, stats = await _ingest(db_session, _lever_outcome(ok=False))

    assert stats.closed == 0
    assert stats.boards_failed == ["alloy"]
    open_after = int(
        (
            await db_session.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN)
            )
        ).scalar_one()
    )
    assert open_after == open_before


def _synthetic_multi_location_raw_job() -> RawJob:
    """A fabricated posting, not a recording — labelled unmistakably as such.

    Every real posting in ``alloy_board.json`` happens to name exactly one
    location (verified by inspection: each entry's ``categories.allLocations``
    has length 1). Without a posting that names two, the "multi-location
    postings produce multiple job_locations rows" acceptance criterion is
    unfalsifiable: `max(count) >= 1` and `count(JobLocation) >= 9` hold even
    if the pipeline could never write more than one location row per job.
    This job is invented here, in the test, for exactly that gap — it borrows
    one real posting's shape only to stay schema-valid, and its id and title
    say plainly that it is not a real Alloy opening.
    """
    template = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())[0]
    payload = {
        **template,
        "id": "SYNTHETIC-TEST-FIXTURE-not-a-real-alloy-posting",
        "text": "SYNTHETIC TEST POSTING (multi-location coverage) — not a real Alloy job",
        "categories": {
            **template["categories"],
            "location": "New York, NY",
            "allLocations": ["New York, NY", "Boston, MA"],
        },
    }
    return RawJob(
        source_job_id=str(payload["id"]),
        source_company_key="alloy",
        canonical_url=None,
        payload=payload,
    )


async def test_multi_location_posting_yields_multiple_rows(db_session: AsyncSession) -> None:
    """A2 and an M1 acceptance criterion, end to end into the table.

    The real fixture has no multi-location posting to exercise this with, so
    one fabricated (and clearly labelled) posting is added to the batch. Its
    two `allLocations` entries must land as two distinct `job_locations` rows
    for that one job — a single collapsed row would still leave the other
    assertions in this suite green, which is exactly the gap this closes.
    """
    outcome = _lever_outcome()
    outcome = outcome.model_copy(
        update={"jobs": (*outcome.jobs, _synthetic_multi_location_raw_job())}
    )
    await _ingest(db_session, outcome)
    per_job = (
        await db_session.execute(
            select(JobLocation.job_id, func.count()).group_by(JobLocation.job_id)
        )
    ).all()
    assert per_job
    assert max(count for _, count in per_job) >= 2, "no job has more than one location row"
    assert await _count(db_session, JobLocation) == 11  # 9 real (1 each) + synthetic (2)


async def test_no_location_row_has_a_coordinate(db_session: AsyncSession) -> None:
    """I1 at the storage layer. Geocoding has not run, so nothing is placed."""
    await _ingest(db_session, _lever_outcome())
    placed = int(
        (
            await db_session.execute(
                select(func.count())
                .select_from(JobLocation)
                .where(JobLocation.latitude.is_not(None))
            )
        ).scalar_one()
    )
    assert placed == 0


async def test_repeated_company_creation_does_not_duplicate(db_session: AsyncSession) -> None:
    """Task 8's upsert, exercised through the name variants that must merge.

    test_companies.py proves normalize_company_name folds these together; this
    proves the insert path honours it rather than raising on the unique index.
    """
    for name in ("Moody's Analytics", "Moodys Analytics", "MOODY'S ANALYTICS"):
        await get_or_create_company(db_session, name)
    await db_session.flush()
    assert await _count(db_session, Company) == 1


async def test_a_posting_that_fails_to_persist_does_not_abort_the_board(
    db_session: AsyncSession,
) -> None:
    """The savepoint in _persist_outcome, proven by making one posting fail
    a real database statement — not the normalize() step before it.

    An empty title raises ValueError inside LeverAdapter.normalize(), which
    is caught by the `try/except` around normalize() in _persist_outcome
    (ingestion.py) *before* any session.execute() runs — so it never reaches
    `session.begin_nested()` and proves nothing about the savepoint. Setting
    the title past the `jobs.title` column's `String(500)` limit instead
    passes normalize() cleanly and fails at flush time, inside the savepoint,
    which is what `_persist_outcome`'s nested transaction exists to contain.

    Without the savepoint, that failed INSERT poisons the shared transaction
    and every posting after it in the board fails too — so this asserts the
    survivors, not just the failure count.
    """
    outcome = _lever_outcome()
    broken = outcome.jobs[0].model_copy(
        update={"payload": {**outcome.jobs[0].payload, "text": "A" * 600}}
    )
    outcome = outcome.model_copy(update={"jobs": (broken, *outcome.jobs[1:])})

    _, stats = await _ingest(db_session, outcome)

    assert stats.failed == 1
    assert stats.created == 8
    assert await _count(db_session, Job) == 8


async def test_ingestion_run_records_the_failure(db_session: AsyncSession) -> None:
    """M1 acceptance: ingestion failures are visible, not only in logs."""
    run, _ = await _ingest(db_session, _lever_outcome(ok=False))
    assert run.error_summary is not None
    assert "alloy" in run.error_summary
    assert run.records_closed == 0


# ---------------------------------------------------------------------------
# M1d: two-phase polling. docs/architecture/conditional-polling.md §4 and §5.
# ---------------------------------------------------------------------------


GREENHOUSE_BOARD = BoardRef(company="Acme", ats="greenhouse", token="acme", nyc_presence=True)


def _greenhouse_posting(job_id: str, *, title: str, updated_at: str) -> RawJob:
    """A posting shaped like Greenhouse's, normalizable by the real adapter."""
    return RawJob(
        source_job_id=job_id,
        source_company_key="acme",
        canonical_url=f"https://boards.greenhouse.io/acme/jobs/{job_id}",
        payload={
            "id": int(job_id),
            "title": title,
            "content": f"&lt;p&gt;Description for {title}&lt;/p&gt;",
            "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{job_id}",
            "location": {"name": "New York, New York, USA"},
            "updated_at": updated_at,
            "first_published": "2026-01-01T00:00:00-05:00",
            "metadata": [],
        },
    )


async def _ingest_greenhouse(
    session: AsyncSession,
    adapter: _StubAdapter,
    *,
    now: Any = None,
) -> Any:
    source = await get_or_create_source(
        session, name="greenhouse_test", source_type=SourceType.ATS_GREENHOUSE
    )
    return await ingest_boards(session, adapter, [GREENHOUSE_BOARD], source=source, now=now)


class TestTwoPhaseFreshness:
    """The defect ADR 0007 creates, and the guard against it.

    `apply_freshness` ages a record whose `last_seen_at` is older than the run,
    on the reasoning that persisting a posting sets it to `now`. That reasoning
    holds only while every listed posting is also persisted. Phase 2 breaks it
    deliberately: an unchanged posting is never refetched, so it looks absent.

    Nothing errors. The damage lands three polls later, which is exactly the
    delayed shape the M1b review called out when it moved a closure assertion
    off the job status and onto the miss counter.
    """

    async def test_an_unchanged_posting_takes_no_miss_when_it_is_not_refetched(
        self, db_session: AsyncSession
    ) -> None:
        """Ten listed, one changed and refetched, nine not fetched at all.

        The nine must take zero misses. Without mark_listed they take one each,
        every poll, and close on the third — the whole board, silently.
        """
        postings = tuple(
            _greenhouse_posting(str(n), title=f"Role {n}", updated_at="2026-07-01T00:00:00-04:00")
            for n in range(10)
        )
        first = FetchOutcome(
            board=GREENHOUSE_BOARD,
            ok=True,
            listed=tuple(
                ListedPosting(
                    source_job_id=p.source_job_id,
                    source_updated_at=datetime(2026, 7, 1, 4, tzinfo=UTC),
                )
                for p in postings
            ),
            http_status=200,
        )
        adapter = _StubAdapter(
            GreenhouseAdapter(client=None),  # type: ignore[arg-type]
            first,
            two_phase=True,
            phase_two=postings,
        )
        await _ingest_greenhouse(db_session, adapter)
        assert await _count(db_session, SourceJobRecord) == 10

        # Second poll an hour later. The board still lists all ten; only #0
        # moved its updated_at, so only #0 should be refetched.
        changed = _greenhouse_posting(
            "0", title="Role 0 (revised)", updated_at="2026-07-02T00:00:00-04:00"
        )
        second = FetchOutcome(
            board=GREENHOUSE_BOARD,
            ok=True,
            listed=(
                ListedPosting(
                    source_job_id="0", source_updated_at=datetime(2026, 7, 2, 4, tzinfo=UTC)
                ),
                *(
                    ListedPosting(
                        source_job_id=str(n),
                        source_updated_at=datetime(2026, 7, 1, 4, tzinfo=UTC),
                    )
                    for n in range(1, 10)
                ),
            ),
            http_status=200,
        )
        adapter2 = _StubAdapter(
            GreenhouseAdapter(client=None),  # type: ignore[arg-type]
            second,
            two_phase=True,
            phase_two=(changed,),
        )
        _run, stats = await _ingest_greenhouse(db_session, adapter2)

        records = (await db_session.execute(select(SourceJobRecord))).scalars().all()

        assert adapter2.fetched_ids == [["0"]], (
            "phase 2 must fetch only the posting whose updated_at moved"
        )
        assert stats.closed == 0
        assert len(records) == 10
        assert {r.consecutive_misses for r in records} == {0}, (
            "a posting the board still lists must not take a miss just because "
            "we did not refetch its content"
        )
        assert {r.source_status for r in records} == {SourceStatus.ACTIVE}

    async def test_a_posting_the_board_stopped_listing_still_takes_a_miss(
        self, db_session: AsyncSession
    ) -> None:
        """The guard must not become "nothing ever ages".

        Dropping out of the listing is exactly how a real closure starts, and a
        fix for the previous test that also suppressed this one would satisfy
        I3 by never trusting anything.
        """
        postings = tuple(
            _greenhouse_posting(str(n), title=f"Role {n}", updated_at="2026-07-01T00:00:00-04:00")
            for n in range(3)
        )
        first = FetchOutcome(
            board=GREENHOUSE_BOARD,
            ok=True,
            listed=_listed_from(postings),
            http_status=200,
        )
        await _ingest_greenhouse(
            db_session,
            _StubAdapter(
                GreenhouseAdapter(client=None),  # type: ignore[arg-type]
                first,
                two_phase=True,
                phase_two=postings,
            ),
        )

        # Posting 2 is gone from the board.
        second = FetchOutcome(
            board=GREENHOUSE_BOARD,
            ok=True,
            listed=_listed_from(postings[:2]),
            http_status=200,
        )
        await _ingest_greenhouse(
            db_session,
            _StubAdapter(
                GreenhouseAdapter(client=None),  # type: ignore[arg-type]
                second,
                two_phase=True,
                phase_two=(),
            ),
        )

        by_id = {
            r.source_job_id: r
            for r in (await db_session.execute(select(SourceJobRecord))).scalars().all()
        }
        assert by_id["0"].consecutive_misses == 0
        assert by_id["1"].consecutive_misses == 0
        assert by_id["2"].consecutive_misses == 1
        assert by_id["2"].source_status == SourceStatus.MISSING

    async def test_a_304_writes_nothing_and_ages_nothing(self, db_session: AsyncSession) -> None:
        """M1 criterion 13, at the pipeline level.

        A 304 says the listing is byte-identical, so every posting we know about
        is still listed. Ageing against a timestamp the board never wrote would
        close the entire board — the I3 failure at the level ADR 0007 introduced.
        """
        postings = tuple(
            _greenhouse_posting(str(n), title=f"Role {n}", updated_at="2026-07-01T00:00:00-04:00")
            for n in range(5)
        )
        await _ingest_greenhouse(
            db_session,
            _StubAdapter(
                GreenhouseAdapter(client=None),  # type: ignore[arg-type]
                FetchOutcome(
                    board=GREENHOUSE_BOARD,
                    ok=True,
                    listed=_listed_from(postings),
                    http_status=200,
                ),
                two_phase=True,
                phase_two=postings,
            ),
        )
        before = await _job_state_snapshot(db_session)

        adapter = _StubAdapter(
            GreenhouseAdapter(client=None),  # type: ignore[arg-type]
            FetchOutcome(
                board=GREENHOUSE_BOARD,
                ok=True,
                not_modified=True,
                etag='W/"abc"',
                http_status=304,
            ),
            two_phase=True,
        )
        _run, stats = await _ingest_greenhouse(db_session, adapter)

        assert stats.not_modified == ["acme"]
        assert stats.closed == 0
        assert stats.created == 0
        assert stats.updated == 0
        assert adapter.fetched_ids == [], "a 304 must not trigger phase 2"
        assert await _job_state_snapshot(db_session) == before, (
            "a 304 must not touch job state at all"
        )

    async def test_a_first_poll_takes_the_whole_board_in_one_request(
        self, db_session: AsyncSession
    ) -> None:
        """ADR 0007 reserves content=true for a board nobody has polled.

        Nothing is stored, so every posting counts as changed and phase 2 would
        mean one request each — 429 of them on Datadog, to fetch what a single
        request returns. The board is polled once, not per posting.
        """
        postings = tuple(
            _greenhouse_posting(str(n), title=f"Role {n}", updated_at="2026-07-01T00:00:00-04:00")
            for n in range(4)
        )
        adapter = _StubAdapter(
            GreenhouseAdapter(client=None),  # type: ignore[arg-type]
            FetchOutcome(
                board=GREENHOUSE_BOARD,
                ok=True,
                listed=_listed_from(postings),
                http_status=200,
            ),
            two_phase=True,
            phase_two=postings,
        )
        _run, stats = await _ingest_greenhouse(db_session, adapter)

        assert adapter.full_board_calls == 1
        assert adapter.fetched_ids == [], "a first poll must not fetch posting by posting"
        assert stats.created == 4

    async def test_a_second_poll_stops_using_the_expensive_endpoint(
        self, db_session: AsyncSession
    ) -> None:
        """The reservation is what makes it a reservation. Once anything is
        stored there is something to diff against, and content=true on a
        routine poll is the bug ADR 0007 names."""
        postings = tuple(
            _greenhouse_posting(str(n), title=f"Role {n}", updated_at="2026-07-01T00:00:00-04:00")
            for n in range(3)
        )
        listing = FetchOutcome(
            board=GREENHOUSE_BOARD,
            ok=True,
            listed=tuple(
                ListedPosting(
                    source_job_id=p.source_job_id,
                    source_updated_at=datetime(2026, 7, 1, 4, tzinfo=UTC),
                )
                for p in postings
            ),
            http_status=200,
        )
        await _ingest_greenhouse(
            db_session,
            _StubAdapter(
                GreenhouseAdapter(client=None),  # type: ignore[arg-type]
                listing,
                two_phase=True,
                phase_two=postings,
            ),
        )

        second = _StubAdapter(
            GreenhouseAdapter(client=None),  # type: ignore[arg-type]
            listing,
            two_phase=True,
            phase_two=postings,
        )
        await _ingest_greenhouse(db_session, second)

        assert second.full_board_calls == 0
        assert second.fetched_ids == [[]], (
            "nothing changed, so phase 2 should be asked for nothing at all"
        )

    async def test_a_failed_first_poll_closes_nothing(self, db_session: AsyncSession) -> None:
        """The cheap listing succeeded, so those postings are known to exist.
        Only their content is missing. I3: nothing ages, nothing closes."""
        postings = tuple(
            _greenhouse_posting(str(n), title=f"Role {n}", updated_at="2026-07-01T00:00:00-04:00")
            for n in range(3)
        )
        adapter = _StubAdapter(
            GreenhouseAdapter(client=None),  # type: ignore[arg-type]
            FetchOutcome(
                board=GREENHOUSE_BOARD,
                ok=True,
                listed=_listed_from(postings),
                http_status=200,
            ),
            two_phase=True,
            phase_two=postings,
            full_board_fails=True,
        )
        _run, stats = await _ingest_greenhouse(db_session, adapter)

        assert adapter.full_board_calls == 1
        assert stats.created == 0
        assert stats.closed == 0
        assert stats.failed == 3
        assert stats.error_summary is not None

    async def test_a_posting_that_fails_phase_two_does_not_age_the_board(
        self, db_session: AsyncSession
    ) -> None:
        """One 404 mid-poll is a fetch failure, not evidence the posting closed.

        It was on the listing, so it is still open. The failure is counted and
        surfaced; the record keeps its miss counter at zero (I3).
        """
        postings = tuple(
            _greenhouse_posting(str(n), title=f"Role {n}", updated_at="2026-07-01T00:00:00-04:00")
            for n in range(3)
        )
        await _ingest_greenhouse(
            db_session,
            _StubAdapter(
                GreenhouseAdapter(client=None),  # type: ignore[arg-type]
                FetchOutcome(
                    board=GREENHOUSE_BOARD,
                    ok=True,
                    listed=_listed_from(postings),
                    http_status=200,
                ),
                two_phase=True,
                phase_two=postings,
            ),
        )

        # All three changed; fetching #1 fails.
        listed = tuple(
            ListedPosting(source_job_id=str(n), source_updated_at=datetime(2026, 7, 9, tzinfo=UTC))
            for n in range(3)
        )
        adapter = _StubAdapter(
            GreenhouseAdapter(client=None),  # type: ignore[arg-type]
            FetchOutcome(board=GREENHOUSE_BOARD, ok=True, listed=listed, http_status=200),
            two_phase=True,
            phase_two=(postings[0], postings[2]),
            phase_two_failures=["1"],
        )
        _run, stats = await _ingest_greenhouse(db_session, adapter)

        records = {
            r.source_job_id: r
            for r in (await db_session.execute(select(SourceJobRecord))).scalars().all()
        }
        assert stats.failed == 1
        assert stats.closed == 0
        assert records["1"].consecutive_misses == 0
        assert records["1"].source_status == SourceStatus.ACTIVE


class TestSinglePhaseIsUnaffected:
    """Lever and Ashby have no phase 2, and must keep behaving exactly as before."""

    async def test_a_single_phase_board_never_calls_fetch_postings(
        self, db_session: AsyncSession
    ) -> None:
        source = await get_or_create_source(
            session=db_session, name="lever_test", source_type=SourceType.ATS_LEVER
        )
        adapter = _StubAdapter(LeverAdapter(client=None), _lever_outcome(), two_phase=False)
        await ingest_boards(db_session, adapter, [LEVER_BOARD], source=source)

        assert adapter.fetched_ids == []
        assert await _count(db_session, SourceJobRecord) == 9

    async def test_repolling_an_unchanged_single_phase_board_ages_nothing(
        self, db_session: AsyncSession
    ) -> None:
        """The regression that would appear if `listed` were left unpopulated
        on a single-phase adapter: every posting ages on the second poll."""
        source = await get_or_create_source(
            session=db_session, name="lever_test", source_type=SourceType.ATS_LEVER
        )
        for _ in range(2):
            adapter = _StubAdapter(LeverAdapter(client=None), _lever_outcome())
            await ingest_boards(db_session, adapter, [LEVER_BOARD], source=source)

        records = (await db_session.execute(select(SourceJobRecord))).scalars().all()
        assert len(records) == 9
        assert {r.consecutive_misses for r in records} == {0}


class TestTwoPhaseIsGatedOnTheFlag:
    """`is_two_phase` decides; the Protocol only narrows.

    `TwoPhaseJobSourceAdapter` is runtime-checkable, which means it answers True
    for anything carrying both method names — including a single-phase stub that
    implements them for convenience, which is precisely what happened while
    building this. Structural typing cannot express "and the provider means it".
    """

    async def test_an_adapter_with_the_methods_but_not_the_flag_stays_single_phase(
        self, db_session: AsyncSession
    ) -> None:
        source = await get_or_create_source(
            session=db_session, name="lever_test", source_type=SourceType.ATS_LEVER
        )
        # The stub implements fetch_postings and fetch_full_board, so it
        # satisfies the Protocol structurally. two_phase=False is the whole
        # assertion: Lever must not be dragged into a second phase it has no
        # endpoint for.
        adapter = _StubAdapter(LeverAdapter(client=None), _lever_outcome(), two_phase=False)
        await ingest_boards(db_session, adapter, [LEVER_BOARD], source=source)

        assert adapter.full_board_calls == 0
        assert adapter.fetched_ids == []
        assert await _count(db_session, SourceJobRecord) == 9

    async def test_claiming_two_phases_without_implementing_them_fails_loudly(
        self, db_session: AsyncSession
    ) -> None:
        """The opposite mismatch. Silently falling back to single-phase would
        mean a Greenhouse-shaped adapter ingesting nothing at all, forever,
        with a green run summary — which is how Task 4 left the pipeline for
        one commit, and nothing went red."""

        class _MethodlessTwoPhase:
            source_name = "broken"
            source_type = SourceType.ATS_GREENHOUSE
            parser_version = "1"
            is_two_phase = True

            async def fetch_board(
                self, board: BoardRef, *, etag: str | None = None
            ) -> FetchOutcome:
                return FetchOutcome(
                    board=board,
                    ok=True,
                    listed=(ListedPosting(source_job_id="1"),),
                    http_status=200,
                )

            def normalize(self, raw_job: RawJob, board: BoardRef) -> Any:
                raise AssertionError("never reached")

        source = await get_or_create_source(
            session=db_session, name="broken_test", source_type=SourceType.ATS_GREENHOUSE
        )
        with pytest.raises(TypeError, match="is_two_phase"):
            await ingest_boards(
                db_session, _MethodlessTwoPhase(), [GREENHOUSE_BOARD], source=source
            )
