"""Classify a discovered token by asking the provider (board-discovery.md §6).

This is the only module in `nightshift/discovery/` that talks to a provider,
and it does so through `PoliteClient` — nothing else in the repo imports httpx
and that stays true.

The employer name is the load-bearing field. `live_named` is the only verdict
eligible for bulk approval (ADR 0005), and it requires that the *provider* told
us who this is:

* Greenhouse — `GET /v1/boards/{token}` returns `{"name": ...}`.
* Ashby — nowhere in the API. The board page's `<title>` carries it, and
  Ashby's robots.txt permits that page (checked 2026-08-02: it disallows only
  `/meeting/`, `/b/` and `/api/`). One extra request per candidate, at
  discovery time only.
* Lever — not available; Lever boards are found by careers-page probing, which
  starts from a company's own domain and therefore already knows the employer.

We never derive a name from the token. Measured on the 23 real Ashby tokens in
the committed crawl slice: **ten of the twenty-one live boards have a name that
is not their token** — `0g` is "0g Labs", `a-place-for-mom` is "A Place for
Mom", `a-team` is "A.Team". Deriving a name from a token would be wrong about
half the time, and wrong in the direction of inventing an employer (I2).
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
_JOBS_SUFFIX = " jobs"


class _Client(Protocol):
    async def get_json(self, url: str) -> Any: ...
    async def get_text(self, url: str) -> str: ...


def extract_ashby_name(html: str) -> str | None:
    """Pull the employer name out of an Ashby board page.

    Ashby suffixes the title with " Jobs" — the recorded `0g` page is
    `<title>0g Labs Jobs</title>`. A title that is *only* that suffix yields
    None rather than an empty string, and this is not a hypothetical: Ashby
    serves HTTP 200 with `<title>Jobs</title>` for any token that does not
    exist, recorded verbatim in `ashby_unnameable_page.html`. None routes the
    candidate to manual review, which is the safe direction; returning the
    token here would be the exact I2 failure this module exists to prevent.

    The suffix is stripped once, not repeatedly, so an employer genuinely
    called "Jobs" survives as "Jobs" rather than being reduced to nothing.
    """
    for pattern in (_OG_TITLE, _TITLE):
        match = pattern.search(html)
        if match is None:
            continue
        title = " ".join(match.group(1).split())
        if title.casefold().endswith(_JOBS_SUFFIX):
            title = title[: -len(_JOBS_SUFFIX)].strip()
        elif title.casefold() == "jobs":
            title = ""
        if title:
            return title
    return None


def _postings(ats: str, payload: Any) -> list[Any] | None:
    """The provider's postings, or None if the payload is the wrong shape.

    None is not zero. A wrong shape means the source changed and we learned
    nothing; zero means the board really is empty (ADR 0003). The two providers
    disagree on the shape of "empty" — Lever's is `[]`, Ashby's is
    `{"jobs": []}` — which is why each is checked against its own.

    ``list[Any]``, not ``list[dict[...]]``: the list itself is checked, its
    *elements* are whatever the provider sent. Claiming they are dicts would be
    a promise this function never verifies, and callers would stop guarding.
    """
    if ats in {"ashby", "greenhouse"}:
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


def _count_nyc(ats: str, postings: list[Any]) -> int:
    """How many postings name a NYC location.

    Read off the postings by the parser, never declared by a registry entry
    (board-discovery.md §8). M1d's hot tier reads this number, which is why the
    parser breadth in M1a was a hard prerequisite for this milestone.

    A non-dict element is skipped rather than counted or fatal: a board that
    sends `{"jobs": [null]}` is still a live board, and one junk element must
    not cost the whole sweep.
    """
    count = 0
    for posting in postings:
        if not isinstance(posting, dict):
            continue
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

    An unknown `ats` does raise, and raises before any request is made — a typo
    in a provider name would otherwise classify every board as unreachable,
    quietly empty the registry, and spend a sweep's worth of requests doing it.
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
    except Exception as exc:
        # Deliberately broad: a sweep must not die on one board.
        log.warning("validate_unexpected_error", ats=ats, token=token, error=str(exc))
        return unreachable(f"unexpected: {type(exc).__name__}: {exc}")

    postings = _postings(ats, payload)
    if postings is None:
        # A 200 with the wrong shape is a source problem, and "no jobs" is the
        # one conclusion we must not draw from it.
        return unreachable(f"unexpected payload shape: {type(payload).__name__}")

    if not postings:
        # No name lookup: there is nothing here to approve, and the extra
        # request would repeat across every dormant board in the registry.
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
    except Exception as exc:
        # Same reason: a failed name lookup downgrades one candidate to manual
        # review, it does not end the sweep.
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

    try:
        collides = normalize_company_name(name) in known_names
    except ValueError:
        # A name that normalises to nothing is not a name. Treat it as if the
        # provider had said nothing rather than inventing a registry key.
        log.warning("name_normalizes_to_nothing", ats=ats, token=token, name=name)
        return Candidate(
            ats=ats,
            token=token,
            verdict=Verdict.LIVE_UNNAMED,
            posting_count=len(postings),
            nyc_posting_count=nyc,
            first_seen=today,
            last_validated=today,
            source=source,
            notes=f"provider returned a name that normalises to nothing: {name!r}",
        )

    return Candidate(
        ats=ats,
        token=token,
        verdict=Verdict.NAME_COLLISION if collides else Verdict.LIVE_NAMED,
        company_name=name,
        posting_count=len(postings),
        nyc_posting_count=nyc,
        first_seen=today,
        last_validated=today,
        source=source,
    )
