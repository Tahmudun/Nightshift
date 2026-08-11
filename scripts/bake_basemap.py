#!/usr/bin/env python3
"""Cut the NYC basemap extract out of a Protomaps planet build, once, by hand.

This is a maintainer script. It is not run by `make setup`, not run in CI, and
not run on a schedule — `scripts/fetch_basemap.py` is what everyone else uses,
and it only ever downloads the artifact this script published.

The split matters and `city.md` §5.2 is where it comes from. Protomaps rebuilds
the planet daily and keeps a dated build for about a week, so "extract it at
setup time" is not a reproducible instruction: it 404s once retention rolls past,
and until then it hands two clones of this repository two different maps. Baking
once and pinning the digest makes the basemap a *fact about this commit* instead
of a fact about what Protomaps happened to be serving that morning. ADR 0022.

    python scripts/bake_basemap.py --build 20260810

Needs the `pmtiles` CLI (https://github.com/protomaps/go-pmtiles). It pulls only
the tiles inside the bounding box over HTTP range requests — roughly 100 MB
transferred against a planet file of several hundred gigabytes, in under a
minute. It writes the extract to `--out` and rewrites `data/basemap.manifest.json`
with everything measured from the result: digest, size, bounds, zoom range, the
build it came from and how fresh OpenStreetMap was inside it.

Publishing is the separate, deliberate second step, printed at the end. Nothing
here uploads anything.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from nightshift.domain.basemap import (
    manifest_path,
    parse_manifest,
    sha256_of,
)

PLANET_URL = "https://build.protomaps.com/{build}.pmtiles"

# New York City's own bounds, not a hand-drawn box around Manhattan. The camera
# limits in M4b clamp to the same numbers, so a job in Staten Island is
# reachable rather than off the edge of the world.
NYC_BBOX = (-74.2591, 40.4774, -73.7002, 40.9176)

# Zoom 15 is where the Protomaps basemap stops adding detail, and the city
# design spends most of its time below it — §2.1's street canyon is a z16-z18
# view, and overzoomed z14 tiles visibly coarsen exactly there. The cost of the
# top zoom level is real (28 MB at z14 against 91 MB at z15) and it buys the
# view the whole milestone is built around.
MAXZOOM = 15

# OpenStreetMap data is ODbL. The attribution is not decoration: it is a licence
# condition, it travels with the artifact, and MapLibre renders it from here.
ATTRIBUTION = (
    '<a href="https://www.openstreetmap.org/copyright" target="_blank">'
    "&copy; OpenStreetMap contributors</a>"
)
LICENCE = "ODbL-1.0 (OpenStreetMap), via the Protomaps Basemap (BSD-3-Clause tooling)"

CLI_NAMES = ("pmtiles", "go-pmtiles")


def find_cli(explicit: str | None) -> str:
    """Locate the pmtiles CLI, or explain how to get it.

    Two names because the two supported install routes disagree: a GitHub
    release binary is `pmtiles`, and `go install` produces `go-pmtiles`.
    """
    if explicit:
        if not shutil.which(explicit):
            sys.exit(f"no such executable: {explicit}")
        return explicit
    for name in CLI_NAMES:
        found = shutil.which(name)
        if found:
            return found
    sys.exit(
        "the pmtiles CLI is not on PATH. Install it with one of:\n"
        "  brew install pmtiles\n"
        "  go install github.com/protomaps/go-pmtiles@latest\n"
        "  https://github.com/protomaps/go-pmtiles/releases\n"
        "\nOnly this script needs it. `make setup` downloads the baked artifact "
        "instead, so nobody else has to install a Go binary."
    )


def run_json(cli: str, *args: str) -> Any:
    """Run the CLI and decode its JSON, failing loudly on either problem."""
    completed = subprocess.run(
        [cli, *args], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        sys.exit(f"{' '.join(args)} failed:\n{completed.stderr.strip()}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        sys.exit(f"{' '.join(args)} did not return JSON: {exc}")


def bake(cli: str, build: str, out: Path, bbox: tuple[float, ...], maxzoom: int) -> None:
    """Extract the bounding box from the remote planet build."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    url = PLANET_URL.format(build=build)
    print(f"==> extracting {bbox} from {url}")
    completed = subprocess.run(
        [
            cli,
            "extract",
            url,
            str(out),
            f"--bbox={','.join(str(edge) for edge in bbox)}",
            f"--maxzoom={maxzoom}",
        ],
        check=False,
    )
    if completed.returncode != 0:
        sys.exit(
            f"extract failed. If it was a 404, build {build} has aged out of "
            "Protomaps' retention — pick a more recent date. Builds are daily and "
            "roughly a week is kept."
        )


def replication_time(metadata: dict[str, Any]) -> str:
    """When OpenStreetMap was last read into the build these tiles came from.

    The single most useful provenance field in the manifest, and the one a
    reader actually wants: not "when did we bake this" but "how old is the
    world inside it".
    """
    stamp = metadata.get("planetiler:osm:osmosisreplicationtime")
    if not isinstance(stamp, str) or not stamp.strip():
        sys.exit(
            "the extract carries no planetiler:osm:osmosisreplicationtime. "
            "Refusing to write a manifest that cannot say how old its map is."
        )
    return stamp.strip()


def build_manifest(
    *, out: Path, build: str, repo: str, tag: str, metadata: dict[str, Any], header: dict[str, Any]
) -> dict[str, Any]:
    """Describe the baked file entirely from measurements of the baked file.

    Nothing here is passed through from an argument that was not also checked
    against the result. The bounds and zooms are read back out of the archive
    rather than echoed from the request, because a CLI that silently clamped
    them would otherwise produce a manifest that describes the ask instead of
    the artifact.
    """
    return {
        "filename": out.name,
        "url": f"https://github.com/{repo}/releases/download/{tag}/{out.name}",
        "sha256": sha256_of(out),
        "size_bytes": out.stat().st_size,
        "protomaps_build": build,
        "protomaps_version": str(metadata.get("version", "")).strip(),
        "osm_replication_time": replication_time(metadata),
        "bbox": [float(edge) for edge in header["bounds"]],
        "minzoom": int(header["minzoom"]),
        "maxzoom": int(header["maxzoom"]),
        "attribution": ATTRIBUTION,
        "licence": LICENCE,
        "baked_on": datetime.now(UTC).date().isoformat(),
    }


def default_repo() -> str:
    """`owner/name` from the git remote, so a fork bakes its own URL."""
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", completed.stdout.strip())
    if not match:
        sys.exit("could not read owner/name from `git remote get-url origin`; pass --repo")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build",
        required=True,
        help="Protomaps daily planet build date, YYYYMMDD (see https://build.protomaps.com)",
    )
    parser.add_argument("--out", type=Path, default=None, help="where to write the extract")
    parser.add_argument("--repo", default=None, help="owner/name hosting the release asset")
    parser.add_argument("--tag", default=None, help="release tag (default: basemap-<build>)")
    parser.add_argument("--maxzoom", type=int, default=MAXZOOM)
    parser.add_argument("--pmtiles-bin", default=None, help="path to the pmtiles CLI")
    args = parser.parse_args()

    if not re.fullmatch(r"\d{8}", args.build):
        sys.exit(f"--build must be YYYYMMDD, got {args.build!r}")

    cli = find_cli(args.pmtiles_bin)
    repo = args.repo or default_repo()
    tag = args.tag or f"basemap-{args.build}"
    out = args.out or ROOT / "data" / "cache" / f"nyc-basemap-{args.build}.pmtiles"

    bake(cli, args.build, out, NYC_BBOX, args.maxzoom)

    metadata = run_json(cli, "show", "--metadata", str(out))
    header = run_json(cli, "show", "--header-json", str(out))
    manifest = build_manifest(
        out=out, build=args.build, repo=repo, tag=tag, metadata=metadata, header=header
    )

    # Parse it back before writing it. The manifest is the thing every other
    # reader trusts, and a bake that produced an unloadable one should fail here
    # rather than at somebody else's `make setup`.
    parse_manifest(manifest)

    destination = manifest_path()
    destination.write_text(json.dumps(manifest, indent=2) + "\n")

    size_mb = manifest["size_bytes"] / 1024 / 1024
    print(f"\n==> {out} ({size_mb:.1f} MB)")
    print(f"==> wrote {destination}")
    print("\nPublish it, then `make basemap` will find it:\n")
    print(f"  gh release create {tag} {out} \\")
    print(f'    --title "NYC basemap — Protomaps build {args.build}" \\')
    print(f'    --notes "OpenStreetMap via Protomaps, {LICENCE}."')


if __name__ == "__main__":
    main()
