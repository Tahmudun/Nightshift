"""Turning an address into a point, or honestly refusing to.

`city.md` §4.3. This is the only module in the product that may produce a
coordinate, and invariant I1 is the reason it is shaped the way it is.

**The ladder.** A4 defines four rungs, and M4a Task 1 measured which of them a
given input can actually reach:

    1. NYC GeoSearch    a street address        -> verified
    2. Nominatim        a street address        -> approximate
    3. Neighbourhood    a named neighbourhood   -> approximate, flagged
    4. nothing resolved                         -> city_only / remote / unknown

A job posting reaches rung 4 and no higher, always — 0 of 247 recorded postings
name a street. The ladder exists for the input it was designed for, which is a
company office address a human confirmed (`city.md` §4.4).

**Two rules the shape enforces rather than documents.**

`GeocodeOutcome` cannot carry coordinates without a confidence and a method, and
cannot carry `verified` without having come from an address containing a street.
A geocoder that *could* return a bare point is a geocoder that eventually will,
and "close enough" is the failure mode I1 exists to prevent.

And a refusal is a value, not an exception. `Unresolved` carries why nothing was
found, so a caller writing to `job_locations` or `company_locations` has
something to put in `resolution_method` other than a guess. Silence and failure
are different, which is the same distinction I3 draws for source outages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from nightshift.db.base import LocationConfidence, ResolutionMethod

# A street address names a thoroughfare. Shared with
# `scripts/census_location_text.py` in intent but deliberately not in code: the
# census is an analysis over recorded fixtures and this is a gate on what may
# become a coordinate. One of them changing should not silently change the
# other. `tests/test_geocoding.py` holds them to the same verdicts on the cases
# that matter, so a divergence is visible rather than assumed away.
_UNAMBIGUOUS_THOROUGHFARE = (
    r"street|avenue|boulevard|broadway|bowery|parkway|turnpike|highway|"
    r"plaza|terrace|drive|lane"
)
_ABBREVIATED_THOROUGHFARE = r"st|ave|blvd|rd|dr|ln|ct|fl|ste|pkwy|pl|ter|sq|hwy"

# The abbreviations collide with US state codes — `ct` with Connecticut, `fl`
# with Florida — so they count only behind a house number, where "200 Park Ave"
# is unambiguous and "Miami, FL" cannot reach. The census's first draft had
# exactly this bug and reported four street addresses that were all state codes.
_NUMBERED_STREET = re.compile(
    rf"\b\d{{1,5}}[a-z]?\b(?:\s+[\w.'-]+){{0,3}}\s+"
    rf"({_UNAMBIGUOUS_THOROUGHFARE}|{_ABBREVIATED_THOROUGHFARE})\b",
    re.IGNORECASE,
)
_NAMED_STREET = re.compile(rf"\b({_UNAMBIGUOUS_THOROUGHFARE})\b", re.IGNORECASE)


def names_a_street(address: str | None) -> bool:
    """True when the text names a thoroughfare.

    The gate on `verified`. "New York, NY" is false and always will be; a city
    name cannot become a building, and this function is where that is decided
    rather than in whichever caller happened to be careful.
    """
    if not address:
        return False
    return bool(_NUMBERED_STREET.search(address) or _NAMED_STREET.search(address))


class GeocodeRefusal(str):
    """Why nothing was resolved. A string subclass so it reads in a log."""

    __slots__ = ()


NO_STREET_IN_INPUT = GeocodeRefusal("no_street_in_input")
PROVIDER_FOUND_NOTHING = GeocodeRefusal("provider_found_nothing")
PROVIDER_UNAVAILABLE = GeocodeRefusal("provider_unavailable")
OUTSIDE_COVERAGE = GeocodeRefusal("outside_coverage")


@dataclass(frozen=True, slots=True)
class Resolved:
    """A point, its precision claim, and which rung produced it.

    Constructed only through `__post_init__`'s checks, which are the same claims
    the `company_locations` DDL makes. Two layers on purpose: the database is the
    guarantee, and this is the layer that makes a violation a test failure with a
    readable message rather than an `IntegrityError` at commit time.
    """

    latitude: float
    longitude: float
    confidence: LocationConfidence
    method: ResolutionMethod
    # What the provider matched, verbatim. Kept so a placement that looks wrong
    # can be argued with: "you asked for X and it matched Y" is a different
    # conversation from "the map is wrong".
    matched_text: str

    def __post_init__(self) -> None:
        if self.confidence in (
            LocationConfidence.CITY_ONLY,
            LocationConfidence.REMOTE,
            LocationConfidence.UNKNOWN,
        ):
            raise ValueError(
                f"{self.confidence} carries no coordinates by definition — "
                "return an Unresolved instead of a point nobody claimed"
            )
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"latitude {self.latitude} is not a latitude")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"longitude {self.longitude} is not a longitude")
        if self.method in (ResolutionMethod.NOT_ATTEMPTED, ResolutionMethod.SOURCE_TEXT_PARSE):
            raise ValueError(
                f"{self.method} never produces a coordinate; a point with this "
                "method would be untraceable to anything that could have found it"
            )


@dataclass(frozen=True, slots=True)
class Unresolved:
    """No point, and the reason. Not an error — the common and correct answer."""

    refusal: GeocodeRefusal
    # The confidence the caller should store. `city_only` when the input named a
    # city we could not place more finely; `unknown` when it named nothing.
    confidence: LocationConfidence = LocationConfidence.UNKNOWN

    def __post_init__(self) -> None:
        if self.confidence in (LocationConfidence.VERIFIED, LocationConfidence.APPROXIMATE):
            raise ValueError(
                f"{self.confidence} is a claim about a coordinate, and this is "
                "the type that has none"
            )


GeocodeOutcome = Resolved | Unresolved


@runtime_checkable
class Geocoder(Protocol):
    """One rung of the ladder.

    Nothing outside `nightshift.adapters` imports `httpx` (CLAUDE.md §7), so an
    implementation of this that talks to a network lives there and this module
    only ever sees the Protocol. That is also what makes the offline path real
    rather than mocked: `make demo` wires a fixture-backed implementation
    through the same interface, not around it.
    """

    @property
    def method(self) -> ResolutionMethod:
        """Which rung this is, for `resolution_method`."""
        ...

    async def geocode(self, address: str) -> GeocodeOutcome:
        """Resolve, or say why not. Never raises for a miss — a miss is data."""
        ...


async def resolve(address: str | None, ladder: tuple[Geocoder, ...]) -> GeocodeOutcome:
    """Walk the ladder until a rung answers, and refuse before starting if it cannot.

    The early refusal is the load-bearing part. Rung 1 exists to turn a street
    into a `verified` point, and handing it a city name does not produce a worse
    answer — it produces a *confident* one, because a Pelias search for
    "New York, NY" returns the city's centroid with a perfectly good score. That
    point would then sit on whichever building the centroid landed in, which is
    the fabrication I1 forbids, arriving with every layer reporting success.

    So an address that names no street never reaches a geocoder at all.
    """
    if not address or not address.strip():
        return Unresolved(NO_STREET_IN_INPUT, LocationConfidence.UNKNOWN)
    if not names_a_street(address):
        # A city was named and nothing finer. That is `city_only`, which is a
        # real answer about a real place, not a failure.
        return Unresolved(NO_STREET_IN_INPUT, LocationConfidence.CITY_ONLY)

    last: Unresolved = Unresolved(PROVIDER_FOUND_NOTHING, LocationConfidence.CITY_ONLY)
    for rung in ladder:
        outcome = await rung.geocode(address)
        if isinstance(outcome, Resolved):
            return outcome
        last = outcome
    return last
