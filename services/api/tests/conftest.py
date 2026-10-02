"""Shared test fixtures.

Tests must not read the developer's ``.env``. A suite whose result depends on a
local file is a suite that passes on one machine and fails in CI, so every
:class:`Settings` here is built with ``_env_file=None`` and explicit values.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nightshift.config import Settings, get_settings
from nightshift.db.base import (
    EligibilityState,
    EvidenceSource,
    JobStatus,
    JobTextField,
    MatchComponent,
    PenaltyName,
)
from nightshift.db.models import (
    Company,
    Job,
    MatchComponentAssessment,
    MatchEvidence,
    MatchPenalty,
    MatchResult,
    User,
)
from nightshift.domain.matching_weights import load_weights

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def make_settings(**overrides: Any) -> Settings:
    """Hermetic settings for tests. Ignores ``.env`` entirely."""
    defaults: dict[str, Any] = {
        "nightshift_env": "test",
        "outbound_http_enabled": False,
        "http_user_agent": "Nightshift/0.1-test (+https://github.com/Tahmudun/Nightshift)",
        # The configured ceiling, so the limiter spaces requests 50ms apart and
        # the suite stays fast. Not higher: the ceiling is a real politeness
        # guardrail (§7.3) and tests do not get to relax product constraints.
        "source_requests_per_second": 20.0,
        "http_max_retries": 2,
        "http_backoff_base_seconds": 0.01,
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[call-arg]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    """Config is a process singleton; leaking one test's config into the next is a trap."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _markets_are_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The product's default market scope (ADR 0041), whatever a developer's
    `.env` says. A suite whose answers changed with `MARKETS=nyc,london` on one
    laptop would be testing that laptop. A module that needs another scope sets
    it itself, and says why."""
    monkeypatch.setenv("MARKETS", "nyc")


def load_json_fixture(*parts: str) -> Any:
    return json.loads((FIXTURE_DIR.joinpath(*parts)).read_text())


@pytest.fixture(scope="session")
def greenhouse_board_payload() -> dict[str, Any]:
    """The committed Datadog board response (see the sibling .meta.json for provenance)."""
    payload = load_json_fixture("greenhouse", "datadog_board.json")
    assert payload["jobs"], "fixture is empty"
    return payload  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Database fixtures — for the ingestion pipeline, which is transactional
# (savepoints, unique constraints, FK ordering, idempotency) and cannot be
# exercised honestly against a fake session.
#
# The original design here skipped whenever `TEST_DATABASE_URL` /
# `DATABASE_URL` was unset in the environment. That is the wrong knob for
# this project: `DATABASE_URL` is commented out of `.env` on purpose (see
# `config.py`), and the connection is built from `POSTGRES_*` fields via
# `Settings.async_database_url` instead. Checking the env var meant every
# test in this file skipped unconditionally, on every machine, including
# ones with the database up and migrated — a green suite that had run
# nothing. Skip only when the database is genuinely unreachable, discovered
# by actually trying to connect, not by an environment variable's absence.
requires_db = pytest.mark.integration


async def make_job_with_text(session: AsyncSession, text_: str | None) -> Job:
    """A canonical job carrying ``text_`` as its description.

    Lives here because it is now wanted in three places. `Job.company_id` is the
    only required foreign key, so a company and a job is the whole fixture — no
    source record, no link row. The company's `normalized_name` is randomised
    because it is unique and these tests are not about company identity.
    """
    company = Company(canonical_name="Acme", normalized_name=f"acme {uuid.uuid4().hex[:8]}")
    session.add(company)
    await session.flush()
    now = datetime.now(tz=UTC)
    job = Job(
        company_id=company.id,
        title="Engineer",
        normalized_title="engineer",
        description_text=text_,
        first_seen_at=now,
        last_seen_at=now,
        status=JobStatus.OPEN,
    )
    session.add(job)
    await session.flush()
    return job


#: Which components are left unassessable to reach a given denominator, and so
#: which totals a stored row can legally carry. Written out rather than computed
#: so the arithmetic a test depends on is visible to the person reading it — the
#: weights are 20, 30, 20, 10, 10, 10, and migration `0018`'s trigger ties
#: `assessed_out_of` to exactly the assessable subset.
#:
#: Moved here from `test_match_ranking_routes.py` at M3d Task 7, when the daily
#: queue became the second surface that ranks stored scores. Two copies of this
#: map would drift, and the failure would be a test asserting an ordering that
#: the trigger would have refused in production.
UNASSESSABLE_FOR: dict[int, tuple[MatchComponent, ...]] = {
    100: (),
    80: (MatchComponent.PROJECT,),
    50: (MatchComponent.SKILL, MatchComponent.PROJECT),
    20: (
        MatchComponent.SKILL,
        MatchComponent.PROJECT,
        MatchComponent.LOCATION,
        MatchComponent.FRESHNESS,
        MatchComponent.PRIORITY,
    ),
    0: tuple(MatchComponent),
}


def quoted_evidence(
    result: MatchResult, *, component: MatchComponent, points: int, quote: str, text_: str
) -> MatchEvidence:
    """A person-claim evidence row quoting ``text_`` at real offsets.

    The quoting trigger reads the field and checks the characters, so the span
    has to be *true of the text* rather than merely plausible. That is the point
    of the trigger and the reason this helper exists instead of a literal.
    """
    start = text_.index(quote)
    return MatchEvidence(
        match_result_id=result.id,
        component=component,
        points=points,
        job_span_text=quote,
        job_span_field=JobTextField.DESCRIPTION_TEXT,
        job_char_start=start,
        job_char_end=start + len(quote),
        user_span_text=quote,
        proposed_by=EvidenceSource.RULE,
    )


async def store_score(
    session: AsyncSession,
    *,
    user: User,
    job: Job,
    overall: int,
    out_of: int,
    state: EligibilityState,
    quote: str = "Python",
    ruleset: str | None = None,
) -> MatchResult:
    """One stored score with the total and denominator a test needs.

    Built by hand rather than scored, because the surfaces that consume these
    rows are about *ordering* and a real scorer cannot be asked for a 40/50 and a
    45/100 on demand. `test_match_routes.py` is where the serialisation of a
    genuinely computed score is checked.

    Points go to `role` and `skill` because those are the two the evidence guard
    has something to check; the split is arbitrary and the fraction is not.
    ``quote`` must appear in the job's description — see `quoted_evidence`.
    """
    unassessable = UNASSESSABLE_FOR[out_of]
    role = min(overall, 20)
    skill = overall - role
    result = MatchResult(
        user_id=user.id,
        job_id=job.id,
        overall_score=overall,
        assessed_out_of=out_of,
        eligibility_status=state,
        role_score=role,
        skill_score=skill,
        project_evidence_score=0,
        location_score=0,
        freshness_score=0,
        priority_score=0,
        penalty_score=0,
        ruleset_version=ruleset or load_weights().ruleset_version,
    )
    result.assessments = [
        MatchComponentAssessment(
            component=component,
            assessable=component not in unassessable,
            why="a reason this test does not depend on",
        )
        for component in MatchComponent
    ]
    result.penalties = [
        MatchPenalty(
            name=name,
            points=0,
            applicable=False,
            why="a reason this test does not depend on",
        )
        for name in PenaltyName
    ]
    session.add(result)
    await session.flush()
    text_ = job.description_text or ""
    for component, points in ((MatchComponent.ROLE, role), (MatchComponent.SKILL, skill)):
        if points:
            session.add(
                quoted_evidence(
                    result, component=component, points=points, quote=quote, text_=text_
                )
            )
    await session.flush()
    return result


async def _ensure_test_database(settings: Settings) -> None:
    """Create the suite's database if this machine has never run the suite.

    ``CREATE DATABASE`` cannot run inside a transaction, hence ``AUTOCOMMIT``.
    The maintenance connection goes to ``postgres``, the database every server
    has, because the one we want may not exist yet.
    """
    # The query string is carried over rather than dropped: on a server that
    # requires `?ssl=require`, a maintenance connection without it does not
    # connect, and the failure would read as "database unreachable" on the one
    # machine that has never run the suite.
    base, _, query = settings.test_database_url.partition("?")
    admin_url = base.rsplit("/", 1)[0] + "/postgres" + (f"?{query}" if query else "")
    admin = create_async_engine(admin_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": settings.postgres_test_db},
            )
            if not exists:
                # The name comes from settings, not from a test, and Postgres
                # has no bind parameters in DDL. Quoted so an unusual but legal
                # name cannot break the statement.
                await connection.execute(text(f'CREATE DATABASE "{settings.postgres_test_db}"'))
    finally:
        await admin.dispose()

    await _install_extensions(settings)


def _read_extension_statements() -> tuple[str, ...]:
    """The statements in `infra/postgres/init/001-extensions.sql`.

    Read at import rather than inside the async fixture, so there is no
    blocking file I/O on the event loop to either commit or apologise for with
    a `noqa`.

    Comments are stripped line by line *before* splitting on ";". Splitting
    first and then discarding chunks that begin with "--" would discard the
    `postgis` statement, because the file's header comment shares a chunk with
    it — and PostGIS is the one extension whose absence is fatal.
    """
    sql_path = (
        Path(__file__).resolve().parents[3] / "infra" / "postgres" / "init" / "001-extensions.sql"
    )
    body = "\n".join(
        line
        for line in sql_path.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    )
    return tuple(chunk.strip() for chunk in body.split(";") if chunk.strip())


#: Replayed against the test database, rather than the list being retyped here,
#: because two copies of it drift and the way you find out is a migration that
#: only fails on a machine which has never run the suite before.
EXTENSION_STATEMENTS = _read_extension_statements()


async def _install_extensions(settings: Settings) -> None:
    """Give the test database the extensions the dev one gets for free.

    `infra/postgres/init/001-extensions.sql` runs once per *cluster*, against
    the database named in compose, so a second database created later has no
    PostGIS and the first migration fails on `type "geometry" does not exist`.
    """
    statements = EXTENSION_STATEMENTS
    engine = create_async_engine(
        settings.test_database_url, future=True, isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as connection:
            for statement in statements:
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


def _migrate_test_database(settings: Settings) -> None:
    """``alembic upgrade head`` against the test database, in a subprocess.

    A subprocess because ``migrations/env.py`` reads ``get_settings()``, which
    is ``lru_cache``d and already populated in this process by the time a
    fixture runs. Overriding ``DATABASE_URL`` in a child is honest; reaching
    into another module's cache is not.
    """
    api_dir = Path(__file__).resolve().parent.parent
    env = {**os.environ, "DATABASE_URL": settings.test_database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=api_dir,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "could not migrate the test database "
            f"({settings.postgres_test_db}):\n{result.stdout}\n{result.stderr}"
        )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """One engine per test session, bound to the suite's **own** database.

    `Settings()` (not `make_settings()`) deliberately reads the real
    environment here: these tests need the actual running Postgres, not a
    hermetic stand-in. Its defaults already match this project's `.env`
    (`localhost:5433`), so it works whether or not `.env` is visible from the
    test process's working directory.

    It binds to `test_database_url`, never `async_database_url`. One test in
    this suite commits and truncates twenty-one tables, by necessity — see
    `tests/test_the_suite_has_its_own_database.py` for why that is correct and
    why it may not happen in the database a person keeps their corpus in.
    """
    settings = Settings()
    url = settings.test_database_url
    try:
        await _ensure_test_database(settings)
    except (OSError, OperationalError) as exc:
        pytest.skip(f"database unreachable ({url}): {exc}")
    _migrate_test_database(settings)
    engine = create_async_engine(url, future=True)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (OSError, OperationalError) as exc:
        await engine.dispose()
        pytest.skip(f"database unreachable ({url}): {exc}")
    yield engine
    await engine.dispose()


# Tables the ingestion tests touch. Truncated at the start of every test (see
# below) and never outside the per-test transaction, so the truncation itself
# is undone by the same rollback that undoes everything else.
_INGESTION_TABLES = (
    # M5a. References `jobs`, so it comes before it. The ninth time this list
    # has been corrected by the database refusing to truncate rather than by
    # somebody remembering — the comment below predicted this exact table and
    # was right, which is the argument for never adding CASCADE here.
    "captured_postings",
    # M3c, and first in the list because all four reference `jobs` or each other
    # and `match_evidence` references `job_requirements` below it. Sixth milestone
    # running that this list has been kept correct by the database refusing to
    # truncate rather than by somebody remembering to edit it —
    # `match_component_assessments` was the seventh time it happened, at Task 9,
    # and `match_penalties` the eighth, at Task 10, both within a minute of the
    # table existing.
    "match_penalties",
    "match_component_assessments",
    "match_evidence",
    "match_results",
    # M3a. References `jobs`, and referenced by `match_evidence` above as of
    # M3c — added because the
    # no-CASCADE choice below refused to truncate the moment this table
    # started existing, which is the fifth milestone running that this list
    # has been kept correct by the database rather than by somebody
    # remembering.
    "job_requirements",
    # M1b's three, listed first because they reference `jobs` and
    # `ingestion_runs`. Adding them here is not optional: the no-CASCADE choice
    # below means TRUNCATE fails loudly the moment a new table references one
    # of these, which is exactly how this list stayed correct across M1b.
    "job_status_events",
    "job_merge_events",
    "job_embeddings",
    "job_source_links",
    "job_locations",
    "ingestion_runs",
    "source_job_records",
    # M1d. Added because the no-CASCADE choice below refused to truncate the
    # moment this table started referencing `sources` — which is the third
    # milestone running that this list has been kept correct by the database
    # rather than by somebody remembering.
    "board_poll_state",
    # M2b. `applications` references `jobs`, so TRUNCATE would fail without
    # these two — which is the fourth milestone running that this list has been
    # kept correct by the database rather than by somebody remembering.
    "application_events",
    "applications",
    "jobs",
    # M4a. References `companies`, so it has to precede it — the fifth milestone
    # running that this list has been kept correct by the database rather than
    # by somebody remembering, and the fifth time the no-CASCADE choice below
    # paid for itself.
    "company_locations",
    "companies",
    "sources",
    # M4a. References nothing — it is keyed on an address string, not on a
    # company — so it truncates in any order. Listed anyway: a cache that
    # survived between tests would make the second test to ask for an address
    # pass without ever reaching the rung it was written to exercise.
    "geocode_cache",
)


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """One transaction per test, rolled back at the end.

    Rollback rather than truncate-and-commit: it is faster, and it means a
    test cannot leave a row behind that makes the next one pass. Binding the
    session maker to the connection (not the engine) is what lets
    `session.begin_nested()` inside the ingestion pipeline keep working —
    ingestion takes a savepoint per posting, and a savepoint needs an outer
    transaction to nest inside.

    This project's dev database is not a disposable test database — it is
    the same Postgres instance `make demo` seeds, and it already carries real
    rows (M0's Datadog/Greenhouse board). The ingestion tests assert absolute
    counts (`created == 9`, `Company count == 1`), which only mean anything
    against an empty table. So this fixture truncates the tables ingestion
    touches *inside* the transaction it is about to roll back: every test
    starts from a genuinely empty slate, and the rollback at the end restores
    the pre-existing seed data exactly as it found it — nothing is lost
    outside this transaction, because nothing here ever commits.
    """
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        maker = async_sessionmaker(bind=connection, expire_on_commit=False)
        async with maker() as session:
            # No CASCADE: all seven FKs among these tables live inside this
            # list today, so it is a no-op — but a later milestone adds
            # tables with a foreign key to `jobs`, and CASCADE would silently
            # pull those into a destructive statement too. Without it,
            # TRUNCATE errors loudly and whoever hits it re-reads this list.
            await session.execute(text(f"TRUNCATE TABLE {', '.join(_INGESTION_TABLES)}"))
            yield session
        await transaction.rollback()


@pytest.fixture(scope="session")
def scoring_corpus() -> tuple[Any, ...]:
    """The 153 recorded postings, read and classified once for the whole session.

    Three test modules score this corpus — the golden file, the mutation
    harness, and Task 11's embedding measurement — and building it means running
    requirement extraction over every posting, which is ~26 seconds. Built per
    module it was the single largest cost any of them had, and none of them is
    *about* extraction.

    Deliberately not used by `test_two_full_runs_are_byte_identical`, which
    rebuilds from scratch on purpose: a determinism test handed a cached corpus
    is comparing one object against itself.
    """
    from tests.matching_corpus import load_corpus

    return load_corpus()
