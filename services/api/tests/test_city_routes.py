"""``/city/signals`` against a real database.

The map's whole data path, and the assertion that matters most is the boring
one: with no confirmed office anywhere in the database, **every role comes back
unresolved**. That is the honest render of this corpus (`city.md` §4.1: no ATS
posting names a street), and a route that quietly found somewhere to put them
would be the failure I1 exists to prevent.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.config import get_settings
from nightshift.db.base import (
    EmploymentType,
    JobStatus,
    LocationConfidence,
    RemotePolicy,
    ResolutionMethod,
)
from nightshift.db.models import (
    Company,
    CompanyLocation,
    Job,
    JobLocation,
    JobSourceLink,
    SourceJobRecord,
)
from nightshift.db.session import get_db_session
from nightshift.domain.capture import confirm_capture, create_capture
from nightshift.domain.markets import current_scope
from tests.conftest import requires_db
from tests.test_capture import _a_user
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
    created = await _seed_alloy_board(db_session)
    assert created > 0, "seed produced no jobs — the tests below would pass vacuously"
    await _move_to_new_york(db_session)
    return client


async def _move_to_new_york(session: AsyncSession) -> None:
    """Put the committed Alloy board's roles in New York.

    As committed they are in Denver, Vancouver and Washington, and the city
    draws New York's roles only (ADR 0041), so none would reach it. The tests
    that use this fixture are about what the city does with the roles it shows
    (placement, inheritance, freshness), so every named city is moved to New
    York, spelled the way the location parser writes it. What the city does
    with a role that is elsewhere is tested on the board as committed, at the
    end of this file.
    """
    await session.execute(
        update(JobLocation)
        .where(JobLocation.city.is_not(None))
        .values(raw_text="New York, NY", city="New York", state="New York", country=None)
    )
    await session.flush()


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


async def _records_of(session: AsyncSession, job: Job) -> list[SourceJobRecord]:
    """Every raw record behind one canonical job. Asserted non-empty, because a
    job with no records would make each test below pass without testing."""
    records = list(
        (
            await session.execute(
                select(SourceJobRecord)
                .join(JobSourceLink, JobSourceLink.source_job_record_id == SourceJobRecord.id)
                .where(JobSourceLink.job_id == job.id)
            )
        )
        .scalars()
        .all()
    )
    assert records, "this job has no source record — the assertions below would be vacuous"
    return records


async def _second_record(
    session: AsyncSession,
    job: Job,
    like: SourceJobRecord,
    *,
    last_verified_at: datetime,
) -> SourceJobRecord:
    """A second board describing the same role, linked to the same canonical job.

    Which is what a merge produces, and what makes an aggregate over a job's
    records mean anything at all.
    """
    record = SourceJobRecord(
        source_id=like.source_id,
        source_job_id=f"{like.source_job_id}-second-board",
        source_company_key=like.source_company_key,
        raw_payload=like.raw_payload,
        first_seen_at=like.first_seen_at,
        last_seen_at=like.last_seen_at,
        last_verified_at=last_verified_at,
    )
    session.add(record)
    await session.flush()
    session.add(
        JobSourceLink(
            job_id=job.id,
            source_job_record_id=record.id,
            match_confidence=0.99,
            link_reason="test fixture: the same role on a second board",
        )
    )
    await session.flush()
    return record


async def test_a_signal_carries_when_it_was_last_seen_on_its_board(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`city.md` §6 dims a stale role and asks the panel to say *how* stale.

    "Reduced opacity + an explicit 'last verified N days ago'" is one row of the
    table, and the second half of it cannot be drawn from anything already on
    this payload: ``first_seen_at`` is when ingestion *first* saw the role, and
    a dimmed beacon with no date on it is the glitch this row exists to refuse.
    """
    seen = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    job = (await db_session.execute(select(Job).limit(1))).scalar_one()
    job.status = JobStatus.POSSIBLY_STALE
    job.last_seen_at = seen
    await db_session.flush()

    body = (await seeded_client.get("/city/signals")).json()

    signal = next(s for s in body["signals"] if s["job_id"] == str(job.id))
    assert signal["status"] == "possibly_stale"
    assert datetime.fromisoformat(signal["last_seen_at"]) == seen


async def test_an_unverified_role_says_null_rather_than_falling_back(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two different observations, and the payload keeps them apart.

    ``source_job_records.last_verified_at`` is the stronger of the two — "we
    refetched its content and read it", against ``last_seen_at``'s "the board
    listed it" — and ADR 0007's phase-2 polling means an unchanged posting is
    deliberately never refetched, so a long-open role can be listed daily and
    verified months ago. Falling back to ``last_seen_at`` here would let the
    panel print "verified" about a posting nobody has read since spring, which
    is I3's failure mode wearing a timestamp.
    """
    job = (await db_session.execute(select(Job).limit(1))).scalar_one()
    records = await _records_of(db_session, job)
    for record in records:
        record.last_verified_at = None
    await db_session.flush()

    body = (await seeded_client.get("/city/signals")).json()

    signal = next(s for s in body["signals"] if s["job_id"] == str(job.id))
    assert signal["last_verified_at"] is None
    assert signal["last_seen_at"] is not None


async def test_a_verified_source_record_reaches_the_signal(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    """And when the stronger check *has* run, the map says so.

    The column is on the source record rather than on the canonical job, so a
    role merged from three boards is as verified as its most recently verified
    record — ``max`` rather than "whichever row the query happened to return".
    """
    verified = datetime(2026, 8, 9, 9, 30, tzinfo=UTC)
    job = (await db_session.execute(select(Job).limit(1))).scalar_one()
    records = await _records_of(db_session, job)
    for record in records:
        record.last_verified_at = datetime(2026, 7, 1, tzinfo=UTC)
    # A *second* board describing the same role, verified more recently. Without
    # it every seeded job has exactly one record, `max` has nothing to choose
    # between, and this test passes just as happily against `min` — which is
    # how it was first written and how the vacuum was found.
    await _second_record(db_session, job, records[0], last_verified_at=verified)
    await db_session.flush()

    body = (await seeded_client.get("/city/signals")).json()

    signal = next(s for s in body["signals"] if s["job_id"] == str(job.id))
    assert datetime.fromisoformat(signal["last_verified_at"]) == verified


async def test_a_signal_carries_its_deadline_when_the_posting_named_one(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Gold is "exceptional match **or urgent deadline**" (§6), and the second
    half of that has never reached the map. It is one column on ``jobs``."""
    closes = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    job = (await db_session.execute(select(Job).limit(1))).scalar_one()
    job.application_deadline = closes
    await db_session.flush()

    body = (await seeded_client.get("/city/signals")).json()

    signal = next(s for s in body["signals"] if s["job_id"] == str(job.id))
    assert datetime.fromisoformat(signal["application_deadline"]) == closes


async def test_a_captured_role_reaches_the_map_saying_it_was_added_by_hand(
    seeded_client: AsyncClient, db_session: AsyncSession
) -> None:
    """M5's second acceptance criterion, the half that had never been walked.

    *"A pasted posting appears on the map with a capture badge."* Before this,
    the first half was true and the second could not be: ``/city/signals``
    carried no provenance at all, so a role somebody pasted in arrived at the
    renderer indistinguishable from one a poller found. The detail page had the
    badge; the map had no way to know.

    ``captured`` is **recorded fact and not a guess** — it is read off the
    source every confirmed capture is attributed to (``manual_capture``), the
    same join ``/jobs/{id}`` already uses for its own badge. ADR 0039 §5 draws
    the line this stays on: *whether* a posting came in by hand is written
    down, and *which website* it came from is not.

    The polled control matters as much as the captured case. A test that only
    asserts ``captured is True`` passes just as well against a field hard-wired
    to ``True``, which would put "added by hand" on all 32 roles in this corpus.
    """
    user = await _a_user(db_session)
    capture = await create_capture(
        db_session,
        user_id=user.id,
        raw_text="Staff Engineer, Platform\nPasted Co.\nNew York, NY\n",
        source_url=None,
    )
    captured_job = await confirm_capture(
        db_session,
        capture=capture,
        title="Staff Engineer, Platform",
        company_name="Pasted Co.",
        location_text="New York, NY",
        employment_type=EmploymentType.FULL_TIME,
        now=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
    )
    await db_session.flush()

    body = (await seeded_client.get("/city/signals")).json()
    by_id = {signal["job_id"]: signal for signal in body["signals"]}

    assert by_id[str(captured_job.id)]["captured"] is True

    polled = [
        signal
        for job_id, signal in by_id.items()
        if job_id != str(captured_job.id) and signal["captured"]
    ]
    assert not polled, (
        "roles nobody pasted came back marked as added by hand: "
        f"{[signal['title'] for signal in polled]}"
    )


# ---------------------------------------------------------------------------
# ADR 0041 (Q14): a role in another city is counted, never drawn.
# ---------------------------------------------------------------------------


async def _elsewhere_job_ids(session: AsyncSession) -> set[uuid.UUID]:
    """Alloy roles every one of whose locations is a named city: Denver,
    Vancouver, Washington. Asserted non-empty, or the tests below test nothing."""
    rows = (await session.execute(select(JobLocation.job_id, JobLocation.city))).all()
    by_job: dict[uuid.UUID, list[str | None]] = {}
    for job_id, city in rows:
        by_job.setdefault(job_id, []).append(city)
    elsewhere = {job_id for job_id, cities in by_job.items() if all(cities)}
    assert elsewhere, "the committed board has no role in another city"
    return elsewhere


async def test_a_role_in_another_city_is_counted_not_drawn(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Placement's third rule draws a non-remote role at its employer's confirmed
    office. With an office in Manhattan, Alloy's Denver roles would be drawn on a
    Manhattan building — Q14's 521, on screen. The city leaves them out and says
    how many it left out."""
    await _seed_alloy_board(db_session)
    alloy = (
        await db_session.execute(select(Company).where(Company.canonical_name == "Alloy"))
    ).scalar_one()
    await _confirm_office(db_session, alloy)
    elsewhere = await _elsewhere_job_ids(db_session)

    body = (await client.get("/city/signals")).json()

    shown = {uuid.UUID(signal["job_id"]) for signal in body["signals"]}
    assert not shown & elsewhere
    assert body["excluded_out_of_market"] == len(elsewhere)
    assert body["counts"]["building"] == 0, "a role elsewhere was drawn on the New York office"


async def test_the_city_stays_new_york_with_the_scope_off(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`MARKETS=all` turns the product's scope off, not the city's. The city is a
    model of New York; nothing else has a building in it."""
    monkeypatch.setenv("MARKETS", "all")
    get_settings.cache_clear()  # the app has already read them; see test_markets.py
    assert current_scope().everywhere, "the scope did not turn off; this would pass vacuously"
    await _seed_alloy_board(db_session)
    elsewhere = await _elsewhere_job_ids(db_session)

    body = (await client.get("/city/signals")).json()

    assert not {uuid.UUID(signal["job_id"]) for signal in body["signals"]} & elsewhere
    assert body["excluded_out_of_market"] == len(elsewhere)
