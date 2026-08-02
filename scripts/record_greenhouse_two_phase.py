#!/usr/bin/env python3
"""Record the two fixtures M1d's Greenhouse two-phase poll needs.

    python scripts/record_greenhouse_two_phase.py datadog

Two recordings, because ADR 0007's poll is two requests:

1. **The listing** — ``GET /v1/boards/{token}/jobs``, no ``content=true``. This
   is the cheap request the whole design rests on: 33 KB against 499 KB for the
   same board with content (measured 2026-08-02). It carries an id, an
   ``updated_at``, a location and a title per posting, and no description.
2. **One posting** — ``GET /v1/boards/{token}/jobs/{id}``, which is what phase 2
   fetches for a posting whose ``updated_at`` moved.

The single-posting recording exists to be *compared*, not just parsed. Its
payload was measured byte-identical to the same posting inside ``?content=true``
— every key, every value — which is why ``GreenhouseAdapter.normalize`` is
reused for both rather than duplicated. A second normalization path is a second
place for the location parser to drift, and I1 failures have come from exactly
that three times in this project. The committed test asserts the equality holds,
so if Greenhouse ever diverges the suite says so instead of quietly producing
two different canonical jobs for one posting.

Run by a human, never on a schedule, never during ingestion. Goes through
``PoliteClient`` so the recorder sees exactly what the adapter would, including
the User-Agent the source logs — and because ``urllib`` cannot verify TLS on
this host (M1c found that the hard way with ``record_crawl_fixture.py``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from nightshift.adapters.http import PoliteClient  # noqa: E402
from nightshift.config import Settings  # noqa: E402

FIXTURE_DIR = ROOT / "services" / "api" / "tests" / "fixtures" / "greenhouse"

LISTING_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
JOB_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}"
FULL_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

#: How many postings to keep in the committed listing. Enough that the phase-2
#: diff has something to select *from* — a fixture with one posting cannot show
#: "one changed, nine did not", which is the behaviour the milestone turns on.
KEEP = 25


async def fetch(url: str) -> Any:
    settings = Settings(outbound_http_enabled=True, http_timeout_seconds=60.0)
    async with PoliteClient(settings) as client:
        return await client.get_json(url)


def _write(path: Path, payload: Any, meta: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
    path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")


async def main(token: str) -> int:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now(UTC).isoformat()

    listing = await fetch(LISTING_URL.format(token=token))
    if not isinstance(listing, dict) or not isinstance(listing.get("jobs"), list):
        raise SystemExit("listing did not return {'jobs': [...]}")
    all_jobs = listing["jobs"]

    # Keep the head of the listing rather than a curated selection. Unlike the
    # board fixture, this one is not exercising location or salary shapes — the
    # adapter reads only id and updated_at from it, so what matters is having
    # enough postings to diff, not which ones.
    kept = all_jobs[:KEEP]
    stamped = sum(1 for j in kept if j.get("updated_at"))
    with_content = sum(1 for j in kept if j.get("content"))

    _write(
        FIXTURE_DIR / "datadog_listing.json",
        {**listing, "jobs": kept},
        {
            "provenance": {
                "endpoint": LISTING_URL.format(token=token),
                "recorded_at": recorded_at,
                "board_token": token,
                "full_response_job_count": len(all_jobs),
                "note": (
                    "The cheap half of ADR 0007's two-phase poll: no content=true. "
                    "Each posting is byte-identical to the live response; only the "
                    f"set was reduced ({len(all_jobs)} -> {len(kept)}). Nothing "
                    "inside a posting was edited or synthesised."
                ),
            },
            "what_this_fixture_proves": {
                "postings_carrying_updated_at": stamped,
                "postings_carrying_content": with_content,
                "why_it_matters": (
                    "updated_at is what the phase-2 diff compares on, and "
                    "Greenhouse is the only one of the three providers that "
                    "publishes it. content must be absent — a listing that "
                    "carried descriptions would make the 15x saving imaginary."
                ),
            },
        },
    )

    job_id = str(kept[0]["id"])
    single = await fetch(JOB_URL.format(token=token, job_id=job_id))
    full = await fetch(FULL_URL.format(token=token))
    same = next(
        (j for j in full.get("jobs", []) if str(j.get("id")) == job_id),
        None,
    )
    identical = same == single

    _write(
        FIXTURE_DIR / "datadog_single_job.json",
        single,
        {
            "provenance": {
                "endpoint": JOB_URL.format(token=token, job_id=job_id),
                "recorded_at": recorded_at,
                "board_token": token,
                "source_job_id": job_id,
                "note": (
                    "One posting with content, as ADR 0007's phase 2 fetches it. "
                    "Recorded verbatim; nothing edited."
                ),
            },
            "compared_against_content_true": {
                "identical": identical,
                "why_it_matters": (
                    "If this is true, GreenhouseAdapter.normalize can be reused "
                    "for phase-2 payloads rather than duplicated, and there is no "
                    "second normalization path for the location parser to drift "
                    "in. The committed test asserts it, so a future divergence "
                    "fails loudly instead of producing two different canonical "
                    "jobs for one posting."
                ),
            },
        },
    )

    if not identical:
        print(
            "WARNING: the per-posting payload is NOT identical to the "
            "content=true item. The design's reuse of normalize needs revisiting.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("token", nargs="?", default="datadog")
    raise SystemExit(asyncio.run(main(parser.parse_args().token)))
