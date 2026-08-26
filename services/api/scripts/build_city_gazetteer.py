"""Build the committed city gazetteer from a GeoNames dump.

ADR 0040. `parse_location_segment` refuses to promote an uncorroborated bare
token to a city, which is what keeps `Global` and `Multiple Locations` out of
the city column. ADR 0008 carved out one exception — an enumerated, reviewed
list — and ruled that widening it to the world needs "a real gazetteer, a
provenance field on the resolution, and its own ADR", not a longer list.

This is the gazetteer half. It turns a 34,000-row GeoNames dump into a
**decided list**: every judgement call is made here, at build time, and what
ships is the answer rather than the rule. That is what preserves ADR 0008's
central property — a reader can see the entire list and grep it — at a scale
no human would enumerate by hand.

Three rules, and each one is a refusal:

  FLOOR    A city under the population floor is dropped. Not because small
           cities do not exist, but because the long tail is where ordinary
           English words turn out to be place names (`Best`, `Central`,
           `Liberty`, `University` are all real towns under 50,000) and a
           location field is full of ordinary English words.

  RATIO    A name borne by more than one surviving city resolves only if the
           largest is RATIO times the runner-up. `London` (21x) resolves.
           `Barcelona` (2.1x) does not, and neither do `Springfield`,
           `Cambridge` or `York` at their own floors. The rule is *refuse on
           ambiguity*, never *pick the biggest*.

  no coords  The output carries names and nothing else. The dump has latitude
           and longitude in columns 4 and 5; they are read and discarded. A
           gazetteer that ships no coordinates cannot fabricate a position,
           which is I1 enforced by the shape of the file rather than by
           anyone's care.

Deterministic: same dump in, byte-identical file out.

Run:
    cd services/api
    curl -sSLO https://download.geonames.org/export/dump/cities15000.zip
    unzip -o cities15000.zip
    ./.venv/bin/python scripts/build_city_gazetteer.py cities15000.txt
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

POPULATION_FLOOR = 50_000
DOMINANCE_RATIO = 10

# GeoNames "geoname" table columns used here. The dump has 19; the three
# unlisted ones this file cares about not having are 4 (latitude), 5
# (longitude) and 16 (elevation).
_COL_NAME = 1
_COL_ASCIINAME = 2
_COL_POPULATION = 14
_MIN_COLUMNS = 15

REPO_DATA = Path(__file__).resolve().parents[3] / "data"
OUTPUT = REPO_DATA / "city-gazetteer.tsv"


def _load(dump: Path) -> dict[str, list[tuple[int, str]]]:
    """Group every surviving city by each spelling it answers to.

    A city contributes both its `name` and its `asciiname`, so `Córdoba` and
    `Cordoba` are the same city rather than two rivals that would then refuse
    each other as ambiguous.
    """
    by_name: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for line in dump.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) < _MIN_COLUMNS:
            continue
        population = int(fields[_COL_POPULATION] or 0)
        if population < POPULATION_FLOOR:
            continue
        display = fields[_COL_NAME]
        for spelling in {fields[_COL_NAME], fields[_COL_ASCIINAME]}:
            if spelling:
                by_name[spelling.casefold()].append((population, display))
    return by_name


def _decide(candidates: list[tuple[int, str]]) -> str | None:
    """The display name this spelling resolves to, or None if contested.

    Sorted descending by population, then by name so a population tie is still
    deterministic rather than dependent on file order.
    """
    ranked = sorted(candidates, key=lambda c: (-c[0], c[1]))
    if len(ranked) == 1:
        return ranked[0][1]
    largest, runner_up = ranked[0][0], ranked[1][0]
    if runner_up and largest >= DOMINANCE_RATIO * runner_up:
        return ranked[0][1]
    return None


def build(dump: Path) -> str:
    by_name = _load(dump)
    resolved: dict[str, str] = {}
    ambiguous: list[str] = []
    for key, candidates in by_name.items():
        display = _decide(candidates)
        if display is None:
            ambiguous.append(key)
        else:
            resolved[key] = display

    digest = hashlib.sha256(dump.read_bytes()).hexdigest()
    lines = [
        "# Nightshift city gazetteer — ADR 0040. Generated; do not hand-edit.",
        "# Regenerate: services/api/scripts/build_city_gazetteer.py",
        "#",
        "# Source:  GeoNames cities15000 (https://download.geonames.org/export/dump/)",
        "# Licence: CC BY 4.0. Attribution is required and is carried on the",
        "#          coverage page as well as here.",
        f"# Digest:  sha256:{digest}",
        "#",
        f"# population_floor={POPULATION_FLOOR} dominance_ratio={DOMINANCE_RATIO}",
        f"# resolved={len(resolved)} ambiguous={len(ambiguous)}",
        "#",
        "# Columns: name_key <TAB> status <TAB> display_name",
        "#   resolved  — a bare token equal to name_key resolves to display_name",
        "#               at city_only confidence, with no coordinate, ever.",
        "#   ambiguous — borne by cities too close in size to choose between.",
        "#               Listed rather than omitted so a refusal is auditable",
        "#               and the coverage page can count it.",
        "#",
        "# No latitude, no longitude, by construction (I1).",
    ]
    for key in sorted(resolved):
        lines.append(f"{key}\tresolved\t{resolved[key]}")
    for key in sorted(ambiguous):
        lines.append(f"{key}\tambiguous\t")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path, help="path to cities15000.txt")
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    if not args.dump.exists():
        print(f"no such dump: {args.dump}", file=sys.stderr)
        return 1

    content = build(args.dump)
    args.out.write_text(content, encoding="utf-8")
    body = [ln for ln in content.splitlines() if not ln.startswith("#")]
    resolved = sum(1 for ln in body if "\tresolved\t" in ln)
    print(f"wrote {args.out} — {resolved} resolved, {len(body) - resolved} ambiguous")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
