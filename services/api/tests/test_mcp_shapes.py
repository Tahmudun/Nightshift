"""What a tool result is allowed to say. Pure functions, no database.

These are I1 and I4's enforcement on the MCP surface, and they are unusual
tests because the thing being protected is a **reading** rather than a value.

Every earlier milestone had a renderer downstream: a React component shows what
it is given, and shipping `location_confidence` as a string was enough because
a designer decided what that string looks like. Here the consumer is a language
model that will paraphrase, summarise, and answer follow-up questions an hour
later. A field it cannot interpret is one it will interpret anyway.

So the assertions below are about structure — a coordinate never travels
without its qualifier, a sentence exists for every enum member, a score appears
in exactly one place — because structure is the part of a reading that can be
tested.
"""

from __future__ import annotations

from typing import Any

import pytest

from nightshift.db.base import LocationConfidence
from nightshift.mcp.shapes import CONFIDENCE_MEANS, job_summary, location_result


def test_every_location_confidence_has_a_sentence() -> None:
    """I1's enforcement, and the reason `shapes.py` may import `db.base` at all.

    `LocationConfidence`'s own docstring says *"There is no sixth value and no
    default of convenience."* If one ever arrives, this fails until somebody
    writes what it licenses a reader to claim — which is the only place that
    can be said, because the consumer is a model rather than a renderer.
    """
    assert set(CONFIDENCE_MEANS) == set(LocationConfidence)

    for value, sentence in CONFIDENCE_MEANS.items():
        assert sentence.strip(), f"{value} has an empty sentence"
        assert len(sentence) > 40, f"{value}'s sentence is too short to constrain a reading"


@pytest.mark.parametrize("confidence", list(LocationConfidence))
def test_a_location_never_travels_without_its_qualifier(confidence: LocationConfidence) -> None:
    """The structural half of I1, over every value rather than a chosen one."""
    result = location_result(text="New York, NY", confidence=confidence)

    assert result["confidence"] == confidence.value
    assert result["means"] == CONFIDENCE_MEANS[confidence]


@pytest.mark.parametrize(
    "confidence",
    [LocationConfidence.CITY_ONLY, LocationConfidence.REMOTE, LocationConfidence.UNKNOWN],
)
def test_an_unplaceable_location_withholds_coordinates_it_was_handed(
    confidence: LocationConfidence,
) -> None:
    """Belt and braces, and the braces are the point.

    The database should never hold a coordinate on a `city_only` row, and this
    is not the place to discover that it does. A latitude on a `city_only`
    result would be read as an address by exactly the consumer this module
    exists to protect against — so it is dropped here rather than trusted
    upstream.
    """
    result = location_result(
        text="New York, NY", confidence=confidence, latitude=40.75, longitude=-73.99
    )

    assert result["coordinates"] is None


def test_a_verified_location_keeps_its_coordinates() -> None:
    """The other direction, so the guard above is not just "always null"."""
    result = location_result(
        text="620 8th Avenue",
        confidence=LocationConfidence.VERIFIED,
        latitude=40.7561,
        longitude=-73.9903,
    )

    assert result["coordinates"] == {"latitude": 40.7561, "longitude": -73.9903}


def test_half_a_coordinate_is_not_a_location() -> None:
    """A latitude with no longitude is a bug upstream, not a place."""
    result = location_result(
        text="620 8th Avenue", confidence=LocationConfidence.VERIFIED, latitude=40.7561
    )

    assert result["coordinates"] is None


# --------------------------------------------------------------------------
# I4: a score appears in exactly one tool's output
# --------------------------------------------------------------------------


def _api_job(**overrides: Any) -> dict[str, Any]:
    """A `JobSummaryOut` as the API serialises it."""
    job: dict[str, Any] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "title": "Backend Engineer",
        "company": {"id": "22222222-2222-2222-2222-222222222222", "canonical_name": "Ramp"},
        "employment_type": "full_time",
        "remote_policy": "onsite",
        "status": "open",
        "locations": [
            {
                "id": "33333333-3333-3333-3333-333333333333",
                "raw_text": "New York, NY",
                "city": "New York",
                "state": "NY",
                "country": "US",
                "latitude": None,
                "longitude": None,
                "location_confidence": "city_only",
                "resolution_method": "none",
                "is_primary": True,
            }
        ],
        "salary": {"min": None, "max": None, "currency": None, "period": None},
        "source_published_at": None,
        "source_updated_at": None,
        "first_seen_at": "2026-08-01T00:00:00Z",
        "last_seen_at": "2026-08-20T00:00:00Z",
        "application_deadline": None,
    }
    job.update(overrides)
    return job


def _walk(value: Any, path: str = "") -> list[tuple[str, Any]]:
    """Every (path, value) pair in a nested structure.

    The shape tests below walk results rather than checking a known key, and
    that is deliberate: a tool added at M5d must trip the same guard without
    anybody remembering to extend a list of paths.
    """
    found: list[tuple[str, Any]] = [(path, value)]
    if isinstance(value, dict):
        for key, item in value.items():
            found += _walk(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += _walk(item, f"{path}[{index}]")
    return found


def test_a_search_result_carries_no_score() -> None:
    """I4: *"a bare number in the UI is a bug"*, and a tool result is a UI.

    A ranked list handing back `78` with nothing behind it is exactly what I4
    forbids. The honest version is a pointer to the tool that decomposes it,
    which `job_summary` includes so the model is told what to do instead of
    estimating one.
    """
    result = job_summary(_api_job())

    scored = [
        path
        for path, _ in _walk(result)
        if any(word in path.lower() for word in ("score", "fraction", "rating", "rank"))
    ]
    assert scored == [], f"a score reached a search result: {scored}"
    assert "explain_match" in result["explain_match_with"]


def test_a_search_result_carries_no_bare_coordinate() -> None:
    """Walked rather than checked at a known path, so a later tool trips it too."""
    result = job_summary(
        _api_job(
            locations=[
                {
                    "id": "44444444-4444-4444-4444-444444444444",
                    "raw_text": "620 8th Avenue",
                    "city": "New York",
                    "state": "NY",
                    "country": "US",
                    "latitude": 40.7561,
                    "longitude": -73.9903,
                    "location_confidence": "verified",
                    "resolution_method": "geosearch",
                    "is_primary": True,
                }
            ]
        )
    )

    for path, value in _walk(result):
        if isinstance(value, dict) and "coordinates" in value:
            assert "confidence" in value, f"{path} has coordinates and no confidence"
            assert "means" in value, f"{path} has coordinates and no explanation of them"


def test_a_city_only_job_reaches_the_model_saying_so() -> None:
    """The end-to-end shape of the thing this module exists for.

    31 of the seeded corpus's jobs are `city_only`. If this is wrong, the most
    common answer the product gives is the one that breaks I1.
    """
    result = job_summary(_api_job())
    location = result["locations"][0]

    assert location["coordinates"] is None
    assert "will not place it on a building" in location["means"]
