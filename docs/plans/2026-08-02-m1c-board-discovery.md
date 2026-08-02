# M1c — Board discovery: filling the registry with a pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The board registry stops being a hand-written list and becomes the
reviewed output of a discovery pipeline — candidates harvested from Common
Crawl, classified by probing the provider, and promoted only by an explicit
human command.

**Architecture:** A new `nightshift/discovery/` package that ingestion never
imports. Three front-ends (crawl index, careers-page probe, committed community
snapshots) feed one validation-and-approval path. Everything writes to
`data/board-candidates.yaml`; only `make registry-approve` writes
`data/board-registry.yaml`, and a human commits the diff.

**Tech Stack:** Python 3.12, Pydantic v2, `PoliteClient` (the only module that
may import httpx), pytest, ruff, mypy strict. No database — discovery is file
and network only.

**Design:** `docs/architecture/board-discovery.md`, which is the approved
design and the only complete statement of it. **ADR 0005** (batch approval,
overriding A1's per-entry review), **ADR 0006** (Common Crawl, and why it is
structurally blind to Lever), **ADR 0007** (two-phase polling — M1d, but its
tier rules are read here). Read §4, §5, §6 and §13 before Task 1.

---

## Where this sits

| Plan | Contents | Status |
|---|---|---|
| M1a — provider breadth | Lever + Ashby adapters, parser breadth, upserts | **Merged** `54ef35a` |
| M1b — canonical spine | Dedupe, freshness, closure, admin table | **Merged** `cf48719` |
| **M1c — board discovery** (this) | `nightshift/discovery/`, Common Crawl, validation, batch approval, coverage page | Ready |
| M1d — polling | Two-phase conditional polling, hot/warm tiers, queue-driven ARQ | Not written — design at ADR 0007 |

All three of `board-discovery.md` §14's prerequisites are done: parser breadth
(M1a), the upserts (M1a), and tests for `domain/ingestion.py` and the routes
(M1a/M1b). Nothing blocks this plan.

---

## Global Constraints

Every task's requirements implicitly include these.

- **I2 — never fabricate a qualification, and by extension never fabricate an
  employer.** An employer name comes from the provider or from the domain that
  led us to the board. Deriving it from the token is the failure this milestone
  is built to prevent: Ashby's `0g` is "0g Labs".
- **I3 — never silently close a listing.** Discovery never writes to a table
  ingestion reads. A Common Crawl outage produces no candidates and never a
  modified registry. `empty` and `unreachable` are not rejections.
- **I6 — record evidence, not intentions.** The coverage page reports what was
  measured. A missing number is worse than a low one.
- **I7 — no mock becomes the product.** Every recorded response is committed
  with a `*.meta.json` stating its provenance, per the pattern M1a established.
- **Nothing outside `nightshift/adapters/http.py` imports `httpx`.** Discovery
  reaches the network only through `PoliteClient`.
- **`OUTBOUND_HTTP_ENABLED` defaults to `false`.** Tests never reach the
  network. Only the recorder scripts and `make discover` enable it, and only
  when a human runs them.
- **Discovery is never scheduled.** It is a `make` target, not an ARQ cron
  (A1, ADR 0006). No task in this plan adds a cron entry.
- **mypy strict must pass**; `make check` before every commit; conventional
  commits, scoped.
- **TODOs carry a milestone**: `TODO(M1d): ...`.

---

## Facts this plan is built on

Re-verified **2026-08-02**, not inherited. `board-discovery.md` §3 says to
re-verify before relying on its numbers, and this is that check.

**Common Crawl is reachable and the measured crawl is still current.**
`GET https://index.commoncrawl.org/collinfo.json` → HTTP 200, 34,675 bytes,
**126 collections**, newest `CC-MAIN-2026-30` ("July 2026 Index") — the same
crawl §3's token counts were measured against. No re-measurement of the 2,605
figure is required by this plan, but Task 1 records what it actually harvests
rather than restating the design's number.

**The CDX query shape works and returns what the design assumes.**
`GET /CC-MAIN-2026-30-index?url=jobs.ashbyhq.com%2F*&output=json&fl=url&limit=8`
returns newline-delimited JSON objects, one per captured URL:

```json
{"url": "https://jobs.ashbyhq.com/0g"}
{"url": "https://jobs.ashbyhq.com/0g/1554138f-15dc-4225-93cc-44b64f2540ed"}
{"url": "https://jobs.ashbyhq.com/0x/08631de8-.../application?source=chainhire.careers"}
```

Three properties of that output drive Task 1's parser, and all three are
visible in those three lines:

1. **The token is the first path segment**, and most URLs are job pages beneath
   it, not board roots. Extraction is "take segment 1", then deduplicate.
2. **Query strings are noise** — `utm_source`, `ref`, `gh_src`, `source` all
   appear. They are already handled by `normalize_url` in
   `nightshift/domain/dedupe.py`, which this plan reuses rather than
   reimplements.
3. **Sub-paths exist that are not tokens** — `/application` appears as a
   segment *after* the token, never as one. A parser taking the last segment
   would harvest UUIDs; a parser taking the first is correct.

**`0g` is in the live index**, which is the case ADR 0005's approval gate turns
on: the token is not the name, and the board page says "0g Labs".

**The three prerequisites in §14 are complete**, verified against the merged
`main` at `cf48719`: `parse_location_list` handles all three providers,
`get_or_create_company`/`get_or_create_source` are `ON CONFLICT` upserts, and
`test_ingestion.py`/`test_routes.py` exist with 55 database-backed tests.

**Reused rather than rebuilt** — checked to exist at `cf48719`:

| Thing | Where | Used for |
|---|---|---|
| `PoliteClient` | `adapters/http.py` | Every network call in this plan |
| `normalize_url` | `domain/dedupe.py` | Stripping tracking params from CDX URLs |
| `normalize_company_name` | `domain/companies.py` | The `name_collision` verdict |
| `BoardEntry`, `BoardRegistry`, `load_registry` | `domain/registry.py` | Approval writes these |
| `SourceUnavailableError`, `FetchOutcome` | `adapters/base.py` | The I3 distinction, unchanged |

---

## File Structure

**Create**

| Path | Responsibility |
|---|---|
| `services/api/nightshift/discovery/__init__.py` | Package marker |
| `services/api/nightshift/discovery/models.py` | `Candidate`, `CandidateVerdict`, `CandidateFile` |
| `services/api/nightshift/discovery/sources/crawl_index.py` | CDX response → tokens. No provider knowledge |
| `services/api/nightshift/discovery/sources/careers_probe.py` | Domain → careers page → embedded Lever board |
| `services/api/nightshift/discovery/validate.py` | `(ats, token)` → `CandidateVerdict`. The only module here that talks to a provider |
| `services/api/nightshift/discovery/candidates.py` | Read/write `data/board-candidates.yaml` |
| `services/api/nightshift/discovery/approve.py` | Promote candidates into the registry. Pure file work |
| `services/api/nightshift/discovery/cli.py` | `discover`, `validate`, `approve`, `coverage` |
| `services/api/tests/discovery/test_crawl_index.py` | Token extraction, deterministic |
| `services/api/tests/discovery/test_validate.py` | The five verdicts, incl. `a3c41b8b71eff8c4` |
| `services/api/tests/discovery/test_approve.py` | The bulk gate, and what it refuses |
| `services/api/tests/discovery/test_coverage.py` | Named blind spots |
| `services/api/tests/fixtures/crawl/*.jsonl` + `.meta.json` | Recorded CDX responses |
| `services/api/tests/fixtures/discovery/*.json` + `.meta.json` | Recorded board + board-page responses |
| `data/board-candidates.yaml` | The candidate file, committed |
| `apps/web/src/app/analyze/coverage/page.tsx` | The coverage page |

**Modify**

| Path | Change |
|---|---|
| `services/api/nightshift/api/routes/sources.py` | `GET /coverage` |
| `services/api/nightshift/api/schemas.py` | `CoverageOut` and its parts |
| `apps/web/src/lib/schemas.ts`, `api.ts` | Zod + client for coverage |
| `Makefile` | `discover`, `registry-validate`, `registry-approve`, `coverage` |
| `docs/PROGRESS.md` | Evidence, "Not real yet", session log |

---

## Task 1: Harvest tokens from a recorded crawl index

**Files:**
- Create: `services/api/nightshift/discovery/__init__.py`, `sources/__init__.py`
- Create: `services/api/nightshift/discovery/sources/crawl_index.py`
- Create: `services/api/tests/discovery/__init__.py`, `test_crawl_index.py`
- Create: `services/api/tests/fixtures/crawl/ashby_cc_main_2026_30.jsonl` + `.meta.json`
- Create: `scripts/record_crawl_fixture.py`

**Interfaces:**
- Produces:
  - `PROVIDER_PATTERNS: dict[str, tuple[str, ...]]` — ats → CDX url patterns
  - `tokens_from_cdx(lines: Iterable[str], *, host: str) -> list[str]`
  - `CDX_URL: str` template
  - Consumed by Task 4's CLI.

- [ ] **Step 1: Write the recorder**

Follows `scripts/record_fixture.py`'s conventions (provenance block, meta file).
Read it first: `sed -n 1,80p scripts/record_fixture.py`.

```python
# scripts/record_crawl_fixture.py
"""Record a Common Crawl CDX response as a committed fixture.

Run by a human, never by a test. Common Crawl's index is a free public service
and this issues exactly one request per invocation, with the project
User-Agent.

    python scripts/record_crawl_fixture.py ashby --limit 400
"""

from __future__ import annotations

import argparse
import json
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
    # structural one, so the recorder refuses instead.
}

OUT = Path(__file__).parent.parent / "services/api/tests/fixtures/crawl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=sorted(PATTERNS))
    parser.add_argument("--limit", type=int, default=400)
    args = parser.parse_args()

    pattern = PATTERNS[args.provider]
    url = CDX.format(
        crawl=CRAWL, pattern=urllib.parse.quote(pattern, safe=""), limit=args.limit
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
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
                        "Truncated by --limit. This is a reviewable slice of the "
                        "index, not the whole of it; token counts derived from it "
                        "are counts for this slice and are labelled as such."
                    ),
                },
                "why_each_job_is_here": {},
                "coverage_not_available_on_this_board": [],
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {stem}.jsonl — {len(lines)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Record the Ashby slice**

```bash
python3 scripts/record_crawl_fixture.py ashby --limit 400
```

Expected: ~400 rows written. Confirm `0g` appears — it is the case Task 3's
approval gate turns on:

```bash
grep -c "" services/api/tests/fixtures/crawl/ashby_cc_main_2026_30.jsonl
grep -o 'ashbyhq.com/[^/"?]*' services/api/tests/fixtures/crawl/ashby_cc_main_2026_30.jsonl \
  | sort -u | head -10
```

If `0g` is absent, raise `--limit` and re-record. Do not hand-add it.

- [ ] **Step 3: Write the failing test**

```python
# services/api/tests/discovery/test_crawl_index.py
"""Token extraction from a recorded Common Crawl index slice.

The fixture is a real recorded response. Its shape is the whole reason this
module is not a one-line regex: most captured URLs are *job pages beneath* a
board, not board roots, and they carry tracking parameters. Taking the last
path segment would harvest UUIDs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nightshift.discovery.sources.crawl_index import (
    PROVIDER_PATTERNS,
    tokens_from_cdx,
)

FIXTURE = (
    Path(__file__).parent.parent
    / "fixtures"
    / "crawl"
    / "ashby_cc_main_2026_30.jsonl"
)


def _lines() -> list[str]:
    return FIXTURE.read_text().splitlines()


def test_extracts_the_first_path_segment_as_the_token() -> None:
    tokens = tokens_from_cdx(_lines(), host="jobs.ashbyhq.com")
    assert tokens
    assert "0g" in tokens, "the ADR 0005 case is missing; re-record with a higher limit"


def test_never_harvests_a_job_id_as_a_token() -> None:
    """Job pages live beneath the board: jobs.ashbyhq.com/{token}/{uuid}.

    A parser taking the last segment would return the uuid, and the registry
    would fill with boards that do not exist.
    """
    tokens = tokens_from_cdx(_lines(), host="jobs.ashbyhq.com")
    for token in tokens:
        assert "-" not in token or len(token) < 36, f"looks like a job id: {token}"
        assert token not in {"application", "api"}


def test_tracking_parameters_do_not_create_duplicate_tokens() -> None:
    lines = [
        '{"url": "https://jobs.ashbyhq.com/acme"}',
        '{"url": "https://jobs.ashbyhq.com/acme?utm_source=x"}',
        '{"url": "https://jobs.ashbyhq.com/acme/1234?ref=y"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["acme"]


def test_a_url_on_another_host_is_ignored() -> None:
    """The CDX response is filtered by pattern server-side, but a pattern can
    match a subdomain we did not mean. The host check is ours, not theirs."""
    lines = [
        '{"url": "https://jobs.ashbyhq.com/real"}',
        '{"url": "https://evil.jobs.ashbyhq.com.attacker.test/fake"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["real"]


def test_the_board_root_alone_is_enough() -> None:
    lines = ['{"url": "https://jobs.ashbyhq.com/solo"}']
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["solo"]


def test_a_bare_host_yields_nothing() -> None:
    """No path segment means no token. Returning "" would put an empty token in
    the registry and produce a request to the provider's root."""
    lines = [
        '{"url": "https://jobs.ashbyhq.com"}',
        '{"url": "https://jobs.ashbyhq.com/"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == []


def test_malformed_lines_are_skipped_not_fatal() -> None:
    """One bad line in a 400-row response must not lose the other 399."""
    lines = [
        "not json at all",
        '{"no_url_key": 1}',
        '{"url": "https://jobs.ashbyhq.com/survivor"}',
    ]
    assert tokens_from_cdx(lines, host="jobs.ashbyhq.com") == ["survivor"]


def test_is_deterministic_and_sorted() -> None:
    """board-discovery.md §13: same input, same token set, twice.

    Sorted rather than insertion-ordered, so the candidate file's diff is
    reviewable — an unordered set would reshuffle the whole file on every run.
    """
    first = tokens_from_cdx(_lines(), host="jobs.ashbyhq.com")
    second = tokens_from_cdx(_lines(), host="jobs.ashbyhq.com")
    assert first == second == sorted(first)


def test_lever_has_no_crawl_pattern() -> None:
    """ADR 0006, asserted rather than commented.

    jobs.lever.co/robots.txt disallows CCBot, so Lever job pages are not in the
    archive and never will be. A pattern here would produce a permanently empty
    harvest that reads as a transient miss.
    """
    assert "lever" not in PROVIDER_PATTERNS
```

- [ ] **Step 4: Run to verify it fails**

Run: `cd services/api && pytest tests/discovery/test_crawl_index.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nightshift.discovery'`.

- [ ] **Step 5: Write the module**

```python
# services/api/nightshift/discovery/sources/crawl_index.py
"""Common Crawl's URL index as a source of board tokens (ADR 0006).

This module knows about URLs and nothing else: no provider APIs, no database,
no notion of what a "board" is beyond "the first path segment". That boundary
is what lets it be tested against a recorded file with no network at all.

**Lever is absent on purpose.** `jobs.lever.co/robots.txt` names CCBot —
Common Crawl's crawler — and disallows it, so Lever job pages are not in the
archive and never will be. Lever boards are found by careers-page probing
instead. A pattern here would harvest zero tokens forever and look like a bug.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Final
from urllib.parse import urlsplit

CRAWL_ID: Final = "CC-MAIN-2026-30"

CDX_URL: Final = (
    "https://index.commoncrawl.org/{crawl}-index?url={pattern}&output=json&fl=url&limit={limit}"
)

# ats -> the URL patterns that find its boards. Greenhouse serves two board
# domains and the newer one contributed 433 tokens the older one did not
# (board-discovery.md §3), so both are queried.
PROVIDER_PATTERNS: Final[dict[str, tuple[str, ...]]] = {
    "greenhouse": ("boards.greenhouse.io/*", "job-boards.greenhouse.io/*"),
    "ashby": ("jobs.ashbyhq.com/*",),
}

# Path segments that are never a board token. `application` appears *after* a
# token on Ashby apply URLs; the others are provider infrastructure.
_NOT_TOKENS: Final = frozenset({"", "application", "api", "assets", "static", "favicon.ico"})


def tokens_from_cdx(lines: Iterable[str], *, host: str) -> list[str]:
    """Extract distinct board tokens from a CDX response.

    The response is newline-delimited JSON, one object per captured URL, and
    most of those URLs are job pages *beneath* a board rather than board roots:

        {"url": "https://jobs.ashbyhq.com/0g"}
        {"url": "https://jobs.ashbyhq.com/0g/1554138f-15dc-..."}

    So the token is path segment 1, never the last one — taking the last would
    harvest job UUIDs and fill the registry with boards that do not exist.

    Returns a sorted list. Sorted rather than insertion-ordered so the candidate
    file's diff stays reviewable across runs; an unordered set would reshuffle
    the whole file every time and make the human's diff useless.
    """
    tokens: set[str] = set()
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            record = json.loads(text)
        except json.JSONDecodeError:
            # One malformed row must not lose the other several hundred.
            continue
        url = record.get("url") if isinstance(record, dict) else None
        if not isinstance(url, str):
            continue

        parts = urlsplit(url)
        # Exact host match. The pattern is applied server-side, but a pattern
        # can match a subdomain we did not mean, and the check is cheap.
        if parts.netloc.lower().split(":")[0] != host:
            continue

        segments = [segment for segment in parts.path.split("/") if segment]
        if not segments:
            continue
        token = segments[0]
        if token.casefold() in _NOT_TOKENS:
            continue
        tokens.add(token)

    return sorted(tokens)
```

- [ ] **Step 6: Run the tests**

Run: `cd services/api && pytest tests/discovery/test_crawl_index.py -v`
Expected: PASS.

If `test_never_harvests_a_job_id_as_a_token` fails on a real token containing a
hyphen, read the failure before loosening it — a legitimate token like
`acme-labs` is fine and the assertion's length guard allows it; a 36-character
UUID is not.

- [ ] **Step 7: Record what was actually harvested**

```bash
cd services/api && python3 -c "
from pathlib import Path
from nightshift.discovery.sources.crawl_index import tokens_from_cdx
lines = Path('tests/fixtures/crawl/ashby_cc_main_2026_30.jsonl').read_text().splitlines()
tokens = tokens_from_cdx(lines, host='jobs.ashbyhq.com')
print(f'rows: {len(lines)}  distinct tokens: {len(tokens)}')
print('first 10:', tokens[:10])
"
```

Put those numbers in the commit message. They are a count for *this recorded
slice*, not for the whole index — say so, rather than restating the design's
2,605.

- [ ] **Step 8: `make check`, then commit**

```bash
make check
git add services/api/nightshift/discovery services/api/tests/discovery \
        services/api/tests/fixtures/crawl scripts/record_crawl_fixture.py
git commit -m "feat(discovery): harvest board tokens from a recorded crawl index

The token is path segment 1, never the last: most captured URLs are job
pages beneath a board, so a last-segment parser would harvest UUIDs and
fill the registry with boards that do not exist.

Lever has no pattern, asserted by a test rather than left as a comment.
jobs.lever.co/robots.txt disallows CCBot, so the archive holds no Lever
pages and never will (ADR 0006) — a pattern would harvest zero forever and
read as a bug.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: The candidate model and file

**Files:**
- Create: `services/api/nightshift/discovery/models.py`
- Create: `services/api/nightshift/discovery/candidates.py`
- Create: `services/api/tests/discovery/test_candidates.py`
- Create: `data/board-candidates.yaml`

**Interfaces:**
- Produces:
  - `class Verdict(StrEnum)` — `LIVE_NAMED`, `LIVE_UNNAMED`, `NAME_COLLISION`,
    `EMPTY`, `UNREACHABLE`
  - `class Candidate(BaseModel)` — `ats`, `token`, `verdict`, `company_name`,
    `posting_count`, `nyc_posting_count`, `first_seen`, `last_validated`,
    `source`, `notes`
  - `load_candidates(path) -> CandidateFile`, `save_candidates(file, path)`
  - `merge_candidate(file, candidate) -> CandidateFile`
  - Consumed by Tasks 3 and 4.

- [ ] **Step 1: Write the failing tests**

```python
# services/api/tests/discovery/test_candidates.py
"""The candidate file: what discovery writes and approval reads.

The rule this file exists to enforce is that **no candidate is ever discarded**
(board-discovery.md §6). A company between hiring rounds returns an empty
board; a provider having a bad morning returns a timeout. Neither is evidence
the board is worthless, and dropping either would recreate one level up the
mistake I3 forbids at the listing level — treating absence of data as data.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nightshift.discovery.candidates import (
    load_candidates,
    merge_candidate,
    save_candidates,
)
from nightshift.discovery.models import Candidate, CandidateFile, Verdict


def _candidate(**overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "ats": "ashby",
        "token": "0g",
        "verdict": Verdict.LIVE_NAMED,
        "company_name": "0g Labs",
        "posting_count": 4,
        "nyc_posting_count": 0,
        "first_seen": date(2026, 8, 2),
        "last_validated": date(2026, 8, 2),
        "source": "crawl_index",
    }
    return Candidate(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_round_trips_through_yaml(tmp_path: Path) -> None:
    path = tmp_path / "candidates.yaml"
    original = CandidateFile(candidates=(_candidate(),))
    save_candidates(original, path)
    assert load_candidates(path) == original


def test_an_absent_file_is_empty_not_an_error(tmp_path: Path) -> None:
    """The first discovery run has no file to read yet."""
    assert load_candidates(tmp_path / "nope.yaml").candidates == ()


def test_re_validating_updates_in_place_rather_than_appending(tmp_path: Path) -> None:
    """Identity is (ats, token). Appending would grow the file without bound
    and make the approval report count one board several times."""
    file = CandidateFile(candidates=(_candidate(posting_count=4),))
    merged = merge_candidate(file, _candidate(posting_count=9))
    assert len(merged.candidates) == 1
    assert merged.candidates[0].posting_count == 9


def test_re_validating_preserves_the_original_first_seen(tmp_path: Path) -> None:
    """`first_seen` is when we discovered it, not when we last looked."""
    file = CandidateFile(candidates=(_candidate(first_seen=date(2026, 7, 1)),))
    merged = merge_candidate(file, _candidate(first_seen=date(2026, 8, 2)))
    assert merged.candidates[0].first_seen == date(2026, 7, 1)


def test_the_same_token_on_two_providers_is_two_candidates() -> None:
    """`ramp` is a live board on both Lever and Ashby (M1a recorded both)."""
    file = CandidateFile(candidates=(_candidate(ats="ashby", token="ramp"),))
    merged = merge_candidate(file, _candidate(ats="lever", token="ramp"))
    assert len(merged.candidates) == 2


class TestNothingIsEverDiscarded:
    def test_an_empty_board_is_kept(self) -> None:
        candidate = _candidate(verdict=Verdict.EMPTY, company_name=None, posting_count=0)
        file = merge_candidate(CandidateFile(), candidate)
        assert len(file.candidates) == 1

    def test_an_unreachable_board_is_kept(self) -> None:
        candidate = _candidate(verdict=Verdict.UNREACHABLE, company_name=None, posting_count=0)
        file = merge_candidate(CandidateFile(), candidate)
        assert len(file.candidates) == 1

    def test_a_board_that_recovers_is_upgraded_not_duplicated(self) -> None:
        """The point of keeping them: an empty board becomes approvable the
        moment it returns named postings."""
        file = merge_candidate(
            CandidateFile(), _candidate(verdict=Verdict.EMPTY, company_name=None, posting_count=0)
        )
        file = merge_candidate(file, _candidate(verdict=Verdict.LIVE_NAMED))
        assert len(file.candidates) == 1
        assert file.candidates[0].verdict is Verdict.LIVE_NAMED


class TestModelRefusesNonsense:
    def test_a_named_verdict_requires_a_name(self) -> None:
        """The whole approval gate rests on this field being trustworthy."""
        with pytest.raises(ValueError, match="live_named requires a company_name"):
            _candidate(verdict=Verdict.LIVE_NAMED, company_name=None)

    def test_an_unnamed_verdict_must_not_carry_a_name(self) -> None:
        """Otherwise a name could be filled in by hand and the candidate would
        still be routed to manual review while looking approvable."""
        with pytest.raises(ValueError, match="live_unnamed must not carry"):
            _candidate(verdict=Verdict.LIVE_UNNAMED, company_name="Invented Ltd")

    def test_a_token_that_could_escape_a_url_is_rejected(self) -> None:
        """The token is interpolated into a provider URL. registry.py already
        rejects these; the candidate file is the earlier door."""
        for bad in ("../etc", "a/b", "a?b", "a#b", ""):
            with pytest.raises(ValueError):
                _candidate(token=bad)

    def test_counts_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError):
            _candidate(posting_count=-1)

    def test_nyc_count_cannot_exceed_the_total(self) -> None:
        """It is a subset by construction. A violation means the validator is
        counting two different things, and the tier assignment in M1d reads
        this number."""
        with pytest.raises(ValueError, match="nyc_posting_count"):
            _candidate(posting_count=2, nyc_posting_count=5)


def test_the_file_is_written_sorted_for_a_reviewable_diff(tmp_path: Path) -> None:
    """A human reads this file as a git diff. Unsorted output would reshuffle
    on every run and make the diff unreadable, which is how a review step
    becomes a rubber stamp."""
    path = tmp_path / "candidates.yaml"
    file = CandidateFile(
        candidates=(
            _candidate(ats="ashby", token="zebra"),
            _candidate(ats="ashby", token="alpha"),
            _candidate(ats="greenhouse", token="beta"),
        )
    )
    save_candidates(file, path)
    text = path.read_text()
    assert text.index("alpha") < text.index("zebra")
    assert text.index("zebra") < text.index("beta")  # ats sorts before token
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/api && pytest tests/discovery/test_candidates.py -v`
Expected: FAIL — no module `nightshift.discovery.models`.

- [ ] **Step 3: Write `models.py`**

```python
# services/api/nightshift/discovery/models.py
"""What a discovered board looks like before a human has approved it.

The verdicts are the whole design (board-discovery.md §6). Three of them route
to manual attention and two of them are *not rejections* — `empty` and
`unreachable` stay candidates and are re-validated on the next run, because a
company between hiring rounds and a provider having a bad morning are not
evidence that a board is worthless.
"""

from __future__ import annotations

import re
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Verdict(StrEnum):
    """Exactly one applies to every candidate."""

    #: 200, at least one posting, and the provider told us the employer's name.
    #: The only verdict eligible for bulk approval (ADR 0005).
    LIVE_NAMED = "live_named"
    #: 200 with postings, but no resolvable employer name. Manual review.
    #: `a3c41b8b71eff8c4` is the recorded example and the reason the gate exists.
    LIVE_UNNAMED = "live_unnamed"
    #: The name normalises onto a company already in the registry. Manual review,
    #: because it is either a duplicate or two genuinely different employers.
    NAME_COLLISION = "name_collision"
    #: 200 with zero postings. Authoritative, not an error (ADR 0003).
    EMPTY = "empty"
    #: Non-200, timeout, or unparseable. Says nothing about the board.
    UNREACHABLE = "unreachable"


#: Same rule registry.py applies. The token is interpolated into a provider URL.
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class Candidate(BaseModel):
    """One discovered board, awaiting review."""

    model_config = ConfigDict(frozen=True)

    ats: str
    token: str
    verdict: Verdict
    #: Present only for LIVE_NAMED and NAME_COLLISION, and never derived from
    #: the token — Ashby's `0g` is "0g Labs" (I2).
    company_name: str | None = None
    posting_count: int = Field(default=0, ge=0)
    nyc_posting_count: int = Field(default=0, ge=0)
    first_seen: date
    last_validated: date
    #: Which front-end found it: crawl_index | careers_probe | community.
    source: str
    notes: str | None = None

    @field_validator("token")
    @classmethod
    def _token_is_url_safe(cls, value: str) -> str:
        if not _TOKEN.match(value):
            raise ValueError(f"token is not URL-safe: {value!r}")
        return value

    @model_validator(mode="after")
    def _name_matches_verdict(self) -> Candidate:
        """The approval gate reads `verdict` and trusts `company_name`.

        Letting the two disagree would allow a hand-edited name to sit on an
        unnamed candidate — approvable-looking and still routed to review, or
        worse, the reverse.
        """
        if self.verdict is Verdict.LIVE_NAMED and not self.company_name:
            raise ValueError("live_named requires a company_name")
        if self.verdict is Verdict.LIVE_UNNAMED and self.company_name:
            raise ValueError("live_unnamed must not carry a company_name")
        if self.nyc_posting_count > self.posting_count:
            raise ValueError(
                f"nyc_posting_count {self.nyc_posting_count} exceeds "
                f"posting_count {self.posting_count}"
            )
        return self

    @property
    def key(self) -> tuple[str, str]:
        """Identity. The same token can be a real board on two providers —
        `ramp` is live on both Lever and Ashby."""
        return (self.ats, self.token)


class CandidateFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: tuple[Candidate, ...] = ()
```

- [ ] **Step 4: Write `candidates.py`**

```python
# services/api/nightshift/discovery/candidates.py
"""Reading and writing `data/board-candidates.yaml`.

Pure file work — no network, no database. The file is committed and a human
reads it as a git diff, which is why everything here sorts deterministically:
an unordered write reshuffles the whole file on every run, and a diff nobody
can read is a review step that becomes a rubber stamp.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from nightshift.discovery.models import Candidate, CandidateFile

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "board-candidates.yaml"

_HEADER = """\
# Discovered board candidates — written by `make discover`, read by
# `make registry-approve`. Committed on purpose: the diff is the review.
#
# NOTHING HERE IS IN THE REGISTRY YET. Promotion happens only when a human runs
# `make registry-approve`, and only `live_named` candidates are promoted in
# bulk (ADR 0005). Everything else waits for individual attention.
#
# No candidate is ever deleted by the pipeline. `empty` means a live board with
# no open roles and `unreachable` means we could not check — neither is
# evidence the board is worthless, and both become approvable the moment they
# return named postings.
"""


def load_candidates(path: Path | None = None) -> CandidateFile:
    """Read the candidate file. A missing file is empty, not an error."""
    target = path or DEFAULT_PATH
    if not target.exists():
        return CandidateFile()
    raw = yaml.safe_load(target.read_text()) or {}
    return CandidateFile.model_validate(raw)


def save_candidates(file: CandidateFile, path: Path | None = None) -> None:
    """Write the candidate file, sorted by (ats, token)."""
    target = path or DEFAULT_PATH
    ordered = sorted(file.candidates, key=lambda candidate: candidate.key)
    payload = {
        "candidates": [
            candidate.model_dump(mode="json", exclude_none=True) for candidate in ordered
        ]
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        _HEADER + yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=88)
    )


def merge_candidate(file: CandidateFile, candidate: Candidate) -> CandidateFile:
    """Insert or update by ``(ats, token)``, preserving the original discovery date.

    Update rather than append: appending would grow the file without bound and
    make the approval report count one board several times. ``first_seen`` is
    when we found it, not when we last looked at it.
    """
    existing = {item.key: item for item in file.candidates}
    previous = existing.get(candidate.key)
    if previous is not None:
        candidate = candidate.model_copy(update={"first_seen": previous.first_seen})
    existing[candidate.key] = candidate
    return CandidateFile(candidates=tuple(sorted(existing.values(), key=lambda c: c.key)))
```

- [ ] **Step 5: Create the empty committed file**

```bash
cd services/api && python3 -c "
from nightshift.discovery.candidates import save_candidates
from nightshift.discovery.models import CandidateFile
save_candidates(CandidateFile())
"
git status --short data/board-candidates.yaml
```

- [ ] **Step 6: Run the tests, then `make check` and commit**

Run: `cd services/api && pytest tests/discovery/test_candidates.py -v`
Expected: PASS.

```bash
make check
git add services/api/nightshift/discovery data/board-candidates.yaml \
        services/api/tests/discovery/test_candidates.py
git commit -m "feat(discovery): add the candidate model and its committed file

No candidate is ever discarded. 'empty' is a live board with no open roles
and 'unreachable' is a board we could not check; discarding either would
recreate one level up the mistake I3 forbids at the listing level —
treating absence of data as data.

The model refuses a live_named candidate with no name and a live_unnamed
one that carries a name, because the approval gate reads the verdict and
trusts the name, and letting them disagree is how the gate goes hollow.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Validation — the five verdicts

The gate that stops a machine-generated board reaching the registry. This is
the task `board-discovery.md` §13 calls the one "that stops the approval gate
becoming decorative".

**Files:**
- Create: `services/api/nightshift/discovery/validate.py`
- Create: `services/api/tests/discovery/test_validate.py`
- Create: `services/api/tests/fixtures/discovery/` recordings + meta files
- Modify: `scripts/record_fixture.py` (a `discovery` mode)

**Interfaces:**
- Consumes: `PoliteClient`; `Candidate`, `Verdict`; `normalize_company_name`;
  `parse_location_list`; `load_registry`.
- Produces:
  - `async def validate_token(client, *, ats, token, today, known_names) -> Candidate`
  - `def extract_ashby_name(html: str) -> str | None`
  - Consumed by Task 4.

- [ ] **Step 1: Record the fixtures**

Five recordings, each with a `.meta.json`. Use the project User-Agent and
space requests ≥1.2s apart.

| File | What | Why |
|---|---|---|
| `ashby_0g_board.json` | `posting-api/job-board/0g` | A live board with no name in the API |
| `ashby_0g_page.html` | `jobs.ashbyhq.com/0g` | Where the name actually is — "0g Labs" |
| `greenhouse_6sense_meta.json` | `/v1/boards/6sense` | Greenhouse *does* return `name` |
| `ashby_junk_board.json` | `posting-api/job-board/a3c41b8b71eff8c4` | 10 well-formed postings, machine-generated token |
| `lever_unknown_404.json` | The 404 body | Already exists from M1a — reuse, do not re-record |

Reuse M1a's `lever/plaid_empty_board.json` and `lever/ramp_unknown_board.json`
rather than recording new ones. They are the I3 pair and they are already
committed.

**Trim the Ashby page HTML to the `<head>` only.** It is the only part with the
title, the rest is a megabyte of application JavaScript, and the meta file must
say the body was removed and that nothing inside `<head>` was edited.

- [ ] **Step 2: Write the failing tests**

```python
# services/api/tests/discovery/test_validate.py
"""Classifying a discovered token into one of five verdicts.

The load-bearing test is `test_a_live_but_unnameable_board_cannot_be_bulk_approved`.
`a3c41b8b71eff8c4` returns HTTP 200 with ten well-formed postings — every
automated liveness check passes it — and it is obviously not a company. It is
the single case that stops the approval gate becoming decorative, and deleting
its fixture would hollow out the whole design.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from nightshift.adapters.base import SourceUnavailableError
from nightshift.discovery.models import Verdict
from nightshift.discovery.validate import extract_ashby_name, validate_token

FIXTURES = Path(__file__).parent.parent / "fixtures"
TODAY = date(2026, 8, 2)


class _StubClient:
    """Replaces the network, not the module under test.

    Keyed by URL substring so a test can serve a board and a board page from
    one stub, which is what Ashby validation actually needs.
    """

    def __init__(self, routes: dict[str, Any]) -> None:
        self._routes = routes
        self.requested: list[str] = []

    def _match(self, url: str) -> Any:
        self.requested.append(url)
        for fragment, result in self._routes.items():
            if fragment in url:
                if isinstance(result, Exception):
                    raise result
                return result
        raise SourceUnavailableError(f"no stub route for {url}", http_status=404)

    async def get_json(self, url: str) -> Any:
        return self._match(url)

    async def get_text(self, url: str) -> str:
        result = self._match(url)
        return result if isinstance(result, str) else json.dumps(result)


def _load(*parts: str) -> Any:
    return json.loads(FIXTURES.joinpath(*parts).read_text())


class TestAshbyNameExtraction:
    def test_resolves_the_real_company_name(self) -> None:
        """board-discovery.md §13: `0g` must resolve to "0g Labs", not "0g".

        A test that accepted the token would pass against a suffix-stripping
        bug and prove nothing.
        """
        html = (FIXTURES / "discovery" / "ashby_0g_page.html").read_text()
        assert extract_ashby_name(html) == "0g Labs"

    def test_strips_the_jobs_suffix_ashby_appends(self) -> None:
        assert extract_ashby_name("<title>Acme Corp Jobs</title>") == "Acme Corp"

    def test_a_page_with_no_title_yields_none(self) -> None:
        """None routes the candidate to manual review, which is the safe
        direction. Returning the token would be I2."""
        assert extract_ashby_name("<html><body>nothing</body></html>") is None

    def test_a_title_that_is_only_the_suffix_yields_none(self) -> None:
        assert extract_ashby_name("<title>Jobs</title>") is None


class TestVerdicts:
    async def test_greenhouse_name_comes_from_the_board_endpoint(self) -> None:
        client = _StubClient(
            {
                "/boards/6sense/jobs": _load("discovery", "greenhouse_6sense_jobs.json"),
                "/boards/6sense": _load("discovery", "greenhouse_6sense_meta.json"),
            }
        )
        candidate = await validate_token(
            client, ats="greenhouse", token="6sense", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.LIVE_NAMED
        assert candidate.company_name == "6sense"

    async def test_ashby_name_comes_from_the_board_page(self) -> None:
        client = _StubClient(
            {
                "posting-api/job-board/0g": _load("discovery", "ashby_0g_board.json"),
                "jobs.ashbyhq.com/0g": (FIXTURES / "discovery" / "ashby_0g_page.html").read_text(),
            }
        )
        candidate = await validate_token(
            client, ats="ashby", token="0g", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.LIVE_NAMED
        assert candidate.company_name == "0g Labs"
        assert candidate.company_name != "0g", "the token is not the name (I2)"

    async def test_a_live_but_unnameable_board_cannot_be_bulk_approved(self) -> None:
        """The case the whole approval gate exists for.

        Ten well-formed postings under a machine-generated token. Every
        automated liveness check passes it. Only the name requirement catches
        it, and only because the name has to come from somewhere real.
        """
        board = _load("discovery", "ashby_junk_board.json")
        assert len(board["jobs"]) >= 1, "fixture lost its postings; it proves nothing empty"
        client = _StubClient(
            {
                "posting-api/job-board/a3c41b8b71eff8c4": board,
                # The board page exists but carries no usable title.
                "jobs.ashbyhq.com/a3c41b8b71eff8c4": "<html><head></head><body></body></html>",
            }
        )
        candidate = await validate_token(
            client,
            ats="ashby",
            token="a3c41b8b71eff8c4",
            today=TODAY,
            known_names=frozenset(),
        )
        assert candidate.verdict is Verdict.LIVE_UNNAMED
        assert candidate.company_name is None
        assert candidate.posting_count >= 1, "it is live — that is what makes it dangerous"

    async def test_a_name_already_in_the_registry_is_a_collision(self) -> None:
        """Not a rejection: it is either a duplicate board or two genuinely
        different employers, and only a human can say which."""
        client = _StubClient(
            {
                "/boards/6sense/jobs": _load("discovery", "greenhouse_6sense_jobs.json"),
                "/boards/6sense": _load("discovery", "greenhouse_6sense_meta.json"),
            }
        )
        candidate = await validate_token(
            client,
            ats="greenhouse",
            token="6sense",
            today=TODAY,
            known_names=frozenset({"6sense"}),
        )
        assert candidate.verdict is Verdict.NAME_COLLISION

    async def test_an_empty_board_is_empty_not_unreachable(self) -> None:
        """I3's distinction, at the discovery layer. M1a recorded the `plaid`
        empty board specifically so this branch has a real payload."""
        client = _StubClient({"postings/plaid": _load("lever", "plaid_empty_board.json")})
        candidate = await validate_token(
            client, ats="lever", token="plaid", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.EMPTY
        assert candidate.posting_count == 0

    async def test_a_404_is_unreachable_not_empty(self) -> None:
        """Collapsing these two is exactly the I3 violation ADR 0003 exists to
        prevent, one level up from listings."""
        client = _StubClient(
            {"postings/ramp": SourceUnavailableError("HTTP 404", http_status=404)}
        )
        candidate = await validate_token(
            client, ats="lever", token="ramp", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.UNREACHABLE
        assert candidate.posting_count == 0

    async def test_a_timeout_is_unreachable(self) -> None:
        client = _StubClient({"postings/slow": SourceUnavailableError("timeout")})
        candidate = await validate_token(
            client, ats="lever", token="slow", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.UNREACHABLE

    async def test_validation_never_raises(self) -> None:
        """A discovery run over 2,605 tokens must not stop at the first bad one."""
        client = _StubClient({"anything": RuntimeError("something unexpected")})
        candidate = await validate_token(
            client, ats="ashby", token="explodes", today=TODAY, known_names=frozenset()
        )
        assert candidate.verdict is Verdict.UNREACHABLE


class TestNycCounting:
    async def test_counts_nyc_postings_from_parsed_locations(self) -> None:
        """board-discovery.md §8: NYC-ness is read off the postings by the
        parser, never declared. M1d's hot tier reads this number."""
        client = _StubClient(
            {
                "posting-api/job-board/ramp": _load("ashby", "ramp_board.json"),
                "jobs.ashbyhq.com/ramp": "<title>Ramp Jobs</title>",
            }
        )
        candidate = await validate_token(
            client, ats="ashby", token="ramp", today=TODAY, known_names=frozenset()
        )
        assert candidate.nyc_posting_count > 0
        assert candidate.nyc_posting_count <= candidate.posting_count


async def test_ashby_costs_one_extra_request_and_only_at_discovery_time() -> None:
    """The name lookup is per *candidate*, not per poll. If it ever leaked into
    polling it would double the request count against Ashby forever."""
    client = _StubClient(
        {
            "posting-api/job-board/0g": _load("discovery", "ashby_0g_board.json"),
            "jobs.ashbyhq.com/0g": (FIXTURES / "discovery" / "ashby_0g_page.html").read_text(),
        }
    )
    await validate_token(client, ats="ashby", token="0g", today=TODAY, known_names=frozenset())
    assert len(client.requested) == 2


async def test_an_unknown_ats_is_refused_loudly() -> None:
    """A typo in a provider name must not silently classify every board as
    unreachable and quietly empty the registry."""
    with pytest.raises(ValueError, match="unknown ats"):
        await validate_token(
            _StubClient({}), ats="workday", token="x", today=TODAY, known_names=frozenset()
        )
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd services/api && pytest tests/discovery/test_validate.py -v`
Expected: FAIL — no module `nightshift.discovery.validate`.

- [ ] **Step 4: Add `get_text` to `PoliteClient`**

Checked while writing this plan: `PoliteClient` has exactly one method,
`get_json` (`adapters/http.py:95`). Ashby's employer name lives in the board
page's HTML, so validation needs text as well.

Add `get_text` **to `PoliteClient`**, sharing its rate limiter, retry policy
and `SourceUnavailableError` behaviour. Do not add a second HTTP path and do
not import httpx anywhere else — that constraint has held since M0 and this is
the first milestone that puts real pressure on it.

Two things `get_text` must do that `get_json` does not:

* **Cap the response size.** A board page is HTML meant for a browser and can
  be megabytes. Read a bounded prefix — 256 KB is far more than a `<head>` —
  because the only thing wanted from it is the title, and an unbounded read
  across thousands of candidates is a memory profile nobody chose.
* **Not raise on a non-JSON content type**, which `get_json` legitimately does.

Add a test alongside the existing `PoliteClient` tests asserting the size cap
truncates rather than raising, since a truncated `<head>` still yields a title
and a raised exception would misclassify a real board as `unreachable`.

- [ ] **Step 5: Write `validate.py`**

```python
# services/api/nightshift/discovery/validate.py
"""Classify a discovered token by asking the provider (board-discovery.md §6).

This is the only module in `nightshift/discovery/` that talks to a provider,
and it does so through `PoliteClient` — nothing else in the repo imports httpx
and that stays true.

The employer name is the load-bearing field. `live_named` is the only verdict
eligible for bulk approval (ADR 0005), and it requires that the *provider* told
us who this is:

* Greenhouse — `GET /v1/boards/{token}` returns `{"name": ...}`.
* Ashby — nowhere in the API. The board page's `<title>` carries it, and
  Ashby's robots.txt permits that page. One extra request per candidate, at
  discovery time only.
* Lever — not available; Lever boards are found by careers-page probing, which
  starts from a company's own domain and therefore already knows the employer.

We never derive a name from the token. Ashby's `0g` is "0g Labs", and
`a3c41b8b71eff8c4` is not a company at all.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Protocol

import structlog

from nightshift.adapters.base import SourceUnavailableError
from nightshift.discovery.models import Candidate, Verdict
from nightshift.domain.companies import normalize_company_name
from nightshift.domain.locations import parse_location_list

log = structlog.get_logger(__name__)

BOARD_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
}
GREENHOUSE_META_URL = "https://boards-api.greenhouse.io/v1/boards/{token}"
ASHBY_PAGE_URL = "https://jobs.ashbyhq.com/{token}"

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_OG_TITLE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE
)


class _Client(Protocol):
    async def get_json(self, url: str) -> Any: ...
    async def get_text(self, url: str) -> str: ...


def extract_ashby_name(html: str) -> str | None:
    """Pull the employer name out of an Ashby board page.

    Ashby suffixes the title with " Jobs". A title that is *only* the suffix
    yields None rather than an empty string, and None routes the candidate to
    manual review — the safe direction. Returning the token here would be the
    exact I2 failure this module exists to prevent.
    """
    for pattern in (_OG_TITLE, _TITLE):
        match = pattern.search(html)
        if match is None:
            continue
        title = " ".join(match.group(1).split())
        if title.casefold().endswith(" jobs"):
            title = title[: -len(" jobs")].strip()
        elif title.casefold() == "jobs":
            title = ""
        if title:
            return title
    return None


def _postings(ats: str, payload: Any) -> list[dict[str, Any]] | None:
    """The provider's postings, or None if the payload is the wrong shape.

    None is not zero. A wrong shape means the source changed and we learned
    nothing; zero means the board really is empty (ADR 0003).
    """
    if ats == "ashby":
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        return jobs if isinstance(jobs, list) else None
    if ats == "greenhouse":
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        return jobs if isinstance(jobs, list) else None
    if ats == "lever":
        return payload if isinstance(payload, list) else None
    raise ValueError(f"unknown ats: {ats}")


def _location_strings(ats: str, posting: dict[str, Any]) -> list[str]:
    if ats == "ashby":
        primary = posting.get("location")
        extra = [
            entry.get("location")
            for entry in posting.get("secondaryLocations") or []
            if isinstance(entry, dict)
        ]
        return [value for value in [primary, *extra] if isinstance(value, str)]
    if ats == "greenhouse":
        location = posting.get("location")
        name = location.get("name") if isinstance(location, dict) else None
        return [name] if isinstance(name, str) else []
    categories = posting.get("categories")
    if not isinstance(categories, dict):
        return []
    all_locations = categories.get("allLocations")
    if isinstance(all_locations, list):
        return [value for value in all_locations if isinstance(value, str)]
    primary = categories.get("location")
    return [primary] if isinstance(primary, str) else []


def _count_nyc(ats: str, postings: list[dict[str, Any]]) -> int:
    """How many postings name a NYC location.

    Read off the postings by the parser, never declared by a registry entry
    (board-discovery.md §8). M1d's hot tier reads this number, which is why the
    parser breadth in M1a was a hard prerequisite for this milestone.
    """
    count = 0
    for posting in postings:
        parsed = parse_location_list(_location_strings(ats, posting))
        if any(location.is_nyc for location in parsed):
            count += 1
    return count


async def _resolve_name(client: _Client, *, ats: str, token: str) -> str | None:
    """Ask the provider who this employer is. Never guess from the token."""
    if ats == "greenhouse":
        try:
            meta = await client.get_json(GREENHOUSE_META_URL.format(token=token))
        except SourceUnavailableError:
            return None
        name = meta.get("name") if isinstance(meta, dict) else None
        return name.strip() if isinstance(name, str) and name.strip() else None

    if ats == "ashby":
        try:
            html = await client.get_text(ASHBY_PAGE_URL.format(token=token))
        except SourceUnavailableError:
            return None
        return extract_ashby_name(html)

    # Lever publishes no name anywhere. Careers-page probing supplies it,
    # because it starts from the employer's own domain.
    return None


async def validate_token(
    client: _Client,
    *,
    ats: str,
    token: str,
    today: date,
    known_names: frozenset[str],
    source: str = "crawl_index",
) -> Candidate:
    """Probe one board and classify it. Never raises for a network reason.

    A discovery run walks thousands of tokens; stopping at the first bad one
    would mean a single dead board costs the whole sweep. Anything unexpected
    becomes `unreachable`, which is a *re-validated* state, not a rejection.

    An unknown `ats` does raise — a typo in a provider name would otherwise
    classify every board as unreachable and quietly empty the registry.
    """
    if ats not in BOARD_URLS:
        raise ValueError(f"unknown ats: {ats}")

    def unreachable(note: str) -> Candidate:
        return Candidate(
            ats=ats,
            token=token,
            verdict=Verdict.UNREACHABLE,
            first_seen=today,
            last_validated=today,
            source=source,
            notes=note,
        )

    try:
        payload = await client.get_json(BOARD_URLS[ats].format(token=token))
    except SourceUnavailableError as exc:
        return unreachable(f"{exc}")
    except Exception as exc:  # noqa: BLE001 — a sweep must not die on one board
        log.warning("validate_unexpected_error", ats=ats, token=token, error=str(exc))
        return unreachable(f"unexpected: {type(exc).__name__}: {exc}")

    postings = _postings(ats, payload)
    if postings is None:
        # A 200 with the wrong shape is a source problem, and "no jobs" is the
        # one conclusion we must not draw from it.
        return unreachable(f"unexpected payload shape: {type(payload).__name__}")

    if not postings:
        return Candidate(
            ats=ats,
            token=token,
            verdict=Verdict.EMPTY,
            first_seen=today,
            last_validated=today,
            source=source,
            notes="live board, zero open postings — re-validated on the next run",
        )

    try:
        name = await _resolve_name(client, ats=ats, token=token)
    except Exception as exc:  # noqa: BLE001
        log.warning("name_lookup_failed", ats=ats, token=token, error=str(exc))
        name = None

    nyc = _count_nyc(ats, postings)

    if name is None:
        return Candidate(
            ats=ats,
            token=token,
            verdict=Verdict.LIVE_UNNAMED,
            posting_count=len(postings),
            nyc_posting_count=nyc,
            first_seen=today,
            last_validated=today,
            source=source,
            notes="live, but the provider did not name the employer — manual review",
        )

    verdict = (
        Verdict.NAME_COLLISION
        if normalize_company_name(name) in known_names
        else Verdict.LIVE_NAMED
    )
    return Candidate(
        ats=ats,
        token=token,
        verdict=verdict,
        company_name=name,
        posting_count=len(postings),
        nyc_posting_count=nyc,
        first_seen=today,
        last_validated=today,
        source=source,
    )
```

- [ ] **Step 6: Run the tests**

Run: `cd services/api && pytest tests/discovery/test_validate.py -v`
Expected: PASS.

- [ ] **Step 7: Prove the gate can fail**

Non-vacuity, and this is the most important one in the plan. Temporarily make
`_resolve_name` fall back to `return token` for Ashby, and confirm
`test_a_live_but_unnameable_board_cannot_be_bulk_approved` **fails** — the junk
board would be classified `live_named` and reach bulk approval. Restore, and
record the result in the commit message.

- [ ] **Step 8: `make check`, then commit**

```bash
make check
git add services/api/nightshift/discovery/validate.py \
        services/api/tests/discovery/test_validate.py \
        services/api/tests/fixtures/discovery scripts/record_fixture.py
git commit -m "feat(discovery): classify candidates into the five verdicts

The name is the load-bearing field: live_named is the only verdict eligible
for bulk approval and it requires the provider to have told us who this is.
Greenhouse says so in its board endpoint; Ashby only on the board page; Lever
nowhere, which is why Lever is found by careers-page probing instead.

Non-vacuity: making the Ashby name fall back to the token classifies
a3c41b8b71eff8c4 — ten well-formed postings under a machine-generated slug —
as live_named and lets it reach bulk approval. That is the failure the gate
exists to prevent and the test catches it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Approval, and the CLI that drives discovery

**Files:**
- Create: `services/api/nightshift/discovery/approve.py`
- Create: `services/api/nightshift/discovery/cli.py`
- Create: `services/api/tests/discovery/test_approve.py`
- Modify: `Makefile`

**Interfaces:**
- Consumes: everything from Tasks 1–3; `load_registry`, `BoardEntry`.
- Produces:
  - `def approvable(file, *, registry) -> list[Candidate]`
  - `def approval_report(candidates) -> str`
  - `def promote(file, *, registry_path, today) -> tuple[int, list[Candidate]]`
  - `make discover`, `make registry-validate`, `make registry-approve`

- [ ] **Step 1: Write the failing tests**

```python
# services/api/tests/discovery/test_approve.py
"""Promotion from candidate to registry entry (ADR 0005).

A1 required per-entry human review. At 2,605 candidates that is a control
nobody performs, and an unperformed control is worse than a weaker one that
runs — because the documentation still claims the strong one. ADR 0005 moved it
to batch approval with typed exceptions, and these tests are what keep the
exceptions real.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from nightshift.discovery.approve import approvable, approval_report, promote
from nightshift.discovery.models import Candidate, CandidateFile, Verdict

TODAY = date(2026, 8, 2)


def _candidate(**overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "ats": "ashby",
        "token": "acme",
        "verdict": Verdict.LIVE_NAMED,
        "company_name": "Acme",
        "posting_count": 3,
        "nyc_posting_count": 1,
        "first_seen": TODAY,
        "last_validated": TODAY,
        "source": "crawl_index",
    }
    return Candidate(**{**defaults, **overrides})  # type: ignore[arg-type]


class TestOnlyLiveNamedReachesBulkApproval:
    @pytest.mark.parametrize(
        "verdict",
        [Verdict.LIVE_UNNAMED, Verdict.NAME_COLLISION, Verdict.EMPTY, Verdict.UNREACHABLE],
    )
    def test_every_other_verdict_is_held(self, verdict: Verdict) -> None:
        name = None if verdict is Verdict.LIVE_UNNAMED else "Acme"
        file = CandidateFile(candidates=(_candidate(verdict=verdict, company_name=name),))
        assert approvable(file, registry_tokens=frozenset()) == []

    def test_the_junk_board_cannot_be_promoted_by_approving_wholesale(self) -> None:
        """board-discovery.md §13's approval test, stated as it means it.

        Approving the entire report must still not promote a live_unnamed
        candidate. If this ever passes, the gate is decorative.
        """
        junk = _candidate(
            token="a3c41b8b71eff8c4",
            verdict=Verdict.LIVE_UNNAMED,
            company_name=None,
            posting_count=10,
        )
        good = _candidate(token="realco", company_name="Real Co")
        file = CandidateFile(candidates=(junk, good))
        promoted = approvable(file, registry_tokens=frozenset())
        assert [c.token for c in promoted] == ["realco"]

    def test_a_candidate_already_in_the_registry_is_not_promoted_twice(self) -> None:
        file = CandidateFile(candidates=(_candidate(),))
        assert approvable(file, registry_tokens=frozenset({("ashby", "acme")})) == []


class TestTheReport:
    def test_orders_nyc_boards_first(self) -> None:
        """§6: review effort lands on what matters and the tail can be skimmed."""
        far = _candidate(token="far", company_name="Far Co", nyc_posting_count=0)
        near = _candidate(token="near", company_name="Near Co", nyc_posting_count=7)
        report = approval_report([far, near])
        assert report.index("Near Co") < report.index("Far Co")

    def test_carries_every_field_the_human_needs_to_decide(self) -> None:
        report = approval_report([_candidate(company_name="Acme", posting_count=3)])
        for expected in ("Acme", "ashby", "acme", "3", "live_named"):
            assert expected in report

    def test_an_empty_report_says_so_rather_than_being_blank(self) -> None:
        """A blank output reads as a crash."""
        assert "no candidates" in approval_report([]).lower()


class TestPromotion:
    def test_writes_registry_entries_for_approved_candidates(self, tmp_path: Path) -> None:
        registry = tmp_path / "board-registry.yaml"
        registry.write_text(yaml.safe_dump({"boards": []}))
        file = CandidateFile(candidates=(_candidate(company_name="Acme"),))

        count, promoted = promote(file, registry_path=registry, today=TODAY)

        assert count == 1
        written = yaml.safe_load(registry.read_text())["boards"]
        assert written[0]["company"] == "Acme"
        assert written[0]["token"] == "acme"
        assert written[0]["status"] == "active"
        assert written[0]["added"] == TODAY.isoformat()

    def test_never_removes_an_existing_entry(self, tmp_path: Path) -> None:
        """A1: `dead` entries stay in the file, and promotion is additive.
        Rewriting the file from candidates alone would delete curated history."""
        registry = tmp_path / "board-registry.yaml"
        registry.write_text(
            yaml.safe_dump(
                {
                    "boards": [
                        {
                            "company": "Datadog",
                            "ats": "greenhouse",
                            "token": "datadog",
                            "added": "2026-07-29",
                            "verified_at": "2026-07-29",
                            "status": "active",
                            "nyc_presence": True,
                        }
                    ]
                }
            )
        )
        promote(CandidateFile(candidates=(_candidate(),)), registry_path=registry, today=TODAY)
        tokens = {b["token"] for b in yaml.safe_load(registry.read_text())["boards"]}
        assert "datadog" in tokens

    def test_is_idempotent(self, tmp_path: Path) -> None:
        registry = tmp_path / "board-registry.yaml"
        registry.write_text(yaml.safe_dump({"boards": []}))
        file = CandidateFile(candidates=(_candidate(),))

        promote(file, registry_path=registry, today=TODAY)
        first = registry.read_text()
        promote(file, registry_path=registry, today=TODAY)
        assert registry.read_text() == first

    def test_the_written_registry_still_loads(self, tmp_path: Path) -> None:
        """The registry has its own validation — path-traversal on the token,
        unique (ats, token). Writing something it refuses to load would break
        ingestion at the next poll rather than here."""
        from nightshift.domain.registry import load_registry

        registry = tmp_path / "board-registry.yaml"
        registry.write_text(yaml.safe_dump({"boards": []}))
        promote(
            CandidateFile(candidates=(_candidate(), _candidate(token="beta", company_name="Beta"))),
            registry_path=registry,
            today=TODAY,
        )
        loaded = load_registry(registry)
        assert len(loaded.boards) == 2


def test_promotion_writes_the_file_and_nothing_else(tmp_path: Path) -> None:
    """§5: nothing writes to board-registry.yaml automatically. The command
    writes it; a human reads the diff and commits. There is no git call here."""
    import inspect

    from nightshift.discovery import approve

    source = inspect.getsource(approve)
    assert "git" not in source.lower(), "approval must never commit on a human's behalf"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd services/api && pytest tests/discovery/test_approve.py -v`
Expected: FAIL — no module `nightshift.discovery.approve`.

- [ ] **Step 3: Write `approve.py`**

```python
# services/api/nightshift/discovery/approve.py
"""Promote reviewed candidates into the board registry (ADR 0005).

Pure file work. No network, no database, and — asserted by a test — no git.
A1 says nothing writes to `board-registry.yaml` automatically; this module is
run by a human typing a command, and the human reads the resulting diff and
commits it themselves.

Only `live_named` candidates are promoted in bulk. `live_unnamed`,
`name_collision`, `empty` and `unreachable` are held for individual attention
and stay in the candidate file, where the next discovery run re-validates them.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from nightshift.discovery.models import Candidate, CandidateFile, Verdict

DEFAULT_REGISTRY = Path(__file__).resolve().parents[3] / "data" / "board-registry.yaml"


def approvable(file: CandidateFile, *, registry_tokens: frozenset[tuple[str, str]]) -> list[Candidate]:
    """Candidates eligible for bulk promotion, NYC-producing boards first.

    The verdict check is the gate. It is deliberately a single equality against
    `LIVE_NAMED` rather than a set of exclusions: a new verdict added later
    defaults to *not* approvable, which is the safe direction.
    """
    return sorted(
        (
            candidate
            for candidate in file.candidates
            if candidate.verdict is Verdict.LIVE_NAMED
            and candidate.key not in registry_tokens
        ),
        key=lambda candidate: (-candidate.nyc_posting_count, candidate.company_name or ""),
    )


def approval_report(candidates: list[Candidate]) -> str:
    """A human-readable summary, ordered so review effort lands where it matters.

    Boards that produced an NYC posting come first (board-discovery.md §6), so
    the tail can be skimmed rather than read. An empty list says so in words —
    a blank output reads as a crash.
    """
    if not candidates:
        return "no candidates are eligible for bulk approval"

    lines = [
        f"{len(candidates)} candidate(s) eligible for bulk approval, NYC-producing first:",
        "",
        f"{'employer':<34} {'ats':<11} {'token':<26} {'posts':>6} {'nyc':>5}  verdict",
    ]
    for candidate in candidates:
        lines.append(
            f"{(candidate.company_name or ''):<34.34} {candidate.ats:<11} "
            f"{candidate.token:<26.26} {candidate.posting_count:>6} "
            f"{candidate.nyc_posting_count:>5}  {candidate.verdict.value}"
        )
    return "\n".join(lines)


def promote(
    file: CandidateFile, *, registry_path: Path | None = None, today: date
) -> tuple[int, list[Candidate]]:
    """Append approved candidates to the registry. Additive, never destructive.

    Existing entries are read and rewritten unchanged, including `dead` ones —
    A1 keeps those in the file so they surface on the source health page.
    Rebuilding the registry from candidates alone would delete curated history
    and silently un-disable boards a human had turned off.
    """
    target = registry_path or DEFAULT_REGISTRY
    raw = yaml.safe_load(target.read_text()) if target.exists() else {}
    boards: list[dict[str, object]] = list((raw or {}).get("boards") or [])
    existing = {(str(entry.get("ats")), str(entry.get("token"))) for entry in boards}

    approved = approvable(file, registry_tokens=frozenset(existing))
    for candidate in approved:
        boards.append(
            {
                "company": candidate.company_name,
                "ats": candidate.ats,
                "token": candidate.token,
                "added": today.isoformat(),
                "verified_at": candidate.last_validated.isoformat(),
                "status": "active",
                # Derived from the postings the validator actually parsed, not
                # asserted by hand. board-discovery.md §16 expects this field to
                # be deleted once M1d computes tiers from the database.
                "nyc_presence": candidate.nyc_posting_count > 0,
                "notes": (
                    f"Discovered by {candidate.source} and approved in bulk on "
                    f"{today.isoformat()} (ADR 0005). {candidate.posting_count} posting(s) "
                    f"at validation, {candidate.nyc_posting_count} naming NYC."
                ),
            }
        )

    if approved:
        target.write_text(
            yaml.safe_dump({"boards": boards}, sort_keys=False, allow_unicode=True, width=88)
        )
    return len(approved), approved
```

**Note on the header comment.** `yaml.safe_dump` discards the explanatory
header at the top of `board-registry.yaml`. Preserve it: read the leading
comment block before dumping and write it back, or the first approval run
silently deletes the file's own documentation.

- [ ] **Step 4: Write `cli.py` and the make targets**

Follow `nightshift/cli.py`'s argparse structure. Four subcommands:

- `discover --provider ashby [--limit N]` — read the committed crawl fixture by
  default; `--live` re-queries Common Crawl and requires
  `OUTBOUND_HTTP_ENABLED=true`.
- `validate [--limit N]` — probe unvalidated and stale candidates, update the
  candidate file.
- `approve [--dry-run]` — print the report; without `--dry-run`, write the
  registry. **Never commits.**
- `coverage` — print the numbers Task 5 exposes.

Makefile:

```make
discover: setup ## Harvest board candidates (reads the committed crawl fixture)
	@$(LOADENV) && $(PY) -m nightshift.discovery.cli discover --provider ashby

registry-validate: setup ## Probe candidates and classify them (needs network)
	@$(LOADENV) && $(PY) -m nightshift.discovery.cli validate

registry-approve: setup ## Show the approval report; --write to apply
	@$(LOADENV) && $(PY) -m nightshift.discovery.cli approve --dry-run
```

`registry-approve` is dry-run by default on purpose: the destructive-looking
target should require an extra word before it changes a committed file.

- [ ] **Step 5: Run the tests, `make check`, commit**

```bash
make check
git add services/api/nightshift/discovery services/api/tests/discovery Makefile
git commit -m "feat(discovery): batch approval with typed exceptions, and the CLI

Only live_named is promoted in bulk, expressed as a single equality rather
than a set of exclusions — a verdict added later defaults to not-approvable,
which is the safe direction.

Promotion is additive: existing entries including 'dead' ones are rewritten
unchanged, because rebuilding the registry from candidates would delete
curated history and silently re-enable boards a human had disabled.

A test asserts the module contains no git call. A1 says a human commits the
diff, and an approval step that commits for them is not a review.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: The coverage page — naming what is *not* covered

The M1 acceptance criterion is that the page names what is **not** covered, so
that is what this task is judged on.

**Files:**
- Modify: `services/api/nightshift/api/routes/sources.py`, `schemas.py`
- Create: `apps/web/src/app/analyze/coverage/page.tsx`
- Create: `services/api/tests/discovery/test_coverage.py`
- Modify: `apps/web/src/lib/schemas.ts`, `api.ts`
- Create: `apps/web/e2e-seeded/coverage.spec.ts`

**Interfaces:**
- Consumes: `load_candidates`, `load_registry`, the `sources`/`jobs` tables.
- Produces: `GET /coverage` → `CoverageOut`.

- [ ] **Step 1: Write the failing API test**

```python
# services/api/tests/discovery/test_coverage.py
"""The coverage report, and the blind spots it is required to name.

`board-discovery.md` §11: "A missing coverage number is worse than a low one."
The M1 acceptance criterion is not that the page reports coverage — it is that
it names what is *not* covered. So that is what these tests assert.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

# The blind spots §11 requires by name. Each is a real gap with a real reason,
# and a coverage page that omits one is claiming a completeness it does not have.
REQUIRED_BLIND_SPOTS = {
    "lever_undiscovered",
    "workday_icims_taleo",
    "no_public_board",
    "aggregator_only",
}


async def test_coverage_reports_boards_by_status_and_ats(client: AsyncClient) -> None:
    body = (await client.get("/coverage")).json()
    assert "boards" in body
    assert isinstance(body["boards"]["by_ats"], dict)


async def test_coverage_names_every_required_blind_spot(client: AsyncClient) -> None:
    body = (await client.get("/coverage")).json()
    named = {spot["id"] for spot in body["blind_spots"]}
    missing = REQUIRED_BLIND_SPOTS - named
    assert not missing, f"the coverage page hides these gaps: {sorted(missing)}"


async def test_every_blind_spot_explains_itself(client: AsyncClient) -> None:
    """An id nobody can read is not a disclosure."""
    body = (await client.get("/coverage")).json()
    for spot in body["blind_spots"]:
        assert len(spot["explanation"]) > 40


async def test_lever_blind_spot_states_the_structural_reason(client: AsyncClient) -> None:
    """Not "we haven't got round to Lever" — Common Crawl *cannot* see it, by
    Lever's own robots.txt, and it never will (ADR 0006)."""
    body = (await client.get("/coverage")).json()
    lever = next(s for s in body["blind_spots"] if s["id"] == "lever_undiscovered")
    assert "ccbot" in lever["explanation"].lower() or "robots" in lever["explanation"].lower()


async def test_candidates_awaiting_review_are_broken_down_by_verdict(
    client: AsyncClient,
) -> None:
    """A single "pending" number would hide that live_unnamed candidates need a
    human and empty ones do not."""
    body = (await client.get("/coverage")).json()
    assert set(body["candidates"]) >= {
        "live_named",
        "live_unnamed",
        "name_collision",
        "empty",
        "unreachable",
    }


async def test_coverage_never_reports_a_percentage_of_the_whole_market(
    client: AsyncClient,
) -> None:
    """There is no denominator. Nobody knows how many NYC tech jobs exist, so a
    coverage percentage would be a fabricated statistic — exactly the kind of
    confident-sounding number I6 forbids."""
    body = (await client.get("/coverage")).json()
    assert "percent_of_market" not in body
    assert "coverage_percent" not in body
```

- [ ] **Step 2: Implement the route and schema**

`CoverageOut` carries: `boards` (counts by status and ats, last polled
windows), `candidates` (counts by verdict), `nyc` (boards that produced an NYC
posting), and `blind_spots` — a list of `{id, title, explanation, count}` where
`count` is `null` when the size of the gap is genuinely unknown.

**`count: null` is a required feature, not a gap.** We do not know how many NYC
employers use Workday, and reporting `0` would be a lie. Null renders as
"unknown" and the page says so.

- [ ] **Step 3: Build the page**

`/analyze/coverage`. Two sections, and the second is the point:

1. **What is covered** — boards by provider and status, how many produced NYC
   roles, candidates awaiting review by verdict, last successful sweep.
2. **What is not** — one row per blind spot, with its explanation in plain
   language and its count or the word "unknown".

The second section must not be collapsible, behind a tab, or below a fold that
the first section pushes off screen. It is the acceptance criterion.

- [ ] **Step 4: Browser test**

```ts
test('the coverage page names what it does not cover', async ({ page }) => {
  await page.goto('/analyze/coverage');
  const gaps = page.getByRole('region', { name: /what is not covered/i });
  await expect(gaps).toBeVisible();
  await expect(gaps).toContainText(/lever/i);
  await expect(gaps).toContainText(/workday/i);
  // The honest answer where we genuinely cannot count.
  await expect(gaps).toContainText(/unknown/i);
});
```

- [ ] **Step 5: `make check`, `make acceptance`, commit**

Record the exact check and browser-test counts; both grow here.

---

## Task 6: Close the milestone

- [ ] **Step 1: Run a real discovery pass end to end**

```bash
make discover
make registry-validate     # needs OUTBOUND_HTTP_ENABLED=true
make registry-approve      # dry run — read the report
```

Record: how many tokens the fixture yielded, how many validated into each
verdict, and how many the report offered. **Do not commit a mass registry
change as part of this plan** — approving thousands of boards is a product
decision for the human, and the plan's job is to prove the pipeline works, not
to fill the registry.

- [ ] **Step 2: Update `docs/PROGRESS.md`**

1. Next action → M1d, with the plan path.
2. M1 acceptance table: mark criteria 10, 11 and 12 verified with evidence.
   Leave 13 (`304`) unclaimed — it is M1d.
3. "Not real yet": add that the registry still contains only hand-added boards
   unless the human approved a batch; add the careers-page probe if it was not
   built.
4. Session log: what the real discovery pass actually yielded, including
   anything that contradicted §3's measurements.
5. Update the test counts.

- [ ] **Step 3: Write `docs/reviews/milestone-1c-review.md`**

Look specifically for: a validator that classifies everything `unreachable`
when a provider changes shape; an approval path that can be tricked by a
hand-edited candidate file; token extraction that admits a path traversal;
rate-limit behaviour across thousands of tokens; and the coverage page claiming
a completeness it has not earned.

- [ ] **Step 4: Commit, push, open a PR, watch CI**

---

## Self-review

**Spec coverage.** Against `board-discovery.md` and the M1 criteria:

| Design section | Task |
|---|---|
| §4 architecture, boundaries | 1–4 (package layout; `crawl_index` has no provider knowledge, `approve` has no network) |
| §5 data flow | 2, 4 |
| §6 verdicts and the approval gate | 3, 4 |
| §8 NYC from parsed locations | 3 (`_count_nyc`) |
| §11 coverage reporting | 5 |
| §12 failure handling | 3 (`validate_token` never raises for a network reason) |
| §13 testing | 1, 3, 4 — every named fixture has a test |
| §7 polling, §10 scale path | **M1d** — not this plan |

M1 criteria: 10 (discovery from a committed fixture, deterministically) → Task
1; 11 (live-but-unnameable cannot reach bulk approval) → Tasks 3 and 4; 12
(coverage names what is not covered) → Task 5. Criterion 13 (`304`) is M1d.

**Deliberately not in this plan.** The careers-page probe for Lever
(`sources/careers_probe.py`) is designed in §4 and **not implemented here**. It
needs a list of employer domains to start from, which nothing in the repo has
yet, and building a domain-guessing heuristic would be the fabrication this
milestone is otherwise about preventing. It is named in Task 6's "Not real yet"
so the gap is recorded rather than hidden. The `community.py` snapshot source is
deferred for the same reason.

**Placeholders.** None in Tasks 1–4, which carry complete code. Task 5's route
and page are specified by their contract and their tests rather than by full
source — the shapes depend on `schemas.py` conventions that should be read at
the time, and the tests pin the behaviour that matters. Task 5 Step 2 says
exactly what `CoverageOut` must carry.

**Type consistency.** `Candidate` and `Verdict` are defined in Task 2 and used
under those names in Tasks 3, 4 and 5. `validate_token(client, *, ats, token,
today, known_names, source)` is defined in Task 3 and called with those
keywords in Task 4's CLI. `tokens_from_cdx(lines, *, host)` is defined in Task
1 and consumed in Task 4. `approvable(file, *, registry_tokens)` is used by
both `approval_report`'s caller and `promote`.

**Risks, checked rather than left open.**

- **`PoliteClient` has no `get_text`** — verified at `adapters/http.py:95`,
  where `get_json` is its only method. Task 3 Step 4 specifies adding one to
  that class, with a size cap, rather than opening a second HTTP path.
- **`yaml.safe_dump` will delete the registry's header comment.** Called out in
  Task 4 Step 3 with the fix.
- **A discovery sweep is thousands of requests.** Rate limiting is
  `PoliteClient`'s existing per-host limiter; the CLI's `--limit` exists so the
  first real run is small. Task 6 Step 1 runs it deliberately, not in CI.
- **The recorded crawl slice is truncated by `--limit`.** The meta file says
  so, and Task 1 Step 7 requires the commit message to report counts for the
  slice rather than restating the design's 2,605.
