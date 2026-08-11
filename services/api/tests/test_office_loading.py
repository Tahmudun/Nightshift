"""Worksheet to building, and every way a row stops short of one.

`city.md` §4.4. The loader's job is not to place as many buildings as possible —
it is to place exactly the ones somebody vouched for and the ladder could
resolve to a street, and to report the rest in enough detail that the coverage
page can be honest about them.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import LocationConfidence, ResolutionMethod
from nightshift.db.models import Company, CompanyLocation, JobLocation
from nightshift.domain.company_locations import read_worksheet
from nightshift.domain.geocoding import (
    OUTSIDE_COVERAGE,
    GeocodeOutcome,
    Resolved,
    Unresolved,
)
from nightshift.domain.office_loading import load_offices
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

_WORKSHEET = """
confirmed_by: Tahmudun
offices:
  - company: Datadog
    label: New York HQ
    street_address: 620 Eighth Avenue
    city: New York
    state: NY
    is_primary: true
    confirmed_on: 2026-08-11
"""


class _Rung:
    def __init__(self, outcome: GeocodeOutcome) -> None:
        self._outcome = outcome

    @property
    def method(self) -> ResolutionMethod:
        return ResolutionMethod.NYC_GEOSEARCH

    async def geocode(self, address: str) -> GeocodeOutcome:
        return self._outcome


def _verified() -> Resolved:
    return Resolved(
        40.755913,
        -73.989658,
        LocationConfidence.VERIFIED,
        ResolutionMethod.NYC_GEOSEARCH,
        "620 EIGHTH AVENUE, New York, NY, USA",
        building_id="1087186",
    )


async def _datadog(session: AsyncSession) -> Company:
    company = Company(canonical_name="Datadog", normalized_name="datadog")
    session.add(company)
    await session.flush()
    return company


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


async def test_a_confirmed_address_becomes_a_building(db_session: AsyncSession) -> None:
    await _datadog(db_session)
    report = await load_offices(db_session, read_worksheet(_WORKSHEET), (_Rung(_verified()),))

    assert report.placed == ["Datadog"]
    office = (await db_session.execute(select(CompanyLocation))).scalar_one()
    assert office.location_confidence is LocationConfidence.VERIFIED
    assert office.building_id == "1087186"
    assert office.confirmed_by == "Tahmudun"
    assert office.is_primary


async def test_confirmed_at_is_the_date_the_human_wrote_not_now(
    db_session: AsyncSession,
) -> None:
    """`now()` would claim somebody checked this address at the moment the
    loader happened to run, which is a statement about a person they did not
    make. The date in the worksheet is the one they did."""
    await _datadog(db_session)
    await load_offices(db_session, read_worksheet(_WORKSHEET), (_Rung(_verified()),))

    office = (await db_session.execute(select(CompanyLocation))).scalar_one()
    assert office.confirmed_at.date().isoformat() == "2026-08-11"


async def test_running_it_twice_updates_rather_than_duplicates(
    db_session: AsyncSession,
) -> None:
    """The worksheet is edited and reloaded. A loader that appended would hit
    `uq_company_locations_one_primary` on the second run, which is a confusing
    way to learn that a file is meant to be idempotent."""
    await _datadog(db_session)
    ladder = (_Rung(_verified()),)
    await load_offices(db_session, read_worksheet(_WORKSHEET), ladder)
    await load_offices(db_session, read_worksheet(_WORKSHEET), ladder)

    offices = (await db_session.execute(select(CompanyLocation))).scalars().all()
    assert len(offices) == 1


# --------------------------------------------------------------------------
# Everything that stops short of a building
# --------------------------------------------------------------------------


async def test_an_unresolvable_address_places_nothing_and_says_so(
    db_session: AsyncSession,
) -> None:
    await _datadog(db_session)
    report = await load_offices(
        db_session,
        read_worksheet(_WORKSHEET),
        (_Rung(Unresolved(OUTSIDE_COVERAGE, LocationConfidence.CITY_ONLY)),),
    )

    assert report.placed == []
    assert report.unresolved == [("Datadog", "outside_coverage")]
    assert (await db_session.execute(select(CompanyLocation))).scalars().all() == []


async def test_a_lower_rung_answer_is_not_a_building(db_session: AsyncSession) -> None:
    """The sharp one.

    An `approximate` point is a real coordinate and an honest confidence — a
    neighbourhood centroid is exactly that. It is still not a *building*, and
    this table's entire purpose is buildings. Storing it would put a company on
    a specific roof the geocoder never claimed it was on.
    """
    await _datadog(db_session)
    approximate = Resolved(
        40.75,
        -73.99,
        LocationConfidence.APPROXIMATE,
        ResolutionMethod.NEIGHBORHOOD_CENTROID,
        "Midtown West",
    )
    report = await load_offices(db_session, read_worksheet(_WORKSHEET), (_Rung(approximate),))

    assert report.placed == []
    assert "only reached" in report.unresolved[0][1]
    assert (await db_session.execute(select(CompanyLocation))).scalars().all() == []


async def test_an_unknown_company_is_reported_not_created(db_session: AsyncSession) -> None:
    """`get_or_create_company` exists and is deliberately not used. Ingestion
    creates a company because a posting proves one exists; an address in a
    worksheet proves nothing, and a typo would otherwise mint an employer with
    no jobs, no board, and a building on the map."""
    report = await load_offices(db_session, read_worksheet(_WORKSHEET), (_Rung(_verified()),))

    assert report.placed == []
    assert report.unknown_company == ["Datadog"]
    assert (await db_session.execute(select(Company))).scalars().all() == []


async def test_blank_entries_are_carried_into_the_report(db_session: AsyncSession) -> None:
    """One number has to cover the whole file, or the coverage page reports on
    a subset and calls it the total."""
    report = await load_offices(
        db_session,
        read_worksheet(
            """
            confirmed_by: Tahmudun
            offices:
              - company: Datadog
                label: New York HQ
                street_address:
            """
        ),
        (_Rung(_verified()),),
    )
    assert report.blank == ["Datadog"]
    assert report.considered == 1


async def test_the_committed_worksheet_places_nothing_yet(db_session: AsyncSession) -> None:
    """The file ships blank. This is the number the coverage page will show
    until somebody fills it in, and it should be reachable without a network."""
    from pathlib import Path

    path = Path(__file__).parent.parent.parent.parent / "data" / "company-locations.yaml"
    report = await load_offices(db_session, read_worksheet(path.read_text()), (_Rung(_verified()),))

    assert report.placed == []
    assert report.considered == 9
    assert len(report.blank) == 9


# --------------------------------------------------------------------------
# What the loader must not touch
# --------------------------------------------------------------------------


async def test_the_loader_never_writes_a_job_location(db_session: AsyncSession) -> None:
    """A job inheriting its employer's office is derived, not stored.

    Materialising it would leave stale rows behind every office correction, and
    it would overwrite the only record of what the *posting* said — replacing a
    `source_text_parse` row with coordinates the posting never contained. §4.4
    makes the inheritance a read-time join and M4c builds it.
    """
    await _datadog(db_session)
    before = len((await db_session.execute(select(JobLocation))).scalars().all())

    await load_offices(db_session, read_worksheet(_WORKSHEET), (_Rung(_verified()),))

    after = len((await db_session.execute(select(JobLocation))).scalars().all())
    assert after == before
