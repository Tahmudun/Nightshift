"""Common Crawl's URL index as a source of board tokens (ADR 0006).

This module knows about URLs and nothing else: no provider APIs, no database,
no notion of what a "board" is beyond "the first path segment". That boundary
is what lets it be tested against a recorded file with no network at all.

**Lever is absent on purpose.** ``jobs.lever.co/robots.txt`` names CCBot —
Common Crawl's crawler — and disallows it, so Lever job pages are not in the
archive and never will be. Lever boards are found by careers-page probing
instead. A pattern here would harvest zero tokens forever and read as a bug
rather than as a structural absence.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Final
from urllib.parse import unquote, urlsplit

CRAWL_ID: Final = "CC-MAIN-2026-30"

CDX_URL: Final = (
    "https://index.commoncrawl.org/{crawl}-index?url={pattern}&output=json&fl=url&limit={limit}"
)

# ats -> the URL patterns that find its boards. Greenhouse serves two board
# domains and the newer one contributed 433 tokens the older one did not
# (board-discovery.md §3), so both are queried; using only one loses a sixth of
# the index.
PROVIDER_PATTERNS: Final[dict[str, tuple[str, ...]]] = {
    "greenhouse": ("boards.greenhouse.io/*", "job-boards.greenhouse.io/*"),
    "ashby": ("jobs.ashbyhq.com/*",),
}

#: Host per ats, used to reject a URL the server-side pattern matched but we
#: did not mean.
PROVIDER_HOSTS: Final[dict[str, tuple[str, ...]]] = {
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "ashby": ("jobs.ashbyhq.com",),
}

# Path segments that are never a board token. `application` appears *after* a
# token on Ashby apply URLs; the rest are provider infrastructure.
_NOT_TOKENS: Final = frozenset({"application", "api", "assets", "static", "favicon.ico"})

# The token is interpolated into a provider URL by validate.py, so it is
# constrained here rather than trusted later. Same shape registry.py enforces.
_TOKEN_SHAPE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

# A UUID is 36 characters. Deliberately a length rule rather than "no hyphens":
# the recorded slice contains real tokens like `a-place-for-mom` and
# `a16z-new-media`, and banning hyphens would reject them while letting nothing
# useful through.
_MAX_TOKEN_LENGTH: Final = 36


def tokens_from_cdx(lines: Iterable[str], *, host: str) -> list[str]:
    """Extract distinct board tokens from a CDX response.

    The response is newline-delimited JSON, one object per captured URL, and
    most of those URLs are job pages *beneath* a board rather than board roots::

        {"url": "https://jobs.ashbyhq.com/0g"}
        {"url": "https://jobs.ashbyhq.com/0g/1554138f-15dc-4225-93cc-44b64f2540ed"}
        {"url": "https://jobs.ashbyhq.com/0x/086...?utm_source=chainhire.careers"}

    So the token is path segment 1, never the last — taking the last would
    harvest job UUIDs and fill the registry with boards that do not exist.

    Returns a sorted list. Sorted rather than insertion-ordered so the candidate
    file's diff stays reviewable across runs; an unordered set would reshuffle
    the whole file every time, and a diff nobody can read is how a review step
    becomes a rubber stamp.
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
        if not isinstance(record, dict):
            continue
        url = record.get("url")
        if not isinstance(url, str):
            continue

        parts = urlsplit(url)
        # Exact host match. The pattern is applied server-side, but a pattern
        # can match a host we did not mean — `evil.jobs.ashbyhq.com.attacker`
        # contains the string we asked for.
        if parts.netloc.lower().split(":")[0] != host:
            continue

        segments = [segment for segment in parts.path.split("/") if segment]
        if not segments:
            continue

        # Decoding normalises a legitimately-encoded segment (`%61bc` -> `abc`)
        # so a real board is not missed because a crawler recorded it encoded.
        # It is NOT the traversal guard — `_TOKEN_SHAPE` is, and it rejects
        # `../x` and `%2E%2E%2Fx` alike because neither `/` nor `%` is in the
        # allowed character set. Verified by mutation: removing this decode
        # fails no test, which is the honest reason the comment says so.
        token = unquote(segments[0])
        if token.casefold() in _NOT_TOKENS:
            continue
        if len(token) >= _MAX_TOKEN_LENGTH:
            continue
        if not _TOKEN_SHAPE.match(token):
            continue
        tokens.add(token)

    return sorted(tokens)
