"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nightshift.api.deps import require_session
from nightshift.api.routes import (
    applications,
    auth,
    capture,
    city,
    companies,
    health,
    jobs,
    matches,
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

    # -- Open by design (M5b, ADR 0037) ------------------------------------
    #
    # Exactly two routers answer an anonymous request, and both have to.
    # `/health` reports on a database that may be down, so requiring a session
    # would make it unable to say so. `/auth` is how a request stops being
    # anonymous.
    app.include_router(health.router)
    app.include_router(auth.router)

    # -- Everything else: default-deny -------------------------------------
    #
    # The dependency is attached here, once, rather than declared by each
    # handler. A route is behind a session because it exists — including
    # `/jobs` and `/city/signals`, which serve the shared corpus and still have
    # no business answering a stranger. Opening one means editing this list,
    # which is a line in a diff rather than a handler that quietly omitted a
    # parameter.
    protected = Depends(require_session)
    for router in (
        jobs.router,
        city.router,
        capture.router,
        matches.router,
        sources.router,
        companies.router,
        applications.router,
        profile.router,
        resumes.router,
        queue.router,
    ):
        app.include_router(router, dependencies=[protected])
    return app


app = create_app()
