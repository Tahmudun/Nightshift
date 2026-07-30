"""Alembic environment, async.

Async rather than sync so there is one database driver in the project instead of
two. Adding psycopg2 purely for migrations means a second driver to install, a
second connection string to keep in sync, and a second set of type behaviours to
be surprised by.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from citysignal.config import get_settings
from citysignal.db import models  # noqa: F401 - import registers the models on Base.metadata
from citysignal.db.autogenerate import build_include_object, reflect_extension_owned
from citysignal.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().async_database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        # Offline mode has no connection to read pg_depend from. It is used for
        # rendering DDL (`upgrade --sql`), never for autogenerate, so the static
        # PostGIS names are the whole of what it needs.
        include_object=build_include_object(target_metadata, frozenset()),
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    extension_owned = reflect_extension_owned(connection)
    # That read autobegan a transaction, and alembic only commits a transaction
    # it opened itself. If one is already open when configure() runs, alembic
    # treats it as externally managed, never commits, and the enclosing
    # `connect()` block rolls the whole migration back on close — every CREATE
    # TABLE and the alembic_version row with them — while `alembic upgrade head`
    # still prints "Running upgrade" and exits 0. Ending the read here leaves
    # alembic owning its own transaction, which is the only reason the DDL
    # survives. The "Upgrade actually persisted" step in .github/workflows/ci.yml
    # is what stops this regressing — it is not detectable from the exit code.
    connection.rollback()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=build_include_object(target_metadata, extension_owned),
        # Alembic's own version table gets a schema-qualified name so a future
        # multi-schema layout does not silently create a second one.
        version_table="alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
