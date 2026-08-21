"""`nightshift offices` — the command that was missing from the promotion path.

`city.md` §4.4 specifies four steps between a human typing an address and a
beacon standing on a roof. Steps 1 and 3 shipped in M4a, `read_worksheet` and
`load_offices` shipped tested in M4b, and **nothing called them**: the worksheet
was a file you could fill in that led nowhere. This command is step 2, and these
tests hold the two properties that make it safe to run.

**It reads a blank worksheet without a network or a database.** That is the
starting state of the committed file, and it is also the state a developer is in
when they run `make offices` to find out what the command wants from them. A
command that demanded Postgres and outbound HTTP before it could tell you the
file is empty would not be usable for the one thing it is first used for.

**It exits non-zero when the worksheet refused an entry.** A refusal is a defect
in a file a human wrote — an address with no date, a "New York, NY" that names
no street — and the exit code is what makes `make offices` go red instead of
printing the reason into a scrollback nobody reads. An *unresolved* entry is a
different thing entirely (the geocoder answered, and the answer was no), and it
must not fail the command: the majority of the registry has no NYC office and
that is a finding, not a mistake.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from nightshift.cli import cmd_offices
from nightshift.domain.company_locations import DEFAULT_WORKSHEET_PATH, read_worksheet

_REFUSING = """
confirmed_by: Tahmudun
offices:
  - company: Datadog
    label: New York HQ
    street_address: New York, NY
    city: New York
    state: NY
    confirmed_on: 2026-08-16
"""

_BLANK = """
confirmed_by: Tahmudun
offices:
  - company: Datadog
    label: New York HQ
    street_address:
    city: New York
"""


def _args(worksheet: Path | None) -> argparse.Namespace:
    return argparse.Namespace(worksheet=str(worksheet) if worksheet else None)


def test_the_default_worksheet_is_the_committed_one() -> None:
    """The path is computed with `parents[4]`, which this repo has got wrong
    before in both directions. If it lands on `services/` the command reads
    nothing and reports an empty file, which looks exactly like a worksheet
    nobody has filled in."""
    assert DEFAULT_WORKSHEET_PATH.exists(), DEFAULT_WORKSHEET_PATH
    assert DEFAULT_WORKSHEET_PATH.name == "company-locations.yaml"
    assert DEFAULT_WORKSHEET_PATH.parent.name == "data"


@pytest.mark.asyncio
async def test_a_blank_worksheet_needs_neither_network_nor_database(
    tmp_path: Path,
) -> None:
    """No session is opened and no geocoder is built, so this passes with
    Postgres down and `OUTBOUND_HTTP_ENABLED=false` — which is the state of a
    fresh clone."""
    worksheet = tmp_path / "blank.yaml"
    worksheet.write_text(_BLANK)
    assert await cmd_offices(_args(worksheet)) == 0


def test_the_committed_worksheet_is_refused_nowhere() -> None:
    """The real file, read the way the command reads it, with no database and no
    network.

    **This replaces a test that asserted the committed file loads offline and
    exits 0**, which was true only while every address was blank. Its own
    docstring said so: "the day somebody fills one in this stops being an
    offline command." That day was 2026-08-17, eight addresses arrived, and the
    command correctly started wanting Postgres and outbound HTTP.

    What survives into the offline suite is the half that does not depend on
    either: every entry a person hand-wrote is *readable*. A refusal here is a
    typo in a file with no editor behind it — an address that names no street, a
    date that is not a date — and catching it in the test suite is cheaper than
    catching it in a run that has already opened a connection.
    """
    reading = read_worksheet(DEFAULT_WORKSHEET_PATH.read_text())
    assert reading.problems == [], [(p.company, p.reason) for p in reading.problems]

    # Not an assertion about how many are filled — that is the human's and moves
    # without notice. It is an assertion that reading the file yields something:
    # a `parents[4]` that lands one directory off returns an empty reading, and
    # an empty reading is indistinguishable from a worksheet nobody has touched.
    assert len(reading.entries) + len(reading.blank) > 0


@pytest.mark.asyncio
async def test_a_refused_entry_fails_the_command(tmp_path: Path) -> None:
    """ "New York, NY" cannot reach `verified` and the database would refuse the
    row. Reported and exited 1, before any session or request."""
    worksheet = tmp_path / "refusing.yaml"
    worksheet.write_text(_REFUSING)
    assert await cmd_offices(_args(worksheet)) == 1


@pytest.mark.asyncio
async def test_a_missing_worksheet_says_so_rather_than_reporting_zero(
    tmp_path: Path,
    capsys,  # type: ignore[no-untyped-def]
) -> None:
    """A typo'd `--worksheet` must not read as "0 companies, all blank"."""
    assert await cmd_offices(_args(tmp_path / "nope.yaml")) == 1
    assert "cannot read worksheet" in capsys.readouterr().err
