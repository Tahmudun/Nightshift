"""Turning API responses into tool results that carry their own qualifiers.

Pure. No I/O, no network, no clock, no database — the one import from
`nightshift.db` is `base`, which holds enums and no engine, so
:data:`CONFIDENCE_MEANS` can be proven exhaustive over `LocationConfidence`.
`tests/test_mcp_boundaries.py` permits exactly that and bans the rest.

**This module is where invariants I1 and I4 are enforced, and the enforcement
is prose.** That reads like a contradiction and is not. Every earlier milestone
had a renderer on the other end: a React component shows what it is given, and
`location_confidence` reaching it as a string is enough, because a designer
decided what that string looks like. Here the other end is a language model
that will paraphrase, summarise and answer follow-up questions hours later. A
field it cannot interpret is a field it will interpret *anyway*.

So every location carries a sentence saying what it licenses a reader to claim,
attached to the row rather than filed in a schema description, because a rule
stated once at the top of a long conversation is a rule that conversation
drifts away from.
"""

from __future__ import annotations

from typing import Any

from nightshift.db.base import LocationConfidence

#: One plain sentence per confidence value, travelling **with** the value.
#:
#: Asserted exhaustive over the enum in `tests/test_mcp_shapes.py`, so a sixth
#: member cannot ship without one. That test is the whole of I1's enforcement
#: on this surface: `LocationConfidence` docstring says "there is no sixth value
#: and no default of convenience", and if one ever arrives it must arrive with
#: an explanation rather than inheriting some neighbour's.
#:
#: They are written for a reader who will paraphrase them, which is why each one
#: says what is **not** known as well as what is.
CONFIDENCE_MEANS: dict[LocationConfidence, str] = {
    LocationConfidence.VERIFIED: (
        "A person confirmed this street address and it geocoded to a specific "
        "building. This is the only value that licenses naming a street address."
    ),
    LocationConfidence.APPROXIMATE: (
        "The coordinates come from a geocoder and land near, but not certainly "
        "on, the right building. Name the neighbourhood if you like; do not name "
        "a street address or a building."
    ),
    LocationConfidence.CITY_ONLY: (
        "The posting names a city and nothing finer. Nightshift does not know "
        "where in the city this role sits and will not place it on a building. "
        "Saying more than the city invents a fact about a real company."
    ),
    LocationConfidence.REMOTE: (
        "The posting says the role is remote. There is no office to name, and a "
        "coordinate would be a fiction rather than a rounding."
    ),
    LocationConfidence.UNKNOWN: (
        "Nightshift could not resolve this location honestly, or has not tried. "
        "This is an admission of ignorance, not a hint — do not guess from the "
        "company name, the posting text, or anything else."
    ),
}


def location_result(
    *,
    text: str | None,
    confidence: LocationConfidence | str,
    latitude: float | None = None,
    longitude: float | None = None,
    city: str | None = None,
    is_primary: bool | None = None,
) -> dict[str, Any]:
    """One location, with its qualifier attached rather than implied.

    ``coordinates`` is ``null`` unless there are both a latitude and a
    longitude. Half a coordinate is not a location, and the guard is here
    rather than at each caller because there are three callers and there will
    be more.

    **The coordinates are also withheld for `city_only`, `remote` and
    `unknown`, even if the row somehow carries them.** The database should
    never hold that combination and this is not the place to find out it does:
    a coordinate on a `city_only` row would be read as an address by exactly
    the consumer this module exists to protect against.
    """
    value = LocationConfidence(confidence)
    placeable = value in (LocationConfidence.VERIFIED, LocationConfidence.APPROXIMATE)
    has_pair = latitude is not None and longitude is not None

    result: dict[str, Any] = {
        "text": text,
        "city": city,
        "confidence": value.value,
        "means": CONFIDENCE_MEANS[value],
        "coordinates": (
            {"latitude": latitude, "longitude": longitude} if placeable and has_pair else None
        ),
    }
    if is_primary is not None:
        result["is_primary"] = is_primary
    return result


def job_summary(job: dict[str, Any]) -> dict[str, Any]:
    """A job as a search result. Locations qualified; **no score**.

    A score appears in exactly one tool's output — `explain_match` — and I4 is
    why: *"a bare number in the UI is a bug"*, and a tool result is a UI. A
    ranked list carrying `78` with nothing behind it is the thing I4 forbids,
    and the honest version is a pointer to the tool that decomposes it.
    """
    return {
        "id": job["id"],
        "title": job["title"],
        "company": job["company"]["name"],
        "employment_type": job["employment_type"],
        "remote_policy": job["remote_policy"],
        "status": job["status"],
        "locations": [_location_from_api(row) for row in job.get("locations", [])],
        "first_seen_at": job["first_seen_at"],
        "source_published_at": job.get("source_published_at"),
        "explain_match_with": (
            "Call explain_match with this job's id for its score and the evidence "
            "behind it. Do not estimate a score yourself."
        ),
    }


def _location_from_api(row: dict[str, Any]) -> dict[str, Any]:
    """`JobLocationOut` → a qualified location."""
    return location_result(
        text=row.get("raw_text"),
        confidence=row["location_confidence"],
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
        city=row.get("city"),
        is_primary=row.get("is_primary"),
    )
