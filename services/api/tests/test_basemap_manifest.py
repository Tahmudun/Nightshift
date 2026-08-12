"""The pinned basemap, and the plausible wrong file it has to refuse.

`city.md` §5.2, ADR 0022. A basemap that fails loudly is a nuisance. A basemap
that fails *quietly* — an HTML error page saved under a `.pmtiles` name, a
download cut off at 40 MB — is a blank map with no error anywhere, and the
person looking at it has no way to tell it from a styling bug.

So every one of these tests is about a file that is wrong in a way that looks
right, and about the specific sentence the failure produces. `test_*_is_named`
assertions check the message rather than just the state, because the message is
the whole deliverable: a `BasemapState` nobody prints helps nobody.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from nightshift.domain.basemap import (
    ARTIFACTS,
    PMTILES_MAGIC,
    BasemapState,
    ManifestError,
    artifact_path,
    cache_dir,
    load_manifest,
    manifest_path,
    parse_manifest,
    sha256_of,
    verify,
)

VALID = {
    "filename": "nyc-basemap-20260810.pmtiles",
    "url": "https://example.invalid/nyc-basemap-20260810.pmtiles",
    "sha256": "0" * 64,
    "size_bytes": 1024,
    "protomaps_build": "20260810",
    "protomaps_version": "4.15.1",
    "osm_replication_time": "2026-08-10T04:00:00Z",
    "bbox": [-74.2591, 40.4774, -73.7002, 40.9176],
    "minzoom": 0,
    "maxzoom": 15,
    "attribution": "&copy; OpenStreetMap contributors",
    "licence": "ODbL-1.0",
    "baked_on": "2026-08-11",
}


def write_archive(path: Path, body: bytes = b"", *, version: int = 3) -> None:
    """A file that opens like a pmtiles archive. The header is what gets read."""
    path.write_bytes(PMTILES_MAGIC + bytes([version]) + body)


def manifest_for(path: Path, **overrides: object) -> object:
    """A manifest that describes exactly the file at `path`."""
    return parse_manifest(
        {**VALID, "sha256": sha256_of(path), "size_bytes": path.stat().st_size, **overrides}
    )


# --------------------------------------------------------------------------
# The committed manifest is itself an assertion about this repository.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("artifact", ARTIFACTS)
def test_every_committed_manifest_loads(artifact: str) -> None:
    """Both archives, not just the basemap.

    They are separate downloads with separate digests, and a second artifact
    added without a second manifest is a `make setup` that half works.
    """
    manifest = load_manifest(artifact=artifact)
    assert manifest.filename.endswith(".pmtiles")
    assert manifest.url.startswith("https://")


def test_the_committed_manifest_loads() -> None:
    manifest = load_manifest()
    assert manifest.filename.endswith(".pmtiles")
    assert manifest.url.startswith("https://")
    assert manifest.protomaps_build in manifest.filename


def test_an_unknown_artifact_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ManifestError, match="unknown artifact"):
        manifest_path("streets")


@pytest.mark.parametrize("artifact", ARTIFACTS)
def test_no_two_artifacts_share_a_cached_filename(artifact: str) -> None:
    """Distinct names, or one archive silently overwrites the other in the cache."""
    names = [load_manifest(artifact=name).filename for name in ARTIFACTS]
    assert len(names) == len(set(names))
    assert load_manifest(artifact=artifact).filename in names


def test_the_buildings_archive_records_what_it_could_not_measure() -> None:
    """§5.3: a footprint with no height takes a default *and is recorded as having*.

    The manifest carries the census — how many structures there are and how many
    of them have no measured height — so the number is auditable rather than an
    impression. A skyline presented as measured, where a fraction of it is a
    default, is exactly the kind of small lie this project does not keep.
    """
    import json

    raw = json.loads(manifest_path("buildings").read_text())
    total = raw["structures"]
    missing = raw["structures_without_height"]
    assert total > 1_000_000, "the whole city, not a borough"
    assert 0 <= missing < total
    assert missing / total < 0.01, "if this rises, the skyline is more default than measured"


def test_the_committed_manifest_covers_all_five_boroughs() -> None:
    """The bounds are the city's, not a box around Manhattan.

    Staten Island's western edge is about -74.26 and the Bronx's northern edge
    about 40.92. A tighter box would render a city where some of New York is
    simply absent, and nothing else in the stack would notice — the camera
    limits read these same numbers.
    """
    manifest = load_manifest()
    assert manifest.west <= -74.25, "cuts off Staten Island"
    assert manifest.north >= 40.91, "cuts off the north Bronx"
    assert manifest.east >= -73.71, "cuts off eastern Queens"
    assert manifest.south <= 40.48, "cuts off southern Staten Island"


def test_the_committed_manifest_reaches_street_level() -> None:
    """Zoom 15 is a decision with a cost (91 MB against 28 MB) and a reason.

    The city design's defining view is a street canyon, which is z16+ and is
    rendered by overzooming the deepest tiles available. Capping lower makes
    that view visibly coarse, so a change here should be argued rather than
    absorbed.
    """
    assert load_manifest().maxzoom == 15


def test_the_committed_manifest_can_say_how_old_its_world_is() -> None:
    manifest = load_manifest()
    assert manifest.osm_replication_time.endswith("Z")
    assert "openstreetmap" in manifest.attribution.lower()
    assert "ODbL" in manifest.licence


def test_the_manifest_path_does_not_depend_on_the_working_directory(tmp_path: Path) -> None:
    """Resolved from the module's own location, not `os.getcwd()`.

    The Makefile, pytest and the bake script all run from different places.
    """
    import os

    before = manifest_path()
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert manifest_path() == before
    finally:
        os.chdir(cwd)


# --------------------------------------------------------------------------
# Parsing: every field a typo could hollow out.
# --------------------------------------------------------------------------


def test_a_valid_manifest_parses() -> None:
    manifest = parse_manifest(VALID)
    assert manifest.bbox == (-74.2591, 40.4774, -73.7002, 40.9176)
    assert manifest.maxzoom == 15


@pytest.mark.parametrize("key", sorted(VALID))
def test_every_field_is_required(key: str) -> None:
    """No field is optional, including the provenance ones.

    A manifest missing `osm_replication_time` still downloads a working map, and
    that is exactly why it has to fail here: the artifact would become a blob of
    unknown age that renders fine.
    """
    with pytest.raises(ManifestError, match=key):
        parse_manifest({field: value for field, value in VALID.items() if field != key})


def test_an_empty_digest_is_refused_rather_than_treated_as_no_check() -> None:
    """The one failure that would silently disable everything else here."""
    with pytest.raises(ManifestError, match="sha256"):
        parse_manifest({**VALID, "sha256": ""})


@pytest.mark.parametrize("digest", ["0" * 63, "0" * 65, "z" * 64, "0" * 32])
def test_a_digest_that_is_not_64_hex_characters_is_refused(digest: str) -> None:
    with pytest.raises(ManifestError, match="64 hex"):
        parse_manifest({**VALID, "sha256": digest})


def test_a_digest_is_compared_case_insensitively() -> None:
    assert parse_manifest({**VALID, "sha256": "A" * 64}).sha256 == "a" * 64


@pytest.mark.parametrize("size", [0, -1, "1024", 1.5, True])
def test_a_size_that_is_not_a_positive_integer_is_refused(size: object) -> None:
    with pytest.raises(ManifestError, match="size_bytes"):
        parse_manifest({**VALID, "size_bytes": size})


@pytest.mark.parametrize("zoom", [-1, 25, "15", 1.5, True])
def test_a_zoom_outside_0_to_24_is_refused(zoom: object) -> None:
    with pytest.raises(ManifestError, match="maxzoom"):
        parse_manifest({**VALID, "maxzoom": zoom})


def test_a_minzoom_above_maxzoom_is_refused() -> None:
    with pytest.raises(ManifestError, match="exceeds"):
        parse_manifest({**VALID, "minzoom": 10, "maxzoom": 5})


@pytest.mark.parametrize(
    "bbox",
    [
        [-74.2591, 40.4774, -73.7002],
        [-74.2591, 40.4774, -73.7002, 40.9176, 0],
        "-74.2591,40.4774,-73.7002,40.9176",
        [-74.2591, 40.4774, "-73.7002", 40.9176],
    ],
)
def test_a_bbox_that_is_not_four_numbers_is_refused(bbox: object) -> None:
    with pytest.raises(ManifestError, match="bbox"):
        parse_manifest({**VALID, "bbox": bbox})


@pytest.mark.parametrize(
    "bbox",
    [
        [-73.7002, 40.4774, -74.2591, 40.9176],  # east and west swapped
        [-74.2591, 40.9176, -73.7002, 40.4774],  # north and south swapped
        [-200.0, 40.4774, -73.7002, 40.9176],  # off the planet
        [-74.2591, 40.4774, -74.2591, 40.9176],  # zero width
    ],
)
def test_a_bbox_in_the_wrong_order_is_refused(bbox: object) -> None:
    """west/south/east/north, and swapping a pair is the classic mistake.

    A reversed box parses as four perfectly good floats and produces a map of
    nowhere.
    """
    with pytest.raises(ManifestError, match="bbox"):
        parse_manifest({**VALID, "bbox": bbox})


def test_a_manifest_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(ManifestError, match="JSON object"):
        parse_manifest([VALID])


def test_unreadable_json_names_the_file(tmp_path: Path) -> None:
    broken = tmp_path / "basemap.manifest.json"
    broken.write_text("{ not json")
    with pytest.raises(ManifestError, match="not valid JSON"):
        load_manifest(broken)


# --------------------------------------------------------------------------
# Verification: the wrong file, in each way it can be wrong.
# --------------------------------------------------------------------------


def test_a_matching_file_verifies(tmp_path: Path) -> None:
    archive = tmp_path / "nyc.pmtiles"
    write_archive(archive, b"tiles go here")
    status = verify(manifest_for(archive), archive)
    assert status.state is BasemapState.ok
    assert status.usable


def test_a_missing_file_names_the_command_that_fixes_it(tmp_path: Path) -> None:
    status = verify(parse_manifest(VALID), tmp_path / "absent.pmtiles")
    assert status.state is BasemapState.missing
    assert not status.usable
    assert "make basemap" in status.detail or "make setup" in status.detail


def test_an_html_error_page_is_named_as_one(tmp_path: Path) -> None:
    """The failure this module exists for.

    An expired release URL or a captive portal returns HTML with a 200. Saved
    under a `.pmtiles` name it is the right *kind* of thing in every way a
    careless check would notice: it exists, it is a file, it is not empty.
    """
    page = tmp_path / "nyc.pmtiles"
    page.write_bytes(b"<!doctype html>\n<html><head><title>Not Found</title>")
    status = verify(manifest_for(page), page)
    assert status.state is BasemapState.not_pmtiles
    assert "<!doctype html>" in status.detail, "the message has to show what it actually is"


def test_gzip_that_is_not_pmtiles_is_named_as_one(tmp_path: Path) -> None:
    """Binary, plausible, and still not a map."""
    blob = tmp_path / "nyc.pmtiles"
    blob.write_bytes(gzip.compress(b"tiles go here"))
    assert verify(manifest_for(blob), blob).state is BasemapState.not_pmtiles


def test_an_empty_file_is_not_mistaken_for_an_archive(tmp_path: Path) -> None:
    """Also pins the check order: format is read before size.

    A zero-byte file is wrong on both counts, and `not_pmtiles` is the more
    useful of the two answers — "this is not a map" rather than "this map is
    the wrong length".
    """
    empty = tmp_path / "nyc.pmtiles"
    empty.write_bytes(b"")
    assert verify(parse_manifest(VALID), empty).state is BasemapState.not_pmtiles


def test_a_future_pmtiles_spec_version_is_refused(tmp_path: Path) -> None:
    """A v4 archive is a real archive this build cannot read.

    Worth its own state: the fix is "re-bake", not "delete and re-download",
    and a digest mismatch would have sent the reader down the wrong path.
    """
    archive = tmp_path / "nyc.pmtiles"
    write_archive(archive, b"tiles", version=4)
    status = verify(manifest_for(archive), archive)
    assert status.state is BasemapState.wrong_spec_version
    assert "version 4" in status.detail


def test_a_truncated_download_is_named_as_one(tmp_path: Path) -> None:
    archive = tmp_path / "nyc.pmtiles"
    write_archive(archive, b"the whole thing")
    manifest = manifest_for(archive)
    write_archive(archive, b"the who")
    status = verify(manifest, archive)
    assert status.state is BasemapState.wrong_size
    assert "interrupted" in status.detail


def test_the_right_size_with_the_wrong_bytes_is_caught(tmp_path: Path) -> None:
    """Size and magic both pass. Only the digest separates these two files.

    This is the case that justifies reading all 91 MB on every setup run: a
    substituted archive of identical length is otherwise indistinguishable.
    """
    archive = tmp_path / "nyc.pmtiles"
    write_archive(archive, b"the real tiles")
    manifest = manifest_for(archive)
    write_archive(archive, b"other tiles!!!")
    assert archive.stat().st_size == manifest.size_bytes
    status = verify(manifest, archive)
    assert status.state is BasemapState.digest_mismatch
    assert manifest.sha256 in status.detail


def test_the_status_carries_the_path_it_checked(tmp_path: Path) -> None:
    archive = tmp_path / "nyc.pmtiles"
    write_archive(archive)
    assert verify(manifest_for(archive), archive).path == archive


# --------------------------------------------------------------------------
# Where the file lives.
# --------------------------------------------------------------------------


def test_the_cache_lives_outside_the_repository() -> None:
    """91 MB does not belong in a checkout, for the reason the ONNX model does not."""
    assert manifest_path().parent not in cache_dir().parents


def test_the_cache_directory_is_overridable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NIGHTSHIFT_BASEMAP_DIR", str(tmp_path))
    assert cache_dir() == tmp_path


def test_the_filename_carries_the_build_so_a_new_bake_is_a_new_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-pointing the manifest at a newer build must not reuse the old file.

    Keying the cache by a fixed name would let a stale artifact sit at the
    expected path forever, verified against a digest it happens to match.
    """
    monkeypatch.setenv("NIGHTSHIFT_BASEMAP_DIR", str(tmp_path))
    old = parse_manifest(VALID)
    new = parse_manifest(
        {**VALID, "protomaps_build": "20261201", "filename": "nyc-basemap-20261201.pmtiles"}
    )
    assert artifact_path(old) != artifact_path(new)


def test_the_downloaded_artifact_matches_the_manifest() -> None:
    """The only test here that touches the real 91 MB file.

    Skipped rather than failed when it has not been downloaded, for the reason
    `embeddings.real_model_available` gives about the ONNX model: a suite that
    cannot run without a large download is a suite people stop running, and one
    that silently passes without it is worse. A skip says which it is.

    When it does run it is the end-to-end claim — that the bytes on this
    machine are the bytes this commit pins, through exactly the code the
    Makefile calls.
    """
    manifest = load_manifest()
    target = artifact_path(manifest)
    if not target.exists():
        pytest.skip(f"basemap not downloaded (run `make basemap`): {target}")
    status = verify(manifest, target)
    assert status.state is BasemapState.ok, status.detail


def test_the_committed_manifest_is_formatted_as_the_bake_script_writes_it() -> None:
    """Indent two, trailing newline — so a re-bake produces a reviewable diff.

    Hand-editing this file is not the intended path; a diff that reformats the
    whole thing hides which measurement actually changed.
    """
    text = manifest_path().read_text()
    assert text == json.dumps(json.loads(text), indent=2) + "\n"
