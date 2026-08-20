"""Company routes against a real database.

``/companies/{id}`` exists so a job's employer is a place you can go, not just
a string on a row. The counts are by closure state because a company page
showing only open roles hides the thing the closure machine exists to make
visible — the same reasoning as ``/jobs/admin``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.models import Company
from nightshift.db.session import get_db_session
from tests.conftest import requires_db
from tests.test_routes import _seed_alloy_board

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


#: A stand-in caller for the corpus routes below (M5b, ADR 0037). Not a row in
#: `users`: nothing these routes read joins to one, and inventing a real
#: account would imply these tests are about a person when they are about a
#: corpus.
_CALLER = uuid.UUID("00000000-0000-4000-8000-0000000000ff")


async def _test_user_id() -> uuid.UUID:
    return _CALLER


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """The app, reading the test's own uncommitted transaction.

    Same hazard as test_routes.py: letting the app open its own session would
    make it blind to this test's seed data, would block on ``db_session``'s
    TRUNCATE, and would commit for real against the developer's database.
    """
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _session_override

    # M5b (ADR 0037): every router except `/health` and `/auth` is behind a
    # session now, including the corpus routes this file tests, which were open
    # before. These tests are about what a route *returns*, not about who may
    # ask — that question has its own module,
    # `test_two_users_cannot_see_each_other.py`, which deliberately overrides
    # nothing and signs in over HTTP.
    app.dependency_overrides[current_user_id] = _test_user_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_client(db_session: AsyncSession, client: AsyncClient) -> AsyncClient:
    """``client``, with the recorded Alloy board persisted."""
    created = await _seed_alloy_board(db_session)
    assert created > 0, "seed produced no jobs — the tests below would pass vacuously"
    return client


async def test_listing_companies_returns_the_seeded_ones(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    seeded = (await db_session.execute(select(Company))).scalars().all()
    assert seeded, "no company in the seed"
    body = (await seeded_client.get("/companies")).json()
    assert body["total"] == len(seeded)
    assert {item["canonical_name"] for item in body["items"]} == {
        company.canonical_name for company in seeded
    }


async def test_a_company_row_carries_its_job_count(seeded_client: AsyncClient) -> None:
    body = (await seeded_client.get("/companies")).json()
    alloy = next(item for item in body["items"] if item["canonical_name"] == "Alloy")
    assert alloy["job_count"] == 9


async def test_a_company_detail_counts_jobs_by_closure_state(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    company = (await db_session.execute(select(Company))).scalars().first()
    assert company is not None
    body = (await seeded_client.get(f"/companies/{company.id}")).json()
    assert body["canonical_name"] == company.canonical_name
    counts = body["job_status_counts"]
    # Every state present as an explicit integer: a missing key and a real zero
    # are different claims and the UI must not have to guess which it is.
    assert set(counts) == {"open", "possibly_stale", "unverified", "closed"}
    assert sum(counts.values()) == 9
    assert counts["closed"] == 0


async def test_an_unknown_company_is_404_not_an_empty_company(client: AsyncClient) -> None:
    """An empty company and a missing one are different answers and must not
    look alike — the same rule /jobs/{id}/history follows."""
    response = await client.get(f"/companies/{uuid4()}")
    assert response.status_code == 404


async def test_company_search_filters_by_name(seeded_client: AsyncClient) -> None:
    body = (await seeded_client.get("/companies", params={"q": "allo"})).json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert "allo" in item["canonical_name"].lower()


async def test_company_search_is_case_insensitive(seeded_client: AsyncClient) -> None:
    upper = (await seeded_client.get("/companies", params={"q": "ALLOY"})).json()
    lower = (await seeded_client.get("/companies", params={"q": "alloy"})).json()
    assert upper["total"] == lower["total"] >= 1


async def test_a_blank_company_query_returns_every_company(
    seeded_client: AsyncClient,
) -> None:
    """Same rule as the job search: an empty box is not a filter."""
    everything = (await seeded_client.get("/companies")).json()["total"]
    blank = (await seeded_client.get("/companies", params={"q": "  "})).json()["total"]
    assert blank == everything


async def test_first_seen_at_is_ours_and_is_the_earliest(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    """A10: named for what it is. It is when *we* first saw a role from this
    employer, never presented as when they started hiring."""
    company = (await db_session.execute(select(Company))).scalars().first()
    assert company is not None
    body = (await seeded_client.get(f"/companies/{company.id}")).json()
    assert body["first_seen_at"] is not None
    jobs = (await seeded_client.get("/jobs", params={"limit": 100})).json()["items"]
    assert body["first_seen_at"] == min(job["first_seen_at"] for job in jobs)
