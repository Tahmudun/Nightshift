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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob, SourceUnavailableError
from nightshift.adapters.internship_list import InternshipListAdapter
from nightshift.db.base import EmploymentType, JobStatus, LocationConfidence, SourceType
from nightshift.db.models import Job, SourceJobRecord
from nightshift.domain.ingestion import IngestionStats, get_or_create_source, ingest_boards
from tests.conftest import requires_db

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
    """As `fetch_board` builds one: the key is the **board**, not the employer.

    Built by hand here, and that is a hazard worth naming — this helper had the
    employer name in `source_company_key` while the adapter had the board token,
    and the freshness test below was therefore asserting about a row shape the
    adapter never writes. It passed against the bug it existed to catch.
    """
    return RawJob(
        source_job_id=str(entry["id"]),
        source_company_key=BOARD.token,
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


class _StubClient:
    """Serves one recorded payload, the way a 200 would."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    async def get_json_conditional(self, url: str, *, etag: str | None = None):
        from nightshift.adapters.http import ConditionalResponse

        return ConditionalResponse(
            not_modified=False, payload=self._payload, etag='"x"', http_status=200
        )


def _entry(entry_id: str, *, active: bool) -> dict[str, object]:
    return {
        "id": entry_id,
        "company_name": "Example Corp",
        "title": "Software Engineer Intern",
        "locations": ["New York, NY"],
        "url": f"https://example.invalid/{entry_id}",
        "date_posted": 1755000000,
        "active": active,
        "is_visible": True,
    }


async def test_the_source_company_key_is_the_board_not_the_employer() -> None:
    """`source_company_key` names **which board a record came from**, and every
    other adapter sets it to `board.token`.

    This adapter set it to the employer name, which reads naturally — the list
    does name an employer per entry — and silently broke freshness. Two queries
    age records by `source_company_key IN (polled tokens)`
    (`ingestion.py:839` and the ageing pass), so with an employer name in that
    column **no list record could ever be aged, or missed, or closed.** It was
    found by sabotaging the `listed`/`jobs` split and watching the test that
    should have caught it stay green.

    The employer is not lost: `normalize` reads `company_name` from the payload,
    which is where it belongs and where `get_or_create_company` looks.
    """
    payload = [_entry("live1", active=True)]
    adapter = InternshipListAdapter(
        client=_StubClient(payload),  # type: ignore[arg-type]
        list_name="simplify_list",
        raw_url="https://example.invalid/listings.json",
    )
    outcome = await adapter.fetch_board(BOARD)

    (job,) = outcome.jobs
    assert job.source_company_key == BOARD.token
    # And the employer still arrives, by the route that is actually for it.
    assert adapter.normalize(job, BOARD).company_name == "Example Corp"


async def test_a_closed_entry_is_listed_but_not_ingested() -> None:
    """The `listed`/`jobs` split, doing the work I3 needs it to do.

    An entry marked `active: false` is the publisher saying that posting is
    closed. Two things have to be true at once and they pull in opposite
    directions:

    * It must not create a canonical job claiming to be open. 12,663 of
      Simplify's 14,918 entries are inactive Summer 2026 roles, and minting an
      open job for each would be asserting something false about a real
      employer 12,663 times.
    * It must not *close* anything either (I3). A job we already know about,
      whose entry later flips to inactive, must stay exactly as it was — the
      list is not evidence about a board this project polls.

    `listed` carries every entry, so freshness never ages a job off the back of
    this flag. `jobs` carries only the active ones, so nothing new is minted
    from a posting the publisher says is over.
    """
    payload = [_entry("live1", active=True), _entry("closed1", active=False)]
    adapter = InternshipListAdapter(
        client=_StubClient(payload),  # type: ignore[arg-type]
        list_name="simplify_list",
        raw_url="https://example.invalid/listings.json",
    )
    outcome = await adapter.fetch_board(BOARD)

    assert outcome.ok is True
    assert [job.source_job_id for job in outcome.jobs] == ["live1"]
    assert set(outcome.listed_source_job_ids) == {"live1", "closed1"}


async def test_a_list_where_everything_closed_is_not_an_empty_board() -> None:
    """I3's exact wording: a list that marks every entry inactive closes zero
    jobs. Every id is still listed, so freshness sees a full board."""
    payload = [_entry("a", active=False), _entry("b", active=False)]
    adapter = InternshipListAdapter(
        client=_StubClient(payload),  # type: ignore[arg-type]
        list_name="simplify_list",
        raw_url="https://example.invalid/listings.json",
    )
    outcome = await adapter.fetch_board(BOARD)

    assert outcome.jobs == ()
    assert set(outcome.listed_source_job_ids) == {"a", "b"}
    assert outcome.is_authoritative_empty is False, (
        "a list of closed postings is not an empty board, and reading it as one "
        "closes every job that came from it"
    )


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


# ---------------------------------------------------------------------------
# I3, end to end: through `ingest_boards` and the freshness pass, not just the
# adapter. The unit tests above prove the adapter reports the right thing; these
# prove the pipeline does the right thing with it, which is a different claim
# and the one a closed job would actually come from.
# ---------------------------------------------------------------------------


class _ListStubAdapter:
    """The real adapter with its network call replaced by a recorded outcome.

    Its own `normalize` runs untouched — replacing that would be mocking the
    thing under test.
    """

    source_type = SourceType.INTERNSHIP_LIST
    parser_version = "1"
    is_two_phase = False

    def __init__(self, outcome: FetchOutcome) -> None:
        self._inner = InternshipListAdapter(
            client=None, list_name="simplify_list", raw_url="https://example.invalid/x"
        )
        self.source_name = "simplify_list"
        self._outcome = outcome

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        return self._outcome

    def normalize(self, raw_job: RawJob, board: BoardRef) -> object:
        return self._inner.normalize(raw_job, board)


async def _ingest_list(session: AsyncSession, outcome: FetchOutcome) -> IngestionStats:
    source = await get_or_create_source(
        session,
        name="simplify_list",
        source_type=SourceType.INTERNSHIP_LIST,
        base_url="https://raw.githubusercontent.com",
    )
    _run, stats = await ingest_boards(session, _ListStubAdapter(outcome), [BOARD], source=source)
    await session.flush()
    return stats


async def _misses(session: AsyncSession) -> list[int]:
    """`consecutive_misses` per source record — what freshness actually ages on.

    The assertion that matters. `stats.closed == 0` after a single pass is true
    whatever happens, because closure takes three consecutive misses (§7.4): a
    test resting on it would pass just as happily against a pipeline that had
    started the countdown. This is the countdown.
    """
    return list((await session.execute(select(SourceJobRecord.consecutive_misses))).scalars().all())


async def _open_jobs(session: AsyncSession) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.OPEN)
            )
        ).scalar_one()
    )


def _live_outcome() -> FetchOutcome:
    entries = [_entry("a", active=True), _entry("b", active=True), _entry("c", active=True)]
    jobs = tuple(_raw(e) for e in entries)
    return FetchOutcome(board=BOARD, ok=True, jobs=jobs)


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_a_list_that_404s_closes_nothing(db_session: AsyncSession) -> None:
    """A dead list is not evidence that anything closed (I3)."""
    await _ingest_list(db_session, _live_outcome())
    before = await _open_jobs(db_session)
    assert before == 3, "the fixture must create jobs, or this asserts nothing"

    stats = await _ingest_list(
        db_session,
        FetchOutcome(board=BOARD, ok=False, http_status=404, error="HTTP 404"),
    )

    assert stats.closed == 0
    assert stats.boards_failed == [BOARD.token]
    assert await _open_jobs(db_session) == before
    assert await _misses(db_session) == [0, 0, 0], (
        "a failed fetch started the closure countdown; I3 says we learned nothing"
    )


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_a_list_that_marks_everything_closed_closes_nothing(
    db_session: AsyncSession,
) -> None:
    """I3's exact wording, through the pipeline rather than at the adapter.

    Every entry flips to `active: false`. They stay `listed`, so freshness sees
    a full board and ages nothing — which is the whole reason `fetch_board`
    keeps them there instead of filtering them out at the top.
    """
    await _ingest_list(db_session, _live_outcome())
    before = await _open_jobs(db_session)
    assert before == 3

    entries = [_entry("a", active=False), _entry("b", active=False), _entry("c", active=False)]
    adapter = InternshipListAdapter(
        client=_StubClient(entries),  # type: ignore[arg-type]
        list_name="simplify_list",
        raw_url="https://example.invalid/x",
    )
    outcome = await adapter.fetch_board(BOARD)
    assert outcome.jobs == (), "the entries must all be inactive, or this proves nothing"

    stats = await _ingest_list(db_session, outcome)

    assert stats.closed == 0
    assert await _open_jobs(db_session) == before
    assert await _misses(db_session) == [0, 0, 0], (
        "an entry going inactive started the closure countdown — the `listed`/`jobs` "
        "split exists precisely to stop that"
    )


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_a_genuinely_empty_list_is_a_different_fact(db_session: AsyncSession) -> None:
    """A list that responded and holds nothing is real evidence of absence, and
    is deliberately not the same as a failure. It still closes nothing on the
    first pass — closure takes three consecutive misses (§7.4) — but the run
    must record it as a success rather than as an outage."""
    await _ingest_list(db_session, _live_outcome())
    before = await _open_jobs(db_session)

    empty = FetchOutcome(board=BOARD, ok=True, jobs=(), listed=(), http_status=200)
    assert empty.is_authoritative_empty is True
    stats = await _ingest_list(db_session, empty)

    assert stats.boards_failed == []
    assert stats.closed == 0
    assert await _open_jobs(db_session) == before
