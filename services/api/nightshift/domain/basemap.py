"""The basemap artifact: what it is, where it lives, and how it refuses.

`city.md` §5.2. A4 offers "OpenFreeMap or self-hosted Protomaps" and declines to
choose. `CLAUDE.md` §4 chooses for it, indirectly and firmly: **`make demo` works
offline from a clean clone, and fixing that is the highest-priority task in the
repo if it breaks.** A hosted tile service is a network call on every pan. So the
basemap is one `.pmtiles` file on local disk, read by MapLibre through the
pmtiles protocol — no tile server, no quota, no key, no network at render time.

Three facts about that file shape everything in this module.

**It cannot be committed.** 91 MB of vector tiles is not history, and `git` is
not an artefact store — the same argument `embeddings.cache_dir` already makes
about the 130 MB ONNX model, settled the same way: it lives in
`~/.cache/nightshift/`, `make setup` puts it there once, and nothing after that
touches the network.

**It cannot be re-derived on demand.** Protomaps builds the planet daily and
keeps a dated build for roughly a week — `20260804.pmtiles` was already a 404 on
2026-08-11, four days after it was current. So "re-extract at setup time" is not
a reproducible instruction: it fails outright once retention rolls past, and
before that it hands two clones of this repository two different maps. The
extract is therefore baked once by `scripts/bake_basemap.py`, published as a
release asset, and pinned here by digest. ADR 0022.

**A wrong file is worse than a missing one.** The characteristic failure is not
corruption, it is a *plausible* file: a proxy or an expired URL returns an HTML
error page, `curl` writes 400 bytes of `<!doctype html>` to `nyc-basemap.pmtiles`,
and the map goes blank with no error anywhere. So verification is layered and
each layer is named in its own right — magic bytes, then size, then digest — and
what comes back is a status carrying *why*, not a bool. The same distinction I3
draws about sources: "I could not check" and "it is wrong" are different answers
and the caller needs to be able to tell them apart.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

# A pmtiles v3 archive opens with these eight bytes: the ASCII name, then the
# spec version. Reading them costs one syscall and separates "this is a
# truncated or substituted file" from "this is the wrong version of the right
# file" — two errors a digest alone collapses into one unhelpful mismatch.
PMTILES_MAGIC = b"PMTiles"
PMTILES_SPEC_VERSION = 3

_CHUNK = 1024 * 1024


class BasemapState(StrEnum):
    """Why the artifact is or is not usable.

    Ordered by how early the check runs, which is also how specific the message
    can be. `missing` is the expected state on a clean clone and is not an
    error condition — it is the state `make setup` exists to leave behind.
    """

    ok = "ok"
    missing = "missing"
    not_pmtiles = "not_pmtiles"
    wrong_spec_version = "wrong_spec_version"
    wrong_size = "wrong_size"
    digest_mismatch = "digest_mismatch"


@dataclass(frozen=True, slots=True)
class BasemapStatus:
    """A verification result, carrying the sentence a human needs.

    `detail` is written to be printed as-is. A caller that reduces this to a
    boolean and prints its own message will produce a worse one, because only
    this module knows whether the file was absent, truncated, or an HTML error
    page wearing a `.pmtiles` extension.
    """

    state: BasemapState
    path: Path
    detail: str

    @property
    def usable(self) -> bool:
        return self.state is BasemapState.ok


@dataclass(frozen=True, slots=True)
class BasemapManifest:
    """The pinned description of one baked extract.

    Committed as `data/basemap.manifest.json` and written by the bake script
    rather than by hand, because every field in it is a measurement. The two
    provenance fields are the ones worth defending: `protomaps_build` names the
    daily planet build the tiles were cut from, and `osm_replication_time` names
    how fresh OpenStreetMap was when Protomaps built it. Without them the file
    is a 91 MB blob of unknown age, and "when was this map last true?" has no
    answer.
    """

    filename: str
    url: str
    sha256: str
    size_bytes: int
    protomaps_build: str
    protomaps_version: str
    osm_replication_time: str
    bbox: tuple[float, float, float, float]
    minzoom: int
    maxzoom: int
    attribution: str
    licence: str
    baked_on: str

    @property
    def west(self) -> float:
        return self.bbox[0]

    @property
    def south(self) -> float:
        return self.bbox[1]

    @property
    def east(self) -> float:
        return self.bbox[2]

    @property
    def north(self) -> float:
        return self.bbox[3]


class ManifestError(ValueError):
    """The manifest is unreadable or incomplete.

    Raised rather than returned. A malformed manifest is a repository defect —
    the file is committed and machine-written, so there is no user action that
    produces one and nothing sensible to degrade to.
    """


_REQUIRED_STRINGS = (
    "filename",
    "url",
    "sha256",
    "protomaps_build",
    "protomaps_version",
    "osm_replication_time",
    "attribution",
    "licence",
    "baked_on",
)


def manifest_path() -> Path:
    """`data/basemap.manifest.json`, found relative to this file.

    Not relative to the working directory: the Makefile, the test suite and the
    bake script all run from different places, and a manifest that resolves
    differently depending on who asked is a bug waiting for a Friday.
    """
    return _repo_root() / "data" / "basemap.manifest.json"


def _repo_root() -> Path:
    # services/api/nightshift/domain/basemap.py -> repo root is four up.
    return Path(__file__).resolve().parents[4]


def load_manifest(path: Path | None = None) -> BasemapManifest:
    """Read and validate the committed manifest."""
    source = path or manifest_path()
    try:
        raw = json.loads(source.read_text())
    except FileNotFoundError as exc:  # pragma: no cover - repository defect
        raise ManifestError(f"no basemap manifest at {source}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{source} is not valid JSON: {exc}") from exc
    return parse_manifest(raw, source=source)


def parse_manifest(raw: Any, *, source: Path | None = None) -> BasemapManifest:
    """Validate a decoded manifest into the frozen record.

    Every field is checked, including the ones a typo would leave merely empty.
    An empty `sha256` would otherwise disable verification silently, which is
    the one failure this whole module exists to prevent.
    """
    where = f" in {source}" if source else ""
    if not isinstance(raw, dict):
        raise ManifestError(f"basemap manifest{where} must be a JSON object")

    values: dict[str, Any] = {}
    for key in _REQUIRED_STRINGS:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ManifestError(f"basemap manifest{where}: {key!r} must be a non-empty string")
        values[key] = value.strip()

    digest = values["sha256"].lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ManifestError(
            f"basemap manifest{where}: 'sha256' must be 64 hex characters, got {digest!r}"
        )
    values["sha256"] = digest

    size = raw.get("size_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ManifestError(f"basemap manifest{where}: 'size_bytes' must be a positive integer")

    zooms: dict[str, int] = {}
    for key in ("minzoom", "maxzoom"):
        zoom = raw.get(key)
        if not isinstance(zoom, int) or isinstance(zoom, bool) or not 0 <= zoom <= 24:
            raise ManifestError(f"basemap manifest{where}: {key!r} must be an integer in 0..24")
        zooms[key] = zoom
    if zooms["minzoom"] > zooms["maxzoom"]:
        raise ManifestError(f"basemap manifest{where}: 'minzoom' exceeds 'maxzoom'")

    bbox = raw.get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ManifestError(f"basemap manifest{where}: 'bbox' must be [west, south, east, north]")
    if not all(isinstance(edge, (int, float)) and not isinstance(edge, bool) for edge in bbox):
        raise ManifestError(f"basemap manifest{where}: 'bbox' edges must be numbers")
    west, south, east, north = (float(edge) for edge in bbox)
    if not (-180 <= west < east <= 180) or not (-90 <= south < north <= 90):
        raise ManifestError(
            f"basemap manifest{where}: 'bbox' is not a west/south/east/north box: {bbox}"
        )

    return BasemapManifest(
        size_bytes=size,
        bbox=(west, south, east, north),
        minzoom=zooms["minzoom"],
        maxzoom=zooms["maxzoom"],
        **values,
    )


def cache_dir() -> Path:
    """Where the extract lives. Outside the repository, like the ONNX model.

    `NIGHTSHIFT_BASEMAP_DIR` overrides it, and the web process reads the same
    variable — one setting, two runtimes, so a developer who moves the cache
    does not end up with a Python side that finds it and a browser that does not.
    """
    override = os.environ.get("NIGHTSHIFT_BASEMAP_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cache" / "nightshift" / "basemap"


def artifact_path(manifest: BasemapManifest | None = None) -> Path:
    """The full path to the cached extract.

    The filename carries the Protomaps build date, so pointing the manifest at a
    newer bake changes the path too. A cache keyed by content cannot serve a
    stale file that happens to sit at the expected name.
    """
    return cache_dir() / (manifest or load_manifest()).filename


def sha256_of(path: Path) -> str:
    """Streamed, because the file is 91 MB and this runs on every setup."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify(manifest: BasemapManifest, path: Path | None = None) -> BasemapStatus:
    """Check a candidate file against the manifest, cheapest test first.

    The order is deliberate. Magic bytes cost one read and catch the common
    disaster — an HTML error page saved under a `.pmtiles` name — with a message
    that says so. Size costs a `stat` and catches a truncated download. Only
    then does the digest run, which reads all 91 MB and is the check that
    actually guarantees the bytes.
    """
    target = path or artifact_path(manifest)

    if not target.exists():
        return BasemapStatus(
            state=BasemapState.missing,
            path=target,
            detail=(
                f"no basemap at {target}. Run `make basemap` (or `make setup`) once, "
                "with a network connection, to download it."
            ),
        )

    # Sixteen bytes rather than the eight the check needs: the extra eight are
    # only ever printed, and "starts with '<!doctype html>'" tells a reader what
    # happened where "starts with '<!doctyp'" makes them go and look.
    with target.open("rb") as handle:
        header = handle.read(16)
    if not header.startswith(PMTILES_MAGIC):
        preview = header.decode("utf-8", errors="replace").strip()
        return BasemapStatus(
            state=BasemapState.not_pmtiles,
            path=target,
            detail=(
                f"{target} is not a pmtiles archive — it starts with {preview!r} rather than "
                "'PMTiles'. A download that returned an error page will look exactly like "
                "this. Delete the file and run `make basemap` again."
            ),
        )
    spec_version = header[len(PMTILES_MAGIC)]
    if spec_version != PMTILES_SPEC_VERSION:
        return BasemapStatus(
            state=BasemapState.wrong_spec_version,
            path=target,
            detail=(
                f"{target} is pmtiles spec version {spec_version}; this build reads "
                f"version {PMTILES_SPEC_VERSION}. Re-bake with a current `pmtiles` CLI."
            ),
        )

    actual_size = target.stat().st_size
    if actual_size != manifest.size_bytes:
        return BasemapStatus(
            state=BasemapState.wrong_size,
            path=target,
            detail=(
                f"{target} is {actual_size} bytes; the manifest pins "
                f"{manifest.size_bytes}. An interrupted download leaves exactly this. "
                "Delete the file and run `make basemap` again."
            ),
        )

    actual_digest = sha256_of(target)
    if actual_digest != manifest.sha256:
        return BasemapStatus(
            state=BasemapState.digest_mismatch,
            path=target,
            detail=(
                f"{target} has sha256 {actual_digest}; the manifest pins "
                f"{manifest.sha256}. The file is the right size and the right format but "
                "not the pinned bytes, so it is not the map this repository describes."
            ),
        )

    return BasemapStatus(
        state=BasemapState.ok,
        path=target,
        detail=(
            f"{target} verified: {actual_size} bytes, Protomaps build "
            f"{manifest.protomaps_build}, OSM as of {manifest.osm_replication_time}."
        ),
    )
