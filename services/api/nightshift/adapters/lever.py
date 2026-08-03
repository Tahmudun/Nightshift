"""Lever job board adapter.

Endpoint (AMENDMENTS A1, verified against live boards on 2026-07-30):

    GET https://api.lever.co/v0/postings/{token}?mode=json

Unauthenticated, poll-only. `api.lever.co/robots.txt` is `Allow: /` with
`Crawl-delay: 1`, which `PoliteClient` already satisfies. Note that
`jobs.lever.co/robots.txt` disallows CCBot — that is why ADR 0006 says Lever
boards cannot be discovered from Common Crawl.

Field shapes were read off two real boards rather than from documentation:

* The response is a **JSON array**, not an object. An object shape is a source
  problem, never evidence of zero jobs (I3).
* `categories.allLocations` is an array of strings; `categories.location` is
  the primary. There is no delimited multi-location string to split.
* `salaryRange` is structured — `{min, max, currency, interval}` — and states
  its interval, so unlike Greenhouse `salary_period` can be set honestly.
* `createdAt` is **epoch milliseconds**.
* There is **no updated/modified field**, so `source_updated_at` stays null and
  change detection falls back to the description hash. M1d measured why this
  costs nothing: the board response already carries every posting in full
  (6,373 characters of `description` on the first `alloy` posting), so there is
  no second fetch here for a timestamp to gate. `is_two_phase` is False.
* It serves an **ETag and honours `If-None-Match`** (measured 2026-08-02),
  which matters more here than anywhere else — Lever is the one provider of the
  three that does **not** compress, so the 200 a 304 replaces is 232 KB.
* There is **no company name**. It comes from the registry entry a human
  approved; deriving it from the token would be the I2 failure ADR 0005 and
  `board-discovery.md` §6 both turn on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import structlog

from nightshift.adapters.base import (
    BoardRef,
    FetchOutcome,
    ListedPosting,
    NormalizedSourceJob,
    RawJob,
    SourceUnavailableError,
)
from nightshift.adapters.greenhouse import content_hash, normalize_title
from nightshift.adapters.http import ConditionalJsonClient
from nightshift.db.base import EmploymentType, SourceType
from nightshift.domain.locations import infer_remote_policy, parse_location_list

log = structlog.get_logger(__name__)

BOARD_URL: Final = "https://api.lever.co/v0/postings/{token}?mode=json"

#: Bumped when normalization changes, so a stored ETag earned by the old parser
#: is discarded rather than letting the new parser never see the payload it was
#: written for (ADR 0007).
PARSER_VERSION: Final = "1"

# Lever's own vocabulary, mapped explicitly. Anything unlisted is `unknown`
# rather than a plausible default — A13 is emphatic that eligibility is M3's
# hard problem and guessing it here would put an unversioned classifier in the
# ingestion path.
_COMMITMENTS: Final[dict[str, EmploymentType]] = {
    "full-time": EmploymentType.FULL_TIME,
    "full time": EmploymentType.FULL_TIME,
    "part-time": EmploymentType.PART_TIME,
    "part time": EmploymentType.PART_TIME,
    "intern": EmploymentType.INTERNSHIP,
    "internship": EmploymentType.INTERNSHIP,
    "contract": EmploymentType.CONTRACT,
    "temporary": EmploymentType.TEMPORARY,
}

# Lever's interval vocabulary. Unmapped values yield None: a period we cannot
# name is not a period we get to invent (A10).
_SALARY_INTERVALS: Final[dict[str, str]] = {
    "per-year-salary": "year",
    "per-month-salary": "month",
    "per-week-salary": "week",
    "per-day-salary": "day",
    "per-hour-wage": "hour",
}


def _epoch_millis_to_datetime(value: object) -> datetime | None:
    """Convert Lever's millisecond epoch to an aware UTC datetime.

    Returns None for anything unparseable. Reading milliseconds as seconds
    silently produces a date tens of thousands of years out, and every
    freshness calculation downstream would inherit it.
    """
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _extract_locations(payload: dict[str, Any]) -> list[str]:
    """Every location string the posting names, primary first."""
    categories = payload.get("categories")
    if not isinstance(categories, dict):
        return []
    all_locations = categories.get("allLocations")
    if isinstance(all_locations, list):
        segments = [str(item) for item in all_locations if isinstance(item, str)]
        if segments:
            primary = categories.get("location")
            # Keep the provider's primary first; A2 lets order carry meaning
            # for sorting and nothing else.
            if isinstance(primary, str) and primary in segments:
                segments.remove(primary)
                segments.insert(0, primary)
            return segments
    primary = categories.get("location")
    return [primary] if isinstance(primary, str) and primary.strip() else []


def _extract_salary(
    payload: dict[str, Any],
) -> tuple[float | None, float | None, str | None, str | None]:
    salary = payload.get("salaryRange")
    if not isinstance(salary, dict):
        return None, None, None, None
    try:
        minimum = float(salary["min"]) if salary.get("min") is not None else None
        maximum = float(salary["max"]) if salary.get("max") is not None else None
    except (TypeError, ValueError):
        return None, None, None, None
    if minimum is None and maximum is None:
        return None, None, None, None
    if minimum is not None and maximum is not None and minimum > maximum:
        # Transposed range: keep the numbers, do not invent an ordering.
        minimum, maximum = maximum, minimum
    currency = salary.get("currency")
    currency = currency.strip().upper()[:3] if isinstance(currency, str) and currency else None
    interval = salary.get("interval")
    period = (
        _SALARY_INTERVALS.get(interval.strip().casefold()) if isinstance(interval, str) else None
    )
    return minimum, maximum, currency, period


def _description_text(payload: dict[str, Any]) -> str | None:
    """Lever ships plain text alongside its HTML, so no unescaping is needed."""
    parts = [
        payload.get("descriptionPlain"),
        payload.get("additionalPlain"),
    ]
    text = "\n\n".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
    return text or None


def _description_html(payload: dict[str, Any]) -> str | None:
    parts = [payload.get("description"), payload.get("additional")]
    html_text = "\n".join(p for p in parts if isinstance(p, str) and p.strip())
    return html_text or None


class LeverAdapter:
    """Implements :class:`~nightshift.adapters.base.JobSourceAdapter`."""

    source_name = "lever"
    source_type = SourceType.ATS_LEVER
    parser_version = PARSER_VERSION
    #: Lever's board response carries every posting in full — 6,373 characters
    #: of `description` on the first alloy posting, measured 2026-08-02 — so a
    #: second phase would be a request that could add nothing.
    is_two_phase = False

    def __init__(self, client: ConditionalJsonClient | None) -> None:
        self._client = client

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        """Poll one board. Never raises for a source failure.

        I3 lives or dies on this method: a bad response, timeout, or
        malformed payload becomes ``ok=False`` on the returned
        :class:`FetchOutcome`, never an exception, because a caller that has
        to catch an exception here is one refactor away from treating "the
        source errored" as "the board is empty" and closing jobs that are
        still open. That guarantee covers source failures only — a missing
        client is a caller bug, not a source failure, and still raises.
        """
        if self._client is None:
            raise RuntimeError("LeverAdapter needs a client to fetch")
        url = BOARD_URL.format(token=board.token)
        try:
            response = await self._client.get_json_conditional(url, etag=etag)
        except SourceUnavailableError as exc:
            log.warning(
                "lever_board_unavailable",
                board=board.token,
                company=board.company,
                error=str(exc),
                http_status=exc.http_status,
            )
            return FetchOutcome(board=board, ok=False, http_status=exc.http_status, error=str(exc))

        if response.not_modified:
            # Zero writes downstream. The board is byte-identical to the copy we
            # already parsed, so every posting we know about is still listed and
            # none of them needs re-reading. Worth most on this provider: Lever
            # is the one of the three that does not compress, so the 200 it
            # replaces is 232 KB on the wire (measured 2026-08-02).
            return FetchOutcome(board=board, ok=True, not_modified=True, etag=etag, http_status=304)

        payload = response.payload
        if not isinstance(payload, list):
            # An unknown token 404s and never reaches here. A 200 with the
            # wrong shape is a source problem, and "no jobs" is the one
            # conclusion we must not draw from it.
            return FetchOutcome(
                board=board,
                ok=False,
                http_status=200,
                error=(
                    f"unexpected payload shape: expected a JSON array, got {type(payload).__name__}"
                ),
            )

        jobs: list[RawJob] = []
        for entry in payload:
            if not isinstance(entry, dict) or entry.get("id") is None:
                continue
            jobs.append(
                RawJob(
                    source_job_id=str(entry["id"]),
                    source_company_key=board.token,
                    canonical_url=entry.get("hostedUrl") or entry.get("applyUrl"),
                    payload=entry,
                )
            )

        log.info("lever_board_fetched", board=board.token, jobs=len(jobs))
        return FetchOutcome(
            board=board,
            ok=True,
            jobs=tuple(jobs),
            # Single-phase: everything fetched is everything listed. Lever
            # publishes `createdAt` and no updated-at field, and needs none —
            # there is no second fetch here for a timestamp to gate, and
            # promoting a creation date to a modification date would make every
            # posting look changed once and then never again.
            listed=tuple(
                ListedPosting(source_job_id=job.source_job_id, source_updated_at=None)
                for job in jobs
            ),
            etag=response.etag,
            http_status=response.http_status,
        )

    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
        """Normalize, taking the employer name from the approved registry entry.

        Lever publishes no company name anywhere in its payload. The name
        comes from `board.company` — the registry entry a human approved,
        never the board token (I2, and `board-discovery.md` §3 "the token is
        not the name").
        """
        payload = raw_job.payload

        title = str(payload.get("text") or "").strip()
        if not title:
            raise ValueError(f"lever job {raw_job.source_job_id} has no title")

        description_text = _description_text(payload)
        locations = parse_location_list(_extract_locations(payload))
        salary_min, salary_max, currency, period = _extract_salary(payload)

        categories = payload.get("categories")
        commitment = categories.get("commitment") if isinstance(categories, dict) else None
        employment_type = EmploymentType.UNKNOWN
        if isinstance(commitment, str):
            employment_type = _COMMITMENTS.get(
                commitment.strip().casefold(), EmploymentType.UNKNOWN
            )

        return NormalizedSourceJob(
            source_job_id=raw_job.source_job_id,
            source_company_key=raw_job.source_company_key,
            company_name=board.company,
            canonical_url=raw_job.canonical_url,
            title=title,
            normalized_title=normalize_title(title),
            description_html=_description_html(payload),
            description_text=description_text,
            description_hash=content_hash(description_text),
            employment_type=employment_type,
            remote_policy=infer_remote_policy(list(locations)),
            locations=tuple(locations),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            salary_period=period,
            # A10: Lever publishes no deadline field at all.
            application_deadline=None,
            source_published_at=_epoch_millis_to_datetime(payload.get("createdAt")),
            # No such field on any Lever posting. Asserted in the test suite so
            # this stays a recorded fact rather than an assumption.
            source_updated_at=None,
        )
