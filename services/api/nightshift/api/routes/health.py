"""Health endpoint.

M0 acceptance is specific: ``/health`` must report DB and Redis honestly,
*including when they are down*. So this endpoint does not merely check that a
connection object exists — it runs a query and issues a PING, times both, and
returns 503 with the failure text when either fails.

A health check that returns 200 because the process is up tells you the one
thing you already knew.
"""

from __future__ import annotations

import asyncio
import time

import structlog
from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.schemas import HealthComponent, HealthResponse
from nightshift.config import Settings, get_settings
from nightshift.db.session import get_db_session
from nightshift.db.types import utcnow

router = APIRouter(tags=["health"])
log = structlog.get_logger(__name__)

# Short: a health probe that hangs for 20 seconds is itself an outage.
PROBE_TIMEOUT_SECONDS = 3.0

VERSION = "0.1.0"


async def _check_database(session: AsyncSession) -> HealthComponent:
    started = time.perf_counter()
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            # Assert the extensions too. A Postgres that lost PostGIS is not a
            # healthy database for this application, even though it answers.
            result = await session.execute(
                text("SELECT count(*) FROM pg_extension WHERE extname IN ('postgis', 'vector')")
            )
            extension_count = result.scalar_one()
    except TimeoutError:
        return HealthComponent(ok=False, detail=f"timed out after {PROBE_TIMEOUT_SECONDS}s")
    except Exception as exc:
        # Report the class and message: "connection refused" and "password
        # authentication failed" need different fixes.
        return HealthComponent(ok=False, detail=f"{type(exc).__name__}: {exc}")

    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    if extension_count < 2:
        return HealthComponent(
            ok=False,
            detail=f"expected postgis and vector extensions, found {extension_count}",
            latency_ms=elapsed_ms,
        )
    return HealthComponent(ok=True, detail="postgis + pgvector present", latency_ms=elapsed_ms)


async def _check_redis(settings: Settings) -> HealthComponent:
    started = time.perf_counter()
    client: Redis | None = None
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            client = Redis.from_url(settings.redis_dsn, socket_connect_timeout=2)
            await client.ping()
    except TimeoutError:
        return HealthComponent(ok=False, detail=f"timed out after {PROBE_TIMEOUT_SECONDS}s")
    except Exception as exc:
        return HealthComponent(ok=False, detail=f"{type(exc).__name__}: {exc}")
    finally:
        if client is not None:
            await client.aclose()

    return HealthComponent(
        ok=True, detail="PONG", latency_ms=round((time.perf_counter() - started) * 1000, 2)
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "One or more dependencies are down"}},
)
async def health(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Report dependency health, with the correct status code either way."""
    database, redis = await asyncio.gather(_check_database(session), _check_redis(settings))

    healthy = database.ok and redis.ok
    if not healthy:
        # 503, so a probe learns the truth from the status line alone.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        log.warning("health_degraded", database_ok=database.ok, redis_ok=redis.ok)

    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=VERSION,
        environment=settings.nightshift_env,
        database=database,
        redis=redis,
        checked_at=utcnow(),
    )


@router.get("/health/live", status_code=status.HTTP_204_NO_CONTENT)
async def liveness() -> None:
    """Process liveness only — no dependency checks.

    Separate from ``/health`` on purpose: a liveness probe that fails when the
    database is briefly unreachable restarts a perfectly healthy process and
    turns a blip into an outage.
    """
    return None
