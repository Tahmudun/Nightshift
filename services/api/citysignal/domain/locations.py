"""Location-string parsing. Invariant I1 is enforced here.

This module segments and classifies the free-text location field an ATS gives
us. It does **not** geocode, and in M0 nothing else does either, so every
:class:`ParsedLocation` it returns has ``latitude is None`` — a fact asserted by
its test suite rather than left to trust.

The parse works right-to-left, because the informative tokens are on the right.
``"620 8th Ave, New York, NY"`` and ``"New York, New York, USA"`` have the same
comma count and completely different shapes; only the tail disambiguates them.

Two rules do most of the work of keeping the output honest:

* A place name is only accepted as a city when something corroborates it — a
  recognised state or country in the same segment, or a preceding comma part.
  A lone token like ``"Global"`` is therefore ``unknown``, not a city called
  Global.
* Coarser-than-city information never rounds up. ``"Germany"`` on its own
  resolves a country and no city, so its confidence is ``unknown``: we know
  something, but not enough to place it, and ``city_only`` would overstate it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from citysignal.db.base import LocationConfidence, ResolutionMethod

# ATS providers delimit multiple locations with ';' (Greenhouse, Ashby) or
# occasionally '|' (some Lever boards).
_SEGMENT_SPLIT = re.compile(r"\s*[;|]\s*")

# "Remote", "Remote - Anywhere", "Remote (US)", "Fully Remote".
_REMOTE_TOKEN = re.compile(r"^(?:fully\s+|100%\s+)?remote\b", re.IGNORECASE)

_US_STATES: dict[str, str] = {
    "alabama": "Alabama",
    "al": "Alabama",
    "alaska": "Alaska",
    "ak": "Alaska",
    "arizona": "Arizona",
    "az": "Arizona",
    "arkansas": "Arkansas",
    "ar": "Arkansas",
    "california": "California",
    "ca": "California",
    "colorado": "Colorado",
    "co": "Colorado",
    "connecticut": "Connecticut",
    "ct": "Connecticut",
    "delaware": "Delaware",
    "de": "Delaware",
    "district of columbia": "District of Columbia",
    "dc": "District of Columbia",
    "washington dc": "District of Columbia",
    "washington, d.c.": "District of Columbia",
    "florida": "Florida",
    "fl": "Florida",
    "georgia": "Georgia",
    "ga": "Georgia",
    "hawaii": "Hawaii",
    "hi": "Hawaii",
    "idaho": "Idaho",
    "id": "Idaho",
    "illinois": "Illinois",
    "il": "Illinois",
    "indiana": "Indiana",
    "in": "Indiana",
    "iowa": "Iowa",
    "ia": "Iowa",
    "kansas": "Kansas",
    "ks": "Kansas",
    "kentucky": "Kentucky",
    "ky": "Kentucky",
    "louisiana": "Louisiana",
    "la": "Louisiana",
    "maine": "Maine",
    "me": "Maine",
    "maryland": "Maryland",
    "md": "Maryland",
    "massachusetts": "Massachusetts",
    "ma": "Massachusetts",
    "michigan": "Michigan",
    "mi": "Michigan",
    "minnesota": "Minnesota",
    "mn": "Minnesota",
    "mississippi": "Mississippi",
    "ms": "Mississippi",
    "missouri": "Missouri",
    "mo": "Missouri",
    "montana": "Montana",
    "mt": "Montana",
    "nebraska": "Nebraska",
    "ne": "Nebraska",
    "nevada": "Nevada",
    "nv": "Nevada",
    "new hampshire": "New Hampshire",
    "nh": "New Hampshire",
    "new jersey": "New Jersey",
    "nj": "New Jersey",
    "new mexico": "New Mexico",
    "nm": "New Mexico",
    "new york": "New York",
    "ny": "New York",
    "north carolina": "North Carolina",
    "nc": "North Carolina",
    "north dakota": "North Dakota",
    "nd": "North Dakota",
    "ohio": "Ohio",
    "oh": "Ohio",
    "oklahoma": "Oklahoma",
    "ok": "Oklahoma",
    "oregon": "Oregon",
    "or": "Oregon",
    "pennsylvania": "Pennsylvania",
    "pa": "Pennsylvania",
    "puerto rico": "Puerto Rico",
    "pr": "Puerto Rico",
    "rhode island": "Rhode Island",
    "ri": "Rhode Island",
    "south carolina": "South Carolina",
    "sc": "South Carolina",
    "south dakota": "South Dakota",
    "sd": "South Dakota",
    "tennessee": "Tennessee",
    "tn": "Tennessee",
    "texas": "Texas",
    "tx": "Texas",
    "utah": "Utah",
    "ut": "Utah",
    "vermont": "Vermont",
    "vt": "Vermont",
    "virginia": "Virginia",
    "va": "Virginia",
    "washington": "Washington",
    "wa": "Washington",
    "west virginia": "West Virginia",
    "wv": "West Virginia",
    "wisconsin": "Wisconsin",
    "wi": "Wisconsin",
    "wyoming": "Wyoming",
    "wy": "Wyoming",
}

# Not a gazetteer, and not trying to be. These are the countries that actually
# appear on tech job boards, plus the spelling variants providers use. An
# unrecognised country yields `unknown` rather than a wrong guess, which is the
# failure mode I1 asks for.
_COUNTRIES: dict[str, str] = {
    "usa": "USA",
    "us": "USA",
    "u.s.": "USA",
    "u.s.a.": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "canada": "Canada",
    "mexico": "Mexico",
    "brazil": "Brazil",
    "brasil": "Brazil",
    "argentina": "Argentina",
    "chile": "Chile",
    "colombia": "Colombia",
    "costa rica": "Costa Rica",
    "peru": "Peru",
    "uruguay": "Uruguay",
    "ireland": "Ireland",
    "france": "France",
    "germany": "Germany",
    "deutschland": "Germany",
    "spain": "Spain",
    "españa": "Spain",
    "portugal": "Portugal",
    "italy": "Italy",
    "italia": "Italy",
    "netherlands": "Netherlands",
    "the netherlands": "Netherlands",
    "holland": "Netherlands",
    "belgium": "Belgium",
    "luxembourg": "Luxembourg",
    "switzerland": "Switzerland",
    "austria": "Austria",
    "denmark": "Denmark",
    "sweden": "Sweden",
    "norway": "Norway",
    "finland": "Finland",
    "iceland": "Iceland",
    "estonia": "Estonia",
    "latvia": "Latvia",
    "lithuania": "Lithuania",
    "poland": "Poland",
    "czech republic": "Czech Republic",
    "czechia": "Czech Republic",
    "slovakia": "Slovakia",
    "hungary": "Hungary",
    "romania": "Romania",
    "bulgaria": "Bulgaria",
    "greece": "Greece",
    "croatia": "Croatia",
    "serbia": "Serbia",
    "slovenia": "Slovenia",
    "ukraine": "Ukraine",
    "turkey": "Turkey",
    "türkiye": "Turkey",
    "israel": "Israel",
    "united arab emirates": "United Arab Emirates",
    "uae": "United Arab Emirates",
    "saudi arabia": "Saudi Arabia",
    "qatar": "Qatar",
    "egypt": "Egypt",
    "south africa": "South Africa",
    "nigeria": "Nigeria",
    "kenya": "Kenya",
    "india": "India",
    "pakistan": "Pakistan",
    "bangladesh": "Bangladesh",
    "china": "China",
    "hong kong": "Hong Kong",
    "taiwan": "Taiwan",
    "japan": "Japan",
    "south korea": "South Korea",
    "korea": "South Korea",
    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "indonesia": "Indonesia",
    "thailand": "Thailand",
    "vietnam": "Vietnam",
    "philippines": "Philippines",
    "australia": "Australia",
    "new zealand": "New Zealand",
}


@dataclass(frozen=True, slots=True)
class ParsedLocation:
    """One location a posting names, with an honest precision claim.

    ``latitude``/``longitude`` are not fields on this class at all. Geocoding is
    a separate stage that produces its own type; a parser that *could* return
    coordinates is a parser that eventually will invent one.
    """

    raw_text: str
    city: str | None
    state: str | None
    country: str | None
    confidence: LocationConfidence
    is_primary: bool
    resolution_method: ResolutionMethod = ResolutionMethod.SOURCE_TEXT_PARSE

    @property
    def is_nyc(self) -> bool:
        """True for the five boroughs. Used to prioritise polling, never to place a point."""
        if self.city is None:
            return False
        return self.city.casefold() in {
            "new york",
            "new york city",
            "manhattan",
            "brooklyn",
            "queens",
            "the bronx",
            "bronx",
            "staten island",
        }


@dataclass(slots=True)
class _Tail:
    """Result of stripping recognised tail tokens off a segment."""

    parts: list[str]
    state: str | None = None
    country: str | None = None
    remote: bool = False
    dropped: list[str] = field(default_factory=list)


def _split_segments(raw: str) -> list[str]:
    """Split the source field into per-location segments, preserving order."""
    segments: list[str] = []
    seen: set[str] = set()
    for chunk in _SEGMENT_SPLIT.split(raw or ""):
        text = " ".join(chunk.split())
        if not text:
            continue
        # Collapse exact duplicates. A board that lists the same office twice
        # should not produce two rows that later look like two offices.
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        segments.append(text)
    return segments


def _strip_tail_tokens(segment: str) -> _Tail:
    """Consume ``Remote``, then a country, then a US state, from the right."""
    parts = [" ".join(p.split()) for p in segment.split(",")]
    parts = [p for p in parts if p]
    tail = _Tail(parts=parts)

    # 1. Remote can appear as its own trailing part ("New York, USA, Remote")
    #    or lead the whole segment ("Remote - Anywhere").
    remaining: list[str] = []
    for part in parts:
        if _REMOTE_TOKEN.match(part):
            tail.remote = True
            tail.dropped.append(part)
        else:
            remaining.append(part)
    tail.parts = remaining

    # 2. Country, then state — in that order, because "New York, USA" puts the
    #    country last and the state immediately before it.
    if tail.parts:
        country = _COUNTRIES.get(tail.parts[-1].casefold())
        if country is not None:
            tail.country = country
            tail.parts.pop()

    if tail.parts:
        state = _US_STATES.get(tail.parts[-1].casefold())
        if state is not None:
            tail.state = state
            tail.parts.pop()

    return tail


def parse_location_segment(segment: str, *, is_primary: bool) -> ParsedLocation:
    """Parse one already-split segment."""
    tail = _strip_tail_tokens(segment)
    corroborated = tail.state is not None or tail.country is not None

    city: str | None = None
    if tail.parts:
        # With a street address the city is the *last* unconsumed part:
        # "620 8th Ave, New York" -> "New York".
        candidate = tail.parts[-1]
        # A bare token with nothing corroborating it is not a city. This is what
        # keeps "Global" and "Multiple Locations" out of the city column.
        if corroborated or len(tail.parts) > 1:
            city = candidate

    if tail.remote:
        confidence = LocationConfidence.REMOTE
    elif city is not None:
        confidence = LocationConfidence.CITY_ONLY
    else:
        # Either nothing parsed, or only country-level information — coarser
        # than city, so it does not earn `city_only`.
        confidence = LocationConfidence.UNKNOWN

    return ParsedLocation(
        raw_text=segment,
        city=city,
        state=tail.state,
        country=tail.country,
        confidence=confidence,
        is_primary=is_primary,
    )


def parse_location_field(raw: str | None) -> list[ParsedLocation]:
    """Parse a source's location field into one :class:`ParsedLocation` per place.

    Returns an empty list for empty input: a posting with no location text gets
    no location rows, rather than one row claiming to be somewhere.

    The first segment is marked primary, matching source order. Providers list
    the requisition's home office first; when they do not, the value is still a
    real location the posting names, so ordering affects sorting and never
    correctness.
    """
    segments = _split_segments(raw or "")
    return [
        parse_location_segment(segment, is_primary=(index == 0))
        for index, segment in enumerate(segments)
    ]


def infer_remote_policy(locations: list[ParsedLocation]) -> str:
    """Derive a job-level remote policy from parsed locations.

    Conservative on purpose: a posting listing both an office and remote states
    is ``hybrid``, one listing only remote segments is ``remote``, and anything
    with no location signal at all stays ``unknown`` rather than defaulting to
    on-site.
    """
    if not locations:
        return "unknown"
    remote = [loc for loc in locations if loc.confidence is LocationConfidence.REMOTE]
    physical = [
        loc
        for loc in locations
        if loc.confidence
        in {
            LocationConfidence.CITY_ONLY,
            LocationConfidence.APPROXIMATE,
            LocationConfidence.VERIFIED,
        }
    ]
    if remote and physical:
        return "hybrid"
    if remote:
        return "remote"
    if physical:
        return "on_site"
    return "unknown"
