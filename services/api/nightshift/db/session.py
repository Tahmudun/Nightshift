"""Async engine and session factory, shared by the API, the worker, and the CLI.

One engine per process. The worker and the API each get their own because they
are separate processes; they must not each get several, which is what happens
when an engine is created inside a request handler.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nightshift.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.async_database_url,
        echo=False,
        pool_pre_ping=True,
        # Small pools on purpose. One user and a few thousand jobs; a large pool
        # only hides a query that should have been fixed (CLAUDE.md §8).
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope for workers and the CLI: commit on success, roll back on error."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency.

    Read paths get a plain session and commit nothing; write routes commit
    explicitly. An implicit commit-on-response makes it impossible to tell from
    a handler's body whether it writes.
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    """Close pooled connections on shutdown so tests and reloads do not leak them."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
