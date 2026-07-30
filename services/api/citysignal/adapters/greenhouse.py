"""Greenhouse job board adapter.

Endpoint (AMENDMENTS A1, re-verified against a live board on 2026-07-29):

    GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

Unauthenticated, poll-only, no webhooks. Field shapes below were read off a real
response (Datadog, 426 postings) rather than from documentation, and the notes
record what that response actually contained:

* ``content`` is HTML **and HTML-escaped** — ``&lt;p&gt;`` on the wire. It needs
  unescaping before it is HTML at all.
* ``location.name`` is a single ``;``-delimited string that routinely names ten
  places. This is the concrete reason ``job_locations`` is its own table (A2).
* ``application_deadline`` was null on all 426 postings, exactly as A10 predicts.
* Compensation is not a top-level field. It hides in ``metadata`` as an entry
  with ``value_type == "currency_range"``, and it is null more often than not.
* ``updated_at`` is a last-modified stamp; ``first_published`` is the real
  publication date. A10 forbids conflating them, so both are carried separately.
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, date, datetime
from typing import Any, Final

import structlog

from citysignal.adapters.base import (
    BoardRef,
    FetchOutcome,
    NormalizedSourceJob,
    RawJob,
    SourceUnavailableError,
)
from citysignal.adapters.http import PoliteClient
from citysignal.db.base import EmploymentType, SourceType
from citysignal.domain.locations import infer_remote_policy, parse_location_field

log = structlog.get_logger(__name__)

BOARD_URL: Final = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"

_TAG = re.compile(r"<[^>]+>")
_BLOCK_END = re.compile(r"</(?:p|div|li|ul|ol|h[1-6]|tr|table|blockquote)\s*>", re.IGNORECASE)
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_LIST_ITEM = re.compile(r"<li[^>]*>", re.IGNORECASE)
_BLANK_LINES = re.compile(r"\n{3,}")
_WHITESPACE = re.compile(r"[ \t]+")

# Word-boundary matching, so "International" is not an internship and
# "Winternship" is not a false positive either.
_INTERNSHIP = re.compile(r"\b(intern|interns|internship|co-?op)\b", re.IGNORECASE)
_CONTRACT = re.compile(r"\b(contract|contractor|temporary|temp)\b", re.IGNORECASE)


def html_to_text(raw_html: str | None) -> str | None:
    """Flatten Greenhouse's escaped HTML description into readable plain text.

    Regex rather than a parser, deliberately: the input is machine-generated
    rich-text output, not arbitrary web HTML, and adding lxml to solve a problem
    we have not confirmed we have is the dependency anti-pattern in CLAUDE.md §8.
    If a real posting breaks this, that is a fixture and then a parser.
    """
    if not raw_html:
        return None
    # Unescape first: the payload is double-encoded, so `&lt;p&gt;` must become
    # `<p>` before any tag handling can see it.
    text = html.unescape(raw_html)
    text = _BREAK.sub("\n", text)
    text = _LIST_ITEM.sub("\n• ", text)
    text = _BLOCK_END.sub("\n\n", text)
    text = _TAG.sub("", text)
    # A second unescape catches entities that were escaped inside the HTML
    # itself (`&amp;nbsp;` -> `&nbsp;` -> a space).
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = _WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text).strip()
    return text or None


def normalize_title(title: str) -> str:
    """Casefolded, whitespace-collapsed title for grouping and dedupe.

    Intentionally shallow. Role-family normalization ("SWE II" and "Software
    Engineer 2" are the same family) is M3's job with M3's fixtures; guessing at
    it here would put an unversioned classifier in the ingestion path.
    """
    # The en and em dashes below are the point — real titles use both as
    # separators, and folding them together is what makes the keys comparable.
    # Hence the RUF001 suppressions: the "ambiguous" characters are deliberate.
    cleaned = _WHITESPACE.sub(" ", title.replace("–", "-").replace("—", "-"))  # noqa: RUF001
    return cleaned.strip().strip("-–—,·|").strip().casefold()  # noqa: RUF001


def content_hash(text: str | None) -> str:
    """Stable sha256 over normalized description text.

    Normalizing whitespace before hashing means a reformatted-but-unchanged
    description does not register as an update, which is what keeps
    re-ingestion from producing spurious updates.
    """
    basis = " ".join((text or "").split())
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _parse_timestamp(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp or date into an aware UTC datetime.

    Returns None for anything unparseable. A wrong timestamp silently corrupts
    every freshness calculation downstream, so a missing one is strictly better.
    """
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


def _metadata_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries = payload.get("metadata")
    if not isinstance(entries, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            index[entry["name"].strip().casefold()] = entry
    return index


def _extract_compensation(
    metadata: dict[str, dict[str, Any]],
) -> tuple[float | None, float | None, str | None]:
    """Pull a pay range out of ``metadata``, if the board publishes one.

    Present on NYC postings because of pay-transparency law, absent on most
    others (A10). No period is returned: Greenhouse does not state whether the
    figures are annual or hourly, and inferring it from magnitude would be a
    guess presented as data. The UI says "period not specified by source".
    """
    for entry in metadata.values():
        if entry.get("value_type") != "currency_range":
            continue
        value = entry.get("value")
        if not isinstance(value, dict):
            continue
        try:
            minimum = float(value["min_value"]) if value.get("min_value") is not None else None
            maximum = float(value["max_value"]) if value.get("max_value") is not None else None
        except (TypeError, ValueError):
            continue
        if minimum is None and maximum is None:
            continue
        if minimum is not None and maximum is not None and minimum > maximum:
            # Transposed range: keep the numbers, do not invent an ordering.
            minimum, maximum = maximum, minimum
        unit = value.get("unit")
        currency = unit.strip().upper()[:3] if isinstance(unit, str) and unit.strip() else None
        return minimum, maximum, currency
    return None, None, None


def _extract_employment_type(title: str, metadata: dict[str, dict[str, Any]]) -> EmploymentType:
    """Classify employment type from explicit signals only.

    Order matters: an explicit "Intern" in the title outranks a "Time Type" of
    "Full time", because internships are routinely tagged full-time hours.

    This is not the seniority or eligibility classifier. A13 is emphatic that
    eligibility is the hard problem, needs at least 50 hand-labeled postings,
    and belongs to M3 — so anything not explicitly stated resolves to
    ``unknown`` rather than to a plausible default.
    """
    if _INTERNSHIP.search(title):
        return EmploymentType.INTERNSHIP
    if _CONTRACT.search(title):
        return EmploymentType.CONTRACT

    time_type = metadata.get("time type", {}).get("value")
    if isinstance(time_type, str):
        normalized = time_type.strip().casefold()
        if normalized in {"full time", "full-time", "fulltime"}:
            return EmploymentType.FULL_TIME
        if normalized in {"part time", "part-time", "parttime"}:
            return EmploymentType.PART_TIME
        if "intern" in normalized:
            return EmploymentType.INTERNSHIP
        if "contract" in normalized or "temp" in normalized:
            return EmploymentType.CONTRACT
    return EmploymentType.UNKNOWN


class GreenhouseAdapter:
    """Implements :class:`~citysignal.adapters.base.JobSourceAdapter`."""

    source_name = "greenhouse"
    source_type = SourceType.ATS_GREENHOUSE

    def __init__(self, client: PoliteClient) -> None:
        self._client = client

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        """Poll one board. Never raises — I3 lives or dies on this method.

        A failure returns ``ok=False``, which tells the caller it learned
        *nothing* about these jobs. That is categorically different from
        ``ok=True`` with an empty list, which means the board really is empty.
        Collapsing the two is how a source outage closes a thousand live jobs.
        """
        url = BOARD_URL.format(token=board.token)
        try:
            payload = await self._client.get_json(url)
        except SourceUnavailableError as exc:
            log.warning(
                "greenhouse_board_unavailable",
                board=board.token,
                company=board.company,
                error=str(exc),
                http_status=exc.http_status,
            )
            return FetchOutcome(board=board, ok=False, http_status=exc.http_status, error=str(exc))

        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            # A 200 with an unexpected shape is a source problem, not evidence
            # of zero jobs. Treat it as unavailable.
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
                    canonical_url=entry.get("absolute_url"),
                    payload=entry,
                )
            )

        log.info("greenhouse_board_fetched", board=board.token, jobs=len(jobs))
        return FetchOutcome(board=board, ok=True, jobs=tuple(jobs), http_status=200)

    def normalize(self, raw_job: RawJob) -> NormalizedSourceJob:
        """Pure mapping from raw payload to domain model. No I/O, no clock."""
        payload = raw_job.payload
        metadata = _metadata_index(payload)

        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError(f"greenhouse job {raw_job.source_job_id} has no title")

        description_html = payload.get("content")
        description_html = description_html if isinstance(description_html, str) else None
        description_text = html_to_text(description_html)

        location_field = payload.get("location")
        location_name = location_field.get("name") if isinstance(location_field, dict) else None
        locations = parse_location_field(location_name if isinstance(location_name, str) else None)

        salary_min, salary_max, currency = _extract_compensation(metadata)

        company_name = str(payload.get("company_name") or "").strip()

        return NormalizedSourceJob(
            source_job_id=raw_job.source_job_id,
            source_company_key=raw_job.source_company_key,
            company_name=company_name or raw_job.source_company_key,
            canonical_url=raw_job.canonical_url,
            title=title,
            normalized_title=normalize_title(title),
            description_html=html.unescape(description_html) if description_html else None,
            description_text=description_text,
            description_hash=content_hash(description_text),
            employment_type=_extract_employment_type(title, metadata),
            remote_policy=infer_remote_policy(list(locations)),
            locations=tuple(locations),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            # Greenhouse states no period. See _extract_compensation.
            salary_period=None,
            application_deadline=_parse_timestamp(payload.get("application_deadline")),
            source_published_at=_parse_timestamp(payload.get("first_published")),
            source_updated_at=_parse_timestamp(payload.get("updated_at")),
        )
