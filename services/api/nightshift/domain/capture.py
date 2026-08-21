"""A posting somebody pasted, and the two steps between that and a job.

M5a / AMENDMENTS A16. Every other way a posting enters this database begins
with a provider serving JSON at a URL we can go back to. This one begins with a
person and a clipboard, and that difference is the whole design of this module.

## Why there is a confirmation step at all

Invariant I2's letter is about user *qualifications*, and a job posting is not
one. The reason capture is gated anyway is invariant **I1**, reached by a route
that is easy to miss:

    pasted text -> a guess at the employer's name -> a company row ->
    that company's confirmed office -> a beacon on a **building**

Greenhouse tells us which string is the company. Free text does not. A parser
that reads the wrong line puts a real job on a real building belonging to
somebody else, and it looks exactly as confident as a correct one. That is a
fabricated location, arrived at through the side door, and no amount of care in
the geocoder prevents it — the geocoder was given the wrong company and did its
job perfectly.

So the parser proposes and a person disposes. What reaches ``jobs`` is what
somebody approved, which makes it user-entered data rather than inferred data,
which is the strongest provenance available to anything in this product.

## What the parser is allowed to do

Decline. Constantly.

Every field here is optional and ``None`` is the expected answer for text the
parser cannot read confidently. A blank field costs a person four seconds of
typing into a form they are already looking at. A *wrong* field costs them a
building. The asymmetry is not close, and every threshold below is set by it.

The location proposal in particular is not decided by a regex written here — it
is decided by ``parse_location_segment``, which already refuses bare tokens like
"Global" and already returns ``UNKNOWN`` rather than inventing a city. Reusing
its judgement rather than writing a second one means the confidence test and the
eventual parse agree by construction.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import NormalizedSourceJob, RawJob
from nightshift.adapters.greenhouse import content_hash, normalize_title
from nightshift.db.base import CaptureStatus, EmploymentType, LocationConfidence, SourceType
from nightshift.db.models import CapturedPosting, Job, JobSourceLink, Source, SourceJobRecord
from nightshift.domain.companies import normalize_company_name
from nightshift.domain.ingestion import get_or_create_source, persist_source_job
from nightshift.domain.locations import (
    ParsedLocation,
    infer_remote_policy,
    parse_location_field,
    parse_location_segment,
)

#: Bumped when the proposal rules below change. Stored on every row so a bad
#: proposal can be attributed to the parser that made it rather than argued
#: about from memory.
CAPTURE_PARSER_VERSION = "1"

#: The name and type of the source every captured posting is attributed to.
#: One source for all users and all captures: a pasted posting is public
#: information and the job corpus is shared, exactly as it is for polled boards.
#: What stays private is the *application*, which lives behind a ``user_id`` in
#: another table entirely.
CAPTURE_SOURCE_NAME = "manual_capture"

#: A job title is a short noun phrase. Anything longer is a paragraph that
#: happened to be first, and proposing it would seed the form with junk.
_MAX_TITLE_CHARS = 200
_MAX_COMPANY_CHARS = 100

#: How far into the paste to look for a location. Job boards put it in the
#: header; a match found in the body is as likely to be a relocation clause.
_LOCATION_SEARCH_LINES = 8

#: Separators job boards put between a company and everything else:
#: "Datadog · New York, NY (Hybrid)", "Acme | Remote", "Foo - New York".
_COMPANY_SEPARATOR = re.compile(r"\s+[·|—–]\s+|\s+-\s+|\s+@\s+", re.UNICODE)  # noqa: RUF001

_URLISH = re.compile(r"https?://|www\.", re.IGNORECASE)

#: Word-boundaried on purpose: "internal tooling" and "international" are not
#: internships, and both appear in real titles.
_INTERNSHIP = re.compile(r"\bintern(ship|ships|s)?\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CaptureProposal:
    """What the parser offers to seed the form with. Every field may be None."""

    title: str | None = None
    company_name: str | None = None
    location_text: str | None = None
    employment_type: EmploymentType | None = None


def _lines(raw_text: str) -> list[str]:
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def employment_type_for_title(title: str | None) -> EmploymentType | None:
    """The one employment type a title states outright, or None.

    Public and named because two callers need the same answer: ``propose``
    when the paste first arrives, and the route when it re-reads a stored
    capture. The first draft kept this inline and had the route return a
    hardcoded ``None``, so the detection worked, was unit-tested, and never
    reached a single person — the form always opened on "Not stated".

    Not stored as a column for the same reason it is derived here: it is a
    function of the title, and a column could disagree with the title sitting
    beside it in the form.
    """
    if title is None:
        return None
    return EmploymentType.INTERNSHIP if _INTERNSHIP.search(title) else None


def _looks_like_a_location(candidate: str) -> bool:
    """Does this string name a place, as opposed to merely parsing as one?

    Reuses ``parse_location_segment``'s reading but **not** its confidence
    value, and the difference is the whole function. That parser's job is to
    read a field already known to be a location; deciding whether an arbitrary
    line *is* one is a different question, and its own docstring records the
    gap — "this still lets pure junk corroborate junk". Any comma is enough:

        "Senior Software Engineer, Platform"  -> city "Platform", city_only
        "Acme, Inc."                          -> city "Inc.",     city_only

    Both are ``city_only``, so a confidence test proposes a job title as a
    location. Measured, not reasoned about — the first draft of this function
    did exactly that and the test above caught it.

    What separates a real place from a corroborated accident is whether
    anything *recognised* came back: a state, a country, or one of the
    enumerated NYC names (ADR 0008) that providers write without a state. A
    city with none of those behind it is a noun that happened to follow a
    comma.
    """
    if not candidate or len(candidate) > 200:
        return False
    parsed = parse_location_segment(candidate, is_primary=True)
    if parsed.confidence is LocationConfidence.REMOTE:
        return True
    return parsed.state is not None or parsed.country is not None or parsed.is_nyc


def propose(raw_text: str) -> CaptureProposal:
    """Read what can be read confidently and decline the rest.

    Deliberately not clever. Job boards put the title first and the employer
    second, and when they do this finds both. When they do not, it returns
    ``None`` and a person types two words.
    """
    lines = _lines(raw_text)
    if not lines:
        return CaptureProposal()

    title: str | None = None
    head = lines[0]
    if len(head) <= _MAX_TITLE_CHARS and not _URLISH.search(head):
        title = head

    company_name: str | None = None
    if len(lines) > 1:
        # The employer is the part before the first separator, because
        # "Datadog · New York, NY (Hybrid)" is one line carrying two facts.
        candidate = _COMPANY_SEPARATOR.split(lines[1])[0].strip()
        if candidate and len(candidate) <= _MAX_COMPANY_CHARS and not _URLISH.search(candidate):
            company_name = candidate

    location_text: str | None = None
    # Skip the line the title came from. One line cannot be both, and every
    # board that puts a title first puts the location after it.
    first_location_line = 1 if title is not None else 0
    for line in lines[first_location_line:_LOCATION_SEARCH_LINES]:
        # Narrowest match wins. "Datadog · New York, NY (Hybrid)" contains a
        # state and so reads as a location *as a whole line* — which would
        # propose the employer's name as part of the place. Splitting first
        # means the segment that is only a location is the one that matches.
        segments = [part.strip() for part in _COMPANY_SEPARATOR.split(line) if part.strip()]
        for segment in segments or [line.strip()]:
            if _looks_like_a_location(segment):
                location_text = segment
                break
        if location_text is not None:
            break

    return CaptureProposal(
        title=title,
        company_name=company_name,
        location_text=location_text,
        employment_type=employment_type_for_title(title),
    )


async def create_capture(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    raw_text: str,
    source_url: str | None,
) -> CapturedPosting:
    """Store the paste and the parser's reading of it. Creates no job.

    Takes no ``now``, unlike its siblings below: ``created_at`` carries a server
    default and ``decided_at`` must stay NULL here — the check constraint
    ``decided_rows_carry_a_time`` refuses a pending row that claims a decision
    time, which is the schema saying the same thing this signature does.
    """
    proposal = propose(raw_text)
    capture = CapturedPosting(
        user_id=user_id,
        raw_text=raw_text,
        source_url=source_url,
        status=CaptureStatus.PENDING,
        proposed_title=proposal.title,
        proposed_company_name=proposal.company_name,
        proposed_location_text=proposal.location_text,
        parser_version=CAPTURE_PARSER_VERSION,
    )
    session.add(capture)
    await session.flush()
    return capture


def capture_source_job_id(*, company_name: str, title: str, description: str) -> str:
    """A stable identity for a posting nobody assigned an id to.

    ``persist_source_job`` is idempotent on ``(source_id, source_job_id)``, so
    this function is what makes pasting the same posting twice a no-op.

    Derived from content rather than from the capture row or the user, and that
    is the load-bearing choice: two *different people* capturing the same
    opening must land on the same job. A per-user or per-capture id would give
    the corpus one row per person who noticed, which is the duplicate problem
    M1's whole dedupe layer exists to prevent, reintroduced at the source.

    The URL is deliberately *not* part of it. The same posting is served at
    ``…?src=share``, ``…?refId=…`` and a dozen other tracking suffixes, so
    keying on the URL would make one opening several.
    """
    basis = "\x1f".join(
        (
            normalize_company_name(company_name),
            normalize_title(title),
            content_hash(description),
        )
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


class CaptureAlreadyDecidedError(Exception):
    """Raised when confirming or discarding a capture that is not pending."""


async def confirm_capture(
    session: AsyncSession,
    *,
    capture: CapturedPosting,
    title: str,
    company_name: str,
    location_text: str | None,
    employment_type: EmploymentType,
    now: datetime,
) -> Job:
    """Turn an approved capture into a real job, through the real pipeline.

    The arguments are what the *person* approved, not what the parser proposed.
    The ``proposed_*`` columns are left as they were so a bad parse stays
    diagnosable after the correction has overwritten it in every other sense.

    Everything downstream of ``persist_source_job`` is the ordinary ingestion
    path — locations, embedding, requirements, classification and dedupe — so a
    captured posting is a second-class citizen in exactly one respect (nothing
    can re-read it) and a first-class one in every other.
    """
    if capture.status is not CaptureStatus.PENDING:
        raise CaptureAlreadyDecidedError(
            f"capture {capture.id} is already {capture.status.value}; "
            "a decision is made once and is not revisited by this path"
        )

    source = await get_or_create_source(
        session,
        name=CAPTURE_SOURCE_NAME,
        source_type=SourceType.MANUAL_CAPTURE,
        base_url=None,
    )

    description = capture.raw_text
    source_job_id = capture_source_job_id(
        company_name=company_name, title=title, description=description
    )
    locations = tuple(parse_location_field(location_text))

    raw_job = RawJob(
        source_job_id=source_job_id,
        source_company_key=normalize_company_name(company_name),
        canonical_url=capture.source_url,
        # The verbatim contract, same as `source_job_records.raw_payload` for a
        # polled board: everything the normalizer read is recoverable from
        # here, so a parser fix is a backfill rather than "paste it again".
        payload={
            "captured": {
                "capture_id": str(capture.id),
                "raw_text": capture.raw_text,
                "source_url": capture.source_url,
                "parser_version": capture.parser_version,
                "captured_at": capture.created_at.isoformat() if capture.created_at else None,
            },
            "confirmed": {
                "title": title,
                "company_name": company_name,
                "location_text": location_text,
                "employment_type": employment_type.value,
                "confirmed_at": now.isoformat(),
            },
            "proposed": {
                "title": capture.proposed_title,
                "company_name": capture.proposed_company_name,
                "location_text": capture.proposed_location_text,
            },
        },
    )

    normalized = _normalized_from_confirmation(
        source_job_id=source_job_id,
        title=title,
        company_name=company_name,
        description=description,
        employment_type=employment_type,
        locations=locations,
        canonical_url=capture.source_url,
    )

    await persist_source_job(
        session, source=source, raw_job=raw_job, normalized=normalized, now=now
    )

    job = await _job_for_capture(session, source=source, source_job_id=source_job_id)
    capture.job_id = job.id
    capture.status = CaptureStatus.CONFIRMED
    capture.decided_at = now
    await session.flush()
    return job


def _normalized_from_confirmation(
    *,
    source_job_id: str,
    title: str,
    company_name: str,
    description: str,
    employment_type: EmploymentType,
    locations: tuple[ParsedLocation, ...],
    canonical_url: str | None,
) -> NormalizedSourceJob:
    return NormalizedSourceJob(
        source_job_id=source_job_id,
        source_company_key=normalize_company_name(company_name),
        company_name=company_name,
        canonical_url=canonical_url,
        title=title,
        normalized_title=normalize_title(title),
        description_html=None,
        description_text=description,
        description_hash=content_hash(description),
        employment_type=employment_type,
        remote_policy=infer_remote_policy(list(locations)),
        locations=locations,
        # A10: absent rather than zero. Nothing in a paste states these
        # reliably, and a parser that guessed a salary would be inventing one.
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_period=None,
        application_deadline=None,
        # Deliberately null. A capture's `created_at` is when *we* saw it, not
        # when the employer published it, and putting our timestamp in a field
        # named `source_published_at` would make every captured posting look
        # brand new to the freshness machinery.
        source_published_at=None,
        source_updated_at=None,
    )


async def _job_for_capture(session: AsyncSession, *, source: Source, source_job_id: str) -> Job:
    """Find the canonical job a just-persisted capture resolved to.

    Goes through ``job_source_links`` rather than assuming the record maps to a
    fresh job, because ``persist_source_job`` runs dedupe on creation: a
    captured posting that duplicates a polled one is *merged into it*, and the
    job this returns is then the poll's, not the capture's. That is the correct
    outcome and the reason this is a query rather than a variable.
    """
    job = (
        await session.execute(
            select(Job)
            .join(JobSourceLink, JobSourceLink.job_id == Job.id)
            .join(SourceJobRecord, SourceJobRecord.id == JobSourceLink.source_job_record_id)
            .where(
                SourceJobRecord.source_id == source.id,
                SourceJobRecord.source_job_id == source_job_id,
            )
        )
    ).scalar_one()
    return job


async def discard_capture(
    session: AsyncSession, *, capture: CapturedPosting, now: datetime
) -> None:
    """Throw the paste away without creating anything. Kept for the audit trail."""
    if capture.status is not CaptureStatus.PENDING:
        raise CaptureAlreadyDecidedError(f"capture {capture.id} is already {capture.status.value}")
    capture.status = CaptureStatus.DISCARDED
    capture.decided_at = now
    await session.flush()


__all__ = [
    "CAPTURE_PARSER_VERSION",
    "CAPTURE_SOURCE_NAME",
    "CaptureAlreadyDecidedError",
    "CaptureProposal",
    "capture_source_job_id",
    "confirm_capture",
    "create_capture",
    "discard_capture",
    "employment_type_for_title",
    "propose",
]
