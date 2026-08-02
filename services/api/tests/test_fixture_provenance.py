"""Every committed fixture must say where it came from.

I7's failure mode is a mock wearing a fixture's name. A fixture with no
provenance file cannot be distinguished from one somebody typed, so the
absence of the meta file is itself the bug this asserts against.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures"
REQUIRED_PROVENANCE_KEYS = {"endpoint", "recorded_at", "board_token"}

#: Every extension a recorded response can arrive in. Extended at M1c: board
#: discovery records a crawl index as `.jsonl` and an Ashby board page as
#: `.html`, and a glob that only saw `.json` would have exempted precisely the
#: newest recordings — the ones least likely to have been checked by hand.
RECORDED_SUFFIXES = (".json", ".jsonl", ".html")


def _payload_fixtures() -> list[Path]:
    return sorted(
        path
        for suffix in RECORDED_SUFFIXES
        for path in FIXTURE_ROOT.rglob(f"*{suffix}")
        if not path.name.endswith(".meta.json")
    )


@pytest.mark.parametrize("fixture", _payload_fixtures(), ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_every_fixture_has_provenance(fixture: Path) -> None:
    meta = fixture.with_suffix(".meta.json")
    assert meta.exists(), f"{fixture.name} has no .meta.json — provenance is not optional"
    data = json.loads(meta.read_text())
    provenance = data["provenance"]
    missing = REQUIRED_PROVENANCE_KEYS - provenance.keys()
    assert not missing, f"{meta.name} provenance missing {sorted(missing)}"
    assert provenance["endpoint"].startswith("https://"), meta.name


def test_the_discovery_name_fixtures_exist() -> None:
    """The approval gate (ADR 0005) rests on two recordings, named rather than
    counted: a page that names an employer and a page that does not.

    Losing either would leave the gate's tests passing against whatever
    remained, which is how a control goes hollow without anything going red.
    """
    discovery = FIXTURE_ROOT / "discovery"
    for name in ("ashby_0g_page.html", "ashby_unnameable_page.html"):
        assert (discovery / name).exists(), f"missing discovery fixture {name}"

    named = (discovery / "ashby_0g_page.html").read_text()
    unnamed = (discovery / "ashby_unnameable_page.html").read_text()
    assert "0g Labs" in named, "the fixture no longer carries the name it exists to carry"
    assert "0g Labs" not in unnamed


def test_the_three_lever_i3_fixtures_exist() -> None:
    """I3 needs 404, empty-200 and populated-200 as three separate recordings.

    Asserted by name rather than by count: a suite that only counts files
    passes when the empty-board recording is quietly dropped, which is the
    exact fixture that stops an outage from closing jobs.
    """
    lever = FIXTURE_ROOT / "lever"
    for name in ("alloy_board", "plaid_empty_board", "ramp_unknown_board"):
        assert (lever / f"{name}.json").exists(), f"missing lever fixture {name}"
