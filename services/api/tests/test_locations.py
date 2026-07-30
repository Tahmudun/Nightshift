"""Location parser tests, driven entirely by ``tests/fixtures/locations.yaml``.

Adding a case means editing the fixture file, not this module. That keeps the
fixture the artifact under review — a reviewer reads real location strings and
their expected classification, not assertion plumbing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from citysignal.db.base import LocationConfidence, ResolutionMethod
from citysignal.domain.locations import (
    ParsedLocation,
    infer_remote_policy,
    parse_location_field,
)

FIXTURE = Path(__file__).parent / "fixtures" / "locations.yaml"


def _load_cases() -> list[dict[str, Any]]:
    data = yaml.safe_load(FIXTURE.read_text())
    cases = data["cases"]
    assert cases, "fixture file is empty — a test that cannot fail is not a test"
    return list(cases)


CASES = _load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_parses_fixture_case(case: dict[str, Any]) -> None:
    parsed = parse_location_field(case["raw"])
    expected = case["expect"]

    assert len(parsed) == len(expected), (
        f"{case['name']}: expected {len(expected)} location(s), got {len(parsed)} "
        f"({[p.raw_text for p in parsed]})"
    )

    for actual, want in zip(parsed, expected, strict=True):
        assert actual.raw_text == want["raw_text"], case["name"]
        assert actual.city == want["city"], f"{case['name']}: city"
        assert actual.state == want["state"], f"{case['name']}: state"
        assert actual.country == want["country"], f"{case['name']}: country"
        assert actual.confidence == LocationConfidence(want["confidence"]), (
            f"{case['name']}: confidence"
        )
        assert actual.is_primary == want["is_primary"], f"{case['name']}: is_primary"


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_never_produces_coordinates(case: dict[str, Any]) -> None:
    """Invariant I1, M0 form: the parser has no path to a coordinate.

    Asserted structurally rather than by value — if someone adds latitude to
    :class:`ParsedLocation` to make a map feature easier, this fails.
    """
    for parsed in parse_location_field(case["raw"]):
        assert not hasattr(parsed, "latitude")
        assert not hasattr(parsed, "longitude")
        assert parsed.resolution_method is ResolutionMethod.SOURCE_TEXT_PARSE


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_raw_text_is_a_substring_of_the_input(case: dict[str, Any]) -> None:
    """Every row must be traceable to the exact text the source sent (A2).

    Whitespace inside a segment is normalised, so compare on a whitespace-free
    projection rather than requiring a literal substring.
    """
    haystack = "".join(case["raw"].split())
    for parsed in parse_location_field(case["raw"]):
        assert "".join(parsed.raw_text.split()) in haystack


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_exactly_one_primary_when_any_location_parses(case: dict[str, Any]) -> None:
    parsed = parse_location_field(case["raw"])
    primaries = [p for p in parsed if p.is_primary]
    assert len(primaries) == (1 if parsed else 0)


def test_parse_is_deterministic() -> None:
    """M1 requires byte-identical normalized output across runs; start as we mean to go on."""
    raw = "Boston, Massachusetts, USA; New York, New York, USA; Texas, USA, Remote"
    first = parse_location_field(raw)
    second = parse_location_field(raw)
    assert first == second


def test_none_and_empty_yield_no_locations() -> None:
    assert parse_location_field(None) == []
    assert parse_location_field("") == []


def test_unrecognised_country_is_unknown_not_guessed() -> None:
    """The failure mode I1 asks for: refuse, do not approximate."""
    (parsed,) = parse_location_field("Wakanda")
    assert parsed.city is None
    assert parsed.country is None
    assert parsed.confidence is LocationConfidence.UNKNOWN


def test_country_only_does_not_round_up_to_city_only() -> None:
    """ "Germany" resolves a country and no city; `city_only` would overstate it."""
    (parsed,) = parse_location_field("Germany")
    assert parsed.country == "Germany"
    assert parsed.city is None
    assert parsed.confidence is LocationConfidence.UNKNOWN


def test_nyc_detection_covers_boroughs_and_rejects_lookalikes() -> None:
    def city_of(raw: str) -> ParsedLocation:
        return parse_location_field(raw)[0]

    assert city_of("Brooklyn, New York, USA").is_nyc
    assert city_of("New York, New York, USA").is_nyc
    assert city_of("Staten Island, New York, USA").is_nyc
    # Real trap: an upstate city in the same state is not New York City.
    assert not city_of("Rochester, New York, USA").is_nyc
    # A statewide-remote row names no city, so it is not NYC.
    assert not city_of("New York, USA, Remote").is_nyc


class TestRemotePolicy:
    def test_office_and_remote_states_is_hybrid(self) -> None:
        locations = parse_location_field("New York, New York, USA; Texas, USA, Remote")
        assert infer_remote_policy(locations) == "hybrid"

    def test_only_remote_is_remote(self) -> None:
        locations = parse_location_field("Texas, USA, Remote; Germany, Remote")
        assert infer_remote_policy(locations) == "remote"

    def test_only_offices_is_on_site(self) -> None:
        locations = parse_location_field("Boston, Massachusetts, USA")
        assert infer_remote_policy(locations) == "on_site"

    def test_no_signal_is_unknown_not_on_site(self) -> None:
        assert infer_remote_policy([]) == "unknown"
        assert infer_remote_policy(parse_location_field("Multiple Locations")) == "unknown"
