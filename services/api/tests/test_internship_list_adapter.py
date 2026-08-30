"""The list is a board with one token and many employers.

`ingestion.py` creates the company per job from `company_name`, so nothing
downstream needs to know this board is unusual.

**About the fixtures.** Both are recorded verbatim from the real files on
2026-08-29 and trimmed: the first 40 entries of the file, in file order,
followed by the first 10 active-and-visible entries naming New York. The tail
is not decoration. Simplify's head-40 contains zero New York entries and 39
inactive ones, and Simplify writes its home city as the bare token `NYC` — the
string that carries all 195 of its New York roles. A fixture cut at 40 would
never exercise the path this milestone exists for.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from nightshift.adapters.base import BoardRef, RawJob, SourceUnavailableError
from nightshift.adapters.internship_list import InternshipListAdapter
from nightshift.db.base import EmploymentType, LocationConfidence, SourceType

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "simplify_listings.json"
VANSH_FIXTURE = FIXTURES / "vansh_listings.json"
BOARD = BoardRef(company="Simplify Summer 2027", ats="simplify_list", token="summer2027")


def _adapter() -> InternshipListAdapter:
    return InternshipListAdapter(
        client=None,
        list_name="simplify_list",
        raw_url="https://example.invalid/listings.json",
    )


def _entries(path: Path = FIXTURE) -> list[dict[str, object]]:
    return json.loads(path.read_text())


def _raw(entry: dict[str, object]) -> RawJob:
    return RawJob(
        source_job_id=str(entry["id"]),
        source_company_key=str(entry["company_name"]),
        canonical_url=str(entry.get("url") or "") or None,
        payload=entry,
    )


def test_source_type_is_the_list_type() -> None:
    assert _adapter().source_type is SourceType.INTERNSHIP_LIST


def test_the_employer_comes_from_the_entry_not_the_board() -> None:
    """The board is one row; the employers are hundreds. This is the whole shape."""
    entry = _entries()[0]
    normalized = _adapter().normalize(_raw(entry), BOARD)
    assert normalized.company_name == entry["company_name"]
    assert normalized.company_name != BOARD.company


def test_normalization_is_deterministic() -> None:
    """M1's criterion, applied to a new adapter: same fixture in, same bytes out, twice."""
    adapter = _adapter()
    raw = _raw(_entries()[0])
    first = adapter.normalize(raw, BOARD).model_dump_json()
    second = adapter.normalize(raw, BOARD).model_dump_json()
    assert first == second


@pytest.mark.parametrize("path", [FIXTURE, VANSH_FIXTURE])
def test_no_entry_ever_produces_verified_confidence(path: Path) -> None:
    """I1. A list carries a city name at best; it never carries a street address."""
    adapter = _adapter()
    for entry in _entries(path):
        for location in adapter.normalize(_raw(entry), BOARD).locations:
            assert location.confidence is not LocationConfidence.VERIFIED


@pytest.mark.parametrize("path", [FIXTURE, VANSH_FIXTURE])
def test_every_recorded_entry_normalizes(path: Path) -> None:
    """Both real files, every entry, no exception.

    The two lists do not agree on their own schema — Simplify carries `terms`
    and `category`, vanshb03 carries `season` and neither — so a parser that
    reached for a field one of them lacks would raise here.
    """
    adapter = _adapter()
    for entry in _entries(path):
        normalized = adapter.normalize(_raw(entry), BOARD)
        assert normalized.title
        assert normalized.company_name


def test_the_bare_token_nyc_reaches_new_york() -> None:
    """Simplify's home city is written `NYC`, and 195 of its roles ride on it.

    Not a parser feature of this adapter — it hands the string to the shared
    normalizer, and this asserts the seam holds. If it ever stops holding, this
    adapter silently stops delivering New York.
    """
    entry = {
        "id": "nyc1",
        "company_name": "Example Corp",
        "title": "Software Engineer Intern",
        "locations": ["NYC"],
        "url": "https://example.invalid/x",
        "date_posted": 1755000000,
        "active": True,
        "is_visible": True,
    }
    (location,) = _adapter().normalize(_raw(entry), BOARD).locations
    assert location.city == "New York"


def test_a_multi_location_entry_produces_one_location_each() -> None:
    entry = {
        "id": "abc123",
        "company_name": "Example Corp",
        "title": "Software Engineer Intern",
        "locations": ["New York, NY", "San Francisco, CA"],
        "url": "https://job-boards.greenhouse.io/example/jobs/1",
        "date_posted": 1755000000,
        "active": True,
        "is_visible": True,
    }
    normalized = _adapter().normalize(_raw(entry), BOARD)
    assert len(normalized.locations) == 2
    assert {loc.city for loc in normalized.locations} == {"New York", "San Francisco"}
    assert [loc.is_primary for loc in normalized.locations] == [True, False]


def test_an_inactive_entry_is_still_normalized_and_never_closes_anything() -> None:
    """I3, in the form this milestone meets it.

    `active: false` is a volunteer's belief about a source we do not poll. It is
    recorded on the payload and it is not a closure signal. The adapter must
    return the entry like any other; anything else would let a list edit close a
    job in this database.
    """
    entry = {
        "id": "gone1",
        "company_name": "Example Corp",
        "title": "Software Engineer Intern",
        "locations": ["New York, NY"],
        "url": "https://example.invalid/x",
        "date_posted": 1755000000,
        "active": False,
        "is_visible": True,
    }
    normalized = _adapter().normalize(_raw(entry), BOARD)
    assert normalized.title == "Software Engineer Intern"


def test_the_description_is_absent_and_says_so() -> None:
    """the-hunt.md §5.3: a list entry carries no description. Do not invent one."""
    normalized = _adapter().normalize(_raw(_entries()[0]), BOARD)
    assert normalized.description_text is None
    assert normalized.description_html is None


def test_the_employment_type_is_internship() -> None:
    """The one fact the list itself states about every entry, by being what it is."""
    normalized = _adapter().normalize(_raw(_entries()[0]), BOARD)
    assert normalized.employment_type is EmploymentType.INTERNSHIP


def test_date_posted_is_read_as_epoch_seconds() -> None:
    """Both lists publish epoch **seconds**, unlike Lever's milliseconds.

    Reading one as the other puts the date tens of thousands of years out, and
    every freshness calculation downstream inherits it.
    """
    entry = {
        "id": "t1",
        "company_name": "Example Corp",
        "title": "Software Engineer Intern",
        "locations": ["NYC"],
        "url": "https://example.invalid/x",
        "date_posted": 1755000000,
        "active": True,
        "is_visible": True,
    }
    published = _adapter().normalize(_raw(entry), BOARD).source_published_at
    assert published is not None
    assert published.year == 2025


class _RaisingClient:
    """A client whose every request fails the way a dead network does."""

    async def get_json_conditional(self, url: str, *, etag: str | None = None) -> object:
        raise SourceUnavailableError("connection refused", http_status=None)


class _ConnectErrorClient:
    """A client that raises the raw httpx error, which the adapter has never seen."""

    async def get_json_conditional(self, url: str, *, etag: str | None = None) -> object:
        raise httpx.ConnectError("no route to host")


async def test_a_dead_list_returns_not_ok_and_never_raises() -> None:
    """I3. One bad list must not abort a run over the others, and must not read
    as an empty list — which is the one conclusion that closes jobs."""
    adapter = InternshipListAdapter(
        client=_RaisingClient(),  # type: ignore[arg-type]
        list_name="simplify_list",
        raw_url="https://example.invalid/listings.json",
    )
    outcome = await adapter.fetch_board(BOARD)
    assert outcome.ok is False
    assert outcome.jobs == ()
    assert outcome.is_authoritative_empty is False


async def test_an_unexpected_transport_error_is_also_not_ok() -> None:
    """The sabotage case: an error class the adapter does not name explicitly.

    `SourceUnavailableError` is what the client promises. An `httpx` error
    escaping it is a bug somewhere else, and I3 says the cost of that bug is a
    skipped board — never a closed job.
    """
    adapter = InternshipListAdapter(
        client=_ConnectErrorClient(),  # type: ignore[arg-type]
        list_name="simplify_list",
        raw_url="https://example.invalid/listings.json",
    )
    outcome = await adapter.fetch_board(BOARD)
    assert outcome.ok is False
    assert outcome.is_authoritative_empty is False
