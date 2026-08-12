#!/usr/bin/env python3
"""Cut New York's own building footprints into extrusion tiles, once, by hand.

A maintainer script, like `bake_basemap.py`, and for the same reasons: it needs
a tool nobody else should have to install, it takes minutes, and its output is
published as a release asset that `make setup` downloads and verifies. ADR 0022
covers the shape; this is the second artifact to use it.

**Why New York's data and not the basemap's own buildings.** The Protomaps
archive carries an OpenStreetMap `buildings` layer with a `height` attribute,
and that height is mostly a guess — OSM records a real height for a small
fraction of buildings and estimates the rest from storey counts or leaves them
out. NYC Open Data publishes `height_roof` for all 1,083,024 structures in the
city, photogrammetrically measured. `city.md` §5.3 chose the measured one, and
the check that it is really measured is easy to state: One World Trade Center
reads 1408.4 ft, which is its roof rather than the 1,776 ft that includes the
spire. A dataset that rounded or guessed would not know the difference.

**Heights are in feet and stay in feet here.** The conversion to metres happens
in the map style, as an expression, so the tiles carry the source's own numbers
and nothing in this pipeline can quietly apply the factor twice.

    python scripts/bake_buildings.py

Needs `tippecanoe` (https://github.com/felt/tippecanoe — `brew install
tippecanoe`). Downloads ~816 MB of GeoJSON from NYC Open Data, which takes
several minutes, and caches it so a re-bake with different tiling options does
not re-download.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from nightshift.domain.basemap import (  # noqa: E402
    manifest_path,
    parse_manifest,
    sha256_of,
)

DATASET = "5zhs-2jue"
EXPORT_URL = (
    f"https://data.cityofnewyork.us/api/geospatial/{DATASET}?method=export&format=GeoJSON"
)
SODA_URL = f"https://data.cityofnewyork.us/resource/{DATASET}.json"

# z13 is where a building first occupies more than a pixel; below it the whole
# layer is noise that costs bytes. z16 is street level, which is the view the
# city design is built around. Outside that range MapLibre overzooms, which for
# extrusions is exactly right — the geometry is the same, only the detail budget
# changes.
MIN_ZOOM = 13
MAX_ZOOM = 16

# Everything except the fourteen structures the city records as demolished.
#
# It is tempting to also drop `feature_code` 5110 — 213,470 features averaging
# eleven feet, which is to say garages and sheds. They were measured and kept:
# excluding a fifth of the city's structures to save download is an editorial
# choice about what counts as a building, and tippecanoe already drops them at
# the zooms where they would be noise. A demolished building is different. It is
# not there, and drawing it would be a small lie.
FEATURE_FILTER = '{"*":["!=","last_status_type","Demolition"]}'

# `last_status_type` is in this list because the filter above is applied *after*
# `--include` prunes attributes, not before. Left out, the filter compares
# against a field tippecanoe has already deleted, prints "attribute not found
# for comparison" into the middle of a progress bar, and keeps every demolished
# structure — the exact outcome the comment above says this does not do. Proved
# both directions on a three-feature fixture: without it a `Demolition` feature
# survives; with it that feature drops and a feature genuinely missing the field
# is still kept, which is the behaviour I3's habit of mind asks for — absence of
# evidence is not evidence the building is gone.
ATTRIBUTES = ("bin", "height_roof", "feature_code", "name", "last_status_type")

ATTRIBUTION = (
    '<a href="https://www.nyc.gov/site/planning/data-maps/open-data.page" '
    'target="_blank">NYC Open Data</a>'
)
LICENCE = "NYC Open Data terms of use — public domain, attribution requested"


def require(names: tuple[str, ...], hint: str) -> str:
    """Find the first of `names` on PATH, or explain how to get it.

    Two names for the pmtiles CLI because the supported install routes disagree:
    a GitHub release binary is `pmtiles`, `go install` produces `go-pmtiles`.
    """
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    sys.exit(f"{' or '.join(names)} is not on PATH.\n  {hint}")


def soda_count(where: str | None = None) -> int:
    """One aggregate query against the dataset, for the manifest's census."""
    url = f"{SODA_URL}?$select=count(*)"
    if where:
        url += f"&$where={quote(where)}"
    completed = subprocess.run(
        ["curl", "-sS", "--max-time", "90", url], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        sys.exit(f"could not reach NYC Open Data: {completed.stderr.strip()}")
    try:
        return int(json.loads(completed.stdout)[0]["count"])
    except (json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
        sys.exit(f"unexpected count response: {exc}")


def download(destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        size_mb = destination.stat().st_size / 1024 / 1024
        print(f"==> reusing cached export ({size_mb:.0f} MB) at {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"==> downloading the whole city from NYC Open Data (~816 MB, several minutes)")
    completed = subprocess.run(
        ["curl", "-sS", "-L", "--max-time", "1800", "-o", str(destination), EXPORT_URL],
        check=False,
    )
    if completed.returncode != 0:
        destination.unlink(missing_ok=True)
        sys.exit("the export download failed")


def bake(tippecanoe: str, source: Path, out: Path, maxzoom: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"==> tiling z{MIN_ZOOM}-z{maxzoom}")
    command = [
        tippecanoe,
        "-o",
        str(out),
        "--force",
        "--layer=buildings",
        f"--minimum-zoom={MIN_ZOOM}",
        f"--maximum-zoom={maxzoom}",
        *[f"--include={name}" for name in ATTRIBUTES],
        f"--feature-filter={FEATURE_FILTER}",
        # Rather than a hard feature cap: keep the sparsest features when a tile
        # overflows, so a dense block thins out instead of losing its tail. The
        # alternative leaves visible holes in Midtown.
        "--drop-densest-as-needed",
        "--extend-zooms-if-still-dropping",
        "--quiet",
        str(source),
    ]
    # `stdin=DEVNULL` is not tidiness. Given no input path tippecanoe reads
    # GeoJSON from standard input, and an input path omitted by mistake then
    # blocks forever on whatever stdin happens to be — no error, no output, no
    # CPU. That is exactly how a 70-minute bake of nothing happened once. With
    # the path present this closes the failure mode rather than relying on it.
    if subprocess.run(command, stdin=subprocess.DEVNULL, check=False).returncode != 0:
        sys.exit("tippecanoe failed")


def build_manifest(*, out: Path, repo: str, tag: str, header: dict[str, Any]) -> dict[str, Any]:
    total = soda_count()
    no_height = soda_count("height_roof IS NULL OR height_roof <= 0")
    return {
        "filename": out.name,
        "url": f"https://github.com/{repo}/releases/download/{tag}/{out.name}",
        "sha256": sha256_of(out),
        "size_bytes": out.stat().st_size,
        "protomaps_build": datetime.now(UTC).strftime("%Y%m%d"),
        "protomaps_version": f"nyc-open-data:{DATASET}",
        "osm_replication_time": datetime.now(UTC).isoformat(timespec="seconds"),
        "bbox": [float(edge) for edge in header["bounds"]],
        "minzoom": int(header["minzoom"]),
        "maxzoom": int(header["maxzoom"]),
        "attribution": ATTRIBUTION,
        "licence": LICENCE,
        "baked_on": datetime.now(UTC).date().isoformat(),
        # §5.3 requires that a footprint with no measured height takes a
        # documented default *and is recorded as having taken it*. This is that
        # record: 732 of 1,083,024 on the 2026-08-12 export, which is 0.07%.
        # The style renders them at DEFAULT_HEIGHT_FEET and the city's coverage
        # page can quote the fraction rather than implying the skyline is
        # entirely measured.
        "structures": total,
        "structures_without_height": no_height,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="Tahmudun/Nightshift")
    parser.add_argument("--tag", default=None, help="release tag (default: buildings-<date>)")
    parser.add_argument("--maxzoom", type=int, default=MAX_ZOOM)
    parser.add_argument(
        "--source",
        type=Path,
        default=ROOT / "data" / "cache" / "nyc-buildings.geojson",
        help="where to cache the raw export",
    )
    args = parser.parse_args()

    tippecanoe = require(
        ("tippecanoe",),
        "brew install tippecanoe — or see https://github.com/felt/tippecanoe. "
        "Only this script needs it; `make setup` downloads the baked artifact.",
    )
    pmtiles = require(
        ("pmtiles", "go-pmtiles"),
        "brew install pmtiles — needed only to read back the header this writes "
        "into the manifest.",
    )

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    tag = args.tag or f"buildings-{stamp}"
    out = ROOT / "data" / "cache" / f"nyc-buildings-{stamp}.pmtiles"

    download(args.source)
    bake(tippecanoe, args.source, out, args.maxzoom)

    header_json = subprocess.run(
        [pmtiles, "show", "--header-json", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    if header_json.returncode != 0:
        sys.exit(f"could not read the baked archive: {header_json.stderr.strip()}")

    manifest = build_manifest(
        out=out, repo=args.repo, tag=tag, header=json.loads(header_json.stdout)
    )
    parse_manifest(manifest)

    destination = manifest_path("buildings")
    destination.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"\n==> {out} ({manifest['size_bytes'] / 1024 / 1024:.0f} MB)")
    print(
        f"==> {manifest['structures']:,} structures, "
        f"{manifest['structures_without_height']:,} without a measured height"
    )
    print(f"==> wrote {destination}\n")
    print(f"  gh release create {tag} {out} \\")
    print(f'    --title "NYC building footprints — {stamp}" \\')
    print(f'    --notes "NYC Open Data {DATASET}. {LICENCE}."')


if __name__ == "__main__":
    main()
