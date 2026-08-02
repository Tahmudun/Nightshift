#!/usr/bin/env python3
"""Record the board and board-page responses that board *discovery* is tested on.

Sibling of ``record_fixture.py``, which records *adapter* fixtures — populated
boards, reduced to a reviewable set of postings. Discovery needs a different
shape: whole small responses, kept verbatim, plus one HTML page, because the
thing under test is "can we find out who this employer is", not "can we parse a
posting".

Run by a human, never on a schedule, never during ingestion:

    python scripts/record_discovery_fixture.py --all

Every request goes through ``PoliteClient`` — the same rate limiter, the same
User-Agent a maintainer would see in their access log. ``jobs.ashbyhq.com``'s
robots.txt was checked on 2026-08-02 and disallows only ``/meeting/``, ``/b/``
and ``/api/``; a board page at ``/{token}`` is permitted.

Nothing here is edited, redacted, or synthesised, with one stated exception: the
Ashby board *page* is trimmed to its ``<head>``, because the rest is a megabyte
of application JavaScript and the only thing discovery reads is the title. The
meta file says so, and nothing inside ``<head>`` is touched.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from nightshift.adapters.base import SourceUnavailableError  # noqa: E402
from nightshift.adapters.http import PoliteClient  # noqa: E402
from nightshift.config import Settings  # noqa: E402

OUT = ROOT / "services" / "api" / "tests" / "fixtures" / "discovery"

ASHBY_BOARD = "https://api.ashbyhq.com/posting-api/job-board/{token}"
ASHBY_PAGE = "https://jobs.ashbyhq.com/{token}"
GREENHOUSE_META = "https://boards-api.greenhouse.io/v1/boards/{token}"
GREENHOUSE_JOBS = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"

#: name -> (kind, url, why this recording exists).
#:
#: "kind" is json or html. The "why" is written into the meta file: a reviewer
#: should not have to reverse-engineer a fixture's purpose from its payload.
RECORDINGS: dict[str, tuple[str, str, str]] = {
    "ashby_0g_board": (
        "json",
        ASHBY_BOARD.format(token="0g"),
        "A live Ashby board whose API never states the employer's name. Paired "
        "with ashby_0g_page: the name is 0g Labs and the token is 0g, which is "
        "the I2 case ADR 0005's approval gate turns on.",
    ),
    "ashby_0g_page": (
        "html",
        ASHBY_PAGE.format(token="0g"),
        "Where an Ashby employer name actually lives: the board page <title>. Trimmed to <head>.",
    ),
    "ashby_unnameable_page": (
        "html",
        ASHBY_PAGE.format(token="a3c41b8b71eff8c4"),
        "Ashby serves HTTP 200 with the bare title 'Jobs' for a board token "
        "that does not exist — verified 2026-08-02 against this token, whose "
        "API endpoint 404s. This is the real recorded shape of a page that "
        "does not name an employer, and it is why extract_ashby_name must "
        "reduce a title of only the suffix to None rather than to ''.",
    ),
    "ashby_0x_empty_board": (
        "json",
        ASHBY_BOARD.format(token="0x"),
        "A live Ashby board with zero open postings. The I3 distinction "
        "(ADR 0003) at the discovery layer, on Ashby rather than only on "
        "Lever: empty is authoritative, unreachable is not.",
    ),
    "greenhouse_6sense_meta": (
        "json",
        GREENHOUSE_META.format(token="6sense"),
        "Greenhouse, unlike Ashby, states the employer name in its board "
        "endpoint. This is the whole reason Greenhouse needs no page fetch.",
    ),
    "greenhouse_6sense_jobs": (
        "json",
        GREENHOUSE_JOBS.format(token="6sense"),
        "The postings half of the same board, so a Greenhouse candidate can be "
        "validated end to end.",
    ),
}

_HEAD = re.compile(r"(.*?</head>)", re.IGNORECASE | re.DOTALL)


def _trim_to_head(html: str) -> tuple[str, bool]:
    """Keep everything up to and including ``</head>``.

    Returns the text and whether a trim happened, so the meta file can state it
    as a fact rather than as a policy that may or may not have applied.
    """
    match = _HEAD.match(html)
    if match is None:
        return html, False
    return match.group(1) + "\n", True


async def record(name: str, *, settings: Settings) -> int:
    kind, url, why = RECORDINGS[name]
    print(f"GET {url}")
    async with PoliteClient(settings) as client:
        try:
            if kind == "json":
                body: Any = await client.get_json(url)
                text = json.dumps(body, indent=2, ensure_ascii=False) + "\n"
                suffix = "json"
                extra: dict[str, Any] = (
                    {"top_level_keys": sorted(body)} if isinstance(body, dict) else {}
                )
                jobs = body.get("jobs") if isinstance(body, dict) else None
                if isinstance(jobs, list):
                    extra["job_count"] = len(jobs)
            else:
                raw = await client.get_text(url)
                text, trimmed = _trim_to_head(raw)
                suffix = "html"
                extra = {
                    "bytes_received": len(raw.encode()),
                    "bytes_kept": len(text.encode()),
                    "trimmed_to_head": trimmed,
                    "title": _title(text),
                }
        except SourceUnavailableError as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            print(
                "  Refusing to write a fixture for a response we did not get. "
                "A missing recording is a finding; a fabricated one is I7.",
                file=sys.stderr,
            )
            return 1

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.{suffix}").write_text(text)
    (OUT / f"{name}.meta.json").write_text(
        json.dumps(
            {
                "provenance": {
                    "endpoint": url,
                    "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "board_token": url.rstrip("/").split("/")[-1],
                    "http_status": 200,
                    "recorded_by": "scripts/record_discovery_fixture.py",
                    "note": (
                        "Verbatim response body."
                        if suffix == "json"
                        else (
                            "Trimmed to <head> — the rest of the page is application "
                            "JavaScript and discovery reads only the title. Nothing "
                            "inside <head> was edited."
                        )
                    ),
                    **extra,
                },
                "why_this_recording_exists": why,
                "why_each_job_is_here": {},
                "coverage_not_available_on_this_board": [],
            },
            indent=2,
        )
        + "\n"
    )
    print(f"  wrote {name}.{suffix}  ({len(text.encode())} bytes)")
    return 0


def _title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return " ".join(match.group(1).split()) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", choices=sorted(RECORDINGS))
    parser.add_argument("--all", action="store_true", help="record every fixture")
    args = parser.parse_args()

    if not args.all and args.name is None:
        parser.error("give a recording name or --all")

    names = sorted(RECORDINGS) if args.all else [args.name]
    # One client per recording is deliberate: these are six requests run by a
    # human, and a shared connection buys nothing worth the extra plumbing.
    settings = Settings(outbound_http_enabled=True, http_timeout_seconds=60.0)
    failures = 0
    for name in names:
        failures += asyncio.run(record(name, settings=settings))
    if failures:
        print(f"\n{failures} recording(s) failed — nothing was faked", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
