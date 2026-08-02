"""Record a Common Crawl CDX response as a committed fixture.

Run by a human, never by a test. Common Crawl's index is a free public service
and this issues exactly one request per invocation, with the project
User-Agent.

    python3 scripts/record_crawl_fixture.py ashby --limit 400
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

CRAWL = "CC-MAIN-2026-30"
CDX = "https://index.commoncrawl.org/{crawl}-index?url={pattern}&output=json&fl=url&limit={limit}"
USER_AGENT = "Nightshift/0.1 (+https://github.com/Tahmudun/Nightshift)"

PATTERNS = {
    "ashby": "jobs.ashbyhq.com/*",
    "greenhouse": "boards.greenhouse.io/*",
    "greenhouse_new": "job-boards.greenhouse.io/*",
    # Deliberately absent: lever. jobs.lever.co/robots.txt disallows CCBot, so
    # the archive holds no Lever job pages and never will (ADR 0006). Recording
    # an empty response would look like a transient miss rather than a
    # structural one, so the recorder refuses to offer the option at all.
}

OUT = Path(__file__).parent.parent / "services/api/tests/fixtures/crawl"


def _ssl_context() -> ssl.SSLContext:
    """A context with a CA bundle that actually exists.

    A python.org install on macOS ships no system CA bundle until someone runs
    `Install Certificates.command`, and until then every https request here
    fails with CERTIFICATE_VERIFY_FAILED while curl works fine — which reads as
    a network problem and is not one. certifi comes in with httpx, so it is
    already present; falling back to the default context keeps this working on
    a machine that is set up properly.
    """
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=sorted(PATTERNS))
    parser.add_argument("--limit", type=int, default=400)
    args = parser.parse_args()

    pattern = PATTERNS[args.provider]
    url = CDX.format(crawl=CRAWL, pattern=urllib.parse.quote(pattern, safe=""), limit=args.limit)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=180, context=_ssl_context()) as response:  # noqa: S310
        status = response.status
        body = response.read().decode("utf-8")

    if status != 200:
        raise SystemExit(f"CDX returned {status}")

    lines = [line for line in body.splitlines() if line.strip()]
    if not lines:
        raise SystemExit(
            f"CDX returned no rows for {pattern!r}. That is a finding, not a "
            "fixture — record why before committing anything."
        )

    OUT.mkdir(parents=True, exist_ok=True)
    stem = f"{args.provider}_{CRAWL.lower().replace('-', '_')}"
    (OUT / f"{stem}.jsonl").write_text("\n".join(lines) + "\n")
    (OUT / f"{stem}.meta.json").write_text(
        json.dumps(
            {
                "provenance": {
                    "endpoint": url,
                    "recorded_at": datetime.now(tz=UTC).isoformat(),
                    "board_token": f"(pattern) {pattern}",
                    "http_status": status,
                    "crawl": CRAWL,
                    "rows": len(lines),
                    "limit": args.limit,
                    "note": (
                        "Truncated by --limit. This is a reviewable slice of the index, "
                        "not the whole of it; any token count derived from it is a count "
                        "for this slice and must be labelled as such. Nothing was edited: "
                        "these are the response's lines verbatim, blank lines dropped."
                    ),
                },
                "why_each_job_is_here": {},
                "coverage_not_available_on_this_board": [
                    "lever - jobs.lever.co/robots.txt disallows CCBot, so no Lever "
                    "page is in this or any Common Crawl index (ADR 0006)"
                ],
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {stem}.jsonl — {len(lines)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
