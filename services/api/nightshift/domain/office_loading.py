"""Worksheet entry → ladder → a building. The last step of the promotion path.

`city.md` §4.4. A human writes an address into `data/company-locations.yaml`,
`read_worksheet` refuses the entries that cannot support themselves, and this
runs what survives through the geocoding ladder into `company_locations`.

**It does not write to `job_locations`, and that is a decision rather than an
omission.**

A job inheriting its employer's office is a *derived* fact: it is true only
while the company's office is what it currently is. Materialising it into
`job_locations` would mean every office correction leaves behind rows that
still point at the old building, and nothing in the schema would know they were
stale — the class of bug this project has caught five times under the name "a
list that stopped describing the thing it names".

It would also be destructive. A job's `job_locations` row already holds what the
*posting* said, parsed, with `resolution_method = source_text_parse`. Overwriting
it with the employer's coordinates would delete the only record of what the
posting actually claimed, to store something the posting never said.

So the inheritance is a read-time join, and `ResolutionMethod.COMPANY_OFFICE`
is what that join reports rather than something stored. **M4c builds it**, next
to the renderer that needs it. Building a renderer's data path before the
renderer is how you find out in M4c that it was shaped wrong.

**A company with no office is not an error.** It is the majority case and the
whole reason §4.8 designs the unresolved layer as the default view.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import LocationConfidence
from nightshift.db.models import Company, CompanyLocation
from nightshift.domain.companies import normalize_company_name
from nightshift.domain.company_locations import OfficeEntry, WorksheetReading
from nightshift.domain.geocoding import Geocoder, Resolved, resolve


@dataclass
class LoadReport:
    """What happened, in enough detail for the coverage page to be honest."""

    placed: list[str] = field(default_factory=list)
    #: Entries that named an address the geocoder could not turn into a building.
    unresolved: list[tuple[str, str]] = field(default_factory=list)
    #: Entries naming a company that has never been ingested, so has no jobs.
    unknown_company: list[str] = field(default_factory=list)
    #: Left blank in the worksheet. The expected case, carried through from the
    #: reading so one number covers the whole file.
    blank: list[str] = field(default_factory=list)
    #: Refused during parsing, before anything reached a geocoder.
    refused: list[tuple[str, str]] = field(default_factory=list)

    @property
    def considered(self) -> int:
        return (
            len(self.placed)
            + len(self.unresolved)
            + len(self.unknown_company)
            + len(self.blank)
            + len(self.refused)
        )

    def summary(self) -> str:
        return (
            f"{self.considered} companies: {len(self.placed)} placed on a building, "
            f"{len(self.blank)} blank, {len(self.unresolved)} unresolved, "
            f"{len(self.unknown_company)} not ingested, {len(self.refused)} refused"
        )


async def load_offices(
    session: AsyncSession,
    reading: WorksheetReading,
    ladder: tuple[Geocoder, ...],
) -> LoadReport:
    """Place every confirmed address that the ladder can resolve to a building."""
    report = LoadReport(
        blank=list(reading.blank),
        refused=[(p.company, p.reason) for p in reading.problems],
    )

    for entry in reading.entries:
        company = await _company_for(session, entry.company)
        if company is None:
            # Not a failure of the worksheet. It names a real employer whose
            # board has not been polled, so there are no jobs to put on the
            # building yet. Recorded so the coverage page can say so rather
            # than the row silently vanishing.
            report.unknown_company.append(entry.company)
            continue

        outcome = await resolve(entry.geocoder_query, ladder)
        if not isinstance(outcome, Resolved):
            report.unresolved.append((entry.company, str(outcome.refusal)))
            continue
        if outcome.confidence is not LocationConfidence.VERIFIED:
            # A lower rung answered. That is a real coordinate and an honest
            # confidence, but it is not a *building*, and this table's whole
            # purpose is buildings — `verified_requires_a_street_address` would
            # accept it and the renderer would place it on a specific roof it
            # has no right to.
            report.unresolved.append((entry.company, f"only reached {outcome.confidence}"))
            continue

        await _upsert(session, company, entry, outcome)
        report.placed.append(entry.company)

    await session.flush()
    return report


async def _company_for(session: AsyncSession, name: str) -> Company | None:
    """Look up, never create.

    `get_or_create_company` exists and is deliberately not used: ingestion
    creates companies because a posting proves one exists. An address in a
    worksheet proves nothing of the sort, and a typo would otherwise mint an
    employer with no jobs, no board, and a building on the map.
    """
    normalized = normalize_company_name(name)
    return (
        await session.execute(select(Company).where(Company.normalized_name == normalized))
    ).scalar_one_or_none()


async def _upsert(
    session: AsyncSession, company: Company, entry: OfficeEntry, outcome: Resolved
) -> None:
    existing = (
        await session.execute(
            select(CompanyLocation).where(
                CompanyLocation.company_id == company.id,
                CompanyLocation.label == entry.label,
            )
        )
    ).scalar_one_or_none()

    # `confirmed_at` is the date the human wrote in the worksheet, at midnight
    # UTC — not `now()`. `now()` would say somebody checked this address at the
    # moment the loader happened to run, which is a claim about a person that
    # the person did not make.
    confirmed_at = datetime.combine(entry.confirmed_on, time.min, tzinfo=UTC)

    # Assigned field by field rather than through a dict and `setattr`.
    # `test_nothing_infers` refuses dynamic attribute writes outside the profile
    # module, and it is right to: a loop that writes whatever keys it is handed
    # is how a column nobody meant to touch gets written by a caller nobody
    # reviewed. Naming all fifteen also makes it obvious at a glance that
    # `company_id` and `label` are the identity and are never among them.
    row = (
        existing
        if existing is not None
        else CompanyLocation(company_id=company.id, label=entry.label)
    )

    row.street_address = entry.street_address
    row.city = entry.city
    row.state = entry.state
    row.postal_code = entry.postal_code
    row.country = entry.country
    row.latitude = outcome.latitude
    row.longitude = outcome.longitude
    row.location_confidence = outcome.confidence
    row.resolution_method = outcome.method
    row.building_id = outcome.building_id
    row.resolved_at = datetime.now(UTC)
    row.is_primary = entry.is_primary
    row.confirmed_by = entry.confirmed_by
    row.confirmed_at = confirmed_at

    if existing is None:
        session.add(row)
