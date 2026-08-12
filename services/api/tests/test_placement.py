"""Where a role is drawn, and every reason it is drawn nowhere.

`city.md` §4.4 and §4.8. `office_loading.py` deferred this join to M4c on the
grounds that a renderer's data path built before the renderer comes out the
wrong shape; this is that join, and these are the rules it is not allowed to
break.

The pure half needs no database, which is the point of splitting it out: the
decision *"is this role on a building?"* is a function of two rows, and a
function of two rows should be testable without a container.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import (
    EmploymentType,
    JobStatus,
    LocationConfidence,
    RemotePolicy,
    ResolutionMethod,
)
from nightshift.db.models import Company, CompanyLocation, Job, JobLocation
from nightshift.domain.placement import (
    PlacementKind,
    primary_offices,
    resolve_placement,
)
from tests.conftest import requires_db


def _job(
    *,
    remote_policy: RemotePolicy = RemotePolicy.ON_SITE,
    locations: list[JobLocation] | None = None,
) -> Job:
    """A job detached from any session. Nothing here touches the database."""
    job = Job(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        title="Software Engineer",
        employment_type=EmploymentType.FULL_TIME,
        remote_policy=remote_policy,
        status=JobStatus.OPEN,
    )
    job.locations = locations if locations is not None else [_city_only()]
    return job


def _city_only(raw_text: str = "New York, NY") -> JobLocation:
    """What every posting in this corpus actually says (§4.1: 0 of 247)."""
    return JobLocation(
        raw_text=raw_text,
        city="New York",
        state="NY",
        country="USA",
        latitude=None,
        longitude=None,
        location_confidence=LocationConfidence.CITY_ONLY,
        resolution_method=ResolutionMethod.SOURCE_TEXT_PARSE,
        is_primary=True,
    )


def _stated_point(
    confidence: LocationConfidence = LocationConfidence.VERIFIED,
) -> JobLocation:
    """The case the corpus has none of: a posting that named its own address."""
    return JobLocation(
        raw_text="620 Eighth Avenue, New York, NY",
        city="New York",
        state="NY",
        country="USA",
        latitude=40.755913,
        longitude=-73.989658,
        location_confidence=confidence,
        resolution_method=ResolutionMethod.NYC_GEOSEARCH,
        is_primary=True,
    )


def _office(
    *,
    confidence: LocationConfidence = LocationConfidence.VERIFIED,
    latitude: float | None = 40.742054,
    longitude: float | None = -74.003748,
    building_id: str | None = "1012179",
    label: str = "New York HQ",
) -> CompanyLocation:
    return CompanyLocation(
        id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        label=label,
        street_address="620 Eighth Avenue",
        city="New York",
        state="NY",
        latitude=latitude,
        longitude=longitude,
        location_confidence=confidence,
        resolution_method=ResolutionMethod.NYC_GEOSEARCH,
        resolved_at=datetime(2026, 8, 11, tzinfo=UTC),
        is_primary=True,
        building_id=building_id,
    )


# ---------------------------------------------------------------------------
# I1, which is the whole reason this module has a test file of its own
# ---------------------------------------------------------------------------


def test_a_city_only_posting_with_no_office_is_unresolved() -> None:
    """The corpus's universal case, and it must never acquire a coordinate."""
    placement = resolve_placement(_job(), office=None)

    assert placement.kind is PlacementKind.UNRESOLVED
    assert placement.latitude is None
    assert placement.longitude is None
    assert placement.building_id is None
    assert placement.location_confidence is LocationConfidence.CITY_ONLY


def test_no_office_can_be_invented_from_a_city_name() -> None:
    """An office row that never resolved places nothing.

    The failure this guards is the tempting one: a company row exists, so the
    renderer wants *something* to draw, and a centroid is right there.
    """
    unresolved_office = _office(
        confidence=LocationConfidence.CITY_ONLY,
        latitude=None,
        longitude=None,
        building_id=None,
    )

    placement = resolve_placement(_job(), office=unresolved_office)

    assert placement.kind is PlacementKind.UNRESOLVED
    assert placement.latitude is None


def test_an_approximate_office_is_an_area_and_never_a_building() -> None:
    """§6: approximate is a translucent radius — an area, never a point."""
    placement = resolve_placement(
        _job(), office=_office(confidence=LocationConfidence.APPROXIMATE, building_id=None)
    )

    assert placement.kind is PlacementKind.AREA
    assert placement.latitude is not None
    assert placement.building_id is None


def test_an_approximate_office_that_somehow_has_a_bin_is_still_an_area() -> None:
    """A BIN is not a promotion. Only `verified` earns a building."""
    placement = resolve_placement(
        _job(), office=_office(confidence=LocationConfidence.APPROXIMATE, building_id="1012179")
    )

    assert placement.kind is PlacementKind.AREA
    assert placement.building_id is None


def test_a_fully_remote_role_is_not_placed_at_its_employers_office() -> None:
    """A remote role is not in the building, and drawing it there says it is.

    This is the one rule here that is a product judgement rather than a
    restatement of I1: the office is a real verified fact, and attaching a
    remote role to it would be a true coordinate under a false sentence.
    """
    placement = resolve_placement(_job(remote_policy=RemotePolicy.REMOTE), office=_office())

    assert placement.kind is PlacementKind.UNRESOLVED
    assert placement.latitude is None


def test_a_hybrid_role_is_placed_because_hybrid_means_partly_there() -> None:
    placement = resolve_placement(_job(remote_policy=RemotePolicy.HYBRID), office=_office())

    assert placement.kind is PlacementKind.BUILDING


# ---------------------------------------------------------------------------
# Inheritance, and saying so
# ---------------------------------------------------------------------------


def test_a_verified_office_puts_the_role_on_a_building_and_names_the_office() -> None:
    placement = resolve_placement(_job(), office=_office())

    assert placement.kind is PlacementKind.BUILDING
    assert placement.latitude == pytest.approx(40.742054)
    assert placement.longitude == pytest.approx(-74.003748)
    assert placement.building_id == "1012179"
    assert placement.resolution_method is ResolutionMethod.COMPANY_OFFICE
    assert placement.office_label == "New York HQ"
    assert placement.office_address == "620 Eighth Avenue, New York, NY"


def test_an_inherited_placement_says_it_is_inherited() -> None:
    """§4.4: never silently.

    `location_confidence` describes the *coordinate*, which really is verified.
    It does not describe the claim that this role sits at it, and `inherited`
    plus `stated` are what stop a reader collapsing the two.
    """
    placement = resolve_placement(_job(), office=_office())

    assert placement.inherited is True
    assert placement.stated == "New York, NY"
    assert placement.location_confidence is LocationConfidence.VERIFIED


def test_a_posting_that_stated_its_own_address_does_not_inherit() -> None:
    """The stronger claim wins, and it is reported as the stronger claim."""
    job = _job(locations=[_stated_point()])

    placement = resolve_placement(job, office=_office())

    assert placement.kind is PlacementKind.BUILDING
    assert placement.inherited is False
    assert placement.resolution_method is ResolutionMethod.NYC_GEOSEARCH
    assert placement.office_label is None
    assert placement.latitude == pytest.approx(40.755913)


def test_a_stated_approximate_point_beats_a_verified_office_and_stays_an_area() -> None:
    """What the posting said is what the posting said.

    Preferring the office here would upgrade a posting's own approximate claim
    into a building by way of a different row — which is exactly the silent
    promotion §4.4 refuses.
    """
    job = _job(locations=[_stated_point(LocationConfidence.APPROXIMATE)])

    placement = resolve_placement(job, office=_office())

    assert placement.kind is PlacementKind.AREA
    assert placement.inherited is False


def test_a_posting_with_no_location_rows_at_all_is_unresolved() -> None:
    job = _job(locations=[])

    placement = resolve_placement(job, office=None)

    assert placement.kind is PlacementKind.UNRESOLVED
    assert placement.location_confidence is LocationConfidence.UNKNOWN
    assert placement.stated is None


def test_the_primary_location_is_the_one_that_speaks_for_a_multi_location_posting() -> None:
    """A2: a posting can name several places. The map draws one of them."""
    secondary = _city_only("Austin, TX")
    secondary.is_primary = False
    primary = _stated_point()
    job = _job(locations=[secondary, primary])

    placement = resolve_placement(job, office=None)

    assert placement.latitude == pytest.approx(40.755913)
    assert placement.stated == "620 Eighth Avenue, New York, NY"


def test_resolving_never_mutates_the_rows_it_read() -> None:
    """The join is a read. `job_locations` still holds what the posting said.

    `office_loading.py` refused to materialise this inheritance precisely so a
    corrected office cannot leave a stale coordinate behind. That only holds if
    nothing downstream writes it back.
    """
    job = _job()
    row = job.locations[0]

    resolve_placement(job, office=_office())

    assert row.latitude is None
    assert row.location_confidence is LocationConfidence.CITY_ONLY
    assert row.resolution_method is ResolutionMethod.SOURCE_TEXT_PARSE


# ---------------------------------------------------------------------------
# The join itself, which does need a database
# ---------------------------------------------------------------------------


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_primary_offices_returns_only_confirmed_primaries(
    db_session: AsyncSession,
) -> None:
    with_office = Company(canonical_name="Datadog", normalized_name=f"datadog-{uuid.uuid4()}")
    without = Company(canonical_name="Ramp", normalized_name=f"ramp-{uuid.uuid4()}")
    db_session.add_all([with_office, without])
    await db_session.flush()

    primary = CompanyLocation(
        company_id=with_office.id,
        label="New York HQ",
        street_address="620 Eighth Avenue",
        city="New York",
        state="NY",
        latitude=40.755913,
        longitude=-73.989658,
        location_confidence=LocationConfidence.VERIFIED,
        resolution_method=ResolutionMethod.NYC_GEOSEARCH,
        resolved_at=datetime.now(UTC),
        is_primary=True,
        building_id="1087186",
        confirmed_at=datetime.now(UTC),
        confirmed_by="Tahmudun",
    )
    secondary = CompanyLocation(
        company_id=with_office.id,
        label="Brooklyn",
        street_address="1 Main Street",
        city="Brooklyn",
        state="NY",
        latitude=40.703,
        longitude=-73.99,
        location_confidence=LocationConfidence.VERIFIED,
        resolution_method=ResolutionMethod.NYC_GEOSEARCH,
        resolved_at=datetime.now(UTC),
        is_primary=False,
        confirmed_at=datetime.now(UTC),
        confirmed_by="Tahmudun",
    )
    db_session.add_all([primary, secondary])
    await db_session.flush()

    offices = await primary_offices(db_session, [with_office.id, without.id])

    assert set(offices) == {with_office.id}
    assert offices[with_office.id].label == "New York HQ"


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_primary_offices_asked_for_nothing_queries_nothing(
    db_session: AsyncSession,
) -> None:
    """A map with no jobs on it must not turn into a `WHERE id IN ()`."""
    assert await primary_offices(db_session, []) == {}
