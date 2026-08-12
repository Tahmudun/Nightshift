"""``/city/signals`` against a real database.

The map's whole data path, and the assertion that matters most is the boring
one: with no confirmed office anywhere in the database, **every role comes back
unresolved**. That is the honest render of this corpus (`city.md` §4.1: no ATS
posting names a street), and a route that quietly found somewhere to put them
would be the failure I1 exists to prevent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.api.main import create_app
from nightshift.db.base import JobStatus, LocationConfidence, RemotePolicy, ResolutionMethod
from nightshift.db.models import Company, CompanyLocation, Job
from nightshift.db.session import get_db_session
from tests.conftest import requires_db
from tests.test_routes import _seed_alloy_board

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _session_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _session_override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_client(db_session: AsyncSession, client: AsyncClient) -> AsyncClient:
    created = await _seed_alloy_board(db_session)
    assert created > 0, "seed produced no jobs — the tests below would pass vacuously"
    return client


async def _confirm_office(
    session: AsyncSession,
    company: Company,
    *,
    confidence: LocationConfidence = LocationConfidence.VERIFIED,
    building_id: str | None = "1087186",
) -> CompanyLocation:
    office = CompanyLocation(
        company_id=company.id,
        label="New York HQ",
        street_address="620 Eighth Avenue",
        city="New York",
        state="NY",
        latitude=40.755913,
        longitude=-73.989658,
        location_confidence=confidence,
        resolution_method=ResolutionMethod.NYC_GEOSEARCH,
        resolved_at=datetime.now(UTC),
        is_primary=True,
        building_id=building_id,
        confirmed_at=datetime.now(UTC),
        confirmed_by="Tahmudun",
    )
    session.add(office)
    await session.flush()
    return office


async def test_with_no_confirmed_office_every_role_is_unresolved(
    seeded_client: AsyncClient,
) -> None:
    """The state of this product today, asserted rather than assumed."""
    body = (await seeded_client.get("/city/signals")).json()

    assert body["counts"]["total"] > 0
    assert body["counts"]["unresolved"] == body["counts"]["total"]
    assert body["counts"]["building"] == 0
    assert body["counts"]["area"] == 0
    for signal in body["signals"]:
        assert signal["placement"]["kind"] == "unresolved"
        assert signal["placement"]["latitude"] is None
        assert signal["placement"]["longitude"] is None


async def test_the_counts_agree_with_the_signals_they_ship_with(
    seeded_client: AsyncClient,
) -> None:
    """Two numbers describing one thing must not be able to disagree."""
    body = (await seeded_client.get("/city/signals")).json()
    counts = body["counts"]

    kinds = [signal["placement"]["kind"] for signal in body["signals"]]
    assert counts["building"] == kinds.count("building")
    assert counts["area"] == kinds.count("area")
    assert counts["unresolved"] == kinds.count("unresolved")
    assert counts["total"] == len(body["signals"])


async def test_a_confirmed_office_lights_its_companys_roles(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    """One address typed by a human moves a whole employer onto a building."""
    alloy = (
        await db_session.execute(select(Company).where(Company.canonical_name == "Alloy"))
    ).scalar_one()
    await _confirm_office(db_session, alloy)

    body = (await seeded_client.get("/city/signals")).json()

    placed = [s for s in body["signals"] if s["placement"]["kind"] == "building"]
    assert placed, "a confirmed office placed nothing"
    assert body["counts"]["building"] == len(placed)
    for signal in placed:
        assert signal["company_name"] == "Alloy"
        placement = signal["placement"]
        assert placement["building_id"] == "1087186"
        assert placement["location_confidence"] == "verified"
        # §4.4: never silently. The response carries the inheritance and the
        # office that caused it, so the panel can say which claim this is.
        assert placement["resolution_method"] == "company_office"
        assert placement["inherited"] is True
        assert placement["office_label"] == "New York HQ"
        # And what the posting itself said survives beside it.
        assert placement["stated"]


async def test_an_approximate_office_produces_areas_and_no_buildings(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    alloy = (
        await db_session.execute(select(Company).where(Company.canonical_name == "Alloy"))
    ).scalar_one()
    await _confirm_office(
        db_session, alloy, confidence=LocationConfidence.APPROXIMATE, building_id=None
    )

    body = (await seeded_client.get("/city/signals")).json()

    assert body["counts"]["building"] == 0
    assert body["counts"]["area"] > 0
    for signal in body["signals"]:
        if signal["placement"]["kind"] == "area":
            assert signal["placement"]["building_id"] is None


async def test_a_remote_role_is_not_moved_into_its_employers_office(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    alloy = (
        await db_session.execute(select(Company).where(Company.canonical_name == "Alloy"))
    ).scalar_one()
    await _confirm_office(db_session, alloy)

    job = (
        await db_session.execute(select(Job).where(Job.company_id == alloy.id).limit(1))
    ).scalar_one()
    job.remote_policy = RemotePolicy.REMOTE
    await db_session.flush()

    body = (await seeded_client.get("/city/signals")).json()

    signal = next(s for s in body["signals"] if s["job_id"] == str(job.id))
    assert signal["placement"]["kind"] == "unresolved"
    assert signal["placement"]["latitude"] is None


async def test_closed_listings_are_absent_until_they_are_asked_for(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    job = (await db_session.execute(select(Job).limit(1))).scalar_one()
    job.status = JobStatus.CLOSED
    # `ck_jobs_closed_at_matches_status` refuses a closed job with no closing
    # time, which is the closure machine's own record keeping — a test is not
    # exempt from it, and reaching for it here is how you find out the
    # constraint is real.
    job.closed_at = datetime.now(UTC)
    await db_session.flush()

    default = (await seeded_client.get("/city/signals")).json()
    assert all(s["job_id"] != str(job.id) for s in default["signals"])

    archive = (await seeded_client.get("/city/signals?include_closed=true")).json()
    assert any(s["job_id"] == str(job.id) for s in archive["signals"])


async def test_a_truncated_city_says_so(seeded_client: AsyncClient) -> None:
    """A partial city that does not admit it is a partial city presented as whole."""
    body = (await seeded_client.get("/city/signals?limit=2")).json()

    assert len(body["signals"]) == 2
    assert body["truncated"] is True
    assert (await seeded_client.get("/city/signals")).json()["truncated"] is False


async def test_the_order_is_stable_across_calls(seeded_client: AsyncClient) -> None:
    """A renderer diffing against its last frame needs the same order twice."""
    first = (await seeded_client.get("/city/signals")).json()
    second = (await seeded_client.get("/city/signals")).json()

    assert [s["job_id"] for s in first["signals"]] == [s["job_id"] for s in second["signals"]]


async def test_the_route_does_not_write_the_inheritance_back(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The join is a read. `job_locations` still holds what the posting said.

    `office_loading.py` refused to materialise this precisely so a corrected
    office cannot strand a stale coordinate. Serving the map must not undo that.
    """
    alloy = (
        await db_session.execute(select(Company).where(Company.canonical_name == "Alloy"))
    ).scalar_one()
    await _confirm_office(db_session, alloy)

    await seeded_client.get("/city/signals")

    job = (
        await db_session.execute(
            select(Job)
            .where(Job.company_id == alloy.id)
            .options(selectinload(Job.locations))
            .limit(1)
        )
    ).scalar_one()
    for row in job.locations:
        assert row.latitude is None
        assert row.location_confidence is not LocationConfidence.VERIFIED
