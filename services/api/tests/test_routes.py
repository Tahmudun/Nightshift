"""API routes against a real database.

Routes validate and delegate (CLAUDE.md §3), so what is worth asserting here
is the contract the web app's Zod schemas parse — and that /health tells the
truth, which is acceptance row 4's whole point.

The response shapes below were read from the real routes and schemas
(``nightshift/api/routes/health.py``, ``nightshift/api/routes/jobs.py``,
``nightshift/api/schemas.py``) rather than assumed, per this task's own
instruction that the route is the contract. Two shapes differ from the first
draft:

* ``/health`` has **no** ``checks`` wrapper. ``HealthResponse`` puts
  ``database`` and ``redis`` at the top level.
* ``/jobs`` returns ``{items, total, limit, offset}``; each item's
  ``locations`` list carries ``location_confidence`` and ``latitude``
  directly on the location object (``JobLocationOut``), not nested further.

HAZARD (see this task's brief): ``session_scope()`` commits. Letting the
FastAPI app open its own session here would mean the app cannot see this
file's uncommitted seed data, would block on ``db_session``'s ``TRUNCATE``
(an ACCESS EXCLUSIVE lock held for the test's duration), and would commit for
real against the developer's database. Every test below overrides
``get_db_session`` with the fixture's own transactional session instead.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob
from nightshift.adapters.lever import LeverAdapter
from nightshift.api.main import create_app
from nightshift.db.base import SourceType
from nightshift.db.session import get_db_session
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from tests.conftest import requires_db

# db_session binds its asyncpg connection to conftest's session-scoped event
# loop (see test_ingestion.py for the same convention), so every test and
# every async fixture that touches it must run on that loop too.
pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

FIXTURES = Path(__file__).parent / "fixtures"
LEVER_BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)


class _StubAdapter:
    """A real adapter with its network call replaced by a recorded outcome.

    Mirrors the helper in test_ingestion.py: the adapter's own normalize()
    runs untouched, so what the route serialises is the real
    fetch -> normalize -> persist output on a real recorded board, not a
    hand-built row.
    """

    def __init__(self, inner: Any, outcome: FetchOutcome) -> None:
        self._inner = inner
        self._outcome = outcome
        self.source_name = inner.source_name
        self.source_type = inner.source_type

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        return self._outcome

    def normalize(self, raw_job: RawJob, board: BoardRef) -> Any:
        return self._inner.normalize(raw_job, board)


async def _seed_alloy_board(session: AsyncSession) -> int:
    """Ingest the committed Lever fixture into the test's transaction.

    Returns the number of jobs created, so tests can assert against it
    instead of a magic number.
    """
    payload = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    jobs = tuple(
        RawJob(
            source_job_id=str(entry["id"]),
            source_company_key="alloy",
            canonical_url=entry.get("hostedUrl"),
            payload=entry,
        )
        for entry in payload
    )
    outcome = FetchOutcome(board=LEVER_BOARD, ok=True, jobs=jobs, http_status=200)
    source = await get_or_create_source(
        session, name="lever_test", source_type=SourceType.ATS_LEVER
    )
    adapter = _StubAdapter(LeverAdapter(client=None), outcome)
    _, stats = await ingest_boards(session, adapter, [LEVER_BOARD], source=source)
    await session.flush()
    return stats.created


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """The ASGI app, wired to the fixture's own transactional session.

    ``app.dependency_overrides`` replaces ``get_db_session`` with a stand-in
    that always yields ``db_session`` — the same connection the truncate/
    rollback fixture holds — so every route in this file sees the test's
    seed data and commits nothing for real.
    """
    app = create_app()

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_client(db_session: AsyncSession, client: AsyncClient) -> AsyncClient:
    """``client``, with one real recorded board already persisted."""
    created = await _seed_alloy_board(db_session)
    assert created > 0, "seed produced no jobs — the tests below would pass vacuously"
    return client


async def test_health_reports_both_dependencies(client: AsyncClient) -> None:
    """M0 acceptance row 4, still true in M1a.

    ``HealthResponse`` has no ``checks`` wrapper — ``database`` and ``redis``
    are top-level keys (nightshift/api/schemas.py).
    """
    response = await client.get("/health")
    assert response.status_code in (200, 503)
    body = response.json()
    for key in ("database", "redis"):
        assert isinstance(body[key]["ok"], bool)
        assert body[key]["detail"]


async def test_liveness_does_not_touch_the_database(client: AsyncClient) -> None:
    """A liveness probe that fails when Postgres is down restarts a healthy app."""
    response = await client.get("/health/live")
    assert response.status_code == 204
    assert response.content == b""


async def test_jobs_route_returns_the_documented_shape(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get("/jobs")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    assert body["total"] == len(body["items"]) == 9
    first = body["items"][0]
    assert {"id", "title", "company", "locations", "salary", "status"} <= first.keys()
    assert first["company"]["canonical_name"] == "Alloy"


async def test_every_returned_location_has_a_confidence(seeded_client: AsyncClient) -> None:
    """I1 at the API boundary. The web app's Zod schema rejects a point whose
    confidence does not justify it; this asserts the field is always there to
    be checked, on a real ingested board rather than a hand-built row."""
    body = (await seeded_client.get("/jobs")).json()
    assert body["items"], "seed produced no jobs to check"
    seen_confidences: set[str] = set()
    for job in body["items"]:
        assert job["locations"], f"{job['title']!r} has no location rows"
        for location in job["locations"]:
            assert location["location_confidence"] in {
                "verified",
                "approximate",
                "city_only",
                "remote",
                "unknown",
            }
            seen_confidences.add(location["location_confidence"])
            if location["location_confidence"] in {"city_only", "remote", "unknown"}:
                assert location["latitude"] is None
    # Geocoding does not exist yet (M1), so every one of the alloy board's
    # locations must land in this branch — an empty set here would mean the
    # loop above never ran.
    assert seen_confidences, "no confidence values observed — test proves nothing"


async def test_unknown_job_id_is_404_not_500(client: AsyncClient) -> None:
    response = await client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
