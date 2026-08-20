"""Capture routes against a real database and a real ASGI app.

The rule this module exists to hold is the two-step. A capture endpoint that
parsed and committed in one request would make the parser's reading
indistinguishable from a person's decision, and that difference is what decides
whether a job lands on the right building.

The second rule is scoping, and it is here rather than waiting for M5b because
the table is user-owned from its first migration (A3) and a test written now
cannot be forgotten later.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.models import Job, User
from nightshift.db.session import get_db_session
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

LINKEDIN_PASTE = """Staff Backend Engineer
Ramp · New York, NY (Hybrid)

About the job
Build payment infrastructure. Python and Postgres.
"""


@pytest_asyncio.fixture(loop_scope="session")
async def user(db_session: AsyncSession) -> User:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="Test User")
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture(loop_scope="session")
async def other_user(db_session: AsyncSession) -> User:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="Somebody Else")
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


async def _paste(client: AsyncClient, text: str = LINKEDIN_PASTE) -> dict[str, Any]:
    response = await client.post("/capture", json={"raw_text": text})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_a_paste_returns_a_proposal_and_creates_no_job(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The two-step, at the level a client can see it."""
    body = await _paste(client)

    assert body["status"] == "pending"
    assert body["job_id"] is None
    assert body["proposed"]["title"] == "Staff Backend Engineer"
    assert body["proposed"]["company_name"] == "Ramp"
    assert body["proposed"]["location_text"] == "New York, NY (Hybrid)"
    assert (await db_session.execute(select(func.count()).select_from(Job))).scalar_one() == 0


async def test_a_proposal_is_null_rather_than_guessed(client: AsyncClient) -> None:
    """A10, and the one place it decides more than a UI label.

    Text the parser cannot read must arrive as `null`, not as a best effort.
    A client renders null as an empty box and a person types two words; a
    client renders a guess and a job lands on somebody else's building.
    """
    body = await _paste(client, "Multiple Locations")
    assert body["proposed"]["company_name"] is None
    assert body["proposed"]["location_text"] is None


async def test_an_empty_paste_is_refused(client: AsyncClient) -> None:
    response = await client.post("/capture", json={"raw_text": ""})
    assert response.status_code == 422


async def test_confirming_creates_the_job(client: AsyncClient, db_session: AsyncSession) -> None:
    capture = await _paste(client)
    response = await client.post(
        f"/capture/{capture['id']}/confirm",
        json={
            "title": "Staff Backend Engineer",
            "company_name": "Ramp",
            "location_text": "New York, NY",
            "employment_type": "full_time",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "confirmed"
    assert body["job_id"] is not None
    assert body["decided_at"] is not None
    job = (
        await db_session.execute(select(Job).where(Job.id == uuid.UUID(body["job_id"])))
    ).scalar_one()
    assert job.title == "Staff Backend Engineer"


async def test_the_person_may_correct_the_parser(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The confirmed values win, and the proposal is kept beside them.

    This is the whole reason the two are separate columns: after a correction
    the job is right *and* the bad parse is still diagnosable.
    """
    capture = await _paste(client)
    response = await client.post(
        f"/capture/{capture['id']}/confirm",
        json={
            "title": "Staff Backend Engineer",
            # The parser read "Ramp" and it was wrong — this is a different
            # employer, and it must not inherit Ramp's confirmed office.
            "company_name": "Actually A Different Company",
            "location_text": "Brooklyn",
            "employment_type": "full_time",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["proposed"]["company_name"] == "Ramp"
    job = (
        await db_session.execute(select(Job).where(Job.id == uuid.UUID(body["job_id"])))
    ).scalar_one()
    await db_session.refresh(job, ["company"])
    assert job.company.canonical_name == "Actually A Different Company"


async def test_discarding_creates_nothing(client: AsyncClient, db_session: AsyncSession) -> None:
    capture = await _paste(client)
    response = await client.post(f"/capture/{capture['id']}/discard")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "discarded"
    assert response.json()["job_id"] is None
    assert (await db_session.execute(select(func.count()).select_from(Job))).scalar_one() == 0


async def test_a_second_decision_is_a_409(client: AsyncClient) -> None:
    capture = await _paste(client)
    fields = {
        "title": "Staff Backend Engineer",
        "company_name": "Ramp",
        "location_text": "New York, NY",
        "employment_type": "full_time",
    }
    assert (await client.post(f"/capture/{capture['id']}/confirm", json=fields)).status_code == 200

    again = await client.post(f"/capture/{capture['id']}/confirm", json=fields)
    assert again.status_code == 409
    assert "already confirmed" in again.json()["detail"]

    discarded = await client.post(f"/capture/{capture['id']}/discard")
    assert discarded.status_code == 409


async def test_an_unknown_capture_is_a_404_that_says_so(client: AsyncClient) -> None:
    """The detail is asserted, not only the code.

    A 404 is also what an *unregistered router* returns, so a bare status
    assertion here would pass whether or not these routes exist — the trap
    `test_application_routes.py` recorded after measuring it.
    """
    response = await client.get(f"/capture/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "capture not found"


async def test_one_person_cannot_see_or_decide_anothers_capture(
    client: AsyncClient, db_session: AsyncSession, other_user: User
) -> None:
    """M5b's central guarantee, written now because the column exists now.

    Scoped in the query rather than fetched-then-checked, so somebody else's
    capture is indistinguishable from one that never existed — a 403 would
    confirm the id is real.
    """
    from nightshift.domain.capture import create_capture

    theirs = await create_capture(
        db_session, user_id=other_user.id, raw_text=LINKEDIN_PASTE, source_url=None
    )
    await db_session.flush()

    assert (await client.get(f"/capture/{theirs.id}")).status_code == 404
    assert (await client.post(f"/capture/{theirs.id}/discard")).status_code == 404
    confirm = await client.post(
        f"/capture/{theirs.id}/confirm",
        json={"title": "X", "company_name": "Y", "employment_type": "full_time"},
    )
    assert confirm.status_code == 404

    # And it is untouched: the 404 was a refusal, not a silent no-op on a row
    # that then got decided anyway.
    await db_session.refresh(theirs)
    assert theirs.status.value == "pending"

    # It is also absent from this user's list, which is the read path the
    # refusals above do not cover.
    listed = await client.get("/capture")
    assert response_ids(listed.json()) == []


def response_ids(body: dict[str, Any]) -> list[str]:
    return [row["id"] for row in body["captures"]]


async def test_the_list_is_scoped_and_filterable(client: AsyncClient) -> None:
    first = await _paste(client)
    second = await _paste(client, "Data Engineer\nAcme · Remote\n\nBody text here.")
    await client.post(f"/capture/{second['id']}/discard")

    everything = await client.get("/capture")
    assert everything.json()["total"] == 2

    pending = await client.get("/capture", params={"status": "pending"})
    assert response_ids(pending.json()) == [first["id"]]
    assert pending.json()["total"] == 1
