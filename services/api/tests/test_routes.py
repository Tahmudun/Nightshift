"""API routes against a real database.

Routes validate and delegate (CLAUDE.md §3), so what is worth asserting here
is the contract the web app's Zod schemas parse — and that /health tells the
truth, which is acceptance row 4's whole point.

The response shapes below were read from the real routes and schemas
(``nightshift/api/routes/health.py``, ``nightshift/api/routes/jobs.py``,
``nightshift/api/schemas.py``) rather than assumed, per this task's own
instruction that the route is the contract. Two shapes differ from the first
draft:

* ``/health`` has **no** ``checks`` wrapper. ``HealthResponse`` puts
  ``database`` and ``redis`` at the top level.
* ``/jobs`` returns ``{items, total, limit, offset}``; each item's
  ``locations`` list carries ``location_confidence`` and ``latitude``
  directly on the location object (``JobLocationOut``), not nested further.

HAZARD (see this task's brief): ``session_scope()`` commits. Letting the
FastAPI app open its own session here would mean the app cannot see this
file's uncommitted seed data, would block on ``db_session``'s ``TRUNCATE``
(an ACCESS EXCLUSIVE lock held for the test's duration), and would commit for
real against the developer's database. Every test below overrides
``get_db_session`` with the fixture's own transactional session instead.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.adapters.base import BoardRef, FetchOutcome, RawJob
from nightshift.adapters.lever import LeverAdapter
from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.base import SourceType
from nightshift.db.models import BoardPollState
from nightshift.db.session import get_db_session
from nightshift.domain.ingestion import get_or_create_source, ingest_boards
from nightshift.domain.polling import sync_board_poll_state
from tests.conftest import requires_db

# db_session binds its asyncpg connection to conftest's session-scoped event
# loop (see test_ingestion.py for the same convention), so every test and
# every async fixture that touches it must run on that loop too.
pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

FIXTURES = Path(__file__).parent / "fixtures"
LEVER_BOARD = BoardRef(company="Alloy", ats="lever", token="alloy", nyc_presence=True)

# A fixed clock for the seed. M1b's closure rules are a function of elapsed
# time, so a test that wants three misses seven days apart needs a known
# starting point rather than "whenever the suite happened to run".
SEED_NOW = datetime(2026, 8, 1, tzinfo=UTC)


class _StubAdapter:
    """A real adapter with its network call replaced by a recorded outcome.

    Mirrors the helper in test_ingestion.py: the adapter's own normalize()
    runs untouched, so what the route serialises is the real
    fetch -> normalize -> persist output on a real recorded board, not a
    hand-built row.
    """

    def __init__(self, inner: Any, outcome: FetchOutcome) -> None:
        self._inner = inner
        self._outcome = outcome
        self.source_name = inner.source_name
        self.source_type = inner.source_type
        self.parser_version = inner.parser_version
        # Lever: one request returns every posting in full, so there is no
        # second phase and fetch_postings is never reached.
        self.is_two_phase = False

    async def fetch_board(self, board: BoardRef, *, etag: str | None = None) -> FetchOutcome:
        return self._outcome

    def normalize(self, raw_job: RawJob, board: BoardRef) -> Any:
        return self._inner.normalize(raw_job, board)


async def _ingest_alloy(
    session: AsyncSession, *, jobs: list[dict[str, Any]] | None = None, now: datetime = SEED_NOW
) -> int:
    """Poll the Alloy board at an explicit time, with an explicit payload.

    The clock is a parameter because M1b's closure rules are a function of it:
    a test that wants three misses has to be able to say when they happened.
    Passing ``jobs=[]`` is a live board with nothing on it — real evidence of
    absence, and deliberately not the same as a failed fetch.

    Returns the number of jobs created, so tests assert against it rather than
    a magic number.
    """
    if jobs is None:
        jobs = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    outcome = FetchOutcome(
        board=LEVER_BOARD,
        ok=True,
        http_status=200,
        jobs=tuple(
            RawJob(
                source_job_id=str(entry["id"]),
                source_company_key="alloy",
                canonical_url=entry.get("hostedUrl"),
                payload=entry,
            )
            for entry in jobs
        ),
    )
    source = await get_or_create_source(
        session, name="lever_test", source_type=SourceType.ATS_LEVER
    )
    adapter = _StubAdapter(LeverAdapter(client=None), outcome)
    _, stats = await ingest_boards(session, adapter, [LEVER_BOARD], source=source, now=now)
    await session.flush()
    return stats.created


async def _seed_alloy_board(session: AsyncSession) -> int:
    """Ingest the committed Lever fixture at ``SEED_NOW``."""
    return await _ingest_alloy(session)


#: A stand-in caller for the corpus routes below (M5b, ADR 0037). Not a row in
#: `users`: nothing these routes read joins to one, and inventing a real
#: account would imply these tests are about a person when they are about a
#: corpus.
_CALLER = uuid.UUID("00000000-0000-4000-8000-0000000000ff")


async def _test_user_id() -> uuid.UUID:
    return _CALLER


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """The ASGI app, wired to the fixture's own transactional session.

    ``app.dependency_overrides`` replaces ``get_db_session`` with a stand-in
    that always yields ``db_session`` — the same connection the truncate/
    rollback fixture holds — so every route in this file sees the test's
    seed data and commits nothing for real.
    """
    app = create_app()

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    # M5b (ADR 0037): every router except `/health` and `/auth` is behind a
    # session now, including the corpus routes this file tests, which were open
    # before. These tests are about what a route *returns*, not about who may
    # ask — that question has its own module,
    # `test_two_users_cannot_see_each_other.py`, which deliberately overrides
    # nothing and signs in over HTTP.
    app.dependency_overrides[current_user_id] = _test_user_id
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_client(db_session: AsyncSession, client: AsyncClient) -> AsyncClient:
    """``client``, with one real recorded board already persisted."""
    created = await _seed_alloy_board(db_session)
    assert created > 0, "seed produced no jobs — the tests below would pass vacuously"
    return client


async def test_health_reports_both_dependencies(client: AsyncClient) -> None:
    """M0 acceptance row 4, still true in M1a.

    ``HealthResponse`` has no ``checks`` wrapper — ``database`` and ``redis``
    are top-level keys (nightshift/api/schemas.py).
    """
    response = await client.get("/health")
    assert response.status_code in (200, 503)
    body = response.json()
    for key in ("database", "redis"):
        assert isinstance(body[key]["ok"], bool)
        assert body[key]["detail"]


async def test_liveness_does_not_touch_the_database(client: AsyncClient) -> None:
    """A liveness probe that fails when Postgres is down restarts a healthy app."""
    response = await client.get("/health/live")
    assert response.status_code == 204
    assert response.content == b""


async def test_jobs_route_returns_the_documented_shape(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get("/jobs")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    assert body["total"] == len(body["items"]) == 9
    first = body["items"][0]
    assert {"id", "title", "company", "locations", "salary", "status"} <= first.keys()
    assert first["company"]["canonical_name"] == "Alloy"


async def test_every_returned_location_has_a_confidence(seeded_client: AsyncClient) -> None:
    """I1 at the API boundary. The web app's Zod schema rejects a point whose
    confidence does not justify it; this asserts the field is always there to
    be checked, on a real ingested board rather than a hand-built row."""
    body = (await seeded_client.get("/jobs")).json()
    assert body["items"], "seed produced no jobs to check"
    seen_confidences: set[str] = set()
    for job in body["items"]:
        assert job["locations"], f"{job['title']!r} has no location rows"
        for location in job["locations"]:
            assert location["location_confidence"] in {
                "verified",
                "approximate",
                "city_only",
                "remote",
                "unknown",
            }
            seen_confidences.add(location["location_confidence"])
            if location["location_confidence"] in {"city_only", "remote", "unknown"}:
                assert location["latitude"] is None
    # Geocoding does not exist yet (M1), so every one of the alloy board's
    # locations must land in this branch — an empty set here would mean the
    # loop above never ran.
    assert seen_confidences, "no confidence values observed — test proves nothing"


async def test_unknown_job_id_is_404_not_500(client: AsyncClient) -> None:
    response = await client.get("/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# M1b — the operational surface. Closure and dedupe are only useful if a human
# can see what they did; §2.6 and M1's "failures visible in the UI, not just
# logs" criterion both land here.
# ---------------------------------------------------------------------------


async def test_admin_route_is_not_read_as_a_job_id(seeded_client: AsyncClient) -> None:
    """FastAPI matches routes in declaration order.

    Declared after ``/{job_id}``, this path resolves as a job whose id is the
    string "admin" and returns 422. The bug is invisible in the code and
    obvious in the response, so the response is what gets asserted.
    """
    response = await seeded_client.get("/jobs/admin")
    assert response.status_code == 200, response.text


async def test_admin_route_reports_every_status_even_at_zero(
    seeded_client: AsyncClient,
) -> None:
    """A missing key and a real zero are different claims.

    The seeded board is entirely open, so three of the four counts are zero.
    They must still be present — otherwise the UI cannot distinguish "no closed
    jobs" from "the API forgot to tell me about closed jobs".
    """
    body = (await seeded_client.get("/jobs/admin")).json()
    assert set(body["status_counts"]) == {"open", "possibly_stale", "unverified", "closed"}
    assert body["status_counts"]["open"] == 9
    assert body["status_counts"]["closed"] == 0
    assert body["total"] == 9


async def test_admin_rows_carry_provenance(seeded_client: AsyncClient) -> None:
    """M1 acceptance: every canonical job traces to at least one raw record.

    Asserted at the API boundary, which is where a human can actually see it.
    """
    body = (await seeded_client.get("/jobs/admin")).json()
    assert body["items"]
    for job in body["items"]:
        assert job["source_count"] >= 1
        assert job["location_count"] >= 1
        assert job["merge_count"] == 0
        assert job["status"] in {"open", "possibly_stale", "unverified", "closed"}
        # I3 at the boundary: an open job has no closure timestamp, and the
        # database constraint that pairs them is mirrored in what we serve.
        assert (job["closed_at"] is not None) == (job["status"] == "closed")


async def test_admin_route_filters_by_status(seeded_client: AsyncClient) -> None:
    body = (await seeded_client.get("/jobs/admin", params={"status": "closed"})).json()
    assert body["items"] == []
    # The breakdown is over the whole table, not the filtered page — otherwise
    # filtering to `closed` would report zero of everything and the operator
    # would lose the only number that says what else exists.
    assert body["status_counts"]["open"] == 9


async def test_admin_route_rejects_an_unknown_status(seeded_client: AsyncClient) -> None:
    """A typo'd filter must be an error, not a silent empty list — the latter
    reads as "no such jobs" and is how an operator concludes nothing is wrong."""
    response = await seeded_client.get("/jobs/admin", params={"status": "not_a_state"})
    assert response.status_code == 422


async def test_history_route_is_404_for_an_unknown_job(client: AsyncClient) -> None:
    """ "No transitions" and "no such job" are different answers."""
    response = await client.get("/jobs/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404


async def test_history_is_empty_for_a_job_that_never_transitioned(
    seeded_client: AsyncClient,
) -> None:
    """A freshly ingested, still-listed job has no transitions — and an empty
    list here is the honest answer, distinct from the 404 above."""
    job_id = (await seeded_client.get("/jobs/admin")).json()["items"][0]["id"]
    response = await seeded_client.get(f"/jobs/{job_id}/history")
    assert response.status_code == 200
    assert response.json() == []


async def test_history_returns_transitions_in_the_words_the_machine_used(
    db_session: AsyncSession, seeded_client: AsyncClient
) -> None:
    """The reason string is the deliverable, not the status change.

    "Why did this job disappear?" is answered by prose a human wrote into
    freshness.py, and this is the route that carries it to them.
    """
    # Three polls of an empty-but-live board: real evidence of absence.
    for day in (1, 2, 3):
        await _ingest_alloy(db_session, jobs=[], now=SEED_NOW + timedelta(days=day))
    await db_session.flush()

    stale = (await seeded_client.get("/jobs/admin", params={"status": "possibly_stale"})).json()
    assert stale["items"], "three misses did not make anything stale"

    history = (await seeded_client.get(f"/jobs/{stale['items'][0]['id']}/history")).json()
    assert len(history) == 1
    event = history[0]
    assert event["from_status"] == "open"
    assert event["to_status"] == "possibly_stale"
    assert "consecutive polls" in event["reason"]
    assert event["observed_misses"] == 3


async def test_source_health_distinguishes_an_outage_from_an_empty_board(
    seeded_client: AsyncClient,
) -> None:
    """§2.6 and I3 at the API boundary.

    If these two timestamps collapsed into one "last seen" field, the UI could
    not tell a user which of the two happened — and those are the two facts the
    whole closure design turns on.
    """
    body = (await seeded_client.get("/sources")).json()
    assert body
    for source in body:
        assert "last_success_at" in source
        assert "last_failure_at" in source


async def test_source_health_breaks_its_jobs_down_by_status(
    db_session: AsyncSession, seeded_client: AsyncClient
) -> None:
    """The count that `job_count` alone cannot give you.

    A provenance link survives a closure, so `job_count` does not move when a
    source's jobs go stale — a dead board and a healthy one report the same
    total. Without this breakdown the source health page would say a source is
    fine while every job it ever produced had aged out.
    """
    before = (await seeded_client.get("/sources")).json()
    lever = next(s for s in before if s["name"] == "lever_test")
    assert lever["job_status_counts"]["open"] == 9
    assert lever["job_status_counts"]["possibly_stale"] == 0

    for day in (1, 2, 3):
        await _ingest_alloy(db_session, jobs=[], now=SEED_NOW + timedelta(days=day))
    await db_session.flush()

    after = (await seeded_client.get("/sources")).json()
    lever = next(s for s in after if s["name"] == "lever_test")
    assert lever["job_status_counts"]["open"] == 0
    assert lever["job_status_counts"]["possibly_stale"] == 9
    # The headline total is unchanged — which is exactly the point.
    assert lever["job_count"] == 9


class TestBoardPollStateRoute:
    """M1d: per-board polling state on the operational surface.

    The ordering assertion is the one that matters. "Which boards have we not
    heard from" is the operational question, and a list sorted by name makes an
    operator scan for trouble instead of being shown it.
    """

    async def test_it_returns_every_board_with_a_poll_state_row(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await sync_board_poll_state(db_session, now=SEED_NOW)
        await db_session.flush()

        response = await client.get("/boards")

        assert response.status_code == 200
        body = response.json()
        assert len(body) >= 3
        assert {"greenhouse", "lever", "ashby"} & {row["ats"] for row in body}

    async def test_a_never_polled_board_says_so_rather_than_guessing(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Null, not a fabricated timestamp and not zero. "We have never heard
        from this board" is a real state and the page has to be able to say it.
        """
        await sync_board_poll_state(db_session, now=SEED_NOW)
        await db_session.flush()

        row = (await client.get("/boards")).json()[0]

        assert row["last_success_at"] is None
        assert row["last_polled_at"] is None
        assert row["last_status"] is None
        assert row["has_etag"] is False
        assert row["consecutive_failures"] == 0

    async def test_boards_we_have_heard_from_least_recently_come_first(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await sync_board_poll_state(db_session, now=SEED_NOW)
        rows = (await db_session.execute(select(BoardPollState))).scalars().all()
        assert len(rows) >= 3
        # Newest first in the database, so a route that preserved insertion
        # order would fail this.
        for offset, row in enumerate(rows):
            row.last_success_at = SEED_NOW - timedelta(hours=offset)
        await db_session.flush()

        body = (await client.get("/boards")).json()

        stamps = [r["last_success_at"] for r in body]
        assert stamps == sorted(stamps), "least-recently-heard-from must come first"

    async def test_a_never_polled_board_sorts_ahead_of_a_healthy_one(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Nulls first. A board nobody has ever reached is the most urgent row
        on the page, and SQL's default puts nulls last on an ascending sort —
        which would bury it below every healthy board."""
        await sync_board_poll_state(db_session, now=SEED_NOW)
        rows = (await db_session.execute(select(BoardPollState))).scalars().all()
        for row in rows[1:]:
            row.last_success_at = SEED_NOW
        await db_session.flush()

        body = (await client.get("/boards")).json()

        assert body[0]["last_success_at"] is None

    async def test_the_etag_value_itself_is_not_exposed(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """Whether one exists is operationally interesting; the opaque provider
        string is not, and printing it invites reading it as an identifier."""
        await sync_board_poll_state(db_session, now=SEED_NOW)
        rows = (await db_session.execute(select(BoardPollState))).scalars().all()
        rows[0].etag = 'W/"secret-looking-token"'
        await db_session.flush()

        body = (await client.get("/boards")).json()

        assert any(r["has_etag"] for r in body)
        assert "secret-looking-token" not in (await client.get("/boards")).text

    async def test_a_304_is_reported_as_success_not_as_a_warning(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """A board answering 304 is healthy. Carrying the status distinctly is
        what lets the UI avoid rendering "no new jobs" as a problem — which is
        how people learn to ignore warnings."""
        await sync_board_poll_state(db_session, now=SEED_NOW)
        rows = (await db_session.execute(select(BoardPollState))).scalars().all()
        rows[0].last_status = 304
        rows[0].last_success_at = SEED_NOW
        rows[0].last_polled_at = SEED_NOW
        await db_session.flush()

        body = (await client.get("/boards")).json()
        board = next(r for r in body if r["last_status"] == 304)

        assert board["last_success_at"] is not None
        assert board["last_error"] is None
        assert board["consecutive_failures"] == 0

    async def test_every_board_reports_a_tier_as_a_word(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """§12.4: no essential information available only through colour."""
        await sync_board_poll_state(db_session, now=SEED_NOW)
        await db_session.flush()

        body = (await client.get("/boards")).json()

        assert all(row["tier"] in {"hot", "warm"} for row in body)


# --- M2a: search and filters -------------------------------------------------
#
# The seeded board is Alloy (Lever), nine postings: Customer Success Manager,
# Account Executive and one Software Developer, in Denver / Vancouver /
# Washington / Remote. There is deliberately no "engineer" in this corpus —
# these tests derive their expectations from what is actually ingested rather
# than from a title somebody hoped would be there.


async def test_text_search_matches_a_title_word(seeded_client: AsyncClient) -> None:
    response = await seeded_client.get("/jobs", params={"q": "developer"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert "developer" in item["title"].lower()


async def test_text_search_narrows_rather_than_returning_everything(
    seeded_client: AsyncClient,
) -> None:
    """The failure this catches is a filter silently ignored by the route,
    which looks like a working search returning suspiciously good results."""
    everything = (await seeded_client.get("/jobs")).json()["total"]
    narrowed = (await seeded_client.get("/jobs", params={"q": "developer"})).json()["total"]
    assert 0 < narrowed < everything


async def test_searching_descriptions_is_opt_in_and_much_wider(
    seeded_client: AsyncClient,
) -> None:
    """The measurement that decided the default, pinned so it cannot drift back.

    'developer' stems to 'develop', and every one of the nine recorded Alloy
    descriptions contains "business development" or "professional development".
    So the description-wide search returns the whole board while the title
    search returns one posting. Without relevance ranking (M3) a
    description-wide *default* is a search box that does nothing, which is why
    it is opt-in.
    """
    title_only = (await seeded_client.get("/jobs", params={"q": "developer"})).json()
    widened = (
        await seeded_client.get("/jobs", params={"q": "developer", "include_description": "true"})
    ).json()

    assert title_only["total"] == 1
    assert widened["total"] == 9
    assert title_only["items"][0]["title"] == "Software Developer, Full Stack"


async def test_a_body_only_term_is_findable_when_you_ask_for_it(
    seeded_client: AsyncClient,
) -> None:
    """The reason the wide search still exists: a term that appears only in the
    description is unreachable from the title index, and sometimes that term is
    exactly what you are looking for."""
    # Appears in three of the nine recorded descriptions and in none of the
    # titles, measured from the fixture rather than guessed.
    body_term = "playbooks"
    title_only = (await seeded_client.get("/jobs", params={"q": body_term})).json()
    widened = (
        await seeded_client.get("/jobs", params={"q": body_term, "include_description": "true"})
    ).json()
    assert title_only["total"] == 0
    assert widened["total"] >= 1


async def test_a_blank_query_returns_the_corpus(seeded_client: AsyncClient) -> None:
    """An empty search box is not a filter. This is the regression that turns
    a search page into a permanently empty one."""
    everything = (await seeded_client.get("/jobs")).json()["total"]
    blank = (await seeded_client.get("/jobs", params={"q": "   "})).json()["total"]
    assert blank == everything


async def test_text_search_does_not_raise_on_punctuation_a_person_typed(
    seeded_client: AsyncClient,
) -> None:
    """websearch_to_tsquery tolerates this; plainto_tsquery would not."""
    for typed in ['"customer success"', "manager -senior", "c++", "&&&"]:
        response = await seeded_client.get("/jobs", params={"q": typed})
        assert response.status_code == 200, f"{typed!r} produced {response.status_code}"


async def test_the_city_filter_matches_what_the_source_wrote(
    seeded_client: AsyncClient,
) -> None:
    """Derived from the corpus: whatever city the first located job names, a
    filter on it must return only jobs naming that city."""
    listing = (await seeded_client.get("/jobs")).json()["items"]
    cities = [loc["city"] for job in listing for loc in job["locations"] if loc["city"]]
    assert cities, "no located job in the seed — this test would pass vacuously"
    target = cities[0]

    body = (await seeded_client.get("/jobs", params={"city": target})).json()
    assert body["total"] >= 1
    for item in body["items"]:
        assert target.lower() in {(loc["city"] or "").lower() for loc in item["locations"]}


async def test_the_city_filter_is_case_insensitive(seeded_client: AsyncClient) -> None:
    listing = (await seeded_client.get("/jobs")).json()["items"]
    cities = [loc["city"] for job in listing for loc in job["locations"] if loc["city"]]
    target = cities[0]
    upper = (await seeded_client.get("/jobs", params={"city": target.upper()})).json()
    lower = (await seeded_client.get("/jobs", params={"city": target.lower()})).json()
    assert upper["total"] == lower["total"] >= 1


async def test_a_salary_floor_reports_what_it_hid(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A10: most postings state no salary, so a floor that silently removed
    them would misrepresent the corpus. The count is the honesty.

    Seeds its own corpus rather than using ``seeded_client``: every one of the
    nine recorded Alloy postings carries a ``salaryRange``, so against that
    board the excluded count is legitimately zero and the assertion could never
    fail. Half the postings here have the field stripped.
    """
    payload = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    for entry in payload[:4]:
        entry.pop("salaryRange", None)
    await _ingest_alloy(db_session, jobs=payload)
    await db_session.flush()

    body = (await client.get("/jobs", params={"salary_at_least": 1})).json()
    assert body["excluded_no_salary"] == 4
    assert body["total"] == 5
    for item in body["items"]:
        assert item["salary"]["provided"] is True


async def test_no_salary_filter_means_no_exclusion_count(seeded_client: AsyncClient) -> None:
    body = (await seeded_client.get("/jobs")).json()
    assert body["excluded_no_salary"] == 0


async def test_the_skill_filter_narrows_and_says_what_it_could_not_read(
    seeded_client: AsyncClient,
) -> None:
    """M3b Task 11, and the count is the condition the filter shipped under.

    Required-technology recall is 0.861, so this filter hides roughly one
    matching role in seven. `excluded_no_requirements` is how many postings it
    could not have matched at all — nothing was extracted from them — and
    without it a thin result reads as "there are only two such jobs" rather
    than "we could not read some of these".
    """
    everything = (await seeded_client.get("/jobs", params={"limit": 100})).json()
    body = (await seeded_client.get("/jobs", params={"skill": "Python", "limit": 100})).json()

    assert 0 < body["total"] < everything["total"], "a filter matching everything is not a filter"
    assert body["excluded_no_requirements"] >= 0
    assert everything["excluded_no_requirements"] == 0, "not asked for, not counted"


async def test_a_skill_alias_finds_the_same_jobs_as_its_canonical_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`golang` and `Go` are one technology, and the person typing the first
    must not be told there are no such jobs.

    `job_requirements.value` stores only the canonical name, so an unresolved
    filter returns zero — indistinguishable from an honest empty result.

    Seeds its own board because the recorded Alloy postings are customer-success
    and account-executive roles that name no technology the vocabulary carries.
    Against those, both sides of this assertion are zero and it could never
    fail — which is the shape of test M3a shipped and this project has since
    learned to check for.
    """
    payload = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    payload[0]["descriptionPlain"] = "Requirements\n3+ years writing Go and Python daily."
    await _ingest_alloy(db_session, jobs=payload)
    await db_session.flush()

    canonical = (await client.get("/jobs", params={"skill": "Go", "limit": 100})).json()
    alias = (await client.get("/jobs", params={"skill": "golang", "limit": 100})).json()

    assert canonical["total"] == 1, "the seeded corpus must exercise this or it asserts nothing"
    assert alias["total"] == canonical["total"]


async def test_a_season_filter_reports_the_internships_it_necessarily_hid(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """11 of 19 corpus internships state no season, so this filter hides more of
    its own subject than any other filter in the product.

    Both kinds are seeded, because the count only means something next to a
    result: one internship states "Summer 2027" and matches, one states nothing
    and is hidden. Without the second row the count is zero and this test would
    pass against a filter that reported nothing at all.
    """
    payload = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    payload[0]["text"] = "Software Engineer Intern, Summer 2027"
    payload[1]["text"] = "Data Science Intern"
    await _ingest_alloy(db_session, jobs=payload)
    await db_session.flush()

    body = (await client.get("/jobs", params={"internship_season": "summer"})).json()

    assert body["total"] == 1
    assert body["items"][0]["title"] == "Software Engineer Intern, Summer 2027"
    assert body["excluded_no_season"] == 1, "the internship stating no season must be counted"


async def test_a_year_filter_and_a_season_filter_hide_different_internships(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The reason the count takes the query rather than being one number.

    "2027 Internship Program" states a year and no season. Asking for `2027`
    finds it; asking for `summer` hides it and must say so. One count that
    ignored which dimension was asked about would be wrong on both.
    """
    payload = json.loads((FIXTURES / "lever" / "alloy_board.json").read_text())
    payload[0]["text"] = "Software Engineer, 2027 Internship Program"
    await _ingest_alloy(db_session, jobs=payload)
    await db_session.flush()

    by_year = (await client.get("/jobs", params={"internship_year": 2027})).json()
    by_season = (await client.get("/jobs", params={"internship_season": "summer"})).json()

    assert by_year["total"] == 1
    assert by_year["excluded_no_season"] == 0, "it states the year that was asked for"
    assert by_season["total"] == 0
    assert by_season["excluded_no_season"] == 1, "it states no season"


async def test_no_season_filter_means_no_season_exclusion_count(
    seeded_client: AsyncClient,
) -> None:
    body = (await seeded_client.get("/jobs")).json()
    assert body["excluded_no_season"] == 0


async def test_filters_compose(seeded_client: AsyncClient) -> None:
    """Two filters must intersect, not union — the classic and silent bug."""
    open_only = (await seeded_client.get("/jobs", params={"status": "open"})).json()["total"]
    both = (await seeded_client.get("/jobs", params={"status": "open", "q": "developer"})).json()[
        "total"
    ]
    assert both <= open_only


async def test_the_response_names_the_filters_it_will_not_fake(
    seeded_client: AsyncClient,
) -> None:
    body = (await seeded_client.get("/jobs")).json()
    names = {entry["name"] for entry in body["deferred_filters"]}
    assert "match_score" in names
    assert "borough" in names
    borough = next(e for e in body["deferred_filters"] if e["name"] == "borough")
    assert borough["blocked_on"] == "M4"


async def test_an_unknown_employment_type_is_rejected_not_ignored(
    seeded_client: AsyncClient,
) -> None:
    """A typo'd filter that returns everything is worse than an error: it looks
    like an answer."""
    response = await seeded_client.get("/jobs", params={"employment_type": "part_time_ish"})
    assert response.status_code == 422


async def test_the_source_filter_reaches_through_provenance(
    seeded_client: AsyncClient,
) -> None:
    """The seed ingests under a source named 'lever_test'."""
    body = (await seeded_client.get("/jobs", params={"source": "lever"})).json()
    assert body["total"] == (await seeded_client.get("/jobs")).json()["total"]
    assert (await seeded_client.get("/jobs", params={"source": "nosuchsource"})).json()[
        "total"
    ] == 0
