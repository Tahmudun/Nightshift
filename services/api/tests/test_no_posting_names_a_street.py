"""The census of `city.md` §4.1, pinned so it cannot go stale in silence.

M4a Task 1 measured that **no recorded ATS posting names a street**, and three
documents now cite that zero: `city.md` §4.1-4.4, `PROGRESS.md`, and Q7. It is
the reason a job can never place itself on a building, and therefore the reason
`data/company-locations.yaml` exists at all.

A number cited in three places and checked in none is how a list stops
describing the thing it names, which has happened five times in this project and
always in the same direction. So the claim is a test.

The pinned claim is deliberately *not* "247 postings". That number moves every
time a fixture is recorded, and pinning it would produce a test that fails for
reasons nobody cares about, which is a test people delete. What is pinned is the
shape:

1. The detector can see a real street address (a zero from a detector nobody
   proved can fire is not a measurement).
2. No recorded posting names one.

**If (2) starts failing, that is good news and not a regression.** It means an
employer began publishing a street address, and the right response is to read the
failure, look at what changed, and update `city.md` §4.1 — not to loosen the test.
The failure message says so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from census_location_text import collect, looks_like_street, self_check


def test_the_street_detector_can_see_a_street() -> None:
    """Without this, the zero below means the detector is broken, not that the
    data is coarse. Both readings look identical from the outside."""
    assert self_check() == []


def test_the_detector_does_not_read_a_state_code_as_a_thoroughfare() -> None:
    """The first draft reported four street addresses and all four were this
    bug: `ct.?` matching Connecticut, `fl.?` matching Florida. It would have
    fired on every posting in two states and inverted the census."""
    assert not looks_like_street("Stamford, CT")
    assert not looks_like_street("Miami, FL")
    assert looks_like_street("200 Park Ave, New York")


def test_the_corpus_is_not_empty() -> None:
    """A census over zero postings reports zero streets and proves nothing."""
    postings = collect()
    assert len(postings) > 200, (
        f"only {len(postings)} postings collected. The fixture layout probably "
        "moved and the census is now measuring almost nothing."
    )


def test_no_recorded_posting_names_a_street() -> None:
    """The claim `city.md` §4.4 is built on."""
    offenders = [
        (p.source, p.fixture, p.title, name, text)
        for p in collect()
        for name, text in p.texts
        if looks_like_street(text)
    ]
    assert offenders == [], (
        "A posting now names a street, which contradicts city.md §4.1 and is "
        "GOOD NEWS — an employer started publishing an address, so some jobs can "
        "reach `verified` on their own. Do not loosen this test. Read the "
        "offenders, confirm they are real addresses rather than a detector bug "
        f"(the first draft had one), and update city.md §4.1:\n{offenders}"
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "location.name",
        "offices[].location",
        "address.postalAddress",
        "categories.location",
    ],
)
def test_each_provider_still_carries_the_field_the_census_measured(field_name: str) -> None:
    """The zero would also be produced by a collector that stopped reading a
    provider's location field. This is the difference between 'measured nothing'
    and 'nothing to measure'."""
    seen = {name for p in collect() for name, _ in p.texts}
    assert field_name in seen, (
        f"{field_name} carried location text when the census ran and carries none "
        "now. The census is measuring less than it reports."
    )
