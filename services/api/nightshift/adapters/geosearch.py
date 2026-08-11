"""NYC GeoSearch — rung 1, and the only rung that can produce `verified`.

Pelias over the city's Property Address Directory. Free, no key, no quota
(AMENDMENTS A4). It is authoritative for NYC addresses in a way no commercial
geocoder is, because it *is* the city's address list rather than a model of it.

**Confidence is not a quality signal here, and that is measured rather than
assumed.** Both responses this module parses are committed in
`tests/fixtures/geosearch/` with provenance. The short version:

    "620 Eighth Avenue, New York, NY"  -> confidence 0.8, match_type fallback  (correct)
    "New York, NY"                     -> confidence 1.0, match_type exact     (a hospital)

The second query returns `NEW YORK HOSPITAL` — a real building at First Avenue
and 68th Street — at maximum confidence, because Pelias matched the words
"New York" against venue names, exactly. It is answering a different question
from the one asked, and saying so with more certainty than it has about the
right answer. **An acceptance rule built on `confidence` would prefer the
garbage.**

So acceptance is structural instead. A result is only an address if the
provider parsed a house number out of the query, the feature carries that same
house number, and the building it names is a real one. Each of those is a fact
about what the response *is*, not about how sure the provider feels.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from nightshift.adapters.base import SourceUnavailableError
from nightshift.adapters.http import PoliteClient
from nightshift.db.base import LocationConfidence, ResolutionMethod
from nightshift.domain.geocoding import (
    OUTSIDE_COVERAGE,
    PROVIDER_FOUND_NOTHING,
    PROVIDER_UNAVAILABLE,
    GeocodeOutcome,
    Resolved,
    Unresolved,
)

SEARCH_URL = "https://geosearch.planninglabs.nyc/v2/search"

# NYC issues one placeholder BIN per borough — 1000000 for Manhattan, 2000000
# for the Bronx, and so on — meaning "the PAD has no building for this record".
# Two of the three results for "New York, NY" carry 1000000. A placeholder is
# the provider saying it has a point and no building, so it is not a building.
_PLACEHOLDER_BIN = re.compile(r"^[1-5]0{6}$")


def _parsed_housenumber(payload: dict[str, Any]) -> str | None:
    """What Pelias reports having parsed out of the query.

    The first and cheapest signal. For "New York, NY" the `parsed_text` block
    has no `housenumber` key at all — the provider states plainly that it saw no
    address, before any feature is even considered.
    """
    query = (payload.get("geocoding") or {}).get("query") or {}
    parsed = query.get("parsed_text") or {}
    value = parsed.get("housenumber")
    return str(value).strip() if value else None


def _is_a_building(properties: dict[str, Any]) -> bool:
    bin_value = ((properties.get("addendum") or {}).get("pad") or {}).get("bin")
    return bool(bin_value) and not _PLACEHOLDER_BIN.match(str(bin_value))


def parse_search_response(payload: dict[str, Any]) -> GeocodeOutcome:
    """Turn a GeoSearch response into a point or a refusal.

    Pure, so every rule below is testable against the committed fixtures without
    a network. The adapter method underneath is a fetch and a call to this.
    """
    housenumber = _parsed_housenumber(payload)
    if housenumber is None:
        # The provider did not see an address. Anything it returned is a match
        # on some other part of the string — a venue name, a locality — and none
        # of it is where the caller meant.
        return Unresolved(PROVIDER_FOUND_NOTHING, LocationConfidence.CITY_ONLY)

    for feature in payload.get("features") or []:
        properties = feature.get("properties") or {}

        # The feature has to be an address, and the *same* address. Pelias will
        # happily return a neighbouring house number as a fallback, which is a
        # different building and therefore a different answer.
        if str(properties.get("housenumber") or "").strip() != housenumber:
            continue
        if not properties.get("street"):
            continue
        if not _is_a_building(properties):
            continue

        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coordinates) != 2:
            continue
        longitude, latitude = float(coordinates[0]), float(coordinates[1])

        return Resolved(
            latitude=latitude,
            longitude=longitude,
            confidence=LocationConfidence.VERIFIED,
            method=ResolutionMethod.NYC_GEOSEARCH,
            matched_text=str(properties.get("label") or ""),
            building_id=str(((properties["addendum"])["pad"])["bin"]),
        )

    # Pelias parsed an address and nothing it returned was that address at a
    # real building. For a service whose entire corpus is NYC, that most often
    # means the address is not in NYC.
    return Unresolved(OUTSIDE_COVERAGE, LocationConfidence.CITY_ONLY)


class NycGeoSearchGeocoder:
    """Rung 1. Implements `domain.geocoding.Geocoder`."""

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    @property
    def method(self) -> ResolutionMethod:
        return ResolutionMethod.NYC_GEOSEARCH

    async def geocode(self, address: str) -> GeocodeOutcome:
        # The URL is built here rather than by extending `PoliteClient.get_json`
        # with a params argument: three adapters share that client, and widening
        # its signature for one caller is how a shared thing accumulates.
        url = f"{SEARCH_URL}?{urlencode({'text': address, 'size': 5})}"
        try:
            payload = await self._client.get_json(url)
        except SourceUnavailableError:
            # I3's distinction, one subsystem over: a provider being down is not
            # evidence about where an office is. The caller must be able to tell
            # "we looked and found nothing" from "we could not look", because
            # only the first is worth caching as an answer.
            return Unresolved(PROVIDER_UNAVAILABLE, LocationConfidence.CITY_ONLY)

        if not isinstance(payload, dict):
            return Unresolved(PROVIDER_UNAVAILABLE, LocationConfidence.CITY_ONLY)
        return parse_search_response(payload)
