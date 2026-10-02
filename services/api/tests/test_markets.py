"""Market scope: New York now, the other tech cities by configuration (ADR 0041, Q14).

Every location here goes through the real location parser, so the rows carry
exactly the spellings ingestion writes. The scope matches on those spellings,
and a fixture that hand-typed ``state="NY"`` would test a database that cannot
exist.

What is pinned:

* each defined market recognises its own cities as the parser writes them,
  and a state or country that disagrees is another place;
* the SQL rule and the Python rule give the same answer on a matrix of real
  location shapes, for one market and for two;
* a job is hidden only on positive knowledge: remote, unresolved and
  location-less roles are always in scope;
* every read path that applies the scope says how many it left out, and its
  other "excluded" counts are taken inside the same scope;
* ``MARKETS`` turns markets on (and ``all`` turns the scope off) without
  touching a row.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.config import get_settings
from nightshift.db.base import EligibilityState, JobStatus, LocationConfidence, Seniority
from nightshift.db.models import Company, Job, JobLocation, User
from nightshift.db.session import get_db_session
from nightshift.domain.locations import parse_location_list
from nightshift.domain.markets import (
    MARKETS,
    NEW_YORK,
    Market,
    current_scope,
    in_scope_filter,
    market_of,
    parse_market_keys,
    scope_of,
)
from nightshift.domain.matching import ranked_for
from nightshift.domain.queue import NEW_INTERNSHIP_DAYS, QueueSectionKey, build_queue
from nightshift.mcp import shapes
from tests.conftest import make_settings, requires_db, store_score

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
DESCRIPTION = "We need strong Python and PostgreSQL."

#: One real posting string per market, as a board would write it. Keyed by
#: market so a new market without a sample fails `test_every_market_...`.
SAMPLES = {
    "nyc": "New York, NY",
    "sf-bay-area": "San Francisco, CA",
    "seattle": "Seattle, WA",
    "boston": "Boston, MA",
    "austin": "Austin, TX",
    "los-angeles": "Los Angeles, CA",
    "chicago": "Chicago, IL",
    "washington-dc": "Washington, DC",
    "london": "London, UK",
    "toronto": "Toronto, ON",
}


def _parsed(raw: str) -> tuple[str | None, str | None, str | None]:
    [location] = parse_location_list([raw])
    return location.city, location.state, location.country


# ---------------------------------------------------------------------------
# The definitions, against the parser.
# ---------------------------------------------------------------------------


def test_every_market_recognises_its_cities_as_the_parser_writes_them() -> None:
    assert set(SAMPLES) == set(MARKETS), "every market needs a sample, and every sample a market"
    for key, raw in SAMPLES.items():
        market = market_of(*_parsed(raw))
        assert market is not None and market.key == key, f"{raw!r} -> {market}"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Brooklyn", "nyc"),
        ("NYC", "nyc"),
        ("Cambridge, MA", "boston"),
        ("Mountain View, California, United States", "sf-bay-area"),
        # The same names, somewhere else.
        ("Cambridge, United Kingdom", None),
        ("London, ON", None),
        ("Washington, USA, Remote", None),
        ("Jersey City, NJ", None),
        ("Denver, CO", None),
        ("Paris, France", None),
    ],
)
def test_a_state_or_country_that_disagrees_is_another_place(raw: str, expected: str | None) -> None:
    market = market_of(*_parsed(raw))
    assert (market.key if market else None) == expected


def test_nyc_is_the_codebases_one_definition_of_new_york() -> None:
    """Polling tiers and discovery ask "is this NYC" of `NYC_CITY_NAMES`. The
    market reuses it rather than restating it, so the two cannot drift."""
    from nightshift.domain.locations import NYC_CITY_NAMES

    assert MARKETS["nyc"].cities is NYC_CITY_NAMES


def test_market_keys_parse_strictly() -> None:
    assert parse_market_keys(" nyc , sf-bay-area,nyc") == ("nyc", "sf-bay-area")
    assert parse_market_keys("all") == ("all",)
    for bad in ("", " , ", "nyx", "nyc,all"):
        with pytest.raises(ValueError):
            parse_market_keys(bad)


def test_an_unknown_market_refuses_to_boot() -> None:
    """A typo must not quietly scope the product to nothing."""
    assert make_settings().enabled_markets == ("nyc",)
    with pytest.raises(ValidationError, match="unknown market"):
        make_settings(markets="new-york")


def test_the_default_scope_is_new_york() -> None:
    scope = current_scope()
    assert scope.names == ["New York City"]
    assert not scope.everywhere


def test_mcp_search_carries_what_the_scope_left_out() -> None:
    """A search with nothing in New York and fourteen in London must not reach
    the reader as "there are none"."""
    shaped = shapes.search_result(
        {"items": [], "total": 0, "markets": ["New York City"], "excluded_out_of_market": 14}
    )
    assert shaped["markets"] == ["New York City"]
    assert shaped["matching_outside_markets"] == 14


# ---------------------------------------------------------------------------
# The rule in SQL agrees with the rule in Python.
# ---------------------------------------------------------------------------


async def _company(session: AsyncSession) -> Company:
    company = Company(canonical_name="Example Inc.", normalized_name=str(uuid.uuid4()))
    session.add(company)
    await session.flush()
    return company


async def _job_at(
    session: AsyncSession,
    *raws: str,
    title: str = "Software Engineer",
    salary_min: float | None = None,
    seniority: Seniority | None = None,
    first_seen_at: datetime = NOW,
) -> Job:
    """A job whose locations are what the parser makes of ``raws``."""
    company = await _company(session)
    job = Job(
        company_id=company.id,
        title=title,
        normalized_title=title.casefold(),
        description_text=DESCRIPTION,
        status=JobStatus.OPEN,
        salary_min=salary_min,
        seniority=seniority,
        first_seen_at=first_seen_at,
        last_seen_at=NOW,
    )
    session.add(job)
    await session.flush()
    for index, parsed in enumerate(parse_location_list(list(raws))):
        session.add(
            JobLocation(
                job_id=job.id,
                raw_text=parsed.raw_text,
                city=parsed.city,
                state=parsed.state,
                country=parsed.country,
                location_confidence=parsed.confidence,
                resolution_method=parsed.resolution_method,
                is_primary=index == 0,
            )
        )
    await session.flush()
    return job


def _python_in_scope(rows: Sequence[JobLocation], markets: Sequence[Market]) -> bool:
    """The rule as ADR 0041 states it, written independently of the SQL."""
    if not rows:
        return True
    for row in rows:
        if row.city is None or row.location_confidence is LocationConfidence.REMOTE:
            return True
        if any(m.contains(row.city, row.state, row.country) for m in markets):
            return True
    return False


SHAPES: list[tuple[str, ...]] = [
    ("New York, NY",),
    ("Brooklyn",),
    ("Denver, CO",),
    ("Denver, CO", "New York, NY (HQ)"),
    ("Denver, CO", "Remote (US)"),
    ("Remote (Canada)",),
    ("Somewhere vague",),
    ("Denver, CO", "Somewhere vague"),
    (),
    ("London, UK",),
    ("London, ON",),
    ("San Francisco, CA", "Seattle, WA"),
    ("Remote - New York",),
]


@requires_db
@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("keys", [("nyc",), ("nyc", "london")])
async def test_the_sql_rule_and_the_python_rule_agree(
    db_session: AsyncSession, keys: tuple[str, ...]
) -> None:
    scope = scope_of(keys)
    jobs = [await _job_at(db_session, *shape) for shape in SHAPES]
    ids = [job.id for job in jobs]

    in_sql = set(
        (await db_session.execute(select(Job.id).where(Job.id.in_(ids), in_scope_filter(scope))))
        .scalars()
        .all()
    )
    rows = (
        await db_session.execute(select(JobLocation).where(JobLocation.job_id.in_(ids)))
    ).scalars()
    by_job: dict[uuid.UUID, list[JobLocation]] = {job_id: [] for job_id in ids}
    for row in rows:
        by_job[row.job_id].append(row)
    in_python = {
        job_id for job_id, located in by_job.items() if _python_in_scope(located, scope.markets)
    }

    assert in_sql == in_python
    # And the rule is not vacuous in either direction on this matrix.
    assert in_sql and set(ids) - in_sql


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_only_positive_knowledge_hides_a_job(db_session: AsyncSession) -> None:
    """Remote, unresolved, location-less: always shown. Hidden only when every
    place a job names is a known city outside the scope."""
    keep = [
        await _job_at(db_session, "Remote (US)"),
        await _job_at(db_session, "Somewhere vague"),
        await _job_at(db_session),
        await _job_at(db_session, "Denver, CO", "Somewhere vague"),
        await _job_at(db_session, "Denver, CO", "New York, NY"),
    ]
    hide = [
        await _job_at(db_session, "Denver, CO"),
        await _job_at(db_session, "San Francisco, CA", "Seattle, WA"),
    ]
    ids = [job.id for job in keep + hide]
    shown = set(
        (await db_session.execute(select(Job.id).where(Job.id.in_(ids), in_scope_filter(NEW_YORK))))
        .scalars()
        .all()
    )
    assert shown == {job.id for job in keep}


# ---------------------------------------------------------------------------
# Read paths.
# ---------------------------------------------------------------------------

_CALLER = uuid.UUID("00000000-0000-4000-8000-0000000000fe")


async def _caller() -> uuid.UUID:
    return _CALLER


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """The app on the test's own session. Who may call is ADR 0037's question and
    `test_two_users_cannot_see_each_other.py`'s; this file asks what comes back."""
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[current_user_id] = _caller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


def _set_markets(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Change MARKETS mid-test. Settings are a cached singleton (and the app has
    already read them by the time a test body runs), so the cache has to go too;
    without that, a test of "turning a market on" passes on the old scope."""
    monkeypatch.setenv("MARKETS", value)
    get_settings.cache_clear()


def _titles(body: dict[str, object]) -> set[str]:
    items = body["items"]
    assert isinstance(items, list)
    return {item["title"] for item in items}


@requires_db
@pytest.mark.asyncio(loop_scope="session")
class TestSearch:
    async def test_it_shows_the_market_and_counts_the_rest(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await _job_at(db_session, "New York, NY", title="NYC role")
        await _job_at(db_session, "Remote (US)", title="Remote role")
        await _job_at(db_session, "Denver, CO", title="Denver role")

        body = (await client.get("/jobs")).json()

        assert _titles(body) == {"NYC role", "Remote role"}
        assert body["total"] == 2
        assert body["excluded_out_of_market"] == 1
        assert body["markets"] == ["New York City"]

    async def test_a_filter_that_only_matches_elsewhere_says_so(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """An empty result with a non-zero count beside it, never a bare zero."""
        await _job_at(db_session, "San Francisco, CA", title="Staff Platform Engineer")

        body = (await client.get("/jobs", params={"q": "platform"})).json()

        assert body["total"] == 0
        assert body["excluded_out_of_market"] == 1

    async def test_the_other_excluded_counts_are_taken_inside_the_scope(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        """`excluded_no_salary` describes this result. A Denver role with no
        salary was never going to be in it, so it is not counted there."""
        await _job_at(db_session, "New York, NY", title="Paid", salary_min=120_000)
        await _job_at(db_session, "New York, NY", title="Unstated")
        await _job_at(db_session, "Denver, CO", title="Unstated elsewhere")

        body = (await client.get("/jobs", params={"salary_at_least": 50_000})).json()

        assert _titles(body) == {"Paid"}
        assert body["excluded_no_salary"] == 1

    async def test_enabling_a_market_is_configuration_not_data(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _job_at(db_session, "New York, NY", title="NYC role")
        await _job_at(db_session, "San Francisco, CA", title="SF role")

        assert _titles((await client.get("/jobs")).json()) == {"NYC role"}

        _set_markets(monkeypatch, "nyc,sf-bay-area")
        body = (await client.get("/jobs")).json()
        assert _titles(body) == {"NYC role", "SF role"}
        assert body["markets"] == ["New York City", "San Francisco Bay Area"]

    async def test_all_turns_the_scope_off(
        self, client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _job_at(db_session, "Denver, CO", title="Denver role")
        _set_markets(monkeypatch, "all")

        body = (await client.get("/jobs")).json()

        assert "Denver role" in _titles(body)
        assert body["excluded_out_of_market"] == 0
        assert body["markets"] == ["Everywhere"]


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_matches_rank_inside_the_scope_and_count_outside_it(
    db_session: AsyncSession,
) -> None:
    """Both are scored. Only the New York one is listed; the other is counted,
    and is ranked the moment its market is enabled."""
    user = User(email=f"{uuid.uuid4()}@example.test")
    db_session.add(user)
    await db_session.flush()
    here = await _job_at(db_session, "New York, NY")
    there = await _job_at(db_session, "Denver, CO")
    for job in (here, there):
        await store_score(
            db_session, user=user, job=job, overall=70, out_of=100, state=EligibilityState.ELIGIBLE
        )

    ranking = await ranked_for(db_session, user_id=user.id, limit=50)

    assert [job.id for job, _ in ranking.rows] == [here.id]
    assert ranking.excluded_out_of_market == 1


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_the_internship_row_names_what_is_elsewhere(db_session: AsyncSession) -> None:
    user = User(email=f"{uuid.uuid4()}@example.test")
    db_session.add(user)
    await db_session.flush()
    for raw in ("New York, NY", "Denver, CO", "San Francisco, CA"):
        job = await _job_at(db_session, raw, title=f"Intern, {raw}", seniority=Seniority.INTERNSHIP)
        await store_score(
            db_session, user=user, job=job, overall=70, out_of=100, state=EligibilityState.ELIGIBLE
        )
    # Outside the window: counted by nothing in this row.
    await _job_at(
        db_session,
        "Denver, CO",
        seniority=Seniority.INTERNSHIP,
        first_seen_at=NOW - timedelta(days=NEW_INTERNSHIP_DAYS + 1),
    )

    queue = await build_queue(db_session, user_id=user.id, now=NOW)
    section = {s.key: s for s in queue.sections}[QueueSectionKey.BEST_NEW_INTERNSHIPS]

    assert [row.job_title for row in section.rows] == ["Intern, New York, NY"]
    spots = {spot.name: spot.count for spot in section.blind_spots}
    assert spots["outside_markets"] == 2


@requires_db
@pytest.mark.asyncio(loop_scope="session")
async def test_stats_says_where_the_rest_is_and_which_market_would_show_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _job_at(db_session, "New York, NY")
    await _job_at(db_session, "Remote (US)")
    await _job_at(db_session, "San Francisco, CA")
    await _job_at(db_session, "Oakland, CA")
    await _job_at(db_session, "Denver, CO")

    scope = (await client.get("/stats")).json()["market_scope"]

    assert scope["everywhere"] is False
    assert scope["enabled"] == [{"key": "nyc", "name": "New York City"}]
    assert scope["open_in_scope"] == 2
    assert scope["open_out_of_scope"] == 3
    assert scope["elsewhere"] == [
        {"label": "San Francisco Bay Area", "market_key": "sf-bay-area", "jobs": 2},
        {"label": "Denver, Colorado", "market_key": None, "jobs": 1},
    ]
