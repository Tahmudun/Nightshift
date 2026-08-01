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


def _payload_fixtures() -> list[Path]:
    return sorted(
        path for path in FIXTURE_ROOT.rglob("*.json") if not path.name.endswith(".meta.json")
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


def test_the_three_lever_i3_fixtures_exist() -> None:
    """I3 needs 404, empty-200 and populated-200 as three separate recordings.

    Asserted by name rather than by count: a suite that only counts files
    passes when the empty-board recording is quietly dropped, which is the
    exact fixture that stops an outage from closing jobs.
    """
    lever = FIXTURE_ROOT / "lever"
    for name in ("alloy_board", "plaid_empty_board", "ramp_unknown_board"):
        assert (lever / f"{name}.json").exists(), f"missing lever fixture {name}"
