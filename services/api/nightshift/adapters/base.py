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
from typing import Any, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class ListedPosting(BaseModel):
    """One posting as it appears in a board *listing*.

    Deliberately thin, because a listing is the cheap request: 33 KB against
    499 KB for the same Greenhouse board with content (measured 2026-08-02). It
    carries an id and a last-modified stamp and no description, and its job is
    to answer two questions — which postings are still open, and which of them
    changed since we last looked.
    """

    model_config = ConfigDict(frozen=True)

    source_job_id: str
    #: Greenhouse publishes this on its listing. Lever and Ashby publish no
    #: updated-at field at all, and need none: their board response already
    #: carries every posting in full, so there is no second fetch for a
    #: timestamp to gate. Measured against live boards on 2026-08-02.
    source_updated_at: datetime | None = None


class FetchOutcome(BaseModel):
    """What happened when we polled one board.

    Invariant I3 depends on this type. ``ok=False`` means we learned nothing
    about the jobs on this board, so the caller must not touch their state.
    ``ok=True`` with an empty ``jobs`` list is a genuine, different fact: the
    board responded and has no open postings.

    M1d adds a third state and one distinction.

    ``not_modified`` is a ``304``: the listing is byte-identical to the copy we
    already parsed. It is neither a failure nor an empty board, and it is the
    cheapest answer a provider can give us.

    ``listed`` versus ``jobs`` is the two-phase split (ADR 0007). ``listed`` is
    every posting the board says exists, and it is what freshness ages against.
    ``jobs`` is the subset we hold full payloads for. Greenhouse's poll makes
    those differ — it fetches content only for postings that changed — while for
    Lever and Ashby they describe the same postings. Ageing against ``jobs``
    would count every unchanged Greenhouse posting as missing and close it three
    polls later, silently. See ``docs/architecture/conditional-polling.md`` §4.
    """

    model_config = ConfigDict(frozen=True)

    board: BoardRef
    ok: bool
    jobs: tuple[RawJob, ...] = ()
    listed: tuple[ListedPosting, ...] = ()
    not_modified: bool = False
    etag: str | None = None
    http_status: int | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _not_modified_carries_nothing(self) -> Self:
        """A 304 has no body, so it cannot describe any posting.

        Enforced rather than documented: an adapter returning postings beside
        ``not_modified`` would make every downstream guard reason about a state
        that cannot physically occur.
        """
        if self.not_modified and (self.jobs or self.listed):
            raise ValueError("not_modified=True cannot carry jobs or listed postings")
        return self

    @property
    def listed_source_job_ids(self) -> tuple[str, ...]:
        """Every posting id the board listed, in the order the board gave them.

        The freshness pass ages on this rather than on ``jobs``. Not sorted:
        determinism is asserted on normalized output, and re-ordering here would
        hide a provider that started shuffling its listing between polls.
        """
        return tuple(posting.source_job_id for posting in self.listed)

    @property
    def is_authoritative_empty(self) -> bool:
        """True only when the source successfully told us the board is empty.

        ``not_modified`` is excluded explicitly. A 304 carries no jobs, so
        without that clause an unchanged board reads as an empty one and every
        posting on it closes — the failure ADR 0007 warned about in the abstract
        before there was code to make it concrete.

        ``listed`` is checked too: phase 1 naming ten postings while phase 2
        fetches none is the normal state of a Greenhouse board where nothing
        changed, and it is not an empty board either.
        """
        return self.ok and not self.not_modified and not self.jobs and not self.listed


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
