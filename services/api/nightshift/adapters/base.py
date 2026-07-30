"""The job source adapter contract.

Differs from PRODUCT-SPEC §7.1 in one deliberate way: there is no
``discover_companies()``. AMENDMENTS A1 explains why — Greenhouse, Lever, and
Ashby all serve public unauthenticated board APIs, and none of them exposes any
way to enumerate their customers. There is no directory to call. Board tokens
come from ``data/board-registry.yaml``, which is version-controlled source data.

Everything crossing the network boundary is a Pydantic model, and nothing
outside this package imports ``httpx`` (CLAUDE.md §7).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from nightshift.db.base import EmploymentType, SourceType
from nightshift.domain.locations import ParsedLocation


class BoardRef(BaseModel):
    """A single company board to poll. One row of the registry."""

    model_config = ConfigDict(frozen=True)

    company: str
    ats: str
    token: str
    nyc_presence: bool = False


class RawJob(BaseModel):
    """One posting exactly as a source returned it.

    ``payload`` is the untouched provider JSON. It is stored verbatim in
    ``source_job_records.raw_payload`` so normalization is always re-derivable
    and a normalization bug is a backfill rather than a re-crawl.
    """

    model_config = ConfigDict(frozen=True)

    source_job_id: str
    source_company_key: str
    canonical_url: str | None = None
    payload: dict[str, Any]


class NormalizedSourceJob(BaseModel):
    """Provider-shaped data mapped onto our domain language.

    Field names match the schema (CLAUDE.md §7 "Naming"). Note what is *not*
    here: no ``posted_at``. A11's point is that Greenhouse's ``updated_at`` is a
    last-modified stamp, so it travels in ``source_updated_at`` and the
    genuine publication date travels in ``source_published_at``. Neither is
    renamed to something more convenient downstream.
    """

    model_config = ConfigDict(frozen=True)

    source_job_id: str
    source_company_key: str
    company_name: str
    canonical_url: str | None

    title: str
    normalized_title: str
    description_html: str | None
    description_text: str | None
    description_hash: str

    employment_type: EmploymentType
    remote_policy: str
    locations: tuple[ParsedLocation, ...] = Field(default=())

    # AMENDMENTS A10: all five of these are frequently absent. None means
    # "not provided by source" and the UI says exactly that.
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    application_deadline: datetime | None = None

    source_published_at: datetime | None = None
    source_updated_at: datetime | None = None


class FetchOutcome(BaseModel):
    """What happened when we polled one board.

    Invariant I3 depends on this type. ``ok=False`` means we learned nothing
    about the jobs on this board, so the caller must not touch their state.
    ``ok=True`` with an empty ``jobs`` list is a genuine, different fact: the
    board responded and has no open postings.
    """

    model_config = ConfigDict(frozen=True)

    board: BoardRef
    ok: bool
    jobs: tuple[RawJob, ...] = ()
    http_status: int | None = None
    error: str | None = None

    @property
    def is_authoritative_empty(self) -> bool:
        """True only when the source successfully told us the board is empty."""
        return self.ok and not self.jobs


class SourceUnavailableError(Exception):
    """Raised when a source could not be reached or returned an unusable response.

    Named for what it means rather than for its HTTP cause, because the
    behaviour it must trigger is the same for a timeout, a 500, and malformed
    JSON: leave listing state alone (I3).
    """

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


@runtime_checkable
class JobSourceAdapter(Protocol):
    """Implemented once per ATS provider. The ingestion pipeline knows only this."""

    source_name: str
    source_type: SourceType

    async def fetch_board(self, board: BoardRef) -> FetchOutcome:
        """Poll one company board.

        Must not raise for an unreachable source — it returns ``ok=False``, so a
        single bad board cannot abort a run over the others.
        """
        ...

    def normalize(self, raw_job: RawJob, board: BoardRef) -> NormalizedSourceJob:
        """Map one raw posting onto the domain model.

        Takes the board because two of the three providers publish no employer
        name. The registry entry is a human-approved fact; the board token is a
        slug, and deriving a company from it is the I2 failure that ADR 0005's
        `live_unnamed` verdict exists to catch.

        Synchronous and pure: same input, same output, no I/O. That is what
        makes M1's "same fixture in, byte-identical output, twice" criterion
        testable.
        """
        ...
