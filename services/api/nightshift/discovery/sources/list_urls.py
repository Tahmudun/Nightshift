"""Board tokens, mined out of the URLs the internship lists already carry.

the-hunt.md §5.3. A list entry is a *pointer*: it names a company, a title, a
location and a URL, and that URL usually points at a Greenhouse, Ashby or Lever
board this repository already knows how to read. Mining the token turns each
list into a discovery front-end aimed at companies that **demonstrably hire
interns**, which is a far better filter for this reader than a Common Crawl
sweep of every company that has ever had a job board (ADR 0006).

Nothing here reaches the network and nothing here approves anything. It emits
`(ats, token)` pairs for the existing `discover` -> `validate` -> `approve`
chain, and ADR 0005's rules apply unchanged — including that a live board whose
employer cannot be named never reaches bulk approval.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final
from urllib.parse import parse_qs, unquote, urlsplit

#: Exact hosts, per ATS. **Exact**, never a substring test: M5d's
#: `capture_origin` used `in` and read `linkedin.com.evil.example` as LinkedIn.
#: The same shape of mistake here would put an attacker-chosen token into the
#: registry, where `validate` would then interpolate it into a provider URL.
PROVIDER_HOSTS: Final[dict[str, tuple[str, ...]]] = {
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "ashby": ("jobs.ashbyhq.com",),
    "lever": ("jobs.lever.co",),
}

_HOST_TO_ATS: Final[dict[str, str]] = {
    host: ats for ats, hosts in PROVIDER_HOSTS.items() for host in hosts
}

#: Path segments that are never a board token. `application` follows a token on
#: Ashby apply URLs; `embed` is Greenhouse's embedded board, whose token lives
#: in the query string instead and is read there.
_NOT_TOKENS: Final = frozenset(
    {"application", "embed", "api", "assets", "static", "favicon.ico", "jobs"}
)

#: Greenhouse's embedded board carries the token here rather than in the path.
_EMBED_TOKEN_PARAMS: Final = ("for",)

#: The token is interpolated into a provider URL by `validate`, so it is
#: constrained here rather than trusted later. Same shape `registry.py` enforces
#: on a committed entry, and it is what rejects `../x` and `%2E%2E%2Fx` alike —
#: neither `/` nor `%` nor a space is in the allowed set.
_TOKEN_SHAPE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

#: A UUID is 36 characters, and Lever and Ashby both put one in the path. A
#: length rule rather than "no hyphens": real tokens include `a-place-for-mom`,
#: and banning hyphens would reject those while letting nothing useful through.
_MAX_TOKEN_LENGTH: Final = 35


def _token_from(url: str) -> tuple[str, str] | None:
    """One URL to one `(ats, token)` pair, or None if it is not a board URL."""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        # A malformed URL is one skipped entry, never a lost run: this runs over
        # 14,918 of them and one bad row must not cost the other 14,917.
        return None

    host = parts.netloc.lower().split(":")[0]
    ats = _HOST_TO_ATS.get(host)
    if ats is None:
        return None

    segments = [segment for segment in parts.path.split("/") if segment]

    # Greenhouse's embedded board: `/embed/job_app?for=<token>`. The path here
    # names no company at all, so reading only path segment 1 would drop these
    # silently — which is the failure mode this whole module exists to avoid.
    if segments and segments[0].casefold() == "embed":
        query = parse_qs(parts.query)
        for name in _EMBED_TOKEN_PARAMS:
            for value in query.get(name, ()):
                token = unquote(value).strip()
                if _is_token(token):
                    return ats, token
        return None

    if not segments:
        return None

    # Decoding normalises a legitimately-encoded segment (`%61bc` -> `abc`) so a
    # real board is not missed. It is NOT the traversal guard; `_TOKEN_SHAPE` is.
    token = unquote(segments[0])
    if not _is_token(token):
        return None
    return ats, token


def _is_token(candidate: str) -> bool:
    if candidate.casefold() in _NOT_TOKENS:
        return False
    if len(candidate) > _MAX_TOKEN_LENGTH:
        return False
    return bool(_TOKEN_SHAPE.match(candidate))


def tokens_from_listing_urls(urls: Iterable[str]) -> list[tuple[str, str]]:
    """Distinct `(ats, token)` pairs, in the order the URLs first named them.

    Insertion-ordered rather than sorted, unlike `tokens_from_cdx`: that one
    reads a whole crawl index and its output is a file a person diffs, so a
    stable sort is what keeps the review readable. This one runs over the stored
    payloads of a list whose own order is meaningful — most-recent first — and
    re-sorting would throw that away before the candidate file is written.
    """
    seen: dict[tuple[str, str], None] = {}
    for url in urls:
        pair = _token_from(url)
        if pair is not None:
            seen.setdefault(pair, None)
    return list(seen)
