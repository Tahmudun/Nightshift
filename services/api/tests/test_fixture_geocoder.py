"""The rung that puts a role on a real building with no network.

`domain/geocoding.py`'s `Geocoder` docstring has promised since M4a that
"`make demo` wires a fixture-backed implementation through the same interface,
not around it". Until now nothing did, and the consequence was visible rather
than theoretical: `make offices` cached its answers in `geocode_cache`, that
table lives in Postgres, `make reset-db` dropped it, and the next `make seed`
produced a city where **31 of 31 roles were `unresolved`** and every beacon
floated in the sky with nothing beneath it. The renderer was correct. The
offices were gone, and there was no offline way to get them back.

So this file guards the two properties that failure needed:

1. A confirmed address resolves to its building **without a network call**, and
   to the same building the live service named.
2. A confirmed address with no recording is loud rather than silent. It is
   reported as *we could not look*, never as *no building is there* — the same
   distinction I3 draws for a source outage, one subsystem over.
"""

from __future__ import annotations

import json

import pytest

from nightshift.adapters.geosearch import parse_search_response
from nightshift.cli import OFFICE_GEOCODE_FIXTURE, FixtureNycGeoSearchGeocoder
from nightshift.db.base import LocationConfidence, ResolutionMethod
from nightshift.domain.company_locations import DEFAULT_WORKSHEET_PATH, read_worksheet
from nightshift.domain.geocoding import (
    PROVIDER_UNAVAILABLE,
    Geocoder,
    Resolved,
    Unresolved,
)

#: The two offices the seeded corpus actually has roles at, and the BINs NYC
#: GeoSearch returned for them — recorded live on 2026-08-17 by `make offices`
#: and again on 2026-08-19 by `scripts/record_office_geocodes.py`, the same
#: both times. Hard-coded rather than read from the fixture, because a test
#: that derived its expectation from the file under test would pass against a
#: fixture somebody had edited by hand.
SEEDED_OFFICES = {
    "620 8th Avenue, New York, NY, 10018": "1087186",
    "28 West 23rd Street, New York, NY, 10010": "1080672",
}


def test_the_fixture_rung_satisfies_the_geocoder_protocol() -> None:
    """Behind the real interface, per I7 — not beside it."""
    assert isinstance(FixtureNycGeoSearchGeocoder(), Geocoder)
    assert FixtureNycGeoSearchGeocoder().method is ResolutionMethod.NYC_GEOSEARCH


@pytest.mark.parametrize(("query", "building_id"), sorted(SEEDED_OFFICES.items()))
@pytest.mark.asyncio
async def test_a_confirmed_address_resolves_to_its_building(query: str, building_id: str) -> None:
    outcome = await FixtureNycGeoSearchGeocoder().geocode(query)

    assert isinstance(outcome, Resolved), outcome
    assert outcome.building_id == building_id
    assert outcome.confidence is LocationConfidence.VERIFIED
    assert outcome.method is ResolutionMethod.NYC_GEOSEARCH


@pytest.mark.asyncio
async def test_every_confirmed_address_in_the_worksheet_has_a_recording() -> None:
    """The guard for the way this breaks next.

    Somebody fills in a ninth address, `make seed` cannot geocode it, and that
    company's roles quietly go back to floating — with nothing red anywhere.
    The worksheet is the input and the fixture set is the answer key; this
    asserts they cover the same addresses.
    """
    reading = read_worksheet(DEFAULT_WORKSHEET_PATH.read_text())
    assert reading.entries, "the worksheet has no confirmed addresses at all"

    rung = FixtureNycGeoSearchGeocoder()
    missing = []
    for entry in reading.entries:
        outcome = await rung.geocode(entry.geocoder_query)
        if isinstance(outcome, Unresolved) and outcome.refusal == PROVIDER_UNAVAILABLE:
            missing.append(f"{entry.company}: {entry.geocoder_query}")

    assert not missing, (
        "no recorded geocode for:\n  "
        + "\n  ".join(missing)
        + "\n\nRun `python scripts/record_office_geocodes.py` with network access."
    )


@pytest.mark.asyncio
async def test_an_unrecorded_address_says_it_could_not_look() -> None:
    """Never "no building found" — that is a claim about New York we cannot make.

    `CachingGeocoder` refuses to write `PROVIDER_UNAVAILABLE` to
    `geocode_cache` for exactly this reason, so getting the refusal right is
    also what stops an offline run from poisoning the cache with a permanent
    wrong answer for an address that is perfectly real.
    """
    outcome = await FixtureNycGeoSearchGeocoder().geocode("1 Nowhere Plaza, New York, NY")

    assert isinstance(outcome, Unresolved)
    assert outcome.refusal == PROVIDER_UNAVAILABLE
    assert outcome.confidence is LocationConfidence.CITY_ONLY


@pytest.mark.asyncio
async def test_the_recording_is_replayed_through_the_production_parser() -> None:
    """Only the bytes' origin differs, which is what makes the fixture honest.

    Asserted by parsing the same recorded payload with the real function and
    demanding the rung agree with it in every field. A rung that had its own
    idea of what a response means would be a mock of the geocoder rather than
    a recording of the provider.
    """
    recordings = json.loads(OFFICE_GEOCODE_FIXTURE.read_text())
    query = "620 8th Avenue, New York, NY, 10018"

    direct = parse_search_response(recordings[query])
    replayed = await FixtureNycGeoSearchGeocoder().geocode(query)

    assert replayed == direct
