"""GET /queue — the shape the page depends on.

The queue's *rules* are tested in ``test_queue.py`` against the database. This
file tests the boundary: that the four sections always appear, that the four
deferred rows are named, and that the thresholds the page renders come from
the same constants the queries use.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.base import JobStatus
from nightshift.db.models import Company, Job, User
from nightshift.db.session import get_db_session
from nightshift.domain.queue import (
    FOLLOW_UP_SILENT_DAYS,
    INTERVIEW_HORIZON_DAYS,
    ROW_CAP,
    STALE_SAVED_DAYS,
    QueueSectionKey,
)
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture(loop_scope="session")
async def user(db_session: AsyncSession) -> User:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="Test User")
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture(loop_scope="session")
async def job(db_session: AsyncSession) -> Job:
    company = Company(canonical_name="Example Inc.", normalized_name=str(uuid.uuid4()))
    db_session.add(company)
    await db_session.flush()
    row = Job(
        company_id=company.id,
        title="Software Engineer",
        normalized_title="software engineer",
        status=JobStatus.OPEN,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession, user: User) -> AsyncIterator[AsyncClient]:
    """Overrides the session *and* the current user, so these tests act as a
    user they created rather than depending on the seeded ``dev_user``."""
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


async def test_the_queue_always_returns_four_sections(client: AsyncClient) -> None:
    """Even with nothing to do. The page renders "nothing today" from a
    well-formed answer, not from an empty body."""
    response = await client.get("/queue")
    assert response.status_code == 200
    body = response.json()
    assert [section["key"] for section in body["sections"]] == [
        key.value for key in QueueSectionKey
    ]


async def test_every_section_carries_a_human_title(client: AsyncClient) -> None:
    body = (await client.get("/queue")).json()
    for section in body["sections"]:
        assert section["title"].strip()
        assert section["title"] != section["key"]


async def test_every_deferred_row_is_named_with_a_reason(client: AsyncClient) -> None:
    """I7. What this page still cannot compute exists on it as a named absence."""
    body = (await client.get("/queue")).json()
    assert body["deferred_rows"]
    assert all(row["reason"].strip() and row["blocked_on"].strip() for row in body["deferred_rows"])


async def test_a_row_that_got_built_is_no_longer_deferred(client: AsyncClient) -> None:
    """M3d Task 7. A deferral is a claim with a date on it, and one left standing
    after its cause is gone is a false statement the page keeps making."""
    body = (await client.get("/queue")).json()
    deferred = {row["name"] for row in body["deferred_rows"]}
    built = {section["key"] for section in body["sections"]}
    assert not any("internship" in name.lower() for name in deferred)
    assert QueueSectionKey.BEST_NEW_INTERNSHIPS.value in built


async def test_no_deferred_row_shows_a_number(client: AsyncClient) -> None:
    """A deferred row with a count beside it reads as real. I4 and I7."""
    body = (await client.get("/queue")).json()
    for row in body["deferred_rows"]:
        assert not any(character.isdigit() for character in row["name"])


async def test_the_thresholds_are_the_constants_the_queries_use(client: AsyncClient) -> None:
    """The guard against the M2c defect: a number transcribed into TypeScript
    by hand and drifting silently from the one Python filters on."""
    thresholds = (await client.get("/queue")).json()["thresholds"]
    assert thresholds == {
        "follow_up_silent_days": FOLLOW_UP_SILENT_DAYS,
        "stale_saved_days": STALE_SAVED_DAYS,
        "interview_horizon_days": INTERVIEW_HORIZON_DAYS,
        "row_cap": ROW_CAP,
    }


async def test_the_queue_has_no_write_route(client: AsyncClient) -> None:
    """§7.3. The queue suggests; it does not act (I5). If a POST appears here
    later, this test is the conversation about whether it should."""
    for method in ("post", "patch", "put", "delete"):
        response = await getattr(client, method)("/queue")
        assert response.status_code == 405, method
