"""What `make tiles` does when an archive cannot be fetched.

There are two archives and they are not equally load-bearing. Without the
basemap there is no map at all, and `city.md` §5.2 spent an ADR on not shipping
that. Without the buildings archive there is a city with no skyline — which the
product already renders honestly, saying what is missing in the corner.

So a missing skyline must not cost a clean clone its `make setup`. That matters
most in exactly the window this test was written in: between baking an artifact
and publishing the release it is pinned to, every clone in the world gets a 404
for it, and `CLAUDE.md` §4 calls a broken `make demo` from a clean clone the
highest-priority task in the repo.

The failure this guards against is not hypothetical and not subtle in hindsight:
committing the manifest before creating the release did break `make setup`, and
nothing said so until someone read the exit path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load_fetcher() -> Any:
    """Import scripts/fetch_tiles.py, which is not a package module."""
    spec = importlib.util.spec_from_file_location(
        "fetch_tiles", ROOT / "scripts" / "fetch_tiles.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_tiles"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fetcher() -> Any:
    return _load_fetcher()


def _run(
    fetcher: Any, monkeypatch: pytest.MonkeyPatch, *, failing: set[str], argv: list[str]
) -> int:
    """Run `main()` with the named artifacts unfetchable. Returns the exit code."""
    attempted: list[str] = []

    def fake_ensure(artifact: str, **_: object) -> None:
        attempted.append(artifact)
        if artifact in failing:
            raise fetcher.Unavailable(f"{artifact} is not published")

    monkeypatch.setattr(fetcher, "ensure", fake_ensure)
    monkeypatch.setattr(sys, "argv", ["fetch_tiles.py", *argv])

    try:
        fetcher.main()
    except SystemExit as exit_:
        code = int(exit_.code or 0)
    else:
        code = 0

    # Whatever the outcome, every archive must have been tried. A loop that
    # stops at the first failure reports one problem per run, and the second one
    # is found only after the first is fixed.
    assert attempted == list(fetcher.ARTIFACTS)
    return code


def test_an_unpublished_skyline_does_not_fail_setup(
    fetcher: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _run(fetcher, monkeypatch, failing={"buildings"}, argv=[]) == 0


def test_a_missing_basemap_still_fails_setup(fetcher: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # The other half of the same rule. If this ever passes, "optional" has
    # quietly spread to the archive the product cannot render without.
    assert _run(fetcher, monkeypatch, failing={"basemap"}, argv=[]) == 1


def test_strict_refuses_an_unpublished_archive(
    fetcher: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # CI runs `--strict`, because the leniency above is for a developer's clone
    # and not for the check that is supposed to notice an unpublished pin.
    assert _run(fetcher, monkeypatch, failing={"buildings"}, argv=["--strict"]) == 1


def test_only_the_basemap_is_required(fetcher: Any) -> None:
    assert fetcher.REQUIRED == frozenset({"basemap"})
    assert set(fetcher.REQUIRED) < set(fetcher.ARTIFACTS)


def test_every_artifact_can_name_the_script_that_bakes_it(fetcher: Any) -> None:
    # The 404 message tells the reader how to produce the missing file. An
    # artifact added without an entry here would send them to a KeyError.
    assert set(fetcher.BAKE_SCRIPT) == set(fetcher.ARTIFACTS)
    for script in fetcher.BAKE_SCRIPT.values():
        assert (ROOT / script).exists(), script
