"""Operational CLI: ``seed``, ``ingest``, ``enqueue``, ``stats``.

The distinction between ``seed`` and ``ingest`` is the important thing in this
module, and it is a direct application of I7.

``make seed`` loads the **committed fixture** — a real recorded Greenhouse
response — through the real adapter, the real normalizer, and the real
persistence path. Only the bytes' origin differs from production. It is
attributed in the database to a source named ``greenhouse_fixture`` with
``source_type = fixture``, so every job it creates is traceable to a fixture
rather than silently indistinguishable from live data. That is what makes
``make demo`` honest as well as offline.

``make ingest`` runs the same code against the live endpoint, attributed to the
``greenhouse`` source. It requires ``OUTBOUND_HTTP_ENABLED=true``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

from nightshift.adapters.ashby import AshbyAdapter
from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob
from nightshift.adapters.greenhouse import GreenhouseAdapter
from nightshift.adapters.http import PoliteClient
from nightshift.adapters.lever import LeverAdapter
from nightshift.config import get_settings
from nightshift.db.base import JobStatus, LocationConfidence, SourceType
from nightshift.db.models import Company, Job, JobLocation, Source, SourceJobRecord, User
from nightshift.db.session import dispose_engine, session_scope
from nightshift.db.types import utcnow
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from nightshift.domain.polling import (
    ADAPTERS,
    adapter_for,
    poll_one_board,
    sync_board_poll_state,
)
from nightshift.domain.registry import get_registry
from nightshift.logging import configure_logging

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "greenhouse"
LEVER_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "lever"
ASHBY_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ashby"
FIXTURE_SOURCE_NAME = "greenhouse_fixture"
LEVER_FIXTURE_SOURCE_NAME = "lever_fixture"
ASHBY_FIXTURE_SOURCE_NAME = "ashby_fixture"


class FixtureGreenhouseAdapter(GreenhouseAdapter):
    """Greenhouse adapter that reads a committed fixture instead of the network.

    Subclasses the real adapter and overrides exactly one method, so
    ``normalize`` — where every interesting decision lives — is the production
    code path, unmodified. Naming it ``Fixture*`` and confining it to the CLI
    keeps it on the right side of I7: it is a clearly-labelled stand-in behind
    the real interface, listed under "Not real yet" in PROGRESS.
    """

    source_name = "greenhouse_fixture"
    source_type = SourceType.FIXTURE
    #: **Not inherited.** The real Greenhouse adapter is two-phase, and this one
    #: must not be: the committed recording *is* the whole board, descriptions
    #: included, so there is no second phase to run. Left inherited, the
    #: pipeline would take the two-phase branch, find nothing stored, and call
    #: the inherited `fetch_full_board` — which reaches for an HTTP client this
    #: adapter deliberately does not have. `make seed` would crash, and
    #: `make demo`'s offline guarantee with it.
    is_two_phase = False

    def __init__(self, fixture_path: Path) -> None:
        # No HTTP client: this adapter must not be able to make a request even
        # if outbound HTTP were enabled.
        super().__init__(client=None)  # type: ignore[arg-type]
        self._fixture_path = fixture_path

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        try:
            payload = json.loads(self._fixture_path.read_text())
        except (OSError, ValueError) as exc:
            return FetchOutcome(board=board, ok=False, error=f"fixture unreadable: {exc}")

        jobs = tuple(
            RawJob(
                source_job_id=str(entry["id"]),
                source_company_key=board.token,
                canonical_url=entry.get("absolute_url"),
                payload=entry,
            )
            for entry in payload.get("jobs", [])
            if entry.get("id") is not None
        )
        return FetchOutcome(board=board, ok=True, jobs=jobs)


class FixtureLeverAdapter(LeverAdapter):
    """Reads a committed recording instead of the network. ADR 0004.

    Constructed with no client, so it cannot make a request even if the kill
    switch were flipped. Attributed to source ``lever_fixture`` with
    ``source_type='fixture'`` and badged "committed fixture" in the Operate
    UI. Overrides exactly ``fetch_board`` — ``normalize`` is the production
    code path, unmodified — following ``FixtureGreenhouseAdapter``'s shape.
    """

    source_name = "lever_fixture"
    source_type = SourceType.FIXTURE

    def __init__(self, fixture: Path) -> None:
        super().__init__(client=None)
        self._fixture = fixture

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        payload = json.loads(self._fixture.read_text())
        jobs = tuple(
            RawJob(
                source_job_id=str(job["id"]),
                source_company_key=board.token,
                canonical_url=job.get("hostedUrl"),
                payload=job,
            )
            for job in payload
            if isinstance(job, dict) and job.get("id") is not None
        )
        return FetchOutcome(board=board, ok=True, jobs=jobs, http_status=200)


class FixtureAshbyAdapter(AshbyAdapter):
    """Reads a committed recording instead of the network. ADR 0004."""

    source_name = "ashby_fixture"
    source_type = SourceType.FIXTURE

    def __init__(self, fixture: Path) -> None:
        super().__init__(client=None)
        self._fixture = fixture

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        payload = json.loads(self._fixture.read_text())
        jobs = tuple(
            RawJob(
                source_job_id=str(job["id"]),
                source_company_key=board.token,
                canonical_url=job.get("jobUrl"),
                payload=job,
            )
            for job in payload.get("jobs", [])
            if isinstance(job, dict) and job.get("id") is not None
        )
        return FetchOutcome(board=board, ok=True, jobs=jobs, http_status=200)


async def cmd_seed(args: argparse.Namespace) -> int:
    """Load the dev user and the three committed fixture boards.

    M1a widened this from one provider to three (Greenhouse, Lever, Ashby) so
    the offline `make demo` path — and the Operate page it feeds — has more
    than one source to show. Each fixture is attributed to its own
    ``*_fixture`` source, per ADR 0004.
    """
    settings = get_settings()
    fixture_path = FIXTURE_DIR / "datadog_board.json"
    lever_fixture_path = LEVER_FIXTURE_DIR / "alloy_board.json"
    ashby_fixture_path = ASHBY_FIXTURE_DIR / "ramp_board.json"
    for path in (fixture_path, lever_fixture_path, ashby_fixture_path):
        if not path.exists():
            print(f"error: fixture missing at {path}", file=sys.stderr)
            return 1

    async with session_scope() as session:
        # -- dev user (AMENDMENTS A3) ---------------------------------------
        existing_user = (
            await session.execute(select(User).where(User.id == settings.dev_user_id))
        ).scalar_one_or_none()
        if existing_user is None:
            session.add(
                User(
                    id=settings.dev_user_id,
                    email=settings.dev_user_email,
                    display_name="Development User",
                    timezone="America/New_York",
                )
            )
            await session.flush()
            print(f"  created dev user {settings.dev_user_email}")
        else:
            print(f"  dev user {settings.dev_user_email} already present")

        # -- Greenhouse fixture board ----------------------------------------
        adapter = FixtureGreenhouseAdapter(fixture_path)
        source = await get_or_create_source(
            session,
            name=FIXTURE_SOURCE_NAME,
            source_type=SourceType.FIXTURE,
            base_url=f"file://{fixture_path}",
        )
        board = BoardRef(company="Datadog", ats="greenhouse", token="datadog", nyc_presence=True)
        run, stats = await ingest_boards(session, adapter, [board], source=source)

        print(
            f"  greenhouse fixture ingest: {stats.created} created, {stats.updated} updated, "
            f"{stats.unchanged} unchanged, {stats.failed} failed ({run.status.value})"
        )

        # -- Lever fixture board ----------------------------------------------
        lever_adapter = FixtureLeverAdapter(lever_fixture_path)
        lever_source = await get_or_create_source(
            session,
            name=LEVER_FIXTURE_SOURCE_NAME,
            source_type=SourceType.FIXTURE,
            base_url=f"file://{lever_fixture_path}",
        )
        # Company and nyc_presence match this board's data/board-registry.yaml
        # entry — the fixture stands in for the network call only.
        lever_board = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=False)
        lever_run, lever_stats = await ingest_boards(
            session, lever_adapter, [lever_board], source=lever_source
        )
        print(
            f"  lever fixture ingest: {lever_stats.created} created, {lever_stats.updated} "
            f"updated, {lever_stats.unchanged} unchanged, {lever_stats.failed} failed "
            f"({lever_run.status.value})"
        )

        # -- Ashby fixture board ------------------------------------------------
        ashby_adapter = FixtureAshbyAdapter(ashby_fixture_path)
        ashby_source = await get_or_create_source(
            session,
            name=ASHBY_FIXTURE_SOURCE_NAME,
            source_type=SourceType.FIXTURE,
            base_url=f"file://{ashby_fixture_path}",
        )
        ashby_board = BoardRef(company="Ramp", ats="ashby", token="ramp", nyc_presence=True)
        ashby_run, ashby_stats = await ingest_boards(
            session, ashby_adapter, [ashby_board], source=ashby_source
        )
        print(
            f"  ashby fixture ingest: {ashby_stats.created} created, {ashby_stats.updated} "
            f"updated, {ashby_stats.unchanged} unchanged, {ashby_stats.failed} failed "
            f"({ashby_run.status.value})"
        )

        # M1d: give every registry board its polling schedule, so `make demo`
        # shows the board table populated rather than empty. Every row reads
        # "never polled", which is the truth — seeding loads committed fixtures
        # and contacts nothing. An empty table would look like a broken page;
        # a table of honest "never" is the actual state.
        created = await sync_board_poll_state(session, now=utcnow())
        print(f"  board poll schedules: {created} created (none polled yet)")

    await _print_summary()
    print("\nseed complete. `make dev` then open http://localhost:3000")
    return 0


async def cmd_ingest(args: argparse.Namespace) -> int:
    """Run one live ingestion pass against the registry's active boards."""
    settings = get_settings()
    if not settings.outbound_http_enabled:
        print(
            "error: outbound HTTP is disabled.\n"
            "       Set OUTBOUND_HTTP_ENABLED=true in .env to poll live boards.\n"
            "       (`make seed` loads the committed fixture instead, fully offline.)",
            file=sys.stderr,
        )
        return 1

    boards = [entry.to_ref() for entry in get_registry().pollable(ats="greenhouse")]
    if not boards:
        print("no active greenhouse boards in data/board-registry.yaml", file=sys.stderr)
        return 1

    print(f"polling {len(boards)} board(s): {', '.join(b.token for b in boards)}")
    async with PoliteClient() as client, session_scope() as session:
        adapter = GreenhouseAdapter(client)
        source = await get_or_create_source(
            session,
            name="greenhouse",
            source_type=SourceType.ATS_GREENHOUSE,
            base_url="https://boards-api.greenhouse.io",
        )
        run, stats = await ingest_boards(session, adapter, boards, source=source)
        print(
            f"  {run.status.value}: fetched={stats.fetched} created={stats.created} "
            f"updated={stats.updated} unchanged={stats.unchanged} failed={stats.failed}"
        )
        if stats.boards_failed:
            print(f"  boards failed: {', '.join(stats.boards_failed)}")
        if stats.errors:
            for error in stats.errors[:10]:
                print(f"    ! {error}")

    await _print_summary()
    return 0


async def cmd_enqueue(args: argparse.Namespace) -> int:
    """Push the ingestion task onto the ARQ queue instead of running it inline."""
    from arq import create_pool

    from nightshift.workers.main import _redis_settings

    pool = await create_pool(_redis_settings())
    job = await pool.enqueue_job("ingest_greenhouse")
    print(f"enqueued ingest_greenhouse as {job.job_id if job else 'unknown'}")
    await pool.aclose()
    return 0


async def cmd_stats(args: argparse.Namespace) -> int:
    await _print_summary()
    return 0


async def _print_summary() -> None:
    """Print corpus counts, including the location-confidence breakdown.

    The breakdown is printed every time on purpose. It is the fastest way for a
    developer to notice that something started claiming precision it has not
    earned — in M0, `verified` and `approximate` must both be zero.
    """
    async with session_scope() as session:
        jobs = (await session.execute(select(func.count()).select_from(Job))).scalar_one()
        open_jobs = (
            await session.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN)
            )
        ).scalar_one()
        companies = (await session.execute(select(func.count()).select_from(Company))).scalar_one()
        records = (
            await session.execute(select(func.count()).select_from(SourceJobRecord))
        ).scalar_one()
        locations = (
            await session.execute(select(func.count()).select_from(JobLocation))
        ).scalar_one()
        confidence_rows = (
            await session.execute(
                select(JobLocation.location_confidence, func.count()).group_by(
                    JobLocation.location_confidence
                )
            )
        ).all()
        by_confidence: dict[LocationConfidence, int] = {row[0]: row[1] for row in confidence_rows}
        sources = (await session.execute(select(Source))).scalars().all()

    print("\n  corpus")
    print(f"    canonical jobs      {jobs} ({open_jobs} open)")
    print(f"    companies           {companies}")
    print(f"    raw source records  {records}")
    print(f"    job locations       {locations}")
    print("\n  location confidence (I1)")
    for confidence in LocationConfidence:
        count = by_confidence.get(confidence, 0)
        marker = ""
        if confidence in {LocationConfidence.VERIFIED, LocationConfidence.APPROXIMATE} and count:
            marker = "   <-- unexpected in M0: nothing is geocoded yet"
        print(f"    {confidence.value:<14} {count}{marker}")
    print("\n  sources")
    for source in sources:
        label = "fixture" if source.source_type is SourceType.FIXTURE else "live"
        print(f"    {source.name:<20} {label}")


async def cmd_poll(args: argparse.Namespace) -> int:
    """Poll one board through the full M1d cycle, conditionally.

    Exists so a human can run a single board's poll without waiting for a cron,
    and — the reason it was written — so M1 criterion 13 can be demonstrated
    against a real provider rather than only in fixtures: run it twice and the
    second run reports ``304`` and writes nothing.

    Goes through ``poll_one_board``, so it reads and writes the same
    ``board_poll_state`` row the scheduler does. A command that polled some
    other way would prove nothing about the thing that actually runs.
    """
    settings = get_settings()
    if not settings.outbound_http_enabled:
        print(
            "error: outbound HTTP is disabled.\n"
            "       Set OUTBOUND_HTTP_ENABLED=true in .env to poll live boards.",
            file=sys.stderr,
        )
        return 1

    async with session_scope() as session:
        await sync_board_poll_state(session, now=utcnow())

    async with PoliteClient() as client, session_scope() as session:
        try:
            adapter = adapter_for(args.ats, client)
            state = await poll_one_board(
                session, adapter, ats=args.ats, token=args.token, now=utcnow()
            )
        except LookupError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print(f"  {args.ats}:{args.token}")
        print(f"    http status         {state.last_status}")
        print(f"    tier                {state.tier.value}")
        print(f"    etag                {state.etag or '(none served)'}")
        print(f"    consecutive fails   {state.consecutive_failures}")
        print(f"    next poll at        {state.next_poll_at.isoformat()}")
    return 0


COMMANDS = {
    "seed": cmd_seed,
    "ingest": cmd_ingest,
    "poll": cmd_poll,
    "enqueue": cmd_enqueue,
    "stats": cmd_stats,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightshift", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="load dev user + committed fixture board (offline)")
    subparsers.add_parser("ingest", help="poll live boards from the registry")
    poll = subparsers.add_parser(
        "poll", help="poll one board conditionally, through board_poll_state"
    )
    poll.add_argument("--ats", required=True, choices=sorted(ADAPTERS))
    poll.add_argument("--token", required=True)
    subparsers.add_parser("enqueue", help="queue the ingestion task for the worker")
    subparsers.add_parser("stats", help="print corpus counts")
    args = parser.parse_args(argv)

    configure_logging()

    async def run() -> int:
        try:
            return await COMMANDS[args.command](args)
        finally:
            await dispose_engine()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
