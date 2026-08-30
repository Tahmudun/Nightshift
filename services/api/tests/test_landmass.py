"""`landmass` is a pure function of one parsed location.

The four values exist because collapsing them would discard a fact the posting
stated. "Remote — United States" and "Remote — anywhere" differ on work
authorisation and time zone, which are the two things a reader filters on
(archipelago.md §4).
"""

from __future__ import annotations

import pytest

from nightshift.db.base import Landmass, LocationConfidence
from nightshift.domain.landmass import landmass_for
from nightshift.domain.locations import ParsedLocation


def _loc(**kwargs: object) -> ParsedLocation:
    base: dict[str, object] = {
        "raw_text": "somewhere",
        "city": None,
        "state": None,
        "country": None,
        "confidence": LocationConfidence.CITY_ONLY,
        "is_primary": True,
    }
    base.update(kwargs)
    return ParsedLocation(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize("city", ["New York", "Brooklyn", "Queens", "Bronx", "Staten Island"])
def test_five_boroughs_are_new_york(city: str) -> None:
    assert landmass_for(_loc(city=city, state="NY", country="US")) is Landmass.NEW_YORK


def test_a_named_city_that_is_not_new_york_is_elsewhere_city() -> None:
    assert (
        landmass_for(_loc(city="San Francisco", state="CA", country="US"))
        is Landmass.ELSEWHERE_CITY
    )


def test_a_country_with_no_city_is_elsewhere_broad() -> None:
    assert (
        landmass_for(
            _loc(
                raw_text="Remote (United States)",
                country="US",
                confidence=LocationConfidence.REMOTE,
            )
        )
        is Landmass.ELSEWHERE_BROAD
    )


def test_a_state_with_no_city_is_elsewhere_broad() -> None:
    assert landmass_for(_loc(state="CA", country="US")) is Landmass.ELSEWHERE_BROAD


def test_remote_anywhere_is_unplaced() -> None:
    assert (
        landmass_for(_loc(raw_text="Remote", confidence=LocationConfidence.REMOTE))
        is Landmass.UNPLACED
    )


def test_nothing_known_is_unplaced() -> None:
    assert (
        landmass_for(_loc(raw_text="Multiple Locations", confidence=LocationConfidence.UNKNOWN))
        is Landmass.UNPLACED
    )


def test_a_new_york_city_outranks_a_remote_confidence() -> None:
    """`confidence` does not decide the landmass; what is known about place does.

    A role written "Remote — New York, NY" states a city. Sorting it to the
    Verge would discard that.
    """
    assert (
        landmass_for(_loc(city="New York", state="NY", confidence=LocationConfidence.REMOTE))
        is Landmass.NEW_YORK
    )
