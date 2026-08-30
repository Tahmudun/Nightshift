"""Discovery CLI: ``discover``, ``validate``, ``approve``.

Three commands, run by a human. **None of them is scheduled** — A1 and ADR 0006
both say discovery is a decision somebody makes, not a cron entry, because it
ends in a change to a committed file that a person has to read.

The split between them is the safety property worth understanding:

* ``discover`` reads a **committed crawl fixture** and writes candidates. It
  touches no network unless ``--live`` is passed, and ``--live`` additionally
  requires ``OUTBOUND_HTTP_ENABLED=true``, so the default path is offline.
* ``validate`` is the only command that must reach providers. It updates
  verdicts in the candidate file and nothing else.
* ``approve`` is **dry-run by default**. It prints the report; only ``--write``
  edits ``data/board-registry.yaml``, and even then a human commits the diff.
* ``coverage`` reads both files and prints what is covered and what is not. It
  writes nothing and exits 0 either way — it is a report, not a check.

Nothing here writes to a table ingestion reads. A Common Crawl outage produces
no candidates and never a modified registry (I3).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import urllib.parse
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select

from nightshift.adapters.http import MAX_TEXT_BYTES, PoliteClient
from nightshift.config import get_settings
from nightshift.db.base import SourceType
from nightshift.db.models import Source, SourceJobRecord
from nightshift.db.session import session_scope
from nightshift.discovery.approve import approvable, approval_report, promote
from nightshift.discovery.candidates import (
    DEFAULT_PATH,
    load_candidates,
    merge_candidate,
    save_candidates,
)
from nightshift.discovery.coverage import coverage_summary, format_coverage
from nightshift.discovery.models import Candidate, Verdict
from nightshift.discovery.sources.crawl_index import (
    CDX_URL,
    CRAWL_ID,
    PROVIDER_PATTERNS,
    tokens_from_cdx,
)
from nightshift.discovery.sources.list_urls import tokens_from_listing_urls
from nightshift.discovery.validate import validate_token
from nightshift.domain.companies import normalize_company_name
from nightshift.domain.registry import DEFAULT_REGISTRY_PATH, get_registry, load_registry
from nightshift.logging import configure_logging

#: Which host each provider's tokens live under. Kept beside the patterns
#: rather than derived from them: the pattern is a CDX query and the host is a
#: check we apply to the results, and conflating them is how a subdomain we did
#: not mean gets harvested.
PROVIDER_HOSTS = {
    "greenhouse": "boards.greenhouse.io",
    "ashby": "jobs.ashbyhq.com",
}

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "crawl"


def _today() -> date:
    return datetime.now(tz=UTC).date()


def _crawl_fixture(provider: str) -> Path:
    return FIXTURE_ROOT / f"{provider}_{CRAWL_ID.lower().replace('-', '_')}.jsonl"


async def _discover_from_lists(args: argparse.Namespace) -> int:
    """Harvest tokens out of the URLs the internship lists already gave us.

    the-hunt.md §5.3. Reads `source_job_records.raw_payload` for the two list
    sources — no network, because the payloads are already stored — and mines
    each entry's `url` for a board token.

    This is discovery aimed at companies that **demonstrably hire interns**,
    which is a far better filter for this reader than a Common Crawl sweep of
    every company that has ever had a job board. It feeds the same
    `discover` -> `validate` -> `approve` chain, with no new approval
    machinery: ADR 0005's rules apply unchanged, including that a live board
    whose employer cannot be named never reaches bulk approval.
    """
    urls: list[str] = []
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(SourceJobRecord.raw_payload)
                .join(Source, Source.id == SourceJobRecord.source_id)
                .where(Source.source_type == SourceType.INTERNSHIP_LIST)
            )
        ).scalars()
        for payload in rows:
            if isinstance(payload, dict):
                url = payload.get("url")
                if isinstance(url, str):
                    urls.append(url)

    if not urls:
        print(
            "no internship-list records are stored yet. Run `make ingest` first — "
            "this reads what the lists already gave us, and asks no provider anything.",
            file=sys.stderr,
        )
        return 2

    pairs = tokens_from_listing_urls(urls)
    file = load_candidates(args.candidates)
    today = _today()
    known = {candidate.key for candidate in file.candidates}
    registry_known = {(entry.ats, entry.token) for entry in get_registry().boards}
    added = 0
    already_registered = 0
    for ats, token in pairs:
        if (ats, token) in registry_known:
            already_registered += 1
            continue
        if (ats, token) in known:
            continue
        file = merge_candidate(
            file,
            Candidate(
                ats=ats,
                token=token,
                verdict=Verdict.UNVALIDATED,
                first_seen=today,
                # Not `today`: nothing has validated this. See cmd_discover.
                last_validated=date.min,
                source="list_urls",
                notes="mined from an internship-list entry's URL; no provider has been asked yet",
            ),
        )
        added += 1

    save_candidates(file, args.candidates)
    print(
        f"{len(urls)} list URLs -> {len(pairs)} distinct (ats, token) pairs; "
        f"{already_registered} already in the registry, {added} new candidate(s), "
        f"{len(file.candidates)} total."
    )
    print("Nothing is in the registry yet. Next: `make registry-validate`.")
    return 0


async def cmd_discover(args: argparse.Namespace) -> int:
    """Harvest tokens into the candidate file. Offline unless --live."""
    if getattr(args, "from_lists", False):
        return await _discover_from_lists(args)

    provider = args.provider
    if provider not in PROVIDER_PATTERNS:
        # Named rather than silently empty: `lever` is the one somebody will
        # try, and it is absent for a structural reason (ADR 0006).
        print(
            f"no crawl pattern for {provider!r}. Known: {', '.join(sorted(PROVIDER_PATTERNS))}.\n"
            "Lever is deliberately absent — jobs.lever.co/robots.txt disallows CCBot, so the "
            "archive holds no Lever pages and never will. Lever boards are found by "
            "careers-page probing (ADR 0006).",
            file=sys.stderr,
        )
        return 2

    host = PROVIDER_HOSTS[provider]

    if args.live:
        settings = get_settings()
        if not settings.outbound_http_enabled:
            print(
                "--live needs OUTBOUND_HTTP_ENABLED=true. Without it, discovery reads the "
                "committed crawl fixture, which is the offline default.",
                file=sys.stderr,
            )
            return 2
        lines: list[str] = []
        async with PoliteClient(settings) as client:
            for pattern in PROVIDER_PATTERNS[provider]:
                url = CDX_URL.format(
                    crawl=CRAWL_ID,
                    pattern=urllib.parse.quote(pattern, safe=""),
                    limit=args.limit,
                )
                print(f"GET {url}")
                body = await client.get_text(url)
                if len(body.encode()) >= MAX_TEXT_BYTES:
                    # get_text truncates rather than raising, which is right for
                    # a board page and wrong to pass over in silence here: a
                    # truncated index is a partial harvest, and a partial
                    # harvest that looks complete is how a board goes missing.
                    print(
                        f"  WARNING: response hit the {MAX_TEXT_BYTES}-byte read cap and was "
                        "truncated. Lower --limit and run again; this harvest is incomplete.",
                        file=sys.stderr,
                    )
                lines.extend(body.splitlines())
        source = f"crawl_index (live {CRAWL_ID})"
    else:
        fixture = _crawl_fixture(provider)
        if not fixture.exists():
            print(f"no committed crawl fixture at {fixture}", file=sys.stderr)
            return 2
        lines = fixture.read_text().splitlines()
        source = "crawl_index"

    tokens = tokens_from_cdx(lines, host=host)
    file = load_candidates(args.candidates)
    today = _today()
    known = {candidate.key for candidate in file.candidates}
    added = 0
    for token in tokens:
        if (provider, token) in known:
            continue
        file = merge_candidate(
            file,
            Candidate(
                ats=provider,
                token=token,
                verdict=Verdict.UNVALIDATED,
                first_seen=today,
                # Not `today`: nothing has validated this. Carrying the harvest
                # date here would make a never-contacted board look freshly
                # checked to anything that ages candidates by this field.
                last_validated=date.min,
                source=source,
                notes="harvested from a crawl index; no provider has been asked yet",
            ),
        )
        added += 1

    save_candidates(file, args.candidates)
    print(
        f"{len(lines)} crawl rows -> {len(tokens)} distinct tokens; "
        f"{added} new candidate(s), {len(file.candidates)} total."
    )
    print("Nothing is in the registry yet. Next: `make registry-validate`.")
    return 0


async def cmd_validate(args: argparse.Namespace) -> int:
    """Probe candidates and classify them. The only command that needs network."""
    settings = get_settings()
    if not settings.outbound_http_enabled:
        print(
            "validation asks each provider whether a board is live and who it belongs to, "
            "so it needs OUTBOUND_HTTP_ENABLED=true.",
            file=sys.stderr,
        )
        return 2

    file = load_candidates(args.candidates)
    if not file.candidates:
        print("no candidates to validate. Run `make discover` first.")
        return 0

    registry = load_registry(args.registry)
    known_names = frozenset(
        normalize_company_name(board.company) for board in registry.boards if board.company.strip()
    )

    pending = [c for c in file.candidates if c.verdict is not Verdict.LIVE_NAMED]
    targets = pending[: args.limit] if args.limit else pending
    today = _today()
    counts: dict[Verdict, int] = dict.fromkeys(Verdict, 0)

    async with PoliteClient(settings) as client:
        for candidate in targets:
            result = await validate_token(
                client,
                ats=candidate.ats,
                token=candidate.token,
                today=today,
                known_names=known_names,
                source=candidate.source,
            )
            counts[result.verdict] += 1
            file = merge_candidate(file, result)
            # Saved as we go: a sweep of thousands can be interrupted, and
            # losing every verdict because the last board timed out would make
            # the command unusable at the size it exists for.
            save_candidates(file, args.candidates)

    print(f"validated {len(targets)} candidate(s):")
    for verdict, count in counts.items():
        if count:
            print(f"  {verdict.value:<15} {count}")
    return 0


async def cmd_approve(args: argparse.Namespace) -> int:
    """Print the approval report. Writes the registry only with --write."""
    file = load_candidates(args.candidates)
    registry_path = args.registry or DEFAULT_REGISTRY_PATH
    registry = load_registry(registry_path)
    existing = frozenset((board.ats, board.token) for board in registry.boards)

    eligible = approvable(file, registry_tokens=existing)
    print(approval_report(eligible))

    held = [c for c in file.candidates if c.verdict is not Verdict.LIVE_NAMED]
    if held:
        print(f"\n{len(held)} candidate(s) held for individual review (ADR 0005):")
        for verdict in Verdict:
            count = sum(1 for c in held if c.verdict is verdict)
            if count:
                print(f"  {verdict.value:<15} {count}")

    # Named explicitly rather than left as a silent absence from the table
    # above. These validated `live_named` and would look approvable to anyone
    # reading the candidate file; the only reason they are missing from the
    # report is a collision the verdict could not see, and an operator who is
    # not told that will conclude the board was never discovered.
    approved_keys = {candidate.key for candidate in eligible}
    withheld = [
        candidate
        for candidate in file.candidates
        if candidate.verdict is Verdict.LIVE_NAMED
        and candidate.key not in approved_keys
        and candidate.key not in existing
    ]
    if withheld:
        print(
            f"\n{len(withheld)} live, named candidate(s) withheld because two or more "
            "of them name the same employer:"
        )
        for candidate in sorted(withheld, key=lambda c: (c.company_name or "", c.ats, c.token)):
            print(
                f"  {(candidate.company_name or ''):<34.34} {candidate.ats:<11} {candidate.token}"
            )
        print(
            "  One employer, more than one board. Which to poll — or whether these are "
            "genuinely different companies — is a human's call (ADR 0005)."
        )

    if not args.write:
        print("\nDry run. Nothing was written. Re-run with --write to edit the registry.")
        return 0

    count, _ = promote(file, registry_path=registry_path, today=_today())
    print(f"\npromoted {count} board(s) into {registry_path}")
    if count:
        print("Read the diff and commit it yourself — this command does not.")
    return 0


async def cmd_coverage(args: argparse.Namespace) -> int:
    """Print what is covered and, more importantly, what is not."""
    print(
        format_coverage(
            coverage_summary(
                candidates=load_candidates(args.candidates),
                registry=load_registry(args.registry),
            )
        )
    )
    return 0


COMMANDS = {
    "discover": cmd_discover,
    "validate": cmd_validate,
    "approve": cmd_approve,
    "coverage": cmd_coverage,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightshift-discovery", description=__doc__)
    parser.add_argument(
        "--candidates",
        type=Path,
        default=DEFAULT_PATH,
        help="candidate file (default: data/board-candidates.yaml)",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help="registry file (default: data/board-registry.yaml)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="harvest board tokens into the candidates")
    discover.add_argument("--provider", default="ashby", help="ashby | greenhouse")
    discover.add_argument(
        "--live",
        action="store_true",
        help="re-query Common Crawl instead of reading the committed fixture",
    )
    discover.add_argument("--limit", type=int, default=400, help="CDX row limit for --live")
    discover.add_argument(
        "--from-lists",
        action="store_true",
        help=(
            "mine tokens from the stored internship-list payloads instead of a crawl "
            "index. Reads the database, asks no provider anything, needs no network."
        ),
    )

    validate = subparsers.add_parser("validate", help="probe candidates and classify them")
    validate.add_argument("--limit", type=int, default=0, help="stop after N candidates (0 = all)")

    approve = subparsers.add_parser("approve", help="show the approval report")
    approve.add_argument(
        "--write",
        action="store_true",
        help="actually promote approved candidates into the registry",
    )

    subparsers.add_parser("coverage", help="print what is and is not covered")

    args = parser.parse_args(argv)
    configure_logging()
    return asyncio.run(COMMANDS[args.command](args))


if __name__ == "__main__":
    sys.exit(main())
