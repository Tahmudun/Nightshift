"""The committed gazetteer, and the rules that decided it (ADR 0040).

`test_locations.py` covers what the parser does with a lookup. These cover the
artifact — because ADR 0040's whole argument is that the judgement calls happen
at build time, so build time is where they have to be pinned.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nightshift.domain.gazetteer import gazetteer, load_from

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_city_gazetteer import (
    DOMINANCE_RATIO,
    POPULATION_FLOOR,
    _decide,
    _load,
    build,
)

ARTIFACT = Path(__file__).resolve().parents[3] / "data" / "city-gazetteer.tsv"


def _dump(rows: list[tuple[str, str, int]]) -> str:
    """A GeoNames-shaped dump: 19 tab-separated columns, only three of them ours."""
    lines = []
    for name, ascii_name, population in rows:
        cols = [""] * 19
        cols[0] = "1"
        cols[1] = name
        cols[2] = ascii_name
        cols[4] = "51.5"  # latitude, present precisely so we can prove it is dropped
        cols[5] = "-0.12"  # longitude, likewise
        cols[14] = str(population)
        lines.append("\t".join(cols))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# The artifact as shipped
# --------------------------------------------------------------------------


def test_artifact_carries_no_coordinates() -> None:
    """I1, enforced by the shape of the file (ADR 0040).

    The dump has latitude and longitude. If a future regeneration starts
    carrying them, a `city_only` resolution acquires a position it has no right
    to and the check constraint on `job_locations` is the only thing left
    standing between that and a beacon. Three columns, always.
    """
    for line in ARTIFACT.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line:
            continue
        assert len(line.split("\t")) == 3, f"unexpected column count: {line!r}"


def test_artifact_resolves_the_names_the_corpus_actually_contains() -> None:
    """The 1200-job corpus's bare city names, minus the ones the rules refuse."""
    g = gazetteer()
    for name in [
        "London",
        "San Francisco",
        "Austin",
        "Miami",
        "Atlanta",
        "Chicago",
        "Madrid",
        "Buenos Aires",
        "Los Angeles",
        "Toronto",
        "Dallas",
        "Shenzhen",
        "Belfast",
        "Milton Keynes",
    ]:
        assert g.lookup(name) == name, f"{name} should resolve"


@pytest.mark.parametrize("name", ["Barcelona", "Springfield", "Cambridge"])
def test_artifact_refuses_contested_names(name: str) -> None:
    """Refuse on ambiguity, never pick the biggest.

    Barcelona is in today's corpus (9 rows) and is refused anyway: Spain is only
    2.1x Venezuela. Lowering the ratio to recover it is the change this test
    exists to make visible.
    """
    g = gazetteer()
    assert g.lookup(name) is None
    assert g.refused(name), f"{name} should ship as an auditable refusal"


@pytest.mark.parametrize("token", ["Global", "Multiple Locations", "Remote", "Anywhere"])
def test_artifact_contains_no_non_places(token: str) -> None:
    """The strings the parser's corroboration rule exists to keep out."""
    g = gazetteer()
    assert g.lookup(token) is None
    assert not g.refused(token)


def test_refusals_ship_rather_than_being_dropped() -> None:
    """A refusal a reader cannot count is a silence (ADR 0040)."""
    g = gazetteer()
    assert len(g.ambiguous) > 0
    assert g.ambiguous.isdisjoint(g.resolved)


# --------------------------------------------------------------------------
# The build rules
# --------------------------------------------------------------------------


def test_population_floor_drops_the_long_tail() -> None:
    """Where ordinary English words turn out to be towns."""
    loaded = _load_dump([("Springfield", "Springfield", POPULATION_FLOOR + 1)])
    assert "springfield" in loaded
    loaded = _load_dump([("Best", "Best", POPULATION_FLOOR - 1)])
    assert loaded == {}


def test_dominance_ratio_resolves_a_landslide_and_refuses_a_contest() -> None:
    landslide = [(100_000 * DOMINANCE_RATIO, "Big"), (100_000, "Small")]
    assert _decide(landslide) == "Big"

    contest = [(100_000 * DOMINANCE_RATIO - 1, "Big"), (100_000, "Small")]
    assert _decide(contest) is None


def test_a_tie_is_deterministic_rather_than_file_ordered() -> None:
    """Same populations, opposite input order, same verdict."""
    assert _decide([(500_000, "Aaa"), (500_000, "Bbb")]) is None
    assert _decide([(500_000, "Bbb"), (500_000, "Aaa")]) is None


def test_ascii_and_native_spellings_are_the_same_city_not_two_rivals() -> None:
    """Otherwise Córdoba would refuse Cordoba as ambiguous with itself."""
    loaded = _load_dump([("Córdoba", "Cordoba", 2_000_000)])
    assert _decide(loaded["córdoba"]) == "Córdoba"
    assert _decide(loaded["cordoba"]) == "Córdoba"


def test_build_is_deterministic(tmp_path: Path) -> None:
    """Same dump in, byte-identical file out — the property that makes a
    regeneration reviewable in a diff."""
    dump = tmp_path / "dump.txt"
    dump.write_text(
        _dump(
            [
                ("London", "London", 8_900_000),
                ("Springfield", "Springfield", 170_000),
                ("Springfield", "Springfield", 154_000),
            ]
        ),
        encoding="utf-8",
    )
    assert build(dump) == build(dump)


def test_build_output_round_trips_through_the_loader(tmp_path: Path) -> None:
    dump = tmp_path / "dump.txt"
    dump.write_text(
        _dump(
            [
                ("London", "London", 8_900_000),
                ("Springfield", "Springfield", 170_000),
                ("Springfield", "Springfield", 154_000),
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "gaz.tsv"
    out.write_text(build(dump), encoding="utf-8")

    g = load_from(out)
    assert g.lookup("london") == "London"
    assert g.lookup("springfield") is None
    assert g.refused("springfield")


def test_loader_rejects_a_malformed_row(tmp_path: Path) -> None:
    """A truncated artifact must not silently become a smaller gazetteer."""
    bad = tmp_path / "bad.tsv"
    bad.write_text("# header\nlondon\tresolved\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        load_from(bad)


def test_loader_rejects_an_unknown_status(tmp_path: Path) -> None:
    bad = tmp_path / "bad.tsv"
    bad.write_text("# header\nlondon\tmaybe\tLondon\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown gazetteer status"):
        load_from(bad)


def _load_dump(rows: list[tuple[str, str, int]]) -> dict[str, list[tuple[int, str]]]:
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
        fh.write(_dump(rows))
        path = Path(fh.name)
    try:
        return _load(path)
    finally:
        path.unlink()
