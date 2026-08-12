#!/usr/bin/env python3
"""Put the pinned tile archives in the local cache, and prove they are the right ones.

Run by `make tiles`, which `make setup` depends on. There are two archives — the
Protomaps basemap and New York's own building footprints — and they are handled
identically because ADR 0022 gave them the same shape: baked by a maintainer,
published as a release asset, pinned by digest, downloaded once.

This is the only place in the product that downloads a map, and it runs at setup
time for the reason
`CLAUDE.md` §4 gives: **`make demo` must work offline from a clean clone.**
`make setup` already needs the network to install dependencies; after it, nothing
does.

It is safe to run repeatedly and cheap when the file is already there — a cached
artifact that verifies is left alone and no request is made. `--check` verifies
without ever downloading, which is what a doctor or a CI step wants.

Two behaviours are the point of the script rather than details of it:

**A file that does not match the manifest is never installed.** It is downloaded
to a temporary name, verified there, and only then moved into place. A partial
or substituted download therefore cannot become the map, and cannot be mistaken
for one on the next run.

**A failure says which failure it was.** "Could not reach GitHub" and "the bytes
are wrong" are different problems with different fixes, and the second one is
the dangerous one — see `nightshift.domain.basemap` for why a *plausible* wrong
file is the failure mode worth all this machinery.
"""

from __future__ import annotations

import argparse
import shutil
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from nightshift.domain.basemap import (
    ARTIFACTS,
    BasemapManifest,
    BasemapState,
    ManifestError,
    artifact_path,
    cache_dir,
    load_manifest,
    verify,
)

USER_AGENT = "nightshift-tile-fetch (+https://github.com/Tahmudun/Nightshift)"


def ssl_context() -> ssl.SSLContext:
    """Trust the same roots the rest of the stack does.

    A Python built against macOS' system OpenSSL has no CA bundle of its own,
    and `urlopen` fails with `CERTIFICATE_VERIFY_FAILED` on the first HTTPS call
    — an error that reads like a network problem and is not one. `certifi` is
    already installed (httpx depends on it), so the roots are on disk; they just
    are not the default. Never falls back to an unverified context: an
    unauthenticated 91 MB download is exactly the substitution this script
    exists to prevent.
    """
    try:
        import certifi
    except ImportError:  # pragma: no cover - certifi ships with the API deps
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def download(manifest: BasemapManifest, destination: Path) -> None:
    """Stream the artifact to `destination`, reporting progress on a tty."""
    expected = manifest.size_bytes
    print(f"==> downloading {manifest.filename} ({expected / 1024 / 1024:.0f} MB)")
    print(f"    {manifest.url}")

    request = urllib.request.Request(manifest.url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(
            request, timeout=60, context=ssl_context()
        ) as response, destination.open("wb") as handle:
            received = 0
            step = 0
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
                received += len(chunk)
                if sys.stderr.isatty() and received - step >= 8 * 1024 * 1024:
                    step = received
                    print(
                        f"\r    {received / 1024 / 1024:6.0f} MB "
                        f"/ {expected / 1024 / 1024:.0f} MB",
                        end="",
                        file=sys.stderr,
                    )
            if sys.stderr.isatty():
                print(file=sys.stderr)
    except urllib.error.HTTPError as exc:
        destination.unlink(missing_ok=True)
        sys.exit(
            f"the basemap URL returned HTTP {exc.code}.\n"
            f"  {manifest.url}\n"
            "If that is a 404, the release asset this commit pins has not been "
            "published yet — see scripts/bake_basemap.py."
        )
    except (urllib.error.URLError, TimeoutError) as exc:
        destination.unlink(missing_ok=True)
        sys.exit(
            f"could not reach the basemap URL ({exc}).\n"
            "This step needs the network exactly once. Nothing after it does — "
            "`make demo` runs entirely offline afterwards."
        )


def ensure(artifact: str, *, check_only: bool, quiet: bool) -> None:
    """Bring one artifact into the cache, or explain why it could not be."""
    try:
        manifest = load_manifest(artifact=artifact)
    except ManifestError as exc:
        sys.exit(str(exc))

    target = artifact_path(manifest)
    status = verify(manifest, target)

    if status.usable:
        if not quiet:
            print(f"==> {artifact} already cached: {status.detail}")
        return

    if check_only:
        sys.exit(f"{artifact} {status.state}: {status.detail}")

    if status.state is not BasemapState.missing:
        # An existing file that fails verification is removed rather than kept.
        # Leaving it means every future run pays a full digest to rediscover the
        # same problem, and a stale file at the expected path is the one thing
        # most likely to be silently served to the browser.
        print(f"==> discarding an unusable cached file\n    {status.detail}")
        target.unlink(missing_ok=True)

    cache_dir().mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    partial.unlink(missing_ok=True)
    download(manifest, partial)

    verified = verify(manifest, partial)
    if not verified.usable:
        partial.unlink(missing_ok=True)
        sys.exit(
            f"the downloaded {artifact} does not match the manifest, so it was not "
            f"installed.\n  {verified.detail}"
        )

    shutil.move(str(partial), str(target))
    print(f"==> {artifact} ready: {target}")
    print(f"    {manifest.licence}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "artifacts",
        nargs="*",
        choices=[*ARTIFACTS, []],
        help=f"which archives to fetch (default: all of {', '.join(ARTIFACTS)})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the cached archives and exit; never download",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="say nothing when the cache already verifies"
    )
    args = parser.parse_args()

    for artifact in args.artifacts or ARTIFACTS:
        ensure(artifact, check_only=args.check, quiet=args.quiet)


if __name__ == "__main__":
    main()
