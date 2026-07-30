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
  recognised state or country in the same segment, or a second comma part
  present at all, resolved or not (``"Bengaluru, KA"`` keeps its city even
  though ``KA`` names no known subdivision). ``Remote`` never corroborates:
  it is the token asserting there is *no* place, so ``"Global, Remote"``
  stays ``unknown`` same as a lone ``"Global"`` would.
* Coarser-than-city information never rounds up. ``"Germany"`` on its own
  resolves a country and no city, so its confidence is ``unknown``: we know
  something, but not enough to place it, and ``city_only`` would overstate it.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from nightshift.db.base import LocationConfidence, ResolutionMethod

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

# Canadian provinces. Added because Lever and Ashby boards name Vancouver and
# Toronto, and without this table `parts[-1]` — the subdivision code — was
# being taken as the city, producing a place called "BC". No code here
# collides with a US postal abbreviation, so lookup order does not matter.
_CA_PROVINCES: dict[str, str] = {
    "alberta": "Alberta",
    "ab": "Alberta",
    "british columbia": "British Columbia",
    "bc": "British Columbia",
    "manitoba": "Manitoba",
    "mb": "Manitoba",
    "new brunswick": "New Brunswick",
    "nb": "New Brunswick",
    "newfoundland and labrador": "Newfoundland and Labrador",
    "nl": "Newfoundland and Labrador",
    "nova scotia": "Nova Scotia",
    "ns": "Nova Scotia",
    "ontario": "Ontario",
    "on": "Ontario",
    "prince edward island": "Prince Edward Island",
    "pe": "Prince Edward Island",
    "quebec": "Quebec",
    "québec": "Quebec",
    "qc": "Quebec",
    "saskatchewan": "Saskatchewan",
    "sk": "Saskatchewan",
}

# ADR 0008. A bare place name normally resolves to `unknown`, because a lone
# token with nothing corroborating it is not evidence of a city. These are the
# documented exceptions: NYC and its boroughs, which M1d's hot tier depends on
# and which providers routinely write without a state.
#
# Enumerated on purpose. The value is (city, state, country), and the result is
# `city_only` — never a coordinate, so I1 is untouched.
_DECIDED_BARE_PLACES: dict[str, tuple[str, str | None, str | None]] = {
    "new york": ("New York", "New York", None),
    "new york city": ("New York", "New York", None),
    "nyc": ("New York", "New York", None),
    "manhattan": ("Manhattan", "New York", None),
    "brooklyn": ("Brooklyn", "New York", None),
    "queens": ("Queens", "New York", None),
    "the bronx": ("The Bronx", "New York", None),
    "bronx": ("The Bronx", "New York", None),
    "staten island": ("Staten Island", "New York", None),
}

# A bare two-letter token that resolved to no subdivision is not a city.
# Fixing "BC" by adding it to a table would leave every unlisted code broken,
# so the guard is on the shape of the token rather than on its value.
_BARE_SUBDIVISION_CODE = re.compile(r"^[A-Za-z]{2}$")

# A trailing parenthetical annotation: "New York, NY (HQ)", "Remote (US)".
# Sometimes noise, sometimes the only geographic signal present, so it is
# lifted out and re-interpreted rather than dropped.
_PAREN_SUFFIX = re.compile(r"\s*\(([^)]*)\)\s*$")

# "Remote - United States", "Remote — US", "Remote: EMEA".
_REMOTE_PREFIX = re.compile(
    r"^(?:fully\s+|100%\s+)?remote\b[\s\-–—:,]*",  # noqa: RUF001
    re.IGNORECASE,
)


def _lookup_subdivision(token: str) -> str | None:
    """Resolve a US state or Canadian province name or code."""
    key = token.casefold()
    return _US_STATES.get(key) or _CA_PROVINCES.get(key)


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
    annotations: list[str] = field(default_factory=list)
    # Comma-part count after ``Remote`` is stripped but before country/
    # subdivision consumption or the bare-code drop. "Bengaluru, KA"
    # corroborates "Bengaluru" as a city even though "KA" resolves to no known
    # subdivision: a second part was named, and naming one is what counts,
    # not whether it decoded to anything. Captured post-``Remote`` on purpose:
    # ``Remote`` itself asserts the *absence* of a place, so counting it here
    # would let "Global, Remote" corroborate "Global" as a city — the opposite
    # of what the token means.
    raw_part_count: int = 0


def _strip_tail_tokens(segment: str) -> _Tail:
    """Consume annotations, ``Remote``, a country, then a US/CA subdivision.

    Right-to-left, because the informative tokens are on the right. The order
    within this function is deliberate and each step depends on the one above:
    annotations must come off before a code like ``NY (HQ)`` can be recognised
    as a state, and ``Remote`` must come off before ``Remote - United States``
    can yield a country.
    """
    raw_parts = [" ".join(p.split()) for p in segment.split(",")]
    raw_parts = [p for p in raw_parts if p]

    # 1. Lift trailing parentheticals out of each part.
    parts: list[str] = []
    annotations: list[str] = []
    for part in raw_parts:
        match = _PAREN_SUFFIX.search(part)
        if match is not None:
            inner = match.group(1).strip()
            if inner:
                annotations.append(inner)
            part = part[: match.start()].strip()
        if part:
            parts.append(part)

    tail = _Tail(parts=parts, annotations=annotations)

    # 2. Remote, wherever it appears. Anything trailing the token on the same
    #    part survives as a part of its own: "Remote - United States" must not
    #    throw away "United States".
    remaining: list[str] = []
    for part in tail.parts:
        if _REMOTE_TOKEN.match(part):
            tail.remote = True
            tail.dropped.append(part)
            residue = _REMOTE_PREFIX.sub("", part).strip()
            if residue:
                remaining.append(residue)
        else:
            remaining.append(part)
    tail.parts = remaining

    # `raw_part_count` is measured here, after Remote is gone but before
    # country/subdivision consumption or the bare-code drop. Measuring before
    # this step would count "Remote" itself as a corroborating comma part,
    # which is backwards: "Remote" is the token that says there is no place.
    tail.raw_part_count = len(tail.parts)

    # 3. Country, then subdivision — in that order, because "New York, USA"
    #    puts the country last and the state immediately before it.
    if tail.parts:
        country = _COUNTRIES.get(tail.parts[-1].casefold())
        if country is not None:
            tail.country = country
            tail.parts.pop()

    # A genuinely bare segment (no comma at all, aside from Remote) that is on
    # the decided-place table (ADR 0008) skips subdivision consumption here.
    # Needed for exactly one collision: "New York" is both a state name and a
    # decided city name, so without this guard the lookup below would consume
    # the lone token as a state, leaving nothing in `tail.parts` for the
    # decided-place check in `parse_location_segment` to ever see.
    #
    # Gated on `raw_part_count == 1`, not on `len(tail.parts) == 1` here, on
    # purpose: "New York, USA, Remote" also has one part left at this point
    # (country already consumed "USA"), but that "New York" names the state a
    # remote role is restricted to, not a specific city — `statewide_remote`
    # is the fixture that pins city=None, state="New York" for it.
    #
    # `raw_part_count` is captured post-`Remote`-stripping (see `_Tail`), so
    # "New York, Remote" counts as *one* part here, not two — the comma before
    # `Remote` does not keep it out of this branch. That is deliberate but
    # easy to misread: it is what makes "New York, Remote" resolve a city
    # while "New York, USA, Remote" does not (ADR 0008 Consequences).
    if tail.parts and not (
        tail.raw_part_count == 1 and tail.parts[-1].casefold() in _DECIDED_BARE_PLACES
    ):
        state = _lookup_subdivision(tail.parts[-1])
        if state is not None:
            tail.state = state
            tail.parts.pop()

    # 4. An annotation can carry the country or the subdivision. Only consulted
    #    where the segment itself said nothing, so an explicit value always
    #    wins over a parenthesised one.
    for annotation in tail.annotations:
        if tail.country is None:
            country = _COUNTRIES.get(annotation.casefold())
            if country is not None:
                tail.country = country
                continue
        if tail.state is None:
            state = _lookup_subdivision(annotation)
            if state is not None:
                tail.state = state

    # 5. A leftover bare two-letter code is an unrecognised subdivision, not a
    #    city. Drop it rather than promote it.
    if tail.parts and _BARE_SUBDIVISION_CODE.match(tail.parts[-1]):
        tail.dropped.append(tail.parts.pop())

    return tail


def parse_location_segment(segment: str, *, is_primary: bool) -> ParsedLocation:
    """Parse one already-split segment."""
    tail = _strip_tail_tokens(segment)
    # Corroboration comes from a resolved state/country, or from a second
    # (non-Remote) comma part having been named at all — even one that decoded
    # to nothing, like "KA" in "Bengaluru, KA". The corroborating part trails
    # the city there, not precedes it, so this is broader than "a preceding
    # comma part": any second geographic-shaped part is enough, resolved or not.
    #
    # TODO(M1): this still lets pure junk corroborate junk — "Global, XX" comes
    # out with city "Global". Not a new failure mode (the pre-fix parser did
    # the same, just naming the city "XX" instead) and not fixable without a
    # gazetteer of real city names, which is Task 5 / ADR-0008 territory.
    corroborated = tail.state is not None or tail.country is not None or tail.raw_part_count > 1

    city: str | None = None
    state = tail.state
    country = tail.country
    if tail.parts:
        # With a street address the city is the *last* unconsumed part:
        # "620 8th Ave, New York" -> "New York".
        candidate = tail.parts[-1]
        if corroborated or len(tail.parts) > 1:
            city = candidate
        else:
            # A bare token with nothing corroborating it is not a city. This is
            # what keeps "Global" and "Multiple Locations" out of the city
            # column. The one exception is an enumerated, reviewed list
            # (ADR 0008): NYC and its boroughs, which M1d's hot-tier
            # assignment depends on and which providers routinely write
            # without a state.
            decided = _DECIDED_BARE_PLACES.get(candidate.casefold())
            if decided is not None:
                city, state, country = (
                    decided[0],
                    state or decided[1],
                    country or decided[2],
                )

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
        state=state,
        country=country,
        confidence=confidence,
        is_primary=is_primary,
    )


def parse_location_list(segments: Sequence[str]) -> list[ParsedLocation]:
    """Parse an already-separated list of location strings.

    Lever's ``categories.allLocations`` and Ashby's ``secondaryLocations`` are
    JSON arrays. Joining them into a delimited string so that
    :func:`parse_location_field` can split them again would discard structure
    the provider handed us — and would break on any location containing the
    delimiter. Both entry points share every downstream rule.
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for chunk in segments:
        text = " ".join((chunk or "").split())
        if not text:
            continue
        # Collapse exact duplicates. A board that lists the same office twice
        # should not produce two rows that later look like two offices.
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)

    return [
        parse_location_segment(segment, is_primary=(index == 0))
        for index, segment in enumerate(cleaned)
    ]


def parse_location_field(raw: str | None) -> list[ParsedLocation]:
    """Parse a source's delimited location field into one location per place.

    Returns an empty list for empty input: a posting with no location text gets
    no location rows, rather than one row claiming to be somewhere.

    The first segment is marked primary, matching source order. Providers list
    the requisition's home office first; when they do not, the value is still a
    real location the posting names, so ordering affects sorting and never
    correctness.
    """
    return parse_location_list(_SEGMENT_SPLIT.split(raw or ""))


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
