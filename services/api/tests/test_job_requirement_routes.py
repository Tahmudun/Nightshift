"""The route, and the property the page depends on.

The extraction *rules* are tested in `test_requirement_extraction.py` and graded
in `test_requirement_extraction_against_the_answer_key.py`. This file tests the
boundary: that the rows reach the response at all, that the response is
internally consistent about its own spans, and that a posting nobody has read is
distinguishable from one that asks for nothing.

Each file under tests/ defines its own `client` fixture rather than sharing one,
because the override covers `current_user_id` as well as the session so the
suite does not depend on `make seed` having run. Pattern copied from
`tests/test_queue_routes.py`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.models import Job, User
from nightshift.db.session import get_db_session
from nightshift.domain.ingestion import sync_requirements
from nightshift.domain.requirement_extraction import EXTRACTOR_VERSION
from tests.conftest import make_job_with_text, requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

#: Two headings and two necessities, so "grouped by necessity" is a real claim
#: rather than one satisfied by a single row.
_TEXT = (
    "About the role. You will build things.\n"
    "REQUIREMENTS\n"
    "Proficiency in Python and 3+ years of experience.\n"
    "NICE TO HAVES\n"
    "Exposure to Kubernetes.\n"
)


@pytest_asyncio.fixture(loop_scope="session")
async def user(db_session: AsyncSession) -> User:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="Test User")
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession, user: User) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _user() -> uuid.UUID:
        return user.id

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[current_user_id] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def job_with_requirements(db_session: AsyncSession) -> Job:
    job = await make_job_with_text(db_session, _TEXT)
    assert await sync_requirements(db_session, job) > 0
    await db_session.flush()
    return job


@pytest_asyncio.fixture(loop_scope="session")
async def job_without_description(db_session: AsyncSession) -> Job:
    return await make_job_with_text(db_session, None)


async def test_job_detail_returns_requirements_grouped_by_necessity(
    client: AsyncClient, job_with_requirements: Job
) -> None:
    response = await client.get(f"/jobs/{job_with_requirements.id}")
    assert response.status_code == 200
    body = response.json()
    necessities = {r["necessity"] for r in body["requirements"]}
    assert "required" in necessities
    assert "preferred" in necessities


async def test_every_returned_span_quotes_the_returned_description(
    client: AsyncClient, job_with_requirements: Job
) -> None:
    """Re-asserted at the API boundary, not only in the database.

    The trigger guarantees the row is honest about the text in `jobs`. This
    guarantees the *response* is internally consistent, which is what the
    browser highlights against — a one-character shift in serialisation turns
    this red and nothing else would.
    """
    body = (await client.get(f"/jobs/{job_with_requirements.id}")).json()
    text = body["description_text"]
    assert body["requirements"]
    for requirement in body["requirements"]:
        start, end = requirement["char_start"], requirement["char_end"]
        assert text[start:end] == requirement["raw_text"], requirement


async def test_requirements_come_back_in_document_order(
    client: AsyncClient, job_with_requirements: Job
) -> None:
    """The page reads top to bottom against the description it is highlighting.

    Row order out of Postgres is not a guarantee, so this is the route's job.
    """
    body = (await client.get(f"/jobs/{job_with_requirements.id}")).json()
    starts = [r["char_start"] for r in body["requirements"]]
    assert starts == sorted(starts)


async def test_the_response_names_the_rules_that_produced_the_rows(
    client: AsyncClient, job_with_requirements: Job
) -> None:
    """I4's habit applied early: a claim carries the version that made it."""
    body = (await client.get(f"/jobs/{job_with_requirements.id}")).json()
    assert body["requirements_extractor_version"] == EXTRACTOR_VERSION


async def test_a_job_with_no_description_returns_an_empty_list_not_null(
    client: AsyncClient, job_without_description: Job
) -> None:
    body = (await client.get(f"/jobs/{job_without_description.id}")).json()
    assert body["requirements"] == []


async def test_nothing_extracted_is_not_reported_as_nothing_required(
    client: AsyncClient, job_without_description: Job
) -> None:
    """A posting that asks for nothing and one nobody has read are not the same.

    An empty list plus a null version is the second. The page renders those
    two states differently, and it can only do that if the response
    distinguishes them.
    """
    body = (await client.get(f"/jobs/{job_without_description.id}")).json()
    assert body["requirements_extractor_version"] is None
