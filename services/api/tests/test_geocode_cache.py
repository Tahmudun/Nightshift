"""The cache, and the outage it must not keep.

`city.md` §4.3. Most of these are ordinary cache tests. The one that matters is
`test_an_outage_is_not_cached`, which is invariant I3 wearing different clothes:
a provider being unreachable says nothing about where an office is, and storing
it would turn one bad afternoon into a permanent refusal to place a building
that was always placeable.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import LocationConfidence, ResolutionMethod
from nightshift.db.models import GeocodeCache
from nightshift.domain.geocode_cache import CachingGeocoder, normalize_query
from nightshift.domain.geocoding import (
    OUTSIDE_COVERAGE,
    PROVIDER_UNAVAILABLE,
    GeocodeOutcome,
    Resolved,
    Unresolved,
)
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

ADDRESS = "620 Eighth Avenue, New York, NY"


class _Counting:
    """A rung that reports how many times it was actually reached."""

    def __init__(self, outcome: GeocodeOutcome) -> None:
        self._outcome = outcome
        self.calls = 0

    @property
    def method(self) -> ResolutionMethod:
        return ResolutionMethod.NYC_GEOSEARCH

    async def geocode(self, address: str) -> GeocodeOutcome:
        self.calls += 1
        return self._outcome


def _hit() -> Resolved:
    return Resolved(
        40.755913,
        -73.989658,
        LocationConfidence.VERIFIED,
        ResolutionMethod.NYC_GEOSEARCH,
        "620 EIGHTH AVENUE, New York, NY, USA",
        building_id="1087186",
    )


async def _rows(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(GeocodeCache))).scalar_one())


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------


async def test_the_key_folds_case_and_whitespace_only() -> None:
    assert normalize_query("  620 Eighth   Avenue,  New York, NY ") == normalize_query(
        "620 eighth avenue, new york, ny"
    )


async def test_the_key_does_not_fold_street_abbreviations() -> None:
    """Deliberate. "620 8th Ave" and "620 Eighth Avenue" are the same building
    and this costs one extra request to learn that. A normaliser aggressive
    enough to fold them would also fold things that are not the same, and the
    cost of *that* is a wrong building rather than a wasted request."""
    assert normalize_query("620 8th Ave") != normalize_query("620 Eighth Avenue")


# --------------------------------------------------------------------------
# Hits and misses
# --------------------------------------------------------------------------


async def test_a_resolved_address_is_asked_once(db_session: AsyncSession) -> None:
    rung = _Counting(_hit())
    cache = CachingGeocoder(rung, db_session)

    first = await cache.geocode(ADDRESS)
    second = await cache.geocode(ADDRESS)

    assert rung.calls == 1
    assert isinstance(first, Resolved) and isinstance(second, Resolved)
    assert second.building_id == "1087186"
    assert second.latitude == pytest.approx(40.755913)


async def test_the_second_ask_survives_a_differently_spaced_query(
    db_session: AsyncSession,
) -> None:
    rung = _Counting(_hit())
    cache = CachingGeocoder(rung, db_session)

    await cache.geocode(ADDRESS)
    await cache.geocode("  620 Eighth   Avenue,  New York, NY  ")

    assert rung.calls == 1


async def test_a_miss_is_cached_too(db_session: AsyncSession) -> None:
    """ "We asked and NYC has no such address" is a durable answer. Re-asking it
    every poll spends a request to learn nothing."""
    rung = _Counting(Unresolved(OUTSIDE_COVERAGE, LocationConfidence.CITY_ONLY))
    cache = CachingGeocoder(rung, db_session)

    await cache.geocode(ADDRESS)
    second = await cache.geocode(ADDRESS)

    assert rung.calls == 1
    assert isinstance(second, Unresolved)
    assert second.refusal == OUTSIDE_COVERAGE
    assert second.confidence is LocationConfidence.CITY_ONLY


async def test_an_outage_is_not_cached(db_session: AsyncSession) -> None:
    """The load-bearing test, and I3 one subsystem over.

    A provider being unreachable is not an answer about the address. Caching it
    would make one bad afternoon into a permanent refusal to place a building
    that was always placeable — the geocoding form of closing a listing because
    a source timed out.
    """
    rung = _Counting(Unresolved(PROVIDER_UNAVAILABLE, LocationConfidence.CITY_ONLY))
    cache = CachingGeocoder(rung, db_session)

    await cache.geocode(ADDRESS)
    await cache.geocode(ADDRESS)

    assert rung.calls == 2, "an outage was cached and the address is now permanently unplaceable"
    assert await _rows(db_session) == 0


async def test_an_outage_then_a_success_resolves(db_session: AsyncSession) -> None:
    """The point of not caching it: the next attempt has to be able to succeed."""
    rung = _Counting(Unresolved(PROVIDER_UNAVAILABLE, LocationConfidence.CITY_ONLY))
    cache = CachingGeocoder(rung, db_session)
    assert isinstance(await cache.geocode(ADDRESS), Unresolved)

    recovered = CachingGeocoder(_Counting(_hit()), db_session)
    assert isinstance(await recovered.geocode(ADDRESS), Resolved)


async def test_two_rungs_cache_the_same_string_separately(db_session: AsyncSession) -> None:
    """The same address asked of GeoSearch and of Nominatim is two different
    answers, and a key without the method would let the first shadow the second."""

    class _Nominatim(_Counting):
        @property
        def method(self) -> ResolutionMethod:
            return ResolutionMethod.NOMINATIM

    await CachingGeocoder(_Counting(_hit()), db_session).geocode(ADDRESS)
    nominatim = _Nominatim(
        Resolved(
            40.75,
            -73.99,
            LocationConfidence.APPROXIMATE,
            ResolutionMethod.NOMINATIM,
            "somewhere",
        )
    )
    await CachingGeocoder(nominatim, db_session).geocode(ADDRESS)

    assert nominatim.calls == 1
    assert await _rows(db_session) == 2


# --------------------------------------------------------------------------
# The database refuses what this layer decides
# --------------------------------------------------------------------------


async def test_the_database_refuses_a_cached_outage(db_session: AsyncSession) -> None:
    """`CachingGeocoder` is where the decision is made. This is where it cannot
    be got around by a writer that never read the docstring."""
    db_session.add(
        GeocodeCache(
            query=ADDRESS,
            normalized_query=normalize_query(ADDRESS),
            resolution_method=ResolutionMethod.NYC_GEOSEARCH,
            refusal="provider_unavailable",
            location_confidence=LocationConfidence.CITY_ONLY,
            resolved_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError, match="an_outage_is_never_cached"):
        await db_session.flush()


async def test_a_row_cannot_be_both_a_hit_and_a_miss(db_session: AsyncSession) -> None:
    db_session.add(
        GeocodeCache(
            query=ADDRESS,
            normalized_query=normalize_query(ADDRESS),
            resolution_method=ResolutionMethod.NYC_GEOSEARCH,
            latitude=40.75,
            longitude=-73.99,
            location_confidence=LocationConfidence.VERIFIED,
            refusal="outside_coverage",
            resolved_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError, match="a_row_is_a_hit_or_a_miss"):
        await db_session.flush()


async def test_a_row_cannot_be_neither(db_session: AsyncSession) -> None:
    db_session.add(
        GeocodeCache(
            query=ADDRESS,
            normalized_query=normalize_query(ADDRESS),
            resolution_method=ResolutionMethod.NYC_GEOSEARCH,
            resolved_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError, match="a_row_is_a_hit_or_a_miss"):
        await db_session.flush()
