"""The test suite may never run against the database a person keeps data in.

Q8 stayed open for four billings because the symptom — a corpus that vanished
after ``make check`` — looked like a fixture leak and was not. The cause was
that the suite and the product share one database, and one test commits.

``tests/test_merge_concurrency.py`` **has** to commit. It exercises two
concurrent transactions merging the same pair of jobs, which cannot be
observed inside a transaction that is rolled back, and it cleans up with
``TRUNCATE`` because ``job_merge_events`` is append-only and refuses a
``DELETE`` (M1b's trigger working as intended). Its table list includes
``jobs``, ``companies``, ``captured_postings``, ``applications`` and
``geocode_cache``.

So the fix is not to stop that test committing. It is to stop it committing
*here*. These tests are the thing that keeps it that way — a defence against
one line of configuration, edited a year from now for a good reason, quietly
handing the suite the live database back.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from nightshift.config import Settings
from tests.conftest import requires_db


def test_the_test_database_is_not_the_development_database() -> None:
    """The two URLs must differ, and differ in the database *name*.

    A different host or port would also isolate them, but the failure this
    guards against is a shared name on one local Postgres, which is what the
    defaults produce.
    """
    settings = Settings()

    assert settings.test_database_url != settings.async_database_url
    assert settings.postgres_test_db != settings.postgres_db


@requires_db
async def test_the_running_suite_is_bound_to_the_test_database(
    db_engine: AsyncEngine,
) -> None:
    """The engine every committing test uses resolves to the test database.

    The assertion above compares two settings properties, which stay true even
    if ``conftest`` stops reading the one it should. This one reads the engine
    the suite actually got.
    """
    settings = Settings()

    assert db_engine.url.database == settings.postgres_test_db
    assert db_engine.url.database != settings.postgres_db
