"""Rung 1, against the two responses that were actually recorded from NYC.

`city.md` §4.3.1. The important test in this file is not that a real address
resolves — it is that the response for `"New York, NY"` does not, even though
the provider returns it at `confidence=1, match_type=exact` and the correct
answer for a real address comes back at `0.8, fallback`.

That inversion is why nothing here reads `confidence`. Every acceptance rule is
a fact about what the response *is*: did the provider parse a house number, does
the feature carry that house number, is the building real. A rule built on how
sure Pelias feels would rank a hospital above the right address.
"""

from __future__ import annotations

import pytest

from nightshift.adapters.geosearch import parse_search_response
from nightshift.db.base import LocationConfidence, ResolutionMethod
from nightshift.domain.geocoding import Resolved, Unresolved
from tests.conftest import load_json_fixture


@pytest.fixture(scope="session")
def street_response() -> dict:
    return load_json_fixture("geosearch", "street_address_search.json")


@pytest.fixture(scope="session")
def city_response() -> dict:
    return load_json_fixture("geosearch", "bare_city_name_search.json")


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_a_real_address_resolves_to_a_verified_point(street_response: dict) -> None:
    outcome = parse_search_response(street_response)

    assert isinstance(outcome, Resolved)
    assert outcome.confidence is LocationConfidence.VERIFIED
    assert outcome.method is ResolutionMethod.NYC_GEOSEARCH
    assert outcome.latitude == pytest.approx(40.755913)
    assert outcome.longitude == pytest.approx(-73.989658)


def test_the_building_id_comes_back_with_the_point(street_response: dict) -> None:
    """A4 assumed this join would be computed in PostGIS from the point. It
    arrives in the geocode response, so a confirmed address yields the building
    rather than somewhere near one — and a key beats a geometric guess in the
    case that matters, a tower whose footprint abuts three others."""
    outcome = parse_search_response(street_response)
    assert isinstance(outcome, Resolved)
    assert outcome.building_id == "1087186"


def test_the_matched_text_is_kept_so_a_placement_can_be_argued_with(
    street_response: dict,
) -> None:
    """ "You asked for X and it matched Y" is a different conversation from
    "the map is wrong"."""
    outcome = parse_search_response(street_response)
    assert isinstance(outcome, Resolved)
    assert outcome.matched_text == "620 EIGHTH AVENUE, New York, NY, USA"


def test_the_first_of_three_borough_matches_wins(street_response: dict) -> None:
    """620 Eighth Avenue exists in Manhattan and Brooklyn, and both score 0.8.
    The response is ordered and the caller supplied the locality parts that
    disambiguate — `OfficeEntry.geocoder_query` appends city, state and postal
    code for exactly this reason."""
    outcome = parse_search_response(street_response)
    assert isinstance(outcome, Resolved)
    assert outcome.latitude == pytest.approx(40.755913), "took the Brooklyn match"


# --------------------------------------------------------------------------
# The response this whole design exists to refuse
# --------------------------------------------------------------------------


def test_a_bare_city_name_resolves_to_nothing(city_response: dict) -> None:
    """The load-bearing test.

    This recorded response contains NEW YORK HOSPITAL at First Avenue and 68th
    Street, `confidence=1`, `match_type=exact`, `accuracy=point`. Accepting it
    would put a company's beacon on a hospital, and every layer would report
    success.
    """
    outcome = parse_search_response(city_response)

    assert isinstance(outcome, Unresolved)
    assert outcome.confidence is LocationConfidence.CITY_ONLY


def test_the_garbage_outscores_the_truth_in_the_recorded_data(
    street_response: dict, city_response: dict
) -> None:
    """Not a test of our code — a test of the premise our code is built on.

    If a future GeoSearch release made `confidence` trustworthy, this fails and
    somebody gets to reconsider §4.3.1 deliberately. Until then it is the
    evidence that ranking by the provider's own score would prefer a hospital.
    """
    correct = street_response["features"][0]["properties"]
    garbage = city_response["features"][0]["properties"]

    assert garbage["confidence"] > correct["confidence"]
    assert garbage["match_type"] == "exact"
    assert correct["match_type"] == "fallback"


def test_pelias_itself_reports_seeing_no_address(city_response: dict) -> None:
    """The cheapest of the three signals, and the one checked first."""
    parsed = city_response["geocoding"]["query"]["parsed_text"]
    assert "housenumber" not in parsed


def test_the_placeholder_bin_is_not_treated_as_a_building(city_response: dict) -> None:
    """NYC issues one placeholder BIN per borough meaning "the PAD has no
    building for this record". Two of the three results here carry 1000000."""
    bins = {f["properties"]["addendum"]["pad"]["bin"] for f in city_response["features"]}
    assert "1000000" in bins

    outcome = parse_search_response(city_response)
    assert isinstance(outcome, Unresolved)


# --------------------------------------------------------------------------
# Each rule, made to fail on its own
# --------------------------------------------------------------------------


def test_a_house_number_that_does_not_match_is_refused(street_response: dict) -> None:
    """Pelias will return a neighbouring house number as a fallback. A different
    house number is a different building and therefore a different answer."""
    mutated = {
        **street_response,
        "features": [
            {
                **street_response["features"][0],
                "properties": {
                    **street_response["features"][0]["properties"],
                    "housenumber": "618",
                },
            }
        ],
    }
    assert isinstance(parse_search_response(mutated), Unresolved)


def test_a_feature_with_a_placeholder_bin_is_refused(street_response: dict) -> None:
    mutated = {
        **street_response,
        "features": [
            {
                **street_response["features"][0],
                "properties": {
                    **street_response["features"][0]["properties"],
                    "addendum": {"pad": {"bin": "1000000"}},
                },
            }
        ],
    }
    assert isinstance(parse_search_response(mutated), Unresolved)


def test_an_empty_result_set_is_refused_not_crashed(street_response: dict) -> None:
    outcome = parse_search_response({**street_response, "features": []})
    assert isinstance(outcome, Unresolved)


def test_a_response_with_no_geocoding_block_is_refused(street_response: dict) -> None:
    """A provider that changes its envelope should cost us placements, not
    produce them."""
    payload = {k: v for k, v in street_response.items() if k != "geocoding"}
    assert isinstance(parse_search_response(payload), Unresolved)
