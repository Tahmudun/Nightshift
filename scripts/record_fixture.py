#!/usr/bin/env python3
"""Re-record a committed adapter fixture from a live board.

Committed fixtures must come from recorded real payloads (CLAUDE.md §7), and a
fixture nobody can regenerate rots into a fossil the moment a provider changes a
field. This script is how a fixture gets refreshed, and it is deliberately
explicit: run by a human, never on a schedule, never during ingestion.

    python scripts/record_fixture.py greenhouse datadog

It reduces the *set* of jobs to keep the file reviewable, and never edits the
contents of a job. A fixture with hand-tweaked values is a mock wearing a
fixture's name, which is the failure mode I7 is about.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from citysignal.adapters.http import PoliteClient  # noqa: E402
from citysignal.config import Settings  # noqa: E402

FIXTURE_ROOT = ROOT / "services" / "api" / "tests" / "fixtures"

ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true",
}


async def fetch(url: str) -> Any:
    """Fetch through the same client ingestion uses.

    Not urllib: the recorder must see exactly what the adapter would see, right
    down to the User-Agent header the source logs. Outbound HTTP is enabled
    explicitly here — this script is the deliberate, human-invoked exception to
    the default-off kill switch.
    """
    settings = Settings(outbound_http_enabled=True, http_timeout_seconds=60.0)
    async with PoliteClient(settings) as client:
        return await client.get_json(url)


def _location(job: dict[str, Any]) -> str:
    value = job.get("location")
    if isinstance(value, dict):
        return str(value.get("name") or "")
    return str(value or "")


def _has_pay_range(job: dict[str, Any]) -> bool:
    for entry in job.get("metadata") or []:
        if isinstance(entry, dict) and entry.get("value_type") == "currency_range" and entry.get("value"):
            return True
    return False


# Each selector is (why-this-job-is-in-the-fixture, predicate, how-many).
# The reasons are written into the .meta.json file, so a reviewer can see the
# coverage rationale without reverse-engineering it from the payloads.
GREENHOUSE_SELECTORS: list[tuple[str, Callable[[dict[str, Any]], bool], int]] = [
    ("single NYC location, pay range published (NYC transparency law)",
     lambda j: _location(j) == "New York, New York, USA" and _has_pay_range(j), 1),
    ("single NYC location, no pay range",
     lambda j: _location(j) == "New York, New York, USA" and not _has_pay_range(j), 1),
    ("three physical offices incl. NYC",
     lambda j: _location(j).count(";") == 2 and "New York, New York, USA" in _location(j), 1),
    ("one office plus many remote states — the A2 case",
     lambda j: _location(j).count(";") >= 8 and "Remote" in _location(j), 1),
    ("internship in the title",
     lambda j: bool(re.search(r"\b(intern|internship|co-?op)\b", j.get("title", ""), re.I)), 1),
    ("non-US single location",
     lambda j: "USA" not in _location(j) and ";" not in _location(j), 1),
    ("remote-only, single segment",
     lambda j: "Remote" in _location(j) and ";" not in _location(j), 1),
    ("contract role in the title",
     lambda j: "contract" in j.get("title", "").lower(), 1),
    ("no requisition id", lambda j: not j.get("requisition_id"), 1),
    ("additional NYC roles",
     lambda j: _location(j) == "New York, New York, USA", 3),
]


def curate(jobs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    picked: list[dict[str, Any]] = []
    chosen_ids: set[Any] = set()
    reasons: dict[str, str] = {}
    for why, predicate, limit in GREENHOUSE_SELECTORS:
        found = 0
        for job in jobs:
            if found >= limit:
                break
            if job.get("id") in chosen_ids or not predicate(job):
                continue
            picked.append(job)
            chosen_ids.add(job["id"])
            reasons[str(job["id"])] = why
            found += 1
    return picked, reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(ENDPOINTS))
    parser.add_argument("token", help="board token, e.g. datadog")
    parser.add_argument("--name", help="fixture basename (default: <token>_board)")
    args = parser.parse_args()

    if args.provider != "greenhouse":
        print(f"curation selectors for {args.provider} arrive with its adapter (M1)", file=sys.stderr)
        return 2

    url = ENDPOINTS[args.provider].format(token=args.token)
    print(f"GET {url}")
    payload = asyncio.run(fetch(url))
    jobs = payload.get("jobs") or []
    if not jobs:
        print("board returned no jobs — refusing to write an empty fixture", file=sys.stderr)
        return 1

    picked, reasons = curate(jobs)
    basename = args.name or f"{args.token}_board"
    out_dir = FIXTURE_ROOT / args.provider
    out_dir.mkdir(parents=True, exist_ok=True)

    fixture_path = out_dir / f"{basename}.json"
    fixture_path.write_text(
        json.dumps({"jobs": picked, "meta": {"total": len(picked)}}, indent=2, ensure_ascii=False)
        + "\n"
    )

    missing = [why for why, _, _ in GREENHOUSE_SELECTORS if why not in reasons.values()]
    meta_path = out_dir / f"{basename}.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "provenance": {
                    "endpoint": url,
                    "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "board_token": args.token,
                    "full_response_job_count": payload.get("meta", {}).get("total", len(jobs)),
                    "note": (
                        f"Each job object is byte-identical to the live response. Only the set "
                        f"of jobs was reduced ({len(jobs)} -> {len(picked)}); nothing inside a "
                        f"job was edited, redacted, or synthesised."
                    ),
                },
                "why_each_job_is_here": reasons,
                "coverage_not_available_on_this_board": missing,
            },
            indent=2,
        )
        + "\n"
    )

    print(f"wrote {len(picked)} jobs -> {fixture_path.relative_to(ROOT)}")
    if missing:
        print("\nnot present on this board (no synthetic substitute was written):")
        for why in missing:
            print(f"  - {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
