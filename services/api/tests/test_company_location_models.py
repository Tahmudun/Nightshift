"""I1 at the database, on the one table that can put a beacon on a building.

`city.md` §4.6. `job_locations` has carried these constraints since ADR 0002 and
has never been able to trip them, because no coordinate has ever been written to
this database. `company_locations` is the table that changes that: M4a Task 1
measured that no ATS posting names a street, so an office address a human
confirmed is the only input in the entire product that can honestly reach
`verified`.

So these tests attack the database directly rather than the code above it. A
constraint that only the ORM respects is a constraint one raw INSERT gets past,
and the whole reason I1 lives in DDL is that it has to hold against writers
nobody has written yet.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import LocationConfidence, ResolutionMethod
from nightshift.db.models import Company, CompanyLocation
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


async def _company(session: AsyncSession, name: str = "Datadog") -> Company:
    company = Company(canonical_name=name, normalized_name=name.lower())
    session.add(company)
    await session.flush()
    return company


def _office(company: Company, **overrides: object) -> CompanyLocation:
    """A well-formed confirmed office. Each test breaks exactly one thing."""
    fields: dict[str, object] = {
        "company_id": company.id,
        "label": "New York HQ",
        "street_address": "620 Eighth Avenue",
        "city": "New York",
        "state": "NY",
        "postal_code": "10018",
        "country": "USA",
        "latitude": 40.756,
        "longitude": -73.990,
        "location_confidence": LocationConfidence.VERIFIED,
        "resolution_method": ResolutionMethod.NYC_GEOSEARCH,
        "resolved_at": datetime.now(UTC),
        "is_primary": True,
        "confirmed_by": "data/company-locations.yaml",
        "confirmed_at": datetime.now(UTC),
    }
    fields.update(overrides)
    return CompanyLocation(**fields)


async def test_a_well_formed_confirmed_office_is_accepted(db_session: AsyncSession) -> None:
    """The control. Without it every test below could pass for the wrong reason."""
    company = await _company(db_session)
    db_session.add(_office(company))
    await db_session.flush()


async def test_a_city_only_row_cannot_carry_coordinates(db_session: AsyncSession) -> None:
    """The core of I1. `city_only` means "we know the city and nothing finer";
    a point attached to it is a precision claim nobody earned."""
    company = await _company(db_session)
    db_session.add(
        _office(
            company,
            location_confidence=LocationConfidence.CITY_ONLY,
            street_address=None,
        )
    )
    with pytest.raises(IntegrityError, match="confidence_matches_coordinates"):
        await db_session.flush()


async def test_a_verified_row_cannot_omit_coordinates(db_session: AsyncSession) -> None:
    company = await _company(db_session)
    db_session.add(_office(company, latitude=None, longitude=None))
    with pytest.raises(IntegrityError, match="confidence_matches_coordinates"):
        await db_session.flush()


async def test_verified_requires_a_street_address(db_session: AsyncSession) -> None:
    """The constraint this table adds beyond `job_locations`.

    `verified` is what puts a beacon on one specific building, and §4.1 measured
    that a city name can never earn it. Without this, an office geocoded from
    "New York, NY" stores as `verified` and the renderer places it on whichever
    building the city centroid landed in — I1's exact failure, through the one
    door `confidence_matches_coordinates` leaves open, since that check only
    asks whether coordinates are *present*.
    """
    company = await _company(db_session)
    db_session.add(_office(company, street_address=None))
    with pytest.raises(IntegrityError, match="verified_requires_a_street_address"):
        await db_session.flush()


async def test_approximate_without_a_street_is_still_allowed(db_session: AsyncSession) -> None:
    """The constraint above must not overreach. `approximate` is the honest
    answer for a neighbourhood centroid, which has coordinates and no street,
    and rung 3 of §4.3's ladder produces exactly that."""
    company = await _company(db_session)
    db_session.add(
        _office(
            company,
            street_address=None,
            location_confidence=LocationConfidence.APPROXIMATE,
            resolution_method=ResolutionMethod.NEIGHBORHOOD_CENTROID,
        )
    )
    await db_session.flush()


async def test_coordinates_travel_together(db_session: AsyncSession) -> None:
    company = await _company(db_session)
    db_session.add(_office(company, longitude=None))
    with pytest.raises(IntegrityError, match="coordinates_are_paired"):
        await db_session.flush()


async def test_a_company_cannot_have_two_primary_offices(db_session: AsyncSession) -> None:
    """A company's building has to be one building. A second primary would make
    the renderer choose arbitrarily, and arbitrary is how a beacon ends up
    somewhere nobody claimed it was."""
    company = await _company(db_session)
    db_session.add(_office(company))
    await db_session.flush()
    db_session.add(_office(company, label="Second HQ"))
    with pytest.raises(IntegrityError, match="uq_company_locations_one_primary"):
        await db_session.flush()


async def test_a_company_may_have_many_non_primary_offices(db_session: AsyncSession) -> None:
    company = await _company(db_session)
    db_session.add(_office(company))
    db_session.add(_office(company, label="Brooklyn", is_primary=False))
    db_session.add(_office(company, label="Queens", is_primary=False))
    await db_session.flush()


async def test_an_office_cannot_exist_without_saying_who_confirmed_it(
    db_session: AsyncSession,
) -> None:
    """The column that makes "a lit building is a verified fact" structural.

    Attacked as raw SQL rather than through the ORM: the point of NOT NULL here
    is that it holds against a writer that does not know the rule, and the ORM
    is a writer that does.
    """
    company = await _company(db_session)
    with pytest.raises(IntegrityError, match="confirmed_by"):
        await db_session.execute(
            text(
                "INSERT INTO company_locations "
                "(company_id, label, location_confidence, resolution_method, confirmed_at) "
                "VALUES (:cid, 'New York HQ', 'city_only', 'manual', now())"
            ),
            {"cid": company.id},
        )


async def test_the_check_constraints_hold_against_raw_sql(db_session: AsyncSession) -> None:
    """The ORM is not the enforcement. This is the same `verified`-without-a-street
    row as above, inserted by something that never loaded a model class."""
    company = await _company(db_session)
    with pytest.raises(IntegrityError, match="verified_requires_a_street_address"):
        await db_session.execute(
            text(
                "INSERT INTO company_locations "
                "(company_id, label, latitude, longitude, location_confidence, "
                " resolution_method, confirmed_by, confirmed_at) "
                "VALUES (:cid, 'New York HQ', 40.756, -73.990, 'verified', "
                "        'nyc_geosearch', 'a raw insert', now())"
            ),
            {"cid": company.id},
        )


async def test_company_office_is_a_usable_resolution_method(db_session: AsyncSession) -> None:
    """The enum value migration 0020 added. A job inheriting its employer's
    office is the only way a beacon reaches a building on this corpus, so the
    value existing in PostgreSQL — not only in Python — is load-bearing."""
    company = await _company(db_session)
    db_session.add(
        _office(
            company,
            street_address=None,
            location_confidence=LocationConfidence.APPROXIMATE,
            resolution_method=ResolutionMethod.COMPANY_OFFICE,
        )
    )
    await db_session.flush()
