"""Operational CLI: ``seed``, ``ingest``, ``offices``, ``enqueue``, ``stats``.

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
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.ashby import AshbyAdapter
from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob
from nightshift.adapters.geosearch import NycGeoSearchGeocoder, parse_search_response
from nightshift.adapters.greenhouse import GreenhouseAdapter
from nightshift.adapters.http import PoliteClient
from nightshift.adapters.lever import LeverAdapter
from nightshift.config import get_settings
from nightshift.db.base import (
    ApplicationStage,
    EventActor,
    JobStatus,
    LocationConfidence,
    ProficiencyLevel,
    RemotePreference,
    ResolutionMethod,
    SourceType,
    WorkAuthorization,
)
from nightshift.db.models import (
    Company,
    CompanyLocation,
    Job,
    JobLocation,
    Source,
    SourceJobRecord,
    User,
    UserProject,
    UserSkill,
)
from nightshift.db.session import dispose_engine, session_scope
from nightshift.db.types import utcnow
from nightshift.domain.applications import change_stage, save_job
from nightshift.domain.companies import normalize_company_name
from nightshift.domain.company_locations import DEFAULT_WORKSHEET_PATH, read_worksheet
from nightshift.domain.geocode_cache import CachingGeocoder
from nightshift.domain.geocoding import (
    PROVIDER_UNAVAILABLE,
    GeocodeOutcome,
    Unresolved,
)
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from nightshift.domain.matching import recompute_pending
from nightshift.domain.office_loading import LoadReport, load_offices
from nightshift.domain.polling import (
    ADAPTERS,
    adapter_for,
    poll_one_board,
    sync_board_poll_state,
)
from nightshift.domain.profile import ProfilePatch, add_project, add_skill, update_profile
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


#: One recorded NYC GeoSearch response per confirmed address in the worksheet,
#: keyed by the exact `OfficeEntry.geocoder_query` the loader sends. Written by
#: `scripts/record_office_geocodes.py`; provenance in the sibling `.meta.json`.
OFFICE_GEOCODE_FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "geosearch"
    / "office_addresses.json"
)


class FixtureNycGeoSearchGeocoder:
    """Rung 1, replayed from a recording. Implements `domain.geocoding.Geocoder`.

    `geocoding.py`'s Protocol docstring promised this at M4a — "`make demo`
    wires a fixture-backed implementation through the same interface, not
    around it" — and nothing implemented it for three milestones. The cost was
    not theoretical. `make offices` cached its answers in `geocode_cache`,
    which is a Postgres table, so `make reset-db` deleted every confirmed
    office and the only way back was a network call `make demo` is forbidden to
    make. The city came back with 31 of 31 roles `unresolved`, every beacon
    floating, and nothing anywhere reporting a fault.

    Like the three fixture *adapters* above, this holds no client and overrides
    only the fetch. `parse_search_response` — where every acceptance rule lives,
    including the one that rejects Pelias's confident garbage — is the
    production code path, unmodified.

    **A missing recording is `PROVIDER_UNAVAILABLE`, not "nothing found".**
    That is I3's distinction applied to a geocoder: we could not look is not
    evidence that there is no building there. It also keeps an offline run from
    poisoning `geocode_cache`, which stores every answer *except* that one.
    """

    method = ResolutionMethod.NYC_GEOSEARCH

    def __init__(self, fixture_path: Path | None = None) -> None:
        self._fixture_path = fixture_path or OFFICE_GEOCODE_FIXTURE
        self._recordings: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._recordings is None:
            try:
                payload = json.loads(self._fixture_path.read_text())
            except (OSError, ValueError):
                # Unreadable is indistinguishable from unrecorded, and both are
                # "we could not look". Raising here would take `make seed` down
                # over a file whose whole purpose is to be optional enrichment.
                payload = {}
            self._recordings = payload if isinstance(payload, dict) else {}
        return self._recordings

    async def geocode(self, address: str) -> GeocodeOutcome:
        payload = self._load().get(address)
        if not isinstance(payload, dict):
            return Unresolved(PROVIDER_UNAVAILABLE, LocationConfidence.CITY_ONLY)
        return parse_search_response(payload)


#: The confirmed skills the demo profile starts with — a subset of what
#: `nadia_okonkwo.txt` names, deliberately.
#:
#: Four of that resume's skills (SQL, FastAPI, Git, Playwright) are left off, so
#: pasting the fixture resume into the seeded profile still has something to
#: propose that nobody has confirmed. Two things depend on that and would fail
#: silently otherwise: `verify.py`'s `check_profile_confirmation`, which confirms
#: one previously-unconfirmed proposal, and `profile.spec.ts`, which needs two.
DEMO_SKILLS = ("Python", "TypeScript", "Go", "React", "PostgreSQL", "Docker")


async def seed_demo_profile(session: AsyncSession, user_id: uuid.UUID) -> str:
    """Give the dev user the profile the committed resume fixture describes.

    **Why the seed does this at all.** M3 scores a *pair*, and half of every pair
    is a person. Against the empty profile the dev user had until M3c Task 12,
    five of the six components are unassessable on nearly every posting, every
    evidence row comes from freshness, and not one of them quotes a description —
    so `make demo` demonstrates the milestone by rendering its empty state, and
    the seeded browser suite has no span to check the §7.2 hallucination rule
    against. The corpus was always half the fixture; this is the other half.

    **Why it is not a fabrication (I2).** Every value below is read off
    `tests/fixtures/resumes/nadia_okonkwo.txt`, which has been the committed
    fixture person since M2c, and every one is written through the same function
    the profile form calls — `update_profile`, `add_skill`, `add_project`, which
    `test_nothing_infers.py` already holds as the only writers. Nothing here
    infers anything from anything: `years_experience` is 0 because a student who
    has tutored is not claiming professional years, not because a subtraction
    said so.

    **It refuses to overwrite a profile somebody has touched.** The condition is
    entry state, not a flag: no confirmed skills, no projects, no graduation
    year. A developer who has typed their own facts in gets to keep them, and
    re-running `make seed` is then a no-op on this table rather than a silent
    revert of their afternoon.
    """
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one()
    skills = int(
        (
            await session.execute(
                select(func.count()).select_from(UserSkill).where(UserSkill.user_id == user_id)
            )
        ).scalar_one()
    )
    projects = int(
        (
            await session.execute(
                select(func.count()).select_from(UserProject).where(UserProject.user_id == user_id)
            )
        ).scalar_one()
    )
    if skills or projects or user.graduation_year is not None:
        return (
            f"demo profile: left alone ({skills} skill(s), {projects} project(s) already "
            "on file — `make reset-db` to get the fixture profile back)"
        )

    await update_profile(
        session,
        user_id=user_id,
        patch=ProfilePatch.from_mapping(
            {
                "display_name": "Nadia Okonkwo",
                # "Expected graduation: May 2027". A month and a year, which is
                # what a resume says and all ADR 0013 lets us store.
                "graduation_year": 2027,
                "graduation_month": 5,
                "degree": "Bachelor of Science in Computer Science",
                "school": "Hunter College, CUNY",
                # A current student with tutoring behind them. This is the value
                # that puts postings stating a years minimum into the dimmed
                # bands, which until now no seeded row reached — PROGRESS listed
                # those bands under "Not real yet" for exactly that reason.
                "years_experience": 0,
                "is_enrolled": True,
                # "Authorized to work in the United States." The resume says that
                # and no more, so this is `other_authorized` and not
                # `us_citizen`: the narrower claim is the one nobody made.
                "work_authorization": WorkAuthorization.OTHER_AUTHORIZED,
                "home_location_text": "Brooklyn, NY",
                "remote_preference": RemotePreference.HYBRID,
                "preferred_roles": ["Software Engineer", "Machine Learning"],
                "preferred_locations": ["New York", "Brooklyn"],
                # `minimum_salary` stays null. A10: most postings do not state
                # one, the compensation component is deferred (§5.1), and a
                # number here would be invented rather than read.
            }
        ),
    )

    for name in DEMO_SKILLS:
        await add_skill(
            session,
            user_id=user_id,
            name=name,
            proficiency_level=ProficiencyLevel.UNSPECIFIED,
        )

    # The two projects the fixture resume lists, with their own bullets as the
    # `evidence` text. The bullets matter: `score_project_evidence` quotes the
    # sentence naming the technology and produces **no row** when there is none,
    # so a project with a technology list and no prose demonstrates nothing.
    await add_project(
        session,
        user_id=user_id,
        name="Transit Delay Tracker",
        summary="Real-time MTA delay tracking, read by around 400 people a week.",
        evidence=(
            "Ingested MTA real-time feeds every 30 seconds into a time-series table with "
            "Python. Stored each snapshot in PostgreSQL and published a dashboard read by "
            "roughly 400 people a week."
        ),
        technologies=["Python", "PostgreSQL"],
    )
    await add_project(
        session,
        user_id=user_id,
        name="Cafe Queue",
        summary="Mobile ordering flow used by a campus coffee shop.",
        evidence=(
            "Built the mobile ordering flow in React and TypeScript. Wrote the Playwright "
            "suite covering the checkout path."
        ),
        technologies=["TypeScript", "React"],
    )

    return (
        f"demo profile: seeded from the committed resume fixture "
        f"({len(DEMO_SKILLS)} skills, 2 projects, graduating 2027-05)"
    )


#: The stages the seeded applications sit at, in the order they are dealt out
#: across the corpus — one per role, cycling.
#:
#: `city.md` §6 gives five of these a treatment on the skyline, and until M4c
#: the seed created no applications at all: every §6 lifecycle row was
#: unreachable in `make demo` and unassertable in the seeded browser suite,
#: which made an implemented encoding look like an unimplemented one. The
#: Makefile's own description of this command has always claimed applications.
#:
#: Every stage that draws something is here, `rejected` included — it is the one
#: §6 hides by default, so without it nothing on the page exercises the toggle.
_DEMO_STAGES: tuple[ApplicationStage, ...] = (
    ApplicationStage.SAVED,
    ApplicationStage.APPLIED,
    ApplicationStage.INTERVIEW,
    ApplicationStage.OFFER,
    ApplicationStage.REJECTED,
)


async def seed_demo_applications(
    session: AsyncSession, user_id: uuid.UUID, *, now: datetime
) -> int:
    """Put one application at each §6 stage, through the real domain path.

    ``save_job`` and ``change_stage`` and nothing else. Inserting `Application`
    rows directly would be faster and would skip the append-only event trail
    that M2 built the whole subsystem around — a demo database whose
    applications have no history is a demo of something this product does not
    do, which is what I7 forbids.

    Idempotent, like `save_job` itself: re-seeding finds the existing
    applications and leaves their stages alone rather than writing a second
    event trail over the first.
    """
    jobs = (
        (await session.execute(select(Job).order_by(Job.title, Job.id).limit(len(_DEMO_STAGES))))
        .scalars()
        .all()
    )
    if not jobs:
        return 0

    tracked = 0
    for job, stage in zip(jobs, _DEMO_STAGES, strict=False):
        application, created = await save_job(session, user_id=user_id, job_id=job.id, now=now)
        if not created:
            continue
        if stage is not ApplicationStage.SAVED:
            await change_stage(
                session,
                application=application,
                to_stage=stage,
                actor=EventActor.USER,
                now=now,
                note="Seeded demo data.",
            )
        tracked += 1
    return tracked


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

        print(f"  {await seed_demo_profile(session, settings.dev_user_id)}")

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

        # -- confirmed offices, from recorded geocodes -------------------------
        #
        # Added 2026-08-19, after the city came back with every beacon
        # floating. `company_locations` is what turns a role into something
        # standing on a roof, and until now it was filled *only* by
        # `make offices` — a separate command, run by hand, that geocodes over
        # the network and caches the answers in `geocode_cache`. That table is
        # in Postgres. `make reset-db` drops it. So one reseed erased both the
        # offices and the cached answers that could have rebuilt them, and the
        # only route back was a network call `make demo` is forbidden to make.
        # `GET /city/signals` returned 31 of 31 `unresolved`, the renderer
        # correctly drew 31 untethered columns, and nothing reported a fault.
        #
        # So the offices are seeded like everything else here: the committed
        # worksheet a human filled in, through `read_worksheet` and
        # `load_offices` — the production loader, with every refusal rule
        # intact — over recorded GeoSearch responses instead of live ones.
        # `CachingGeocoder` still wraps the rung, so a later `make offices`
        # finds the answers already cached and asks the network nothing.
        offices = await load_offices(
            session,
            read_worksheet(DEFAULT_WORKSHEET_PATH.read_text()),
            (CachingGeocoder(FixtureNycGeoSearchGeocoder(), session),),
        )
        # `LoadReport.summary()` rather than a line of my own: it is the same
        # sentence `make offices` prints, and a second one here would be free
        # to leave a category out. The first draft of this line did exactly
        # that — it dropped `unknown_company` and printed four numbers that
        # summed to 17 of 23 companies.
        print(f"  confirmed offices: {offices.summary()}")
        if not offices.placed:
            # Not fatal — a worksheet with no addresses is a legitimate state,
            # and it is the state a fresh clone starts in. But it is the exact
            # shape of the failure above, so it says so in words rather than
            # leaving somebody to infer it from a city that looks broken.
            print(
                "  warning: no role will stand on a building. Every beacon will "
                "float, which is what `city.md` §4.8 says an unplaced role looks "
                "like — not a rendering fault.",
                file=sys.stderr,
            )

        # M3c Task 12: score what was just seeded, through the function the ARQ
        # cron calls and no other.
        #
        # Without this the seeded database has 31 postings and zero scores, and
        # every M3 surface — the panel, the ranked list — renders its honest
        # empty state. `make demo` would fill in a minute later when the worker's
        # cron first fires, but `make acceptance` runs no worker at all, so
        # `verify` and the seeded browser suite would both be asserting against a
        # milestone's output that is not there. A suite that passes over an
        # unscored database is the M3b stale-server failure with a different
        # cause: green, and about nothing.
        #
        # `recompute_pending` and not a seeding shortcut, because a fixture
        # `match_result` would be exactly the mock I7 forbids — a stored claim
        # about a person that the scorer never made. These rows are the real
        # scorer's real output over fixture *inputs*, which is what every other
        # derived row in this database already is.
        #
        # Re-running is a no-op: the sweep selects pairs with no row at the
        # current ruleset version, and after this there are none.
        report = await recompute_pending(session)
        print(
            f"  match scores: {report.scored} scored, {report.skipped} skipped "
            f"(ruleset {report.ruleset})"
        )

        # M4c Task 5: one application at each of §6's lifecycle stages, so the
        # skyline's encoding has something to encode. Without these every mark
        # in `city.md` §6 is unreachable in `make demo` and unassertable in the
        # seeded browser suite — an implemented language with nothing speaking
        # it, which reads exactly like an unimplemented one.
        tracked = await seed_demo_applications(session, settings.dev_user_id, now=utcnow())
        print(f"  applications: {tracked} tracked, one at each stage the city draws")

    await _print_summary()

    # A seed that persisted nothing must not exit 0.
    #
    # Found on 2026-08-05, in the worst possible way: a model change landed
    # before its migration, every INSERT failed with `type "role_family" does
    # not exist`, `ingest_boards` counted all 31 into `stats.failed` — which is
    # right, I3 says one bad posting may not kill a board — and this command
    # printed "seed complete" and exited 0 over an empty database.
    #
    # The counts *were* on screen. That is not enough: CI's "Seed loads" step
    # reads the exit code and nothing else, so a completely broken seed was a
    # green check. `make demo` would have handed a developer an empty city and
    # a success message.
    #
    # The condition is deliberately "ended with zero jobs" rather than "any
    # posting failed". The fixtures are committed and deterministic so a failure
    # is always a defect, but failing the whole seed over one bad posting would
    # make this command brittle in exactly the way `ingest_boards` refuses to
    # be. Zero jobs is unambiguous: the seed's entire purpose is a populated
    # database to demo.
    total_jobs = await _canonical_job_count()
    if total_jobs == 0:
        print(
            "\nerror: the seed persisted no canonical jobs. Something above "
            "failed — read the `failed` counts and the warnings.",
            file=sys.stderr,
        )
        return 1

    print("\nseed complete. `make dev` then open http://localhost:3000")
    return 0


async def _canonical_job_count() -> int:
    async with session_scope() as session:
        return int((await session.execute(select(func.count()).select_from(Job))).scalar_one())


async def cmd_score(args: argparse.Namespace) -> int:
    """Score every pair that has no score at the current ruleset version.

    The same sweep the ARQ cron runs each minute, on demand. Two callers wanted
    it and neither is a test of it: a developer who has just edited their profile
    and does not want to watch a page say "computed in the background" for a
    minute, and the seeded browser suite, which runs with no worker behind it and
    whose earlier specs invalidate every score on their way past.

    It takes no arguments and cannot be pointed at a subset. *Which* pairs are
    due is `pending_pairs`' answer and nobody else's — a flag here would be a
    second definition of due-ness, which is the drift M3c Task 8 collapsed three
    triggers into one query to avoid.
    """
    async with session_scope() as session:
        report = await recompute_pending(session)
    print(
        f"scored {report.scored}, skipped {report.skipped} "
        f"(ruleset {report.ruleset})" + ("" if report.scored else " — nothing was due")
    )
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


async def cmd_offices(args: argparse.Namespace) -> int:
    """Load `data/company-locations.yaml` into `company_locations`.

    The last two steps of the promotion path in `city.md` §4.4, which existed as
    tested functions with no caller until now. A human writes a street address
    into the worksheet; this reads it, refuses what cannot support itself, walks
    the geocoding ladder, and writes the rows that reach `verified`. It is the
    only way a coordinate a person vouched for enters this product.

    **Run by a human, never scheduled.** Geocoding is a real request to
    `geosearch.planninglabs.nyc`, so this is gated on `OUTBOUND_HTTP_ENABLED`
    exactly like `ingest` and `poll`. The gate is checked only when there is
    something to geocode: an all-blank worksheet is the starting state and
    reporting on it must not require the network, or a fresh clone could not run
    this command to find out what it is being asked to fill in.

    `CachingGeocoder` wraps the rung, so every address is requested once ever.
    After a run the answers live in `geocode_cache` and `make demo` stays
    offline, which is the property ADR 0022 protects for tiles and this protects
    for addresses.

    **Exit code separates the two kinds of failure.** A *refused* entry is a
    defect in the file — an address with no date, a "New York, NY" that names no
    street — and the human has to fix it, so it exits 1 and `make offices` goes
    red. An *unresolved* entry is the world answering: the address is outside
    NYC GeoSearch's corpus, or names a place it does not know. That is a real
    finding, not a mistake, and it exits 0.
    """
    path = Path(args.worksheet) if args.worksheet else DEFAULT_WORKSHEET_PATH
    try:
        source = path.read_text()
    except OSError as exc:
        print(f"error: cannot read worksheet at {path}: {exc}", file=sys.stderr)
        return 1

    reading = read_worksheet(source)
    print(f"  {path}")
    print(f"  {reading.summary()}")

    if not reading.entries:
        # Nothing to geocode. Report what the file said and stop — no session,
        # no network, no ladder.
        report = LoadReport(
            blank=list(reading.blank),
            refused=[(p.company, p.reason) for p in reading.problems],
        )
        _print_office_report(report, placed_rows=[])
        return 1 if report.refused else 0

    settings = get_settings()
    if not settings.outbound_http_enabled:
        print(
            f"\nerror: {len(reading.entries)} entr(ies) name an address, and geocoding "
            "one is a network call.\n"
            "       Set OUTBOUND_HTTP_ENABLED=true in .env to run them through NYC "
            "GeoSearch.\n"
            "       (Answers are cached permanently, so `make demo` stays offline "
            "afterwards.)",
            file=sys.stderr,
        )
        return 1

    async with PoliteClient() as client, session_scope() as session:
        ladder = (CachingGeocoder(NycGeoSearchGeocoder(client), session),)
        report = await load_offices(session, reading, ladder)
        placed_rows = await _placed_rows(session, report)
        _print_office_report(report, placed_rows=placed_rows)

    return 1 if report.refused else 0


async def _placed_rows(
    session: AsyncSession, report: LoadReport
) -> list[tuple[str, CompanyLocation]]:
    """Read back what was actually written, rather than reprinting the input.

    `LoadReport.placed` carries company names and nothing else, and a command
    that echoed the address it was handed would look identical whether the row
    reached the database or not. I6 wants evidence: the confidence and the BIN
    below are the columns the renderer will read, straight out of the table.
    """
    if not report.placed:
        return []
    # Matched on `normalized_name`, the same key `load_offices` looked the
    # company up by. `report.placed` holds the name as the worksheet spells it,
    # and "8Fleet Inc." and "8fleet inc" are one employer to this database.
    normalized = [normalize_company_name(name) for name in report.placed]
    rows = (
        (
            await session.execute(
                select(Company.canonical_name, CompanyLocation)
                .join(CompanyLocation, CompanyLocation.company_id == Company.id)
                .where(Company.normalized_name.in_(normalized))
                .order_by(Company.canonical_name, CompanyLocation.label)
            )
        )
        .tuples()
        .all()
    )
    return [(name, row) for name, row in rows]


def _print_office_report(
    report: LoadReport, *, placed_rows: list[tuple[str, CompanyLocation]]
) -> None:
    """One line per company, grouped by what happened to it."""
    print()
    if placed_rows:
        print("  placed on a building")
        for name, row in placed_rows:
            bin_text = f"BIN {row.building_id}" if row.building_id else "no BIN returned"
            print(
                f"    {name:<24} {row.street_address}"
                f"  ->  {row.location_confidence.value}, {bin_text}"
            )

    if report.unresolved:
        print("  address given, no building found")
        for name, reason in report.unresolved:
            print(f"    {name:<24} {reason}")

    if report.unknown_company:
        print("  address recorded but the company has no jobs yet (board not polled)")
        for name in report.unknown_company:
            print(f"    {name}")

    if report.refused:
        print("  refused — fix these in the worksheet")
        for name, reason in report.refused:
            print(f"    {name:<24} {reason}")

    if report.blank:
        print(f"  blank ({len(report.blank)}) — a correct answer; these jobs stay unplaced")
        print(f"    {', '.join(report.blank)}")

    print(f"\n  {report.summary()}")


COMMANDS = {
    "seed": cmd_seed,
    "offices": cmd_offices,
    "score": cmd_score,
    "ingest": cmd_ingest,
    "poll": cmd_poll,
    "enqueue": cmd_enqueue,
    "stats": cmd_stats,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightshift", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seed", help="load dev user + committed fixture board (offline)")
    offices = subparsers.add_parser(
        "offices", help="load data/company-locations.yaml into company_locations"
    )
    offices.add_argument(
        "--worksheet",
        default=None,
        help="worksheet file (default: data/company-locations.yaml)",
    )
    subparsers.add_parser("score", help="score every pair due at the current ruleset version")
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
