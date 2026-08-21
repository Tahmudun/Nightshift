"""Reading the office worksheet, and refusing the entries that would lie.

`city.md` §4.4. `data/company-locations.yaml` is the promotion path: a human
writes an address down, and that is the only way a coordinate with
`location_confidence = verified` can enter this product. Everything here exists
to make sure the file's contents mean what the schema says they mean.

**A blank entry is a correct answer and is loaded as nothing.** Not a city
centroid, not `unknown` with coordinates attached, not a row that looks filled.
The company's jobs stay in the unresolved signal layer, where they are fully
usable — §4.8 designs that layer as the default view precisely because this is
the expected case rather than the sad one.

**A filled entry must carry a date.** Offices move. An address with no
`confirmed_on` is a claim with no age, and `confirmed_at` is `NOT NULL` in the
database because a row that cannot say when somebody checked it cannot be
audited later.

**An address that names no street is refused rather than downgraded.** A caller
could reasonably store "New York, NY" as `city_only` and move on, and that is
what would happen if this file were treated as ordinary input. But somebody
typing into this worksheet is asserting *an office is here*, and the honest
response to an assertion that cannot support itself is to say so, not to quietly
record a weaker version of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from nightshift.domain.geocoding import names_a_street

# `parents[4]` from `nightshift/domain/company_locations.py` is the repo root,
# matching `domain/registry.py`. `parents[3]` is `services/`.
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_WORKSHEET_PATH = _REPO_ROOT / "data" / "company-locations.yaml"


@dataclass(frozen=True, slots=True)
class OfficeEntry:
    """One office a human vouched for, before geocoding."""

    company: str
    label: str
    street_address: str
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    is_primary: bool
    confirmed_on: date
    confirmed_by: str

    @property
    def geocoder_query(self) -> str:
        """What gets sent to NYC GeoSearch. Street first, then the locality
        parts that disambiguate it — Pelias scores a fuller string better, and
        an office on a street name that repeats across boroughs needs them."""
        parts = [self.street_address, self.city, self.state, self.postal_code]
        return ", ".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class Problem:
    """An entry that cannot be loaded, and the sentence explaining why.

    Carried as data rather than raised, so one bad row does not stop the other
    eight from loading and the report can name every problem at once instead of
    the first.
    """

    company: str
    reason: str


@dataclass
class WorksheetReading:
    """What the file said, split by what can be done with it."""

    entries: list[OfficeEntry] = field(default_factory=list)
    blank: list[str] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.entries) + len(self.blank) + len(self.problems)

    def summary(self) -> str:
        return (
            f"{self.total} companies: {len(self.entries)} with a confirmed address, "
            f"{len(self.blank)} blank, {len(self.problems)} refused"
        )


def _clean(value: Any) -> str | None:
    """YAML gives `None` for a blank key and `''` for an empty string. Both mean
    the same thing here, and neither should reach the database as a value."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def read_worksheet(source: str) -> WorksheetReading:
    """Parse the worksheet. Never raises for a bad entry — that is a Problem."""
    document = yaml.safe_load(source) or {}
    confirmed_by = _clean(document.get("confirmed_by"))
    reading = WorksheetReading()

    raw_offices = document.get("offices") or []
    for raw in raw_offices:
        company = _clean(raw.get("company")) or "(unnamed entry)"
        street = _clean(raw.get("street_address"))

        if street is None:
            # The expected case, and not a failure. §4.4.
            reading.blank.append(company)
            continue

        if confirmed_by is None:
            reading.problems.append(
                Problem(
                    company,
                    "the file has an address but no top-level `confirmed_by`, so no "
                    "row could say who vouched for it",
                )
            )
            continue

        confirmed_on = raw.get("confirmed_on")
        if not isinstance(confirmed_on, date):
            reading.problems.append(
                Problem(
                    company,
                    "an address with no `confirmed_on` date is a claim with no age, "
                    "and offices move. Add the date you checked it",
                )
            )
            continue

        if not names_a_street(street):
            reading.problems.append(
                Problem(
                    company,
                    f"{street!r} names no street, so it cannot reach `verified` and "
                    "the database would refuse the row. Leave it blank instead — a "
                    "blank entry is a correct answer and the jobs stay usable",
                )
            )
            continue

        label = _clean(raw.get("label"))
        if label is None:
            reading.problems.append(
                Problem(company, "every office needs a `label` to tell two of them apart")
            )
            continue

        reading.entries.append(
            OfficeEntry(
                company=company,
                label=label,
                street_address=street,
                city=_clean(raw.get("city")),
                state=_clean(raw.get("state")),
                postal_code=_clean(raw.get("postal_code")),
                country=_clean(raw.get("country")),
                is_primary=bool(raw.get("is_primary", False)),
                confirmed_on=confirmed_on,
                confirmed_by=confirmed_by,
            )
        )

    _refuse_duplicate_primaries(reading)
    return reading


def _refuse_duplicate_primaries(reading: WorksheetReading) -> None:
    """`uq_company_locations_one_primary` would refuse the second row at commit,
    after the first had been written. Catching it here means the file is
    rejected as a whole rather than half-applied."""
    seen: dict[str, str] = {}
    surviving: list[OfficeEntry] = []
    for entry in reading.entries:
        if not entry.is_primary:
            surviving.append(entry)
            continue
        if entry.company in seen:
            reading.problems.append(
                Problem(
                    entry.company,
                    f"two entries are both marked `is_primary` ({seen[entry.company]!r} "
                    f"and {entry.label!r}). One company, one building — mark the other "
                    "`is_primary: false`",
                )
            )
            continue
        seen[entry.company] = entry.label
        surviving.append(entry)
    reading.entries = surviving
