"""Record NYC GeoSearch's answer for every confirmed address in the worksheet.

`make offices` geocodes over the network and caches the answers in
`geocode_cache`. That table lives in Postgres, so `make reset-db` — or any
`docker compose down -v` — deletes them, and the only route back is another
network call. `make demo` is required to work offline from a clean clone, so
that route does not exist there, and the observable result was a city where
every role floated: `company_locations` empty, 31 of 31 signals `unresolved`.

This script is the recording half of the fix. It asks the live service the
*exact* question `load_offices` will ask — `OfficeEntry.geocoder_query`, the
same string, through the same URL shape as `NycGeoSearchGeocoder` — and writes
the response verbatim. `FixtureNycGeoSearchGeocoder` then replays it into the
real `parse_search_response`, so the offline path runs every acceptance rule
the live one does and only the bytes' origin differs.

Run by a human, with the network, when the worksheet gains an address:

    python scripts/record_office_geocodes.py

Nothing is edited, redacted or synthesised. A response that resolves to no
building is recorded too — "GeoSearch does not know this address" is an answer
about the world, and a fixture set that quietly dropped it would make the
offline path look better than the live one.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "services" / "api"))

from nightshift.adapters.geosearch import (
    SEARCH_URL,
    parse_search_response,
)
from nightshift.adapters.http import PoliteClient
from nightshift.config import Settings
from nightshift.domain.company_locations import (
    DEFAULT_WORKSHEET_PATH,
    read_worksheet,
)
from nightshift.domain.geocoding import Resolved

OUT_DIR = _REPO_ROOT / "services" / "api" / "tests" / "fixtures" / "geosearch"
FIXTURE_PATH = OUT_DIR / "office_addresses.json"
META_PATH = OUT_DIR / "office_addresses.meta.json"

#: The `size` the live geocoder asks for. Recording a different one would make
#: the fixture a response to a question this product never asks.
SEARCH_SIZE = 5


async def fetch(client: PoliteClient, query: str) -> dict[str, object]:
    """One live search, verbatim, through the same client the live path uses.

    `PoliteClient` carries this project's user agent, its rate limiting and its
    backoff, and `record_fixture.py` sets the same precedent: a recorder that
    reached the network by some other means would be recording a request the
    product never makes.
    """
    url = f"{SEARCH_URL}?{urlencode({'text': query, 'size': SEARCH_SIZE})}"
    payload = await client.get_json(url)
    if not isinstance(payload, dict):
        raise TypeError(f"{query}: expected an object, got {type(payload).__name__}")
    return payload


async def main() -> int:
    reading = read_worksheet(DEFAULT_WORKSHEET_PATH.read_text())
    print(f"  {DEFAULT_WORKSHEET_PATH}")
    print(f"  {reading.summary()}\n")

    if reading.problems:
        for problem in reading.problems:
            print(f"  refused: {problem.company:<24} {problem.reason}", file=sys.stderr)
        print("\nerror: fix the worksheet before recording.", file=sys.stderr)
        return 1

    # `outbound_http_enabled=True` explicitly: this script is the one thing in
    # the repo whose whole job is to reach the network, and it is run by a
    # human, by hand. Everything else honours the default-off switch.
    settings = Settings(outbound_http_enabled=True, http_timeout_seconds=60.0)
    recordings: dict[str, object] = {}
    async with PoliteClient(settings) as client:
        for entry in sorted(reading.entries, key=lambda e: e.company):
            query = entry.geocoder_query
            payload = await fetch(client, query)
            recordings[query] = payload

            # Parse it here with the production function, so the recorder
            # reports what the loader will actually make of these bytes rather
            # than that some bytes arrived. A fixture that records a 200
            # nobody can use is the failure this whole exercise is about.
            outcome = parse_search_response(payload)
            if isinstance(outcome, Resolved):
                print(f"  {entry.company:<16} {query}\n{'':<18}-> BIN {outcome.building_id}")
            else:
                print(f"  {entry.company:<16} {query}\n{'':<18}-> {outcome.refusal}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(recordings, indent=1, sort_keys=True) + "\n")
    META_PATH.write_text(
        json.dumps(
            {
                "provenance": {
                    "endpoint": f"{SEARCH_URL}?text=<geocoder_query>&size={SEARCH_SIZE}",
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "provider": (
                        "NYC GeoSearch (Pelias over the NYC Property Address Directory)"
                    ),
                    "recorded_by": "scripts/record_office_geocodes.py",
                    "note": (
                        "Byte-identical to the live responses. Nothing edited, "
                        "redacted or synthesised."
                    ),
                },
                "what_this_is": (
                    "One recorded search per confirmed address in "
                    "data/company-locations.yaml, keyed by the exact "
                    "OfficeEntry.geocoder_query the loader sends. Replayed by "
                    "FixtureNycGeoSearchGeocoder through the real "
                    "parse_search_response, which is what lets `make seed` put "
                    "roles on real buildings with no network."
                ),
                "how_to_refresh": (
                    "Add an address to data/company-locations.yaml, then run "
                    "python scripts/record_office_geocodes.py with outbound "
                    "network access. An address with no recording here is "
                    "reported by the fixture rung as 'provider unavailable' — "
                    "we could not look — never as 'no building found'."
                ),
                "queries": sorted(recordings),
            },
            indent=1,
        )
        + "\n"
    )
    print(f"\n  wrote {len(recordings)} recordings to {FIXTURE_PATH.relative_to(_REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
