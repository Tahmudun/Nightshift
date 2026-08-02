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

Nothing here writes to a table ingestion reads. A Common Crawl outage produces
no candidates and never a modified registry (I3).

``coverage`` is deliberately not here yet: the numbers it prints are computed
in M1c Task 5, and a subcommand that exists before its data would be a mock
wearing a command's name (I7).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import urllib.parse
from datetime import UTC, date, datetime
from pathlib import Path

from nightshift.adapters.http import MAX_TEXT_BYTES, PoliteClient
from nightshift.config import get_settings
from nightshift.discovery.approve import approvable, approval_report, promote
from nightshift.discovery.candidates import (
    DEFAULT_PATH,
    load_candidates,
    merge_candidate,
    save_candidates,
)
from nightshift.discovery.models import Candidate, Verdict
from nightshift.discovery.sources.crawl_index import (
    CDX_URL,
    CRAWL_ID,
    PROVIDER_PATTERNS,
    tokens_from_cdx,
)
from nightshift.discovery.validate import validate_token
from nightshift.domain.companies import normalize_company_name
from nightshift.domain.registry import DEFAULT_REGISTRY_PATH, load_registry
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


async def cmd_discover(args: argparse.Namespace) -> int:
    """Harvest tokens into the candidate file. Offline unless --live."""
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

    if not args.write:
        print("\nDry run. Nothing was written. Re-run with --write to edit the registry.")
        return 0

    count, _ = promote(file, registry_path=registry_path, today=_today())
    print(f"\npromoted {count} board(s) into {registry_path}")
    if count:
        print("Read the diff and commit it yourself — this command does not.")
    return 0


COMMANDS = {
    "discover": cmd_discover,
    "validate": cmd_validate,
    "approve": cmd_approve,
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

    validate = subparsers.add_parser("validate", help="probe candidates and classify them")
    validate.add_argument("--limit", type=int, default=0, help="stop after N candidates (0 = all)")

    approve = subparsers.add_parser("approve", help="show the approval report")
    approve.add_argument(
        "--write",
        action="store_true",
        help="actually promote approved candidates into the registry",
    )

    args = parser.parse_args(argv)
    configure_logging()
    return asyncio.run(COMMANDS[args.command](args))


if __name__ == "__main__":
    sys.exit(main())
