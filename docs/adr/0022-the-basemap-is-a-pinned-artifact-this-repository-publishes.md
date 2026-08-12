# ADR 0022 — The basemap is a pinned artifact this repository publishes, not a URL it trusts

- **Status:** accepted
- **Date:** 2026-08-11
- **Milestone:** M4b (Task 1)
- **Relates to:** `city.md` §5.2; AMENDMENTS A4 and A9; `CLAUDE.md` §4 (`make demo` is offline) and §8 (first-party sources, no speculative dependencies)

> **Since accepted — M4b Task 4 renamed the machinery, not the decision.** This
> shape turned out to be worth reusing immediately: NYC's building footprints
> are a second artifact handled identically. So `make basemap` is now
> `make tiles` and fetches both, `scripts/fetch_basemap.py` is
> `scripts/fetch_tiles.py`, and the route named below at `/api/basemap` is now
> `/api/tiles/[artifact]` — one handler, because the archives differ in nothing
> it cares about. Everything this ADR decided still holds; read the old names as
> the new ones.

## Context

A4 names the tile source as "OpenFreeMap or self-hosted Protomaps" and does not
choose between them. `city.md` §5.2 argued the choice was already made
elsewhere: **`make demo` working offline from a clean clone is a hard
requirement, and fixing it is the highest-priority task in the repo if it
breaks.** OpenFreeMap is a hosted tile service — a network call on every pan, a
donation-funded third party in the render path, and a demo that fails on a train.

So: self-hosted Protomaps. One `.pmtiles` archive of the NYC bounding box, on
local disk, read by MapLibre through the pmtiles protocol. No tile server
process, no quota, no key, no network at render time.

§5.2 then sketched the split that keeps both requirements true — `make setup`
downloads the archive once, `make demo` never touches the network — and left one
sentence doing more work than it could carry:

> The download is checksummed, its absence is a clear error message naming the
> command to fix it rather than a broken map.

Building it turned that sentence into three decisions, one of which the design
had not anticipated at all.

## The thing the design did not know

Protomaps rebuilds the planet daily and publishes each build at
`https://build.protomaps.com/YYYYMMDD.pmtiles`. The obvious implementation is
for `make setup` to fetch the `pmtiles` CLI and cut the NYC box itself: no
hosting, no artifact to manage, and the tiles are always current.

Measured on 2026-08-11:

| Build | Age that day | Result |
|---|---|---|
| `20260811` | current | 206 |
| `20260810` | 1 day | 206 |
| `20260809` | 2 days | 206 |
| `20260804` | 7 days | **404** |
| `20260801` | 10 days | **404** |
| `20260706` | 5 weeks | **404** |

Retention is roughly a week. That kills setup-time extraction twice over:

1. **It expires.** A commit pinning `--build 20260810` stops working within days.
   Not degrades — 404s, at `make setup`, on a clean clone, which is the exact
   scenario `CLAUDE.md` §4 protects hardest.
2. **Before it expires, it is not reproducible.** "Extract from whatever build
   is current" hands two clones of this repository two different maps, with no
   record anywhere of which one anybody has. There is nothing to checksum, so
   §5.2's "the download is checksummed" becomes unimplementable rather than
   merely unimplemented.

## Decision

**Bake once, publish the artifact, pin it by digest.**

- `scripts/bake_basemap.py` is a maintainer script. It cuts the NYC bbox out of
  a named daily build over HTTP range requests — 100 MB transferred against a
  planet file of several hundred gigabytes, in eight seconds — and writes
  `data/basemap.manifest.json` from measurements *of the result*, never from the
  arguments it was given.
- The archive is published as a **GitHub release asset on this repository**.
  Free, no key, no quota, stable URL, and independent of Q2 (the deployment
  target), which is still open and now does not block this.
- `data/basemap.manifest.json` is committed and pins: the URL, the sha256, the
  byte length, the bbox, the zoom range, the Protomaps build and basemap
  version, and the OpenStreetMap replication timestamp inside it.
- `make basemap` — a prerequisite of `make setup` — downloads it once into
  `~/.cache/nightshift/basemap/`, the same place and for the same reason as the
  ONNX embedding model. Re-running is cheap and makes no request.

The current artifact: build `20260810`, basemap v4.15.1, OpenStreetMap as of
`2026-08-10T04:00:00Z`, bounds `-74.2591,40.4774,-73.7002,40.9176`, zoom 0–15,
95,348,122 bytes.

### Zoom 15, at three times the size

z13 is 11 MB, z14 is 28 MB, z15 is 91 MB. The city design's defining view is a
street canyon (§2.1), which is z16–z18 and is drawn by overzooming the deepest
tiles in the archive. Capping at z14 makes exactly that view coarse. The 130 MB
embedding model is the precedent that one large cached artifact in `make setup`
is acceptable here; a second one is not a new category.

### The whole city, not a box around Manhattan

The bbox is New York's own bounds. The camera limits read the same numbers, so a
job in Staten Island is reachable rather than off the edge of the world. A
committed test asserts each of the four edges, because a tighter box renders a
city where part of New York is simply absent and nothing else in the stack would
notice.

## Verification, and why there is so much of it

The failure this design has to survive is not a corrupt download. It is a
**plausible** one.

An expired release URL, a captive portal, or a proxy returns an HTML error page
with a 200. `curl` writes 400 bytes of `<!doctype html>` to a file named
`nyc-basemap-20260810.pmtiles`. Every careless check passes: the file exists, it
is not empty, it is at the expected path. The map renders blank, the console
shows a decoding error from deep inside pmtiles.js, and nothing anywhere says
"that is not a map."

So verification is layered, and each layer is a **named state carrying its own
sentence** rather than a boolean:

| State | Caught by | Because the fix differs |
|---|---|---|
| `missing` | `exists()` | Run `make basemap` — and this is the *expected* state on a clean clone, not an error |
| `not_pmtiles` | magic bytes | Delete it; you downloaded an error page. The message quotes what the file actually starts with |
| `wrong_spec_version` | the version byte | Re-bake with a current CLI. A real archive this build cannot read |
| `wrong_size` | `stat` | An interrupted download. Delete and refetch |
| `digest_mismatch` | sha256 | The right length and the right format, and still not the pinned bytes |

This is invariant I3's distinction one subsystem over: "I could not check" and
"it is wrong" are different answers, and a caller that cannot tell them apart
will handle both badly. Nothing is installed until it verifies — the download
lands on a `.partial` name and is moved into place only after — so a bad fetch
can never *become* the map, and can never be mistaken for one on the next run.

## Serving it

A Next.js route handler at `/api/basemap`, with real `Range` support.

- **Next rather than FastAPI**, because §5.6 requires the degraded path
  (`make test-e2e`, no API behind it) to show a usable product. A basemap from
  the Python service would make that path a blank screen rather than a city with
  no jobs in it.
- **503 rather than 404 when the archive is absent.** pmtiles.js reads a 404's
  HTML body as an archive header and reports a decoding failure. The 503 body is
  plain text naming `make setup`.
- **The length is checked against the manifest on every request**, using a
  `stat` the route already needed for `Content-Range`. `make basemap` checks the
  digest; this catches an archive swapped out afterwards.
- A server that ignored `Range` would still "work" and send 91 MB per tile.
  That is a silent failure, not a loud one, which is why the range parser is a
  separate tested module rather than four lines in a handler.

## Consequences

**Cost stays $0/month and zero keys.** `docs/architecture/costs.md` gains the
row. GitHub release hosting is free and has a 2 GB per-asset limit against a
91 MB artifact.

**Refreshing the map is a deliberate act**, not a background drift: re-run the
bake, publish a new release, commit the new manifest. The filename carries the
build date, so a new bake is a new cache path and a stale archive cannot sit at
the expected name. §5.3 already schedules the building footprints quarterly and
this fits the same cadence.

**The artifact is public.** The repository is public and the data is
OpenStreetMap under ODbL, which requires attribution — carried in the manifest,
returned on every response as `x-attribution`, and rendered by MapLibre's
attribution control.

**CI caches it and runs `make basemap`.** Without that,
`test_the_downloaded_artifact_matches_the_manifest` skips, and the one
end-to-end claim in this design — that the pinned digest is what the release
actually serves — would be checked nowhere. That is the argument the embedding
model's cache comment already makes, applied a second time.

**A fork must bake its own.** The bake script reads `owner/name` from the git
remote, so the URL it writes points at the fork's own releases rather than at
this repository's.

## What was rejected

| Option | Why not |
|---|---|
| **OpenFreeMap** | A network call at render time. `make demo` must be offline, and a donation-funded third party in the render path is a dependency this project cannot fix when it breaks |
| **Extract at setup time** | Expires within a week, and until it does it is not reproducible. Nothing to checksum |
| **Commit the archive** | 91 MB. `git` is not an artefact store, and this is the argument `embeddings.cache_dir` already made about the 130 MB model |
| **Git LFS** | Quota, a second storage system, and a clone that fails differently. A release asset is the same free hosting with none of it |
| **Cap at zoom 14 to fit in 28 MB** | Coarsens the street-level view the whole milestone is built around, to save a one-time download smaller than the model already in `make setup` |
| **Serve tiles from FastAPI** | Removes the basemap from the degraded path that §5.6 requires to stay usable |
| **A hosted tile key (Mapbox, MapTiler)** | A key, a quota, and a bill. `costs.md` already rejects Mapbox GL JS on the same grounds |
