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
from datetime import UTC, datetime, timedelta
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

# A fixed clock for the seed. M1b's closure rules are a function of elapsed
# time, so a test that wants three misses seven days apart needs a known
# starting point rather than "whenever the suite happened to run".
SEED_NOW = datetime(2026, 8, 1, tzinfo=UTC)


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


async def _ingest_alloy(
    session: AsyncSession, *, jobs: list[dict[str, Any]] | None = None, now: datetime = SEED_NOW
) -> int:
    """Poll the Alloy board at an explicit time, with an explicit payload.

    The clock is a parameter because M1b's closure rules are a function of it:
    a test that wants three misses has to be able to say when they happened.
    Passing ``jobs=[]`` is a live board with nothing on it — real evidence of
    absence, and deliberately not the same as a failed fetch.

    Returns the number of jobs created, so tests assert against it rather than
    a magic number.
    """
    if jobs is None:
        jobs = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    outcome = FetchOutcome(
        board=LEVER_BOARD,
        ok=True,
        http_status=200,
        jobs=tuple(
            RawJob(
                source_job_id=str(entry["id"]),
                source_company_key="alloy",
                canonical_url=entry.get("hostedUrl"),
                payload=entry,
            )
            for entry in jobs
        ),
    )
    source = await get_or_create_source(
        session, name="lever_test", source_type=SourceType.ATS_LEVER
    )
    adapter = _StubAdapter(LeverAdapter(client=None), outcome)
    _, stats = await ingest_boards(session, adapter, [LEVER_BOARD], source=source, now=now)
    await session.flush()
    return stats.created


async def _seed_alloy_board(session: AsyncSession) -> int:
    """Ingest the committed Lever fixture at ``SEED_NOW``."""
    return await _ingest_alloy(session)


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


# ---------------------------------------------------------------------------
# M1b — the operational surface. Closure and dedupe are only useful if a human
# can see what they did; §2.6 and M1's "failures visible in the UI, not just
# logs" criterion both land here.
# ---------------------------------------------------------------------------


async def test_admin_route_is_not_read_as_a_job_id(seeded_client: AsyncClient) -> None:
    """FastAPI matches routes in declaration order.

    Declared after ``/{job_id}``, this path resolves as a job whose id is the
    string "admin" and returns 422. The bug is invisible in the code and
    obvious in the response, so the response is what gets asserted.
    """
    response = await seeded_client.get("/jobs/admin")
    assert response.status_code == 200, response.text


async def test_admin_route_reports_every_status_even_at_zero(
    seeded_client: AsyncClient,
) -> None:
    """A missing key and a real zero are different claims.

    The seeded board is entirely open, so three of the four counts are zero.
    They must still be present — otherwise the UI cannot distinguish "no closed
    jobs" from "the API forgot to tell me about closed jobs".
    """
    body = (await seeded_client.get("/jobs/admin")).json()
    assert set(body["status_counts"]) == {"open", "possibly_stale", "unverified", "closed"}
    assert body["status_counts"]["open"] == 9
    assert body["status_counts"]["closed"] == 0
    assert body["total"] == 9


async def test_admin_rows_carry_provenance(seeded_client: AsyncClient) -> None:
    """M1 acceptance: every canonical job traces to at least one raw record.

    Asserted at the API boundary, which is where a human can actually see it.
    """
    body = (await seeded_client.get("/jobs/admin")).json()
    assert body["items"]
    for job in body["items"]:
        assert job["source_count"] >= 1
        assert job["location_count"] >= 1
        assert job["merge_count"] == 0
        assert job["status"] in {"open", "possibly_stale", "unverified", "closed"}
        # I3 at the boundary: an open job has no closure timestamp, and the
        # database constraint that pairs them is mirrored in what we serve.
        assert (job["closed_at"] is not None) == (job["status"] == "closed")


async def test_admin_route_filters_by_status(seeded_client: AsyncClient) -> None:
    body = (await seeded_client.get("/jobs/admin", params={"status": "closed"})).json()
    assert body["items"] == []
    # The breakdown is over the whole table, not the filtered page — otherwise
    # filtering to `closed` would report zero of everything and the operator
    # would lose the only number that says what else exists.
    assert body["status_counts"]["open"] == 9


async def test_admin_route_rejects_an_unknown_status(seeded_client: AsyncClient) -> None:
    """A typo'd filter must be an error, not a silent empty list — the latter
    reads as "no such jobs" and is how an operator concludes nothing is wrong."""
    response = await seeded_client.get("/jobs/admin", params={"status": "not_a_state"})
    assert response.status_code == 422


async def test_history_route_is_404_for_an_unknown_job(client: AsyncClient) -> None:
    """ "No transitions" and "no such job" are different answers."""
    response = await client.get("/jobs/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404


async def test_history_is_empty_for_a_job_that_never_transitioned(
    seeded_client: AsyncClient,
) -> None:
    """A freshly ingested, still-listed job has no transitions — and an empty
    list here is the honest answer, distinct from the 404 above."""
    job_id = (await seeded_client.get("/jobs/admin")).json()["items"][0]["id"]
    response = await seeded_client.get(f"/jobs/{job_id}/history")
    assert response.status_code == 200
    assert response.json() == []


async def test_history_returns_transitions_in_the_words_the_machine_used(
    db_session: AsyncSession, seeded_client: AsyncClient
) -> None:
    """The reason string is the deliverable, not the status change.

    "Why did this job disappear?" is answered by prose a human wrote into
    freshness.py, and this is the route that carries it to them.
    """
    # Three polls of an empty-but-live board: real evidence of absence.
    for day in (1, 2, 3):
        await _ingest_alloy(db_session, jobs=[], now=SEED_NOW + timedelta(days=day))
    await db_session.flush()

    stale = (await seeded_client.get("/jobs/admin", params={"status": "possibly_stale"})).json()
    assert stale["items"], "three misses did not make anything stale"

    history = (await seeded_client.get(f"/jobs/{stale['items'][0]['id']}/history")).json()
    assert len(history) == 1
    event = history[0]
    assert event["from_status"] == "open"
    assert event["to_status"] == "possibly_stale"
    assert "consecutive polls" in event["reason"]
    assert event["observed_misses"] == 3


async def test_source_health_distinguishes_an_outage_from_an_empty_board(
    seeded_client: AsyncClient,
) -> None:
    """§2.6 and I3 at the API boundary.

    If these two timestamps collapsed into one "last seen" field, the UI could
    not tell a user which of the two happened — and those are the two facts the
    whole closure design turns on.
    """
    body = (await seeded_client.get("/sources")).json()
    assert body
    for source in body:
        assert "last_success_at" in source
        assert "last_failure_at" in source


async def test_source_health_breaks_its_jobs_down_by_status(
    db_session: AsyncSession, seeded_client: AsyncClient
) -> None:
    """The count that `job_count` alone cannot give you.

    A provenance link survives a closure, so `job_count` does not move when a
    source's jobs go stale — a dead board and a healthy one report the same
    total. Without this breakdown the source health page would say a source is
    fine while every job it ever produced had aged out.
    """
    before = (await seeded_client.get("/sources")).json()
    lever = next(s for s in before if s["name"] == "lever_test")
    assert lever["job_status_counts"]["open"] == 9
    assert lever["job_status_counts"]["possibly_stale"] == 0

    for day in (1, 2, 3):
        await _ingest_alloy(db_session, jobs=[], now=SEED_NOW + timedelta(days=day))
    await db_session.flush()

    after = (await seeded_client.get("/sources")).json()
    lever = next(s for s in after if s["name"] == "lever_test")
    assert lever["job_status_counts"]["open"] == 0
    assert lever["job_status_counts"]["possibly_stale"] == 9
    # The headline total is unchanged — which is exactly the point.
    assert lever["job_count"] == 9
