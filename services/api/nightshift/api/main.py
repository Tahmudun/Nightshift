"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nightshift.api.routes import (
    applications,
    companies,
    health,
    jobs,
    profile,
    queue,
    resumes,
    sources,
)
from nightshift.config import get_settings
from nightshift.db.session import dispose_engine
from nightshift.logging import configure_logging

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    # Settings are constructed here, so an invalid environment fails at startup
    # with a message naming the field rather than mid-request with a timeout.
    log.info("api_starting", **settings.redacted())
    yield
    await dispose_engine()
    log.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Nightshift API",
        description="Live career intelligence for New York tech.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allow_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(sources.router)
    app.include_router(companies.router)
    app.include_router(applications.router)
    app.include_router(profile.router)
    app.include_router(resumes.router)
    app.include_router(queue.router)
    return app


app = create_app()
