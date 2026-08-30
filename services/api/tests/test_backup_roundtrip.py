"""A backup is only a backup if a restore brings the row back.

Q8 gave the suite its own database (`nightshift_test`). This test dumps that one
and restores into a **scratch** database it creates and drops itself. It never
writes to the dev database, and it never truncates anything: a backup test that
destroyed data to prove a point would be destroying exactly what it exists to
protect.

The scratch database starting empty is what makes the middle of this test real.
A restore test that never establishes the row was absent passes just as happily
when `restore.sh` does nothing at all.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from nightshift.config import get_settings
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRATCH_DB = "nightshift_backup_probe"

_PSQL = ("docker", "exec", "nightshift-postgres-1", "psql", "-U", "nightshift")


def _psql_blocking(database: str, sql: str) -> str:
    result = subprocess.run(
        [*_PSQL, "-d", database, "-tAc", sql],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


async def _psql(database: str, sql: str) -> str:
    """One statement in the postgres container, off the event loop.

    `subprocess.run` blocks, and blocking the loop inside an async test stalls
    the very connections the test is about to use.
    """
    return await asyncio.to_thread(_psql_blocking, database, sql)


def _script_blocking(name: str, arg: str, env: dict[str, str]) -> None:
    subprocess.run([name, arg], cwd=REPO_ROOT, env=env, check=True)


async def _script(name: str, arg: str, env: dict[str, str]) -> None:
    """Run one of the shell scripts under test, off the event loop."""
    await asyncio.to_thread(_script_blocking, name, arg, env)


async def test_a_backup_restores_the_readers_application(tmp_path: Path) -> None:
    """Deliberately does **not** take `db_session`.

    That fixture truncates the tables it is about to hand you, inside a
    transaction it holds open until teardown — and `TRUNCATE` takes an
    ACCESS EXCLUSIVE lock. This test needs a second connection that commits, so
    taking the fixture deadlocks it against itself: the insert below waits for a
    lock that is only released when the test it is part of finishes. It hung
    exactly that way before this comment existed.
    """
    settings = get_settings()
    assert "nightshift_test" in settings.test_database_url, (
        "this test dumps a database by name; it must never point at the dev one"
    )

    marker = f"restored-{uuid.uuid4()}"
    email = f"{marker}@example.invalid"

    # Committed on its own connection: `db_session` rolls back by design, and a
    # row that never leaves a transaction cannot be in a dump.
    engine = create_async_engine(settings.test_database_url)
    try:
        async with engine.begin() as connection:
            user_id = (
                await connection.execute(
                    text(
                        "INSERT INTO users (email, timezone) "
                        "VALUES (:email, 'America/New_York') RETURNING id"
                    ),
                    {"email": email},
                )
            ).scalar_one()
            company_id = (
                await connection.execute(
                    text(
                        "INSERT INTO companies (canonical_name, normalized_name) "
                        "VALUES (:name, :name) RETURNING id"
                    ),
                    {"name": marker},
                )
            ).scalar_one()
            job_id = (
                await connection.execute(
                    text(
                        "INSERT INTO jobs (company_id, title, normalized_title, "
                        "first_seen_at, last_seen_at) "
                        "VALUES (:company, :title, :title, now(), now()) RETURNING id"
                    ),
                    {"company": company_id, "title": marker},
                )
            ).scalar_one()
            await connection.execute(
                # `application_url` carries the marker: `applications` has no
                # free-text column, and this is the one a person would notice
                # missing — it is where they clicked apply.
                text(
                    "INSERT INTO applications (user_id, job_id, application_url) "
                    "VALUES (:user, :job, :marker)"
                ),
                {"user": user_id, "job": job_id, "marker": f"https://example.invalid/{marker}"},
            )

        dump = tmp_path / "backup.dump"
        await _script(
            "./scripts/backup.sh",
            str(dump),
            {**os.environ, "POSTGRES_DB": settings.postgres_test_db},
        )
        assert dump.stat().st_size > 0

        # A scratch database, empty by construction. "The row is not here" is
        # therefore a fact rather than something the test hopes it arranged.
        await _psql("postgres", f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"')
        await _psql("postgres", f'CREATE DATABASE "{SCRATCH_DB}"')
        try:
            missing = await _psql(
                SCRATCH_DB,
                "select count(*) from information_schema.tables where table_name = 'applications'",
            )
            assert missing == "0", "the scratch database is not empty; the restore proves nothing"

            await _script(
                "./scripts/restore.sh",
                str(dump),
                {**os.environ, "POSTGRES_DB": SCRATCH_DB},
            )

            restored = await _psql(
                SCRATCH_DB,
                "select count(*) from applications where application_url = "
                f"'https://example.invalid/{marker}'",
            )
            assert restored == "1", "the application did not survive the round trip"
        finally:
            await _psql("postgres", f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"')
    finally:
        # **Each statement in its own transaction.** These were one transaction
        # until a `finally` block hit an FK-ordering error, rolled the whole
        # cleanup back, and left a committed user in `nightshift_test`. Nothing
        # said so; the damage surfaced twenty minutes later as two unrelated
        # scoring tests failing `score_count == 1` with 2, because
        # `recompute_pending` scores every (user, job) pair and there was now an
        # extra user in the shared database.
        #
        # FK order still applies — innermost first — but one failure can no
        # longer keep the others from running, and `users` is the row that
        # actually matters.
        for statement, params in (
            (
                "DELETE FROM applications WHERE job_id IN "
                "(SELECT id FROM jobs WHERE title = :name)",
                {"name": marker},
            ),
            ("DELETE FROM jobs WHERE title = :name", {"name": marker}),
            ("DELETE FROM companies WHERE canonical_name = :name", {"name": marker}),
            ("DELETE FROM users WHERE email = :email", {"email": email}),
        ):
            try:
                async with engine.begin() as connection:
                    await connection.execute(text(statement), params)
            except SQLAlchemyError as exc:  # pragma: no cover - cleanup diagnostics
                print(f"cleanup failed for {statement!r}: {exc}")

        # Says so immediately rather than as somebody else's failure later.
        async with engine.connect() as connection:
            leaked = (
                await connection.execute(
                    text("SELECT count(*) FROM users WHERE email = :email"), {"email": email}
                )
            ).scalar_one()
        await engine.dispose()
        assert leaked == 0, (
            "this test leaked a committed user into the shared test database; "
            "every scoring test in the suite will now see an extra (user, job) pair"
        )
