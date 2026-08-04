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
import html
import json
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "services" / "api"))

from nightshift.adapters.http import PoliteClient  # noqa: E402
from nightshift.config import Settings  # noqa: E402

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


def _content_text(job: dict[str, Any]) -> str:
    """Greenhouse ships the description as escaped HTML inside `content`.

    Unescaped twice on purpose: the payload is HTML-escaped, and the HTML it
    decodes to contains its own entities (`&amp;nbsp;` is common).
    """
    raw = job.get("content") or ""
    text = html.unescape(html.unescape(str(raw)))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def _mentions_doctorate(job: dict[str, Any]) -> bool:
    return bool(re.search(r"\b(ph\.?d|doctorate)\b", _content_text(job), re.I))


def _mentions_equivalence(job: dict[str, Any]) -> bool:
    """"or equivalent experience" — the escape hatch A13 names by hand."""
    return bool(re.search(r"\bor\s+(have\s+)?equivalent\b", _content_text(job), re.I))


def _mentions_sponsorship(job: dict[str, Any]) -> bool:
    return bool(re.search(r"\bsponsor(ship|ing|ed)?\b", _content_text(job), re.I))


def _states_graduation_year(job: dict[str, Any]) -> bool:
    """A graduation window stated numerically — "graduating in 2027"."""
    text = _content_text(job)
    return bool(re.search(r"graduat\w*[^.]{0,60}\b20\d{2}\b", text, re.I))


def _states_years_of_experience(job: dict[str, Any]) -> bool:
    return bool(re.search(r"\b\d{1,2}\s*\+?\s*years?\b", _content_text(job), re.I))


def _has_preferred_section(job: dict[str, Any]) -> bool:
    """The section whose contents must never become a gap."""
    return bool(
        re.search(
            r"(nice[- ]to[- ]have|bonus points|preferred qualifications|"
            r"pluses|it'?s a plus)",
            _content_text(job),
            re.I,
        )
    )


def _title_matches(job: dict[str, Any], pattern: str) -> bool:
    return bool(re.search(pattern, job.get("title", ""), re.I))


#: Chosen for *eligibility* shape. The existing GREENHOUSE_SELECTORS choose for
#: location shape, which was M1's invariant (I1) and is a different question.
#: Every reason here names a case AMENDMENTS A13 lists as genuinely hard.
ELIGIBILITY_SELECTORS: list[tuple[str, Callable[[dict[str, Any]], bool], int]] = [
    ("internship in the title",
     lambda j: _title_matches(j, r"\b(intern|internship|co-?op)\b"), 3),
    ("new grad / university programme in the title",
     lambda j: _title_matches(j, r"\b(new ?grad|university|campus|early career)\b"), 2),
    ("a graduation year stated numerically",
     _states_graduation_year, 3),
    ("sponsorship stated in writing",
     _mentions_sponsorship, 2),
    ("a doctorate named as a requirement",
     _mentions_doctorate, 2),
    ("'or equivalent experience' — the A13 escape hatch",
     _mentions_equivalence, 2),
    ("a numeric years-of-experience requirement",
     _states_years_of_experience, 3),
    ("a preferred / nice-to-have section, whose contents are not gaps",
     _has_preferred_section, 3),
    ("senior or above in the title — the seniority mismatch case",
     lambda j: _title_matches(j, r"\b(senior|staff|principal|lead|director|vp)\b"), 2),
    ("multi-level posting spanning an eligibility boundary",
     lambda j: _title_matches(j, r"\b(i{1,3}|1|2|3)\s*/\s*(i{1,3}|1|2|3)\b"), 1),
    ("non-engineering role at a technical employer",
     lambda j: not _title_matches(
         j, r"\b(engineer|developer|scientist|researcher|swe|programmer)\b"), 2),
]


def curate(
    jobs: list[dict[str, Any]],
    selectors: list[tuple[str, Callable[[dict[str, Any]], bool], int]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    selectors = selectors if selectors is not None else GREENHOUSE_SELECTORS
    picked: list[dict[str, Any]] = []
    chosen_ids: set[Any] = set()
    reasons: dict[str, str] = {}
    for why, predicate, limit in selectors:
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


def _reduce_lever(payload: Any, limit: int) -> tuple[Any, dict[str, str], list[str]]:
    """Pick a reviewable subset of a Lever board, preserving each job verbatim.

    Selection is by *shape*, not by sampling: one job per distinct location
    string, so the fixture covers every location convention the board uses
    rather than whichever nine came back first.
    """
    if not isinstance(payload, list):
        raise SystemExit(f"lever board did not return a JSON array: {type(payload).__name__}")

    kept: list[Any] = []
    reasons: dict[str, str] = {}
    seen_shapes: set[str] = set()

    for job in payload:
        categories = job.get("categories") or {}
        shape = f"{categories.get('location')}|{job.get('workplaceType')}"
        if shape in seen_shapes and len(kept) >= limit:
            continue
        if shape not in seen_shapes:
            reasons[str(job["id"])] = (
                f"location {categories.get('location')!r}, "
                f"workplaceType {job.get('workplaceType')!r}"
            )
            seen_shapes.add(shape)
            kept.append(job)
        elif len(kept) < limit:
            reasons[str(job["id"])] = "additional posting on the same board"
            kept.append(job)

    gaps: list[str] = []
    if not any((j.get("categories") or {}).get("commitment") == "Intern" for j in payload):
        gaps.append("internship commitment")
    if not any("New York" in str((j.get("categories") or {}).get("allLocations")) for j in payload):
        gaps.append("NYC location")
    return kept, reasons, gaps


def _reduce_ashby(payload: Any, limit: int) -> tuple[Any, dict[str, str], list[str]]:
    """Pick a reviewable subset of an Ashby board, preserving each job verbatim.

    Deliberately keeps one job per (location, employmentType) pair. The Ramp
    board is 123 postings and 95 of them share one location string; sampling
    the first N would produce a fixture that proves the adapter handles one
    shape twelve times.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise SystemExit("ashby board did not return {'jobs': [...]}")

    kept: list[Any] = []
    reasons: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()

    for job in payload["jobs"]:
        secondary = tuple(sorted(s.get("location", "") for s in job.get("secondaryLocations", [])))
        key = (f"{job.get('location')}|{secondary}", str(job.get("employmentType")))
        if key in seen or len(kept) >= limit:
            continue
        seen.add(key)
        reasons[str(job["id"])] = (
            f"location {job.get('location')!r}, "
            f"{len(secondary)} secondary, "
            f"employmentType {job.get('employmentType')!r}, "
            f"isRemote {job.get('isRemote')!r}"
        )
        kept.append(job)

    gaps: list[str] = []
    if not any(j.get("employmentType") == "Intern" for j in payload["jobs"]):
        gaps.append("internship employmentType")
    if not any(j.get("compensation", {}).get("compensationTiers") for j in payload["jobs"]):
        gaps.append("published compensation")
    return {"apiVersion": payload.get("apiVersion"), "jobs": kept}, reasons, gaps


#: Providers with a reducer wired up below.
_SUPPORTED_PROVIDERS = frozenset({"greenhouse", "lever", "ashby"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(ENDPOINTS))
    parser.add_argument("token", help="board token, e.g. datadog")
    parser.add_argument("--name", help="fixture basename (default: <token>_board)")
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="max postings kept per distinct shape (lever, ashby)",
    )
    parser.add_argument(
        "--profile",
        choices=("locations", "eligibility"),
        default="locations",
        help="which selector set to curate with (greenhouse only)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="fixture subdirectory (default: the provider name)",
    )
    args = parser.parse_args()

    if args.provider not in _SUPPORTED_PROVIDERS:
        print(f"curation selectors for {args.provider} arrive with its adapter (M1)", file=sys.stderr)
        return 2

    url = ENDPOINTS[args.provider].format(token=args.token)
    print(f"GET {url}")
    payload = asyncio.run(fetch(url))

    fixture_body: Any
    reasons: dict[str, str]
    missing: list[str]
    full_count: int

    if args.provider == "greenhouse":
        jobs = payload.get("jobs") or []
        if not jobs:
            print("board returned no jobs — refusing to write an empty fixture", file=sys.stderr)
            return 1
        selectors = (
            ELIGIBILITY_SELECTORS if args.profile == "eligibility"
            else GREENHOUSE_SELECTORS
        )
        picked, reasons = curate(jobs, selectors)
        missing = [why for why, _, _ in selectors if why not in reasons.values()]
        full_count = payload.get("meta", {}).get("total", len(jobs))
        fixture_body = {"jobs": picked, "meta": {"total": len(picked)}}
    elif args.provider == "lever":
        if not payload:
            print(
                "board returned no postings — refusing to write an empty fixture "
                "(this case is recorded by hand; see the task brief)",
                file=sys.stderr,
            )
            return 1
        picked, reasons, missing = _reduce_lever(payload, args.limit)
        full_count = len(payload)
        fixture_body = picked
    else:  # ashby
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not jobs:
            print("board returned no jobs — refusing to write an empty fixture", file=sys.stderr)
            return 1
        fixture_body, reasons, missing = _reduce_ashby(payload, args.limit)
        full_count = len(jobs)
        picked = fixture_body["jobs"]

    basename = args.name or f"{args.token}_board"
    out_dir = FIXTURE_ROOT / (args.out_dir or args.provider)
    out_dir.mkdir(parents=True, exist_ok=True)

    fixture_path = out_dir / f"{basename}.json"
    fixture_path.write_text(json.dumps(fixture_body, indent=2, ensure_ascii=False) + "\n")

    meta_path = out_dir / f"{basename}.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "provenance": {
                    "endpoint": url,
                    "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "board_token": args.token,
                    "http_status": 200,
                    "full_response_job_count": full_count,
                    "note": (
                        f"Each job object is byte-identical to the live response. Only the set "
                        f"of jobs was reduced ({full_count} -> {len(picked)}); nothing inside a "
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
