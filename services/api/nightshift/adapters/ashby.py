"""Ashby job board adapter.

Endpoint (AMENDMENTS A1, verified against a live board on 2026-07-30):

    GET https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true

Unauthenticated, poll-only. Field shapes read off the Ramp board (123
postings, 12 kept in the committed fixture):

* The response is `{"apiVersion": 1, "jobs": [...]}`. A missing `jobs` key is
  a source problem, never evidence of zero jobs (I3).
* `location` is the primary; `secondaryLocations` is an array of objects each
  carrying a `location` string. Both routinely annotate parenthetically —
  "New York, NY (HQ)", "Remote (Canada)".
* `isRemote` does **not** mean the job is remote. On the recorded board, 10 of
  the 12 postings are at the New York headquarters with `isRemote: true`.
  Mapping that field onto `remote_policy` would relabel the entire
  headquarters as remote, and every one of those jobs is one a New York user
  is looking for. Remote policy is derived from the parsed locations, exactly
  as it is for the other two providers, and `isRemote` is deliberately not
  consulted anywhere in this module.
* `compensation.compensationTiers[].components[]` states its `interval`
  ("1 YEAR"), so `salary_period` is set — unlike Greenhouse, which states no
  period and therefore gets None. A tier also carries `EquityPercentage`,
  `EquityCashValue`, and `Commission` components with null `minValue`; only
  the component whose `compensationType` is `"Salary"` is read as pay.
* `employmentType` is explicit and includes "Intern".
* There is **no updated/modified field** and **no company name**
  (`board-discovery.md` §3). Both are asserted in the test suite.
* `address.postalAddress` is structured and would be a better location source
  than the free-text `location`/`secondaryLocations` strings. Deliberately
  unused here: geocoding is a later stage, and feeding a second location
  source into `job_locations` before it has its own fixtures would mean two
  code paths writing the same table.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Final, Protocol

import structlog

from nightshift.adapters.base import (
    BoardRef,
    FetchOutcome,
    NormalizedSourceJob,
    RawJob,
    SourceUnavailableError,
)
from nightshift.adapters.greenhouse import content_hash, html_to_text, normalize_title
from nightshift.db.base import EmploymentType, SourceType
from nightshift.domain.locations import infer_remote_policy, parse_location_list

log = structlog.get_logger(__name__)

BOARD_URL: Final = "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"

# Ashby's own vocabulary, mapped explicitly. Anything unlisted is `unknown`
# rather than a plausible default — A13 is emphatic that eligibility is M3's
# hard problem and guessing it here would put an unversioned classifier in the
# ingestion path.
_EMPLOYMENT_TYPES: Final[dict[str, EmploymentType]] = {
    "fulltime": EmploymentType.FULL_TIME,
    "parttime": EmploymentType.PART_TIME,
    "intern": EmploymentType.INTERNSHIP,
    "internship": EmploymentType.INTERNSHIP,
    "contract": EmploymentType.CONTRACT,
    "temporary": EmploymentType.TEMPORARY,
}

# Ashby's interval vocabulary. Unmapped values yield None: a period we cannot
# name is not a period we get to invent (A10).
_SALARY_INTERVALS: Final[dict[str, str]] = {
    "1 year": "year",
    "1 month": "month",
    "1 week": "week",
    "1 day": "day",
    "1 hour": "hour",
}


class _JsonClient(Protocol):
    async def get_json(self, url: str) -> Any: ...


def _parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed: datetime | date = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = date.fromisoformat(raw[:10])
        except ValueError:
            return None
    if isinstance(parsed, datetime):
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _map_employment_type(raw_employment: object) -> EmploymentType:
    """Map Ashby's `employmentType` string onto the domain enum.

    Split out from :meth:`AshbyAdapter.normalize` so the full vocabulary can
    be exercised directly: the recorded board only ever says "FullTime" or
    "Intern", so "Contract", "PartTime", and "Temporary" have no real posting
    to test against and are covered as synthetic values instead (I7 — a
    fabricated "real" posting would be the mock this invariant forbids).
    """
    if not isinstance(raw_employment, str):
        return EmploymentType.UNKNOWN
    return _EMPLOYMENT_TYPES.get(
        raw_employment.strip().casefold().replace("-", "").replace(" ", ""),
        EmploymentType.UNKNOWN,
    )


def _extract_locations(payload: dict[str, Any]) -> list[str]:
    """Primary first, then every secondary location, in source order."""
    segments: list[str] = []
    primary = payload.get("location")
    if isinstance(primary, str) and primary.strip():
        segments.append(primary)
    secondary = payload.get("secondaryLocations")
    if isinstance(secondary, list):
        for entry in secondary:
            if isinstance(entry, dict):
                value = entry.get("location")
                if isinstance(value, str) and value.strip():
                    segments.append(value)
    return segments


def _extract_salary(
    payload: dict[str, Any],
) -> tuple[float | None, float | None, str | None, str | None]:
    """Pull the Salary component out of the compensation tiers.

    Only `compensationType == "Salary"` is read. A tier also carries
    EquityPercentage, EquityCashValue, and Commission components with null
    values, and treating any of them as pay would publish a range the
    employer never stated (A10).
    """
    compensation = payload.get("compensation")
    if not isinstance(compensation, dict):
        return None, None, None, None
    tiers = compensation.get("compensationTiers")
    if not isinstance(tiers, list):
        return None, None, None, None

    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        components = tier.get("components")
        if not isinstance(components, list):
            continue
        for component in components:
            if not isinstance(component, dict):
                continue
            if component.get("compensationType") != "Salary":
                continue
            try:
                minimum = (
                    float(component["minValue"]) if component.get("minValue") is not None else None
                )
                maximum = (
                    float(component["maxValue"]) if component.get("maxValue") is not None else None
                )
            except (TypeError, ValueError):
                continue
            if minimum is None and maximum is None:
                continue
            if minimum is not None and maximum is not None and minimum > maximum:
                minimum, maximum = maximum, minimum
            currency = component.get("currencyCode")
            currency = (
                currency.strip().upper()[:3] if isinstance(currency, str) and currency else None
            )
            interval = component.get("interval")
            period = (
                _SALARY_INTERVALS.get(interval.strip().casefold())
                if isinstance(interval, str)
                else None
            )
            return minimum, maximum, currency, period
    return None, None, None, None


class AshbyAdapter:
    """Implements :class:`~nightshift.adapters.base.JobSourceAdapter`."""

    source_name = "ashby"
    source_type = SourceType.ATS_ASHBY

    def __init__(self, client: _JsonClient | None) -> None:
        self._client = client

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        """Poll one board. Never raises — I3 lives or dies on this method."""
        if self._client is None:
            raise RuntimeError("AshbyAdapter needs a client to fetch")
        url = BOARD_URL.format(token=board.token)
        try:
            payload = await self._client.get_json(url)
        except SourceUnavailableError as exc:
            log.warning(
                "ashby_board_unavailable",
                board=board.token,
                company=board.company,
                error=str(exc),
                http_status=exc.http_status,
            )
            return FetchOutcome(board=board, ok=False, http_status=exc.http_status, error=str(exc))

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            # A response shaped like `{"apiVersion": 1}` with no `jobs` key at
            # all is a source problem, and "no jobs" is the one conclusion we
            # must not draw from it (I3).
            return FetchOutcome(
                board=board,
                ok=False,
                http_status=200,
                error="unexpected payload shape: missing 'jobs' array",
            )

        jobs: list[RawJob] = []
        for entry in payload["jobs"]:
            if not isinstance(entry, dict) or entry.get("id") is None:
                continue
            jobs.append(
                RawJob(
                    source_job_id=str(entry["id"]),
                    source_company_key=board.token,
                    canonical_url=entry.get("jobUrl") or entry.get("applyUrl"),
                    payload=entry,
                )
            )

        log.info("ashby_board_fetched", board=board.token, jobs=len(jobs))
        return FetchOutcome(board=board, ok=True, jobs=tuple(jobs), http_status=200)

    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
        """Normalize, taking the employer name from the approved registry entry.

        Ashby publishes no company name anywhere in its API. The board page
        title carries one, which discovery reads at candidate time
        (`board-discovery.md` §6); ingestion uses the reviewed registry entry,
        never the board token — deriving it from the token is the I2 failure
        ADR 0005's `live_unnamed` verdict exists to prevent ("0g" is "0g Labs").
        """
        payload = raw_job.payload

        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError(f"ashby job {raw_job.source_job_id} has no title")

        description_html = payload.get("descriptionHtml")
        description_html = description_html if isinstance(description_html, str) else None
        description_plain = payload.get("descriptionPlain")
        description_text = (
            description_plain.strip()
            if isinstance(description_plain, str) and description_plain.strip()
            else html_to_text(description_html)
        )

        locations = parse_location_list(_extract_locations(payload))
        salary_min, salary_max, currency, period = _extract_salary(payload)

        employment_type = _map_employment_type(payload.get("employmentType"))

        return NormalizedSourceJob(
            source_job_id=raw_job.source_job_id,
            source_company_key=raw_job.source_company_key,
            company_name=board.company,
            canonical_url=raw_job.canonical_url,
            title=title,
            normalized_title=normalize_title(title),
            description_html=description_html,
            description_text=description_text,
            description_hash=content_hash(description_text),
            employment_type=employment_type,
            # Derived from parsed locations, exactly as for every other
            # provider. `isRemote` is deliberately not consulted — see the
            # module docstring and test_is_remote_does_not_mean_remote.
            remote_policy=infer_remote_policy(list(locations)),
            locations=tuple(locations),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            salary_period=period,
            # A10: Ashby publishes no application-deadline field at all.
            application_deadline=None,
            source_published_at=_parse_timestamp(payload.get("publishedAt")),
            # No such field on any Ashby posting. Asserted in the test suite
            # so this stays a recorded fact rather than an assumption.
            source_updated_at=None,
        )
