"""The promotion path, and every way an entry can fail to earn a building.

`city.md` §4.4. This file is the only route by which a `verified` coordinate can
enter the product, so the interesting tests are the refusals: each one is an
entry that would otherwise become a lit building nobody actually vouched for.

The committed `data/company-locations.yaml` is read here too. It ships blank on
purpose — every entry a blank address, which loads as nothing — and that is
asserted rather than assumed, because a worksheet that silently stopped parsing
would look identical to one nobody had filled in yet.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from nightshift.domain.company_locations import read_worksheet
from nightshift.domain.registry import get_registry

WORKSHEET = Path(__file__).parent.parent.parent.parent / "data" / "company-locations.yaml"

_FILLED = """
confirmed_by: Tahmudun
offices:
  - company: Datadog
    label: New York HQ
    street_address: 620 Eighth Avenue
    city: New York
    state: NY
    postal_code: "10018"
    country: USA
    is_primary: true
    confirmed_on: 2026-08-11
"""


def test_a_filled_entry_becomes_an_office() -> None:
    reading = read_worksheet(_FILLED)
    assert reading.problems == []
    assert len(reading.entries) == 1

    entry = reading.entries[0]
    assert entry.company == "Datadog"
    assert entry.street_address == "620 Eighth Avenue"
    assert entry.confirmed_by == "Tahmudun"
    assert entry.confirmed_on == date(2026, 8, 11)
    assert entry.is_primary


def test_the_geocoder_query_carries_the_locality_parts() -> None:
    """Pelias scores a fuller string better, and a street name that repeats
    across boroughs needs them to land on the right one."""
    entry = read_worksheet(_FILLED).entries[0]
    assert entry.geocoder_query == "620 Eighth Avenue, New York, NY, 10018"


def test_a_blank_address_loads_as_nothing_and_is_not_a_problem() -> None:
    """The expected case. §4.4: blank is a correct answer, the company's jobs
    stay in the unresolved layer, and nothing is guessed on its behalf."""
    reading = read_worksheet(
        """
        confirmed_by: Tahmudun
        offices:
          - company: Datadog
            label: New York HQ
            street_address:
            city: New York
        """
    )
    assert reading.entries == []
    assert reading.problems == []
    assert reading.blank == ["Datadog"]


def test_an_address_with_no_date_is_refused() -> None:
    """Offices move. An address with no age cannot be audited later, which is
    why `confirmed_at` is NOT NULL in the database."""
    reading = read_worksheet(
        """
        confirmed_by: Tahmudun
        offices:
          - company: Datadog
            label: New York HQ
            street_address: 620 Eighth Avenue
        """
    )
    assert reading.entries == []
    assert len(reading.problems) == 1
    assert "confirmed_on" in reading.problems[0].reason


def test_an_address_with_no_street_is_refused_rather_than_downgraded() -> None:
    """The sharp one.

    Storing "New York, NY" as `city_only` and moving on is what would happen if
    this file were ordinary input. But somebody typing here is asserting *an
    office is at this address*, and the honest response to an assertion that
    cannot support itself is to say so — not to quietly record a weaker version
    of it that still reads as a filled-in row.
    """
    reading = read_worksheet(
        """
        confirmed_by: Tahmudun
        offices:
          - company: Datadog
            label: New York HQ
            street_address: New York, NY
            confirmed_on: 2026-08-11
        """
    )
    assert reading.entries == []
    assert "names no street" in reading.problems[0].reason
    assert "blank entry is a correct answer" in reading.problems[0].reason


def test_an_address_with_no_one_vouching_is_refused() -> None:
    reading = read_worksheet(
        """
        offices:
          - company: Datadog
            label: New York HQ
            street_address: 620 Eighth Avenue
            confirmed_on: 2026-08-11
        """
    )
    assert reading.entries == []
    assert "confirmed_by" in reading.problems[0].reason


def test_two_primary_offices_for_one_company_are_refused() -> None:
    """`uq_company_locations_one_primary` would refuse the second row at commit,
    after the first was already written. Catching it in the reading means the
    file is rejected whole rather than half-applied."""
    reading = read_worksheet(
        """
        confirmed_by: Tahmudun
        offices:
          - company: Datadog
            label: New York HQ
            street_address: 620 Eighth Avenue
            is_primary: true
            confirmed_on: 2026-08-11
          - company: Datadog
            label: Second HQ
            street_address: 200 Park Avenue
            is_primary: true
            confirmed_on: 2026-08-11
        """
    )
    assert len(reading.entries) == 1
    assert reading.entries[0].label == "New York HQ"
    assert "both marked `is_primary`" in reading.problems[0].reason


def test_a_second_non_primary_office_is_fine() -> None:
    reading = read_worksheet(
        """
        confirmed_by: Tahmudun
        offices:
          - company: Datadog
            label: New York HQ
            street_address: 620 Eighth Avenue
            is_primary: true
            confirmed_on: 2026-08-11
          - company: Datadog
            label: Brooklyn
            street_address: 1 Bowery
            is_primary: false
            confirmed_on: 2026-08-11
        """
    )
    assert reading.problems == []
    assert len(reading.entries) == 2


def test_one_bad_entry_does_not_stop_the_others() -> None:
    """Problems are data, not exceptions. A file with one mistake in it should
    report that mistake and load the rest, or filling it in becomes a game of
    fixing one error per run."""
    reading = read_worksheet(
        """
        confirmed_by: Tahmudun
        offices:
          - company: Datadog
            label: New York HQ
            street_address: 620 Eighth Avenue
            confirmed_on: 2026-08-11
          - company: Ramp
            label: New York HQ
            street_address: New York, NY
            confirmed_on: 2026-08-11
          - company: Stripe
            label: New York HQ
            street_address: 200 Park Avenue
            confirmed_on: 2026-08-11
        """
    )
    assert [e.company for e in reading.entries] == ["Datadog", "Stripe"]
    assert [p.company for p in reading.problems] == ["Ramp"]


def test_an_empty_file_reads_as_empty_rather_than_crashing() -> None:
    assert read_worksheet("").total == 0


# --------------------------------------------------------------------------
# The committed file
# --------------------------------------------------------------------------


def test_the_committed_worksheet_parses() -> None:
    """A worksheet that had silently stopped parsing would look identical to one
    nobody had filled in yet — both produce zero offices."""
    reading = read_worksheet(WORKSHEET.read_text())
    assert reading.total == len(get_registry().boards), reading.summary()
    assert reading.problems == [], reading.summary()


def test_the_committed_worksheet_names_who_is_vouching() -> None:
    """Without a top-level `confirmed_by`, every address typed into this file
    would be refused — and the refusal would look like a bug in the entry rather
    than a missing line at the top."""
    reading = read_worksheet(
        WORKSHEET.read_text().replace("street_address:\n", "street_address: 1 Bowery\n", 1)
    )
    assert not any("confirmed_by" in p.reason for p in reading.problems), reading.summary()


def _named_in_worksheet() -> set[str]:
    reading = read_worksheet(WORKSHEET.read_text())
    return (
        {e.company for e in reading.entries}
        | set(reading.blank)
        | {p.company for p in reading.problems}
    )


def test_every_registry_board_has_a_row_to_fill() -> None:
    """The registry is the set of employers this product can see. A company in
    it with no row here can never reach a building, and nothing would say why —
    the absence is indistinguishable from a company somebody checked and found
    had no NYC office.

    Held over the whole registry rather than the `nyc_presence` subset, which is
    what this asserted until 2026-08-16. `nyc_presence` is derived from posting
    text, and posting text is not a company directory: a board whose postings
    all say "Remote" can still be run out of an office on Lafayette Street.
    """
    missing = {board.company for board in get_registry().boards} - _named_in_worksheet()
    assert not missing, f"in data/board-registry.yaml but not in the worksheet: {sorted(missing)}"


def test_the_worksheet_names_no_company_the_registry_does_not() -> None:
    """The other direction, and the one that rots quietly. `load_offices` looks
    a company up and never creates one, so a row naming an employer no board
    belongs to is reported `not ingested` forever — a line in the report that
    can never turn green and that nobody can act on.
    """
    unknown = _named_in_worksheet() - {board.company for board in get_registry().boards}
    assert not unknown, f"in the worksheet but not in data/board-registry.yaml: {sorted(unknown)}"
