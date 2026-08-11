"""Count what the recorded payloads actually say about where a job is.

`docs/architecture/city.md` §4.1: the first task of M4 is a measurement, not a
geocoder. The renderer's shape depends on an unmeasured number — of the location
text this product already has, how much could ever reach a street, and how much
tops out at a city name?

This walks every committed fixture payload, pulls **every** field that could
carry location text (not only the one the adapters normalise), and buckets each
posting by the best precision anything in it could support:

    street_address  something names a street → could reach `verified`
    place_name      a city is named and nothing finer → `city_only` at best
    remote_only     remote is asserted and no place is named
    nothing         no usable location text at all

It is deliberately generous. Any street-looking token in any field counts, and
the parser's own verdict is reported beside the raw text so a disagreement is
visible rather than averaged away. If the generous count is still low, the
answer is not "look harder".

Run: `cd services/api && ./.venv/bin/python scripts/census_location_text.py`
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nightshift.domain.locations import parse_location_field

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"

# Thoroughfare words split by how much they can be trusted alone.
#
# The abbreviations collide with US state codes, and the collision is not
# theoretical: the first draft of this script reported four street addresses,
# and all four were `ct\.?` matching Connecticut in "Stamford, CT" and `fl\.?`
# matching Florida in "Miami, FL". A detector that fires on every posting in
# two states would have made the census say the opposite of what it says.
#
# So an abbreviation counts only behind a house number, where "200 Park Ave"
# is unambiguous and "Miami, FL" cannot reach.
_UNAMBIGUOUS = (
    r"street|avenue|boulevard|broadway|bowery|parkway|turnpike|highway|"
    r"plaza|terrace|drive|lane"
)
_ABBREVIATED = r"st|ave|blvd|rd|dr|ln|ct|fl|ste|pkwy|pl|ter|sq|hwy"

# "620 Eighth Avenue", "200 Park Ave", "1 World Trade Center, 285 Fulton St"
_NUMBERED = re.compile(
    rf"\b\d{{1,5}}[a-z]?\b(?:\s+[\w.'-]+){{0,3}}\s+({_UNAMBIGUOUS}|{_ABBREVIATED})\b",
    re.IGNORECASE,
)
# A spelled-out thoroughfare needs no number: "Broadway", "Park Avenue".
_NAMED = re.compile(rf"\b({_UNAMBIGUOUS})\b", re.IGNORECASE)


def looks_like_street(text: str) -> bool:
    """True when the text names a thoroughfare — the only thing that can geocode
    to `verified`. "New York, NY" is false; "620 Eighth Avenue, New York" is true."""
    if not text:
        return False
    return bool(_NUMBERED.search(text) or _NAMED.search(text))


# A zero from a detector nobody proved can fire is not a measurement. These run
# on every invocation and the census refuses to print if any of them is wrong.
_MUST_FIRE = (
    "620 Eighth Avenue, New York, NY 10018",
    "200 Park Ave, New York",
    "1 Bowery, New York, NY",
    "Broadway, Manhattan",
    "85 Broad Street",
)
_MUST_NOT_FIRE = (
    "Miami, FL",
    "Stamford, CT",
    "New York, NY",
    "New York City",
    "Remote (US)",
    "San Francisco, California, United States",
    "Bengaluru, KA",
)


def self_check() -> list[str]:
    """Return the cases the detector gets wrong. Empty means it can see a street."""
    wrong = [f"should fire:     {t!r}" for t in _MUST_FIRE if not looks_like_street(t)]
    wrong += [f"should not fire: {t!r}" for t in _MUST_NOT_FIRE if looks_like_street(t)]
    return wrong


_REMOTE = re.compile(r"\bremote\b|\bdistributed\b|\banywhere\b", re.IGNORECASE)


@dataclass
class Posting:
    """One posting's location material, from every field that carries any."""

    source: str
    fixture: str
    title: str
    texts: list[tuple[str, str]] = field(default_factory=list)  # (field name, text)
    remote_flag: bool = False

    @property
    def all_text(self) -> str:
        return " | ".join(text for _, text in self.texts)

    @property
    def bucket(self) -> str:
        if any(looks_like_street(text) for _, text in self.texts):
            return "street_address"
        parsed = [p for _, text in self.texts for p in parse_location_field(text)]
        if any(p.city for p in parsed):
            return "place_name"
        if self.remote_flag or _REMOTE.search(self.all_text):
            return "remote_only"
        return "nothing"

    @property
    def is_nyc(self) -> bool:
        return any(p.is_nyc for _, text in self.texts for p in parse_location_field(text))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _greenhouse(payload: dict[str, Any], fixture: str) -> list[Posting]:
    postings = []
    for job in payload.get("jobs", []):
        p = Posting("greenhouse", fixture, _text(job.get("title")))
        if name := _text((job.get("location") or {}).get("name")):
            p.texts.append(("location.name", name))
        for office in job.get("offices") or []:
            if loc := _text(office.get("location")):
                p.texts.append(("offices[].location", loc))
            if name := _text(office.get("name")):
                p.texts.append(("offices[].name", name))
        postings.append(p)
    return postings


def _lever(payload: list[dict[str, Any]], fixture: str) -> list[Posting]:
    postings = []
    for job in payload:
        p = Posting("lever", fixture, _text(job.get("text")))
        categories = job.get("categories") or {}
        if loc := _text(categories.get("location")):
            p.texts.append(("categories.location", loc))
        for loc in categories.get("allLocations") or []:
            if text := _text(loc):
                p.texts.append(("categories.allLocations[]", text))
        if country := _text(job.get("country")):
            p.texts.append(("country", country))
        p.remote_flag = _text(job.get("workplaceType")).lower() == "remote"
        postings.append(p)
    return postings


def _postal(address: Any) -> str:
    """Flatten an Ashby postalAddress. Reports every key it actually carries."""
    postal = (address or {}).get("postalAddress") or {}
    parts = [
        _text(postal.get(key))
        for key in ("streetAddress", "addressLocality", "addressRegion", "addressCountry")
    ]
    return ", ".join(part for part in parts if part)


def _ashby(payload: dict[str, Any], fixture: str) -> list[Posting]:
    postings = []
    for job in payload.get("jobs", []):
        p = Posting("ashby", fixture, _text(job.get("title")))
        if loc := _text(job.get("location")):
            p.texts.append(("location", loc))
        if postal := _postal(job.get("address")):
            p.texts.append(("address.postalAddress", postal))
        for secondary in job.get("secondaryLocations") or []:
            if loc := _text(secondary.get("location")):
                p.texts.append(("secondaryLocations[].location", loc))
            if postal := _postal(secondary.get("address")):
                p.texts.append(("secondaryLocations[].address", postal))
        p.remote_flag = bool(job.get("isRemote"))
        postings.append(p)
    return postings


def collect() -> list[Posting]:
    postings: list[Posting] = []
    for path in sorted(FIXTURES.rglob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        name = f"{path.parent.name}/{path.name}"
        if isinstance(payload, dict) and "jobs" in payload:
            # Greenhouse and Ashby both key on "jobs"; Ashby carries apiVersion.
            if "apiVersion" in payload:
                postings.extend(_ashby(payload, name))
            else:
                postings.extend(_greenhouse(payload, name))
        elif isinstance(payload, list) and payload and isinstance(payload[0], dict):
            if "categories" in payload[0]:
                postings.extend(_lever(payload, name))
    return postings


def main() -> None:
    if wrong := self_check():
        print("The street detector is broken. Refusing to report a count:")
        for case in wrong:
            print(f"  {case}")
        raise SystemExit(1)

    postings = collect()
    if not postings:
        print("No postings found. Did the fixture layout change?")
        return

    print(f"{len(postings)} postings across {len({p.fixture for p in postings})} fixtures\n")

    print("=== best precision anything in the payload could support ===")
    buckets = Counter(p.bucket for p in postings)
    for bucket in ("street_address", "place_name", "remote_only", "nothing"):
        count = buckets[bucket]
        print(f"  {bucket:<16} {count:>4}  {count / len(postings):>6.1%}")

    print("\n=== by source ===")
    for source in sorted({p.source for p in postings}):
        subset = [p for p in postings if p.source == source]
        by_bucket = Counter(p.bucket for p in subset)
        summary = "  ".join(f"{b}={by_bucket[b]}" for b in sorted(by_bucket))
        print(f"  {source:<12} {len(subset):>4}  {summary}")

    print("\n=== NYC postings, which are the only ones the city renders ===")
    nyc = [p for p in postings if p.is_nyc]
    print(f"  {len(nyc)} of {len(postings)} ({len(nyc) / len(postings):.1%})")
    nyc_buckets = Counter(p.bucket for p in nyc)
    for bucket in ("street_address", "place_name", "remote_only", "nothing"):
        count = nyc_buckets[bucket]
        share = count / len(nyc) if nyc else 0
        print(f"  {bucket:<16} {count:>4}  {share:>6.1%}")

    print("\n=== every field that carries location text, and whether it ever names a street ===")
    fields: Counter[str] = Counter()
    streets: Counter[str] = Counter()
    for p in postings:
        for name, text in p.texts:
            fields[name] += 1
            if looks_like_street(text):
                streets[name] += 1
    print(f"  {'field':<34} {'postings':>8} {'with a street':>14}")
    for name, count in fields.most_common():
        print(f"  {name:<34} {count:>8} {streets[name]:>14}")

    print("\n=== the distinct location strings, most common first ===")
    distinct = Counter(text for p in postings for _, text in p.texts)
    for text, count in distinct.most_common(25):
        print(f"  {count:>4}  {text}")
    print(f"  ({len(distinct)} distinct strings in total)")


if __name__ == "__main__":
    main()
