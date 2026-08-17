"""The `/matches` ceiling, held equal on both sides of the network boundary.

`useTreatments.ts` asked for 500 rows from an endpoint that accepts 200, and
**every city page load 422'd for as long as that code existed.** Nothing was
red. TanStack Query turned the rejection into an error state, the hook's own
docstring says a failed match query is survivable ("a beacon with no treatment
is a plain beacon"), and the city went on drawing plain beacons — so the
symptom was the absence of gold, on a corpus where gold is rare anyway.

That is the same defect M4c's review found between `MAX_BEACONS` and
`MAX_SIGNALS`: **two ceilings coupled by a comment.** A comment does not fail a
build. This does.

It is a text test rather than a request against a running server on purpose. It
needs no database, no stack and no network, so it runs in the unit suite where
somebody editing either constant will actually see it — a contract test that
only runs in `test-e2e-seeded` would have caught this defect months after it
shipped, which is roughly what happened.
"""

from __future__ import annotations

import re
from pathlib import Path

from nightshift.api.routes.matches import MAX_LIMIT

_API_TS = Path(__file__).parent.parent.parent.parent / "apps" / "web" / "src" / "lib" / "api.ts"


def test_the_web_client_knows_the_endpoints_real_ceiling() -> None:
    source = _API_TS.read_text()
    match = re.search(r"^export const MATCH_LIMIT = (\d+);$", source, re.MULTILINE)

    # A missing constant is the interesting failure, not a `None` attribute
    # error twelve lines later. If somebody inlines the number back into the
    # call site, this is the assertion that says so.
    assert match is not None, f"no `export const MATCH_LIMIT` in {_API_TS}"

    assert int(match.group(1)) == MAX_LIMIT, (
        f"apps/web/src/lib/api.ts asks for at most {match.group(1)} matches; "
        f"`GET /matches` accepts at most {MAX_LIMIT} and 422s above it"
    )


def test_no_caller_asks_for_more_than_the_ceiling() -> None:
    """The constant existing does not stop the next caller passing a literal.

    `fetchMatches(500)` type-checked, linted and shipped. What makes a number a
    ceiling is that reaching past it fails here rather than in a browser
    console nobody has open.
    """
    web_src = _API_TS.parent.parent
    offenders: list[str] = []

    for path in web_src.rglob("*.ts*"):
        if path.name.endswith(".test.ts") or path.name.endswith(".test.tsx"):
            continue
        for line, text in enumerate(path.read_text().splitlines(), start=1):
            for requested in re.findall(r"fetchMatches\(\s*(\d+)\s*\)", text):
                if int(requested) > MAX_LIMIT:
                    offenders.append(f"{path.relative_to(web_src)}:{line} asks for {requested}")

    assert offenders == [], (
        "these callers ask `/matches` for more rows than it will return, "
        f"which is a 422 on every load rather than a smaller answer: {offenders}"
    )
