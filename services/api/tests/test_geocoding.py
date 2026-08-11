"""The ladder, and the refusals that keep I1 out of the renderer's hands.

`city.md` §4.3. Every test here is about one of two things: a coordinate that
must not be produced, or a refusal that must carry enough information for the
caller to store an honest `resolution_method`.

The sharpest case is `test_a_city_name_never_reaches_a_geocoder`. Handing
"New York, NY" to Pelias does not fail — it succeeds, with a good score, and
returns the city centroid. Every layer reports success and a beacon lands on
whichever building that centroid fell inside. That is the failure mode this
module is shaped to make impossible, and it is invisible to any test that only
checks whether the geocoder was *right*.
"""

from __future__ import annotations

import pytest

from nightshift.db.base import LocationConfidence, ResolutionMethod
from nightshift.domain.geocoding import (
    NO_STREET_IN_INPUT,
    PROVIDER_FOUND_NOTHING,
    PROVIDER_UNAVAILABLE,
    GeocodeOutcome,
    Resolved,
    Unresolved,
    names_a_street,
    resolve,
)

pytestmark = pytest.mark.asyncio


class _Recording:
    """A rung that records what it was asked, so a test can assert it was not."""

    def __init__(self, outcome: GeocodeOutcome, method: ResolutionMethod) -> None:
        self._outcome = outcome
        self._method = method
        self.asked: list[str] = []

    @property
    def method(self) -> ResolutionMethod:
        return self._method

    async def geocode(self, address: str) -> GeocodeOutcome:
        self.asked.append(address)
        return self._outcome


def _point(
    confidence: LocationConfidence = LocationConfidence.VERIFIED,
    method: ResolutionMethod = ResolutionMethod.NYC_GEOSEARCH,
) -> Resolved:
    return Resolved(40.756, -73.990, confidence, method, "620 8 Avenue, New York, NY 10018")


# --------------------------------------------------------------------------
# The street gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "620 Eighth Avenue, New York, NY 10018",
        "200 Park Ave, New York",
        "85 Broad Street",
        "1 Bowery, New York, NY",
        "Broadway, Manhattan",
    ],
)
async def test_a_real_address_names_a_street(address: str) -> None:
    assert names_a_street(address)


@pytest.mark.parametrize(
    "address",
    [
        "New York, NY",
        "New York City",
        "New York, New York, USA",
        "Remote (US)",
        "San Francisco, California, United States",
        "Bengaluru, KA",
        "",
        None,
    ],
)
async def test_a_place_name_does_not(address: str | None) -> None:
    assert not names_a_street(address)


@pytest.mark.parametrize("address", ["Miami, FL", "Stamford, CT", "Portland, OR"])
async def test_a_state_code_is_not_a_thoroughfare(address: str) -> None:
    """`ct` is Connecticut before it is Court and `fl` is Florida before it is
    Floor. The census's first draft got this wrong and reported four street
    addresses that were all state codes — on this corpus that is the difference
    between "no posting names a street" and "postings in two states do"."""
    assert not names_a_street(address)


# --------------------------------------------------------------------------
# The ladder
# --------------------------------------------------------------------------


async def test_a_city_name_never_reaches_a_geocoder() -> None:
    """The load-bearing test in this file.

    Pelias answers "New York, NY" with the city centroid and a good score. The
    protection cannot be "the geocoder will decline", because it will not — it
    has to be that the geocoder is never asked.
    """
    rung = _Recording(_point(), ResolutionMethod.NYC_GEOSEARCH)
    outcome = await resolve("New York, NY", (rung,))

    assert rung.asked == []
    assert isinstance(outcome, Unresolved)
    assert outcome.refusal == NO_STREET_IN_INPUT
    assert outcome.confidence is LocationConfidence.CITY_ONLY


async def test_a_named_city_refuses_as_city_only_not_unknown() -> None:
    """`city_only` and `unknown` are different claims. "We know the city and
    nothing finer" is information; "we know nothing" is not, and collapsing the
    first into the second loses the thing the unresolved layer sorts by."""
    outcome = await resolve("New York, NY", ())
    assert isinstance(outcome, Unresolved)
    assert outcome.confidence is LocationConfidence.CITY_ONLY

    nothing = await resolve("", ())
    assert isinstance(nothing, Unresolved)
    assert nothing.confidence is LocationConfidence.UNKNOWN


async def test_the_first_rung_that_answers_wins() -> None:
    first = _Recording(_point(), ResolutionMethod.NYC_GEOSEARCH)
    second = _Recording(
        _point(LocationConfidence.APPROXIMATE, ResolutionMethod.NOMINATIM),
        ResolutionMethod.NOMINATIM,
    )
    outcome = await resolve("620 Eighth Avenue, New York", (first, second))

    assert isinstance(outcome, Resolved)
    assert outcome.method is ResolutionMethod.NYC_GEOSEARCH
    assert second.asked == [], "a lower rung was consulted after a higher one answered"


async def test_a_miss_falls_through_to_the_next_rung() -> None:
    first = _Recording(Unresolved(PROVIDER_FOUND_NOTHING), ResolutionMethod.NYC_GEOSEARCH)
    second = _Recording(
        _point(LocationConfidence.APPROXIMATE, ResolutionMethod.NOMINATIM),
        ResolutionMethod.NOMINATIM,
    )
    outcome = await resolve("620 Eighth Avenue, New York", (first, second))

    assert isinstance(outcome, Resolved)
    assert outcome.method is ResolutionMethod.NOMINATIM
    assert first.asked and second.asked


async def test_an_exhausted_ladder_keeps_the_last_refusal() -> None:
    """The reason has to survive. A caller storing `resolution_method` needs to
    know whether nothing matched or nothing was reachable — I3's distinction,
    one subsystem over."""
    outcome = await resolve(
        "620 Eighth Avenue, New York",
        (
            _Recording(Unresolved(PROVIDER_FOUND_NOTHING), ResolutionMethod.NYC_GEOSEARCH),
            _Recording(Unresolved(PROVIDER_UNAVAILABLE), ResolutionMethod.NOMINATIM),
        ),
    )
    assert isinstance(outcome, Unresolved)
    assert outcome.refusal == PROVIDER_UNAVAILABLE


# --------------------------------------------------------------------------
# The types refuse the thing the DDL refuses
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "confidence",
    [LocationConfidence.CITY_ONLY, LocationConfidence.REMOTE, LocationConfidence.UNKNOWN],
)
async def test_a_coordinate_cannot_be_built_with_a_pointless_confidence(
    confidence: LocationConfidence,
) -> None:
    """The same claim `ck_company_locations_confidence_matches_coordinates`
    makes, one layer up, so a violation is a readable failure rather than an
    IntegrityError at commit."""
    with pytest.raises(ValueError, match="carries no coordinates"):
        _point(confidence)


async def test_an_unresolved_cannot_claim_a_precision_it_has_no_point_for() -> None:
    with pytest.raises(ValueError, match="claim about a coordinate"):
        Unresolved(PROVIDER_FOUND_NOTHING, LocationConfidence.VERIFIED)


@pytest.mark.parametrize(
    "method", [ResolutionMethod.NOT_ATTEMPTED, ResolutionMethod.SOURCE_TEXT_PARSE]
)
async def test_a_coordinate_cannot_claim_a_method_that_produces_none(
    method: ResolutionMethod,
) -> None:
    """`source_text_parse` reads a posting's words. It has never produced a
    coordinate and cannot — a point wearing it would be untraceable to anything
    that could have found it."""
    with pytest.raises(ValueError, match="never produces a coordinate"):
        _point(method=method)


@pytest.mark.parametrize("lat,lon", [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)])
async def test_a_coordinate_off_the_globe_is_refused(lat: float, lon: float) -> None:
    with pytest.raises(ValueError, match="is not a"):
        Resolved(lat, lon, LocationConfidence.VERIFIED, ResolutionMethod.NYC_GEOSEARCH, "x")


async def test_the_census_and_the_gate_agree_on_the_cases_that_matter() -> None:
    """`scripts/census_location_text.py` has its own copy of this rule, on
    purpose — one is an analysis over fixtures and the other is a gate on what
    may become a coordinate, and they should be free to diverge. This test makes
    a divergence visible instead of assumed away."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from census_location_text import looks_like_street

    for address in (
        "620 Eighth Avenue, New York, NY 10018",
        "200 Park Ave, New York",
        "New York, NY",
        "Miami, FL",
        "Stamford, CT",
        "Remote (US)",
    ):
        assert looks_like_street(address) == names_a_street(address), (
            f"the census and the geocoding gate disagree about {address!r}. That "
            "may be fine — they are allowed to differ — but it should be a "
            "decision somebody made, not a drift nobody noticed."
        )
