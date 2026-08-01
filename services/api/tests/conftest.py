"""Shared test fixtures.

Tests must not read the developer's ``.env``. A suite whose result depends on a
local file is a suite that passes on one machine and fails in CI, so every
:class:`Settings` here is built with ``_env_file=None`` and explicit values.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
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


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """One engine per test session, bound to the project's own settings.

    `Settings()` (not `make_settings()`) deliberately reads the real
    environment here: these tests need the actual running Postgres, not a
    hermetic stand-in. Its defaults already match this project's `.env`
    (`localhost:5433/nightshift`), so it works whether or not `.env` is
    visible from the test process's working directory.
    """
    url = Settings().async_database_url
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
    "job_source_links",
    "job_locations",
    "ingestion_runs",
    "source_job_records",
    "jobs",
    "companies",
    "sources",
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
