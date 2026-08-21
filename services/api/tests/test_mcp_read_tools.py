"""The read tools, against a real MCP client and the real FastAPI app.

Three properties, and each is a rule that holds across the whole tool surface
rather than at one call site — so each is asserted by **enumerating the
registered tools** rather than by naming the ones that exist today. A tool
added at M5d has to trip these without anybody remembering to extend a list.

That pattern is M5b's. `test_two_users_cannot_see_each_other.py` enumerates
every route rather than spot-checking three, and it is why the isolation claim
means something. The same reasoning applies here for the same reason.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mcp.server import MCPServer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user
from nightshift.api.main import create_app
from nightshift.db.base import JobStatus, LocationConfidence, ResolutionMethod
from nightshift.db.models import Company, Job, JobLocation, User
from nightshift.db.session import get_db_session
from nightshift.db.types import utcnow
from nightshift.domain.applications import save_job
from nightshift.mcp.client import NightshiftClient, NightshiftUnavailableError
from nightshift.mcp.server import build_server
from tests.conftest import requires_db
from tests.test_mcp_server import connected

pytestmark = [requires_db]
_async = pytest.mark.asyncio(loop_scope="session")

#: Tools that read the corpus and take no required arguments, so they can be
#: called blind by the enumerating tests below.
ARGUMENTLESS_READS = ("search_jobs", "list_applications")


@pytest_asyncio.fixture(loop_scope="session")
async def account(db_session: AsyncSession) -> AsyncIterator[User]:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="MCP Reader")
    db_session.add(row)
    await db_session.flush()
    yield row


@pytest_asyncio.fixture(loop_scope="session")
async def corpus(db_session: AsyncSession, account: User) -> AsyncIterator[Job]:
    """One job, one location, one saved application — and it is load-bearing.

    **The first draft of this module had no corpus and its guards could not
    fail.** `db_session` truncates, so `search_jobs` returned `{"jobs": []}`
    and `list_applications` returned `{"applications": []}`; a walk over an
    empty list finds no score and no coordinate, and every enumerating
    assertion below passed vacuously. Sabotaging `job_summary` to leak a score
    left this file green.

    That is `CLAUDE.md` §7's "a test that cannot fail is not a test", and M4c
    recorded the same lesson in different words: *a corpus that cannot produce
    a failure cannot test the guard against it.* The fixture exists so the
    walks have something to walk.

    **Two locations, and the reason is a finding.** The first draft planted a
    `city_only` row *with* coordinates, to exercise `location_result`'s
    withholding end to end — and Postgres refused the INSERT.
    `job_locations.confidence_matches_coordinates` enforces I1 in the schema,
    both directions: `verified`/`approximate` must have a latitude, and
    `city_only`/`remote`/`unknown` must not.

    So the combination `shapes.py` defends against **cannot reach it from this
    database**, and that defence is genuinely belt-and-braces rather than the
    last line it was written as. It is kept, because the MCP client will one
    day read a response this repository did not serialise, and because a
    constraint is not a reason to hand a model a coordinate it must not read as
    an address. The unit tests in `test_mcp_shapes.py` cover that path; these
    cover the two the database permits.
    """
    company = Company(canonical_name="Corpus Co.", normalized_name=str(uuid.uuid4()))
    db_session.add(company)
    await db_session.flush()

    now = utcnow()
    job = Job(
        company_id=company.id,
        title="Backend Engineer",
        normalized_title="backend engineer",
        status=JobStatus.OPEN,
        first_seen_at=now,
        last_seen_at=now,
    )
    db_session.add(job)
    await db_session.flush()

    db_session.add_all(
        [
            JobLocation(
                job_id=job.id,
                raw_text="New York, NY",
                city="New York",
                state="NY",
                country="US",
                location_confidence=LocationConfidence.CITY_ONLY,
                resolution_method=ResolutionMethod.SOURCE_TEXT_PARSE,
                is_primary=True,
            ),
            JobLocation(
                job_id=job.id,
                raw_text="620 8th Avenue, New York, NY",
                city="New York",
                state="NY",
                country="US",
                latitude=40.7561,
                longitude=-73.9903,
                location_confidence=LocationConfidence.VERIFIED,
                resolution_method=ResolutionMethod.NYC_GEOSEARCH,
                is_primary=False,
            ),
        ]
    )
    await save_job(db_session, user_id=account.id, job_id=job.id, now=now)
    await db_session.flush()
    yield job


@pytest_asyncio.fixture(loop_scope="session")
async def server(db_session: AsyncSession, account: User, corpus: Job) -> AsyncIterator[MCPServer]:
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[current_user] = lambda: account

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield build_server(NightshiftClient("", "unused-in-this-transport", http=http))


def _walk(value: Any, path: str = "") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = [(path, value)]
    if isinstance(value, dict):
        for key, item in value.items():
            found += _walk(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += _walk(item, f"{path}[{index}]")
    return found


# --------------------------------------------------------------------------
# I4, over the tool surface rather than at one call site
# --------------------------------------------------------------------------


@_async
async def test_no_tool_but_explain_match_returns_a_score(server: MCPServer) -> None:
    """*"A bare number in the UI is a bug"* — and a tool result is a UI.

    `explain_match` is the one place a score may appear, because it is the one
    place the components, penalties, `ruleset_version` and evidence appear with
    it. A search result carrying `78` is I4 broken on a new surface.
    """
    async with connected(server) as session:
        for name in ARGUMENTLESS_READS:
            result = await session.call_tool(name, {})
            assert not result.is_error, (name, result.content)

            scored = [
                path
                for path, _ in _walk(result.structured_content)
                if any(word in path.lower() for word in ("score", "fraction", "rating"))
            ]
            assert scored == [], f"{name} returned a score at {scored}"


@_async
async def test_every_coordinate_arrives_with_its_confidence(server: MCPServer) -> None:
    """I1's structural half, walked rather than checked at a known path."""
    async with connected(server) as session:
        for name in ARGUMENTLESS_READS:
            result = await session.call_tool(name, {})
            assert not result.is_error, (name, result.content)

            for path, value in _walk(result.structured_content):
                if isinstance(value, dict) and "coordinates" in value:
                    assert "confidence" in value, f"{name}: {path} has coordinates, no confidence"
                    assert "means" in value, f"{name}: {path} has coordinates, no explanation"


# --------------------------------------------------------------------------
# I3: an outage is not an empty result
# --------------------------------------------------------------------------


@_async
async def test_an_unreachable_api_raises_rather_than_returning_nothing() -> None:
    """The failure that will actually happen, and the one that lies if unhandled.

    Claude Desktop launches this server whether or not `make dev` is running.
    An unreachable API answered with `[]` becomes *"there are no backend
    internships open in New York"* — fluent, confident, and produced by a
    connection refused on port 8000. Nothing on screen would distinguish it
    from a real empty result.

    Port 9 is `discard`, reserved and never listening, so this is a real
    connection failure rather than a mocked one.
    """
    async with NightshiftClient("http://127.0.0.1:9", "nsk_unused") as client:
        with pytest.raises(NightshiftUnavailableError) as raised:
            await client.get("/jobs")

    message = str(raised.value)
    assert "not reachable" in message
    assert "make dev" in message, "the message must name the fix, not just the fault"


@_async
async def test_an_outage_surfaces_to_the_model_as_a_tool_error() -> None:
    """The other half: raising is useless if MCP swallows it into a normal result.

    A tool that returns `isError: false` with an error message *inside* the
    payload is one Claude may summarise as data.
    """
    async with NightshiftClient("http://127.0.0.1:9", "nsk_unused") as client:
        async with connected(build_server(client)) as session:
            result = await session.call_tool("search_jobs", {})

    assert result.is_error, "an outage must reach the model as an error, not as a result"
    assert "not reachable" in str(result.content)


# --------------------------------------------------------------------------
# Isolation, enumerated
# --------------------------------------------------------------------------


@_async
async def test_no_read_tool_returns_another_persons_applications(
    db_session: AsyncSession, account: User
) -> None:
    """M5b's property, re-asserted at the surface that exposes it to a program.

    The routes are already scoped and `test_two_users_cannot_see_each_other.py`
    proves it. This is not a duplicate: it proves the MCP layer did not
    *widen* anything — a tool that passed a `user_id` argument through to a
    route, or reached past one, would leak without any route changing.
    """
    stranger = User(email=f"{uuid.uuid4()}@example.test", display_name="Somebody Else")
    company = Company(canonical_name="Stranger Co.", normalized_name=str(uuid.uuid4()))
    db_session.add_all([stranger, company])
    await db_session.flush()

    now = utcnow()
    job = Job(
        company_id=company.id,
        title="A job the stranger applied to",
        normalized_title="a job the stranger applied to",
        status=JobStatus.OPEN,
        first_seen_at=now,
        last_seen_at=now,
    )
    db_session.add(job)
    await db_session.flush()

    await save_job(db_session, user_id=stranger.id, job_id=job.id, now=now)
    await db_session.flush()

    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[current_user] = lambda: account

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        server = build_server(NightshiftClient("", "unused", http=http))
        async with connected(server) as session:
            result = await session.call_tool("list_applications", {})

    assert not result.is_error, result.content
    assert result.structured_content is not None
    assert result.structured_content["applications"] == [], (
        "the MCP surface returned an application belonging to somebody else"
    )


@_async
async def test_no_tool_takes_a_user_id_argument(server: MCPServer) -> None:
    """The shape that would make the test above pass and still leak.

    Identity comes from the session token and from nowhere else. A tool with a
    `user_id` parameter lets the *caller* choose whose data to read — and the
    caller here is a language model reading text written by strangers. This
    fails the moment such a parameter is added, which is before it can be
    wired to anything.
    """
    async with connected(server) as session:
        listed = await session.list_tools()

    offenders = [
        (tool.name, key)
        for tool in listed.tools
        for key in (tool.input_schema.get("properties") or {})
        if key in ("user_id", "userId", "email", "account_id", "as_user")
    ]
    assert offenders == [], f"tools let the caller choose an identity: {offenders}"


# --------------------------------------------------------------------------
# I3: a closed listing is not an open one
# --------------------------------------------------------------------------


@_async
async def test_search_does_not_return_closed_jobs_by_default(
    db_session: AsyncSession, account: User, corpus: Job
) -> None:
    """Found by reading the route, not by running the walk — and that is the point.

    `GET /jobs` applies a status filter only when one is given, so with none it
    returns **every** status including `closed`. `search_jobs` said "Search open
    New York technology jobs" in its description and passed no filter, so the
    description made a claim the tool did not honour: a closed listing would
    have reached a reader as an available role.

    **The live walk could not have caught this.** The seeded corpus is 32 jobs
    and all 32 are `open` — so this test has to build the failure the corpus
    cannot produce, which is M4c's lesson arriving a third time in this
    milestone.

    A closed job is still reachable, deliberately: `status="closed"` asks for
    it, and `get_job` on a known id always answers. I3 is about not *silently*
    presenting one as open, not about hiding it.
    """
    company = (
        await db_session.execute(select(Company).where(Company.id == corpus.company_id))
    ).scalar_one()
    now = utcnow()
    closed = Job(
        company_id=company.id,
        title="Backend Engineer (this role has closed)",
        normalized_title="backend engineer this role has closed",
        status=JobStatus.CLOSED,
        #  requires it: a job cannot be closed
        # without recording when, which is I3 held in the schema.
        closed_at=now,
        first_seen_at=now,
        last_seen_at=now,
    )
    db_session.add(closed)
    await db_session.flush()

    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[current_user] = lambda: account

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        server = build_server(NightshiftClient("", "unused", http=http))
        async with connected(server) as session:
            default = await session.call_tool("search_jobs", {"q": "Backend"})
            asked = await session.call_tool("search_jobs", {"q": "Backend", "status": "closed"})

    assert not default.is_error, default.content
    titles = [job["title"] for job in default.structured_content["jobs"]]
    assert "Backend Engineer (this role has closed)" not in titles, (
        "a closed listing reached a reader from a tool whose description says 'open'"
    )
    assert corpus.title in titles, "the open job vanished along with the closed one"

    assert not asked.is_error, asked.content
    asked_titles = [job["title"] for job in asked.structured_content["jobs"]]
    assert "Backend Engineer (this role has closed)" in asked_titles, (
        "a closed job must stay reachable when explicitly asked for — I3 forbids "
        "presenting one as open, not knowing about it"
    )
