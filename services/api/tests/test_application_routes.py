"""Application routes against a real database and a real ASGI app.

The `client` fixture overrides both `get_db_session` (so the app sees this
test's uncommitted rows) and `current_user_id` (so the app acts as a user this
test created). Without the second override every test would need the seeded
dev_user to exist, which makes the suite depend on `make seed` having run.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.db.base import JobStatus
from nightshift.db.models import Company, Job, User
from nightshift.db.session import get_db_session
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


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


async def _save(client: AsyncClient, job: Job) -> dict[str, Any]:
    response = await client.post("/applications", json={"job_id": str(job.id)})
    assert response.status_code in (200, 201), response.text
    return response.json()  # type: ignore[no-any-return]


async def test_saving_a_job_returns_201_then_200(client: AsyncClient, job: Job) -> None:
    """The status code is the only place "created" and "already there" differ."""
    first = await client.post("/applications", json={"job_id": str(job.id)})
    assert first.status_code == 201
    second = await client.post("/applications", json={"job_id": str(job.id)})
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


async def test_saving_an_unknown_job_is_a_404(client: AsyncClient) -> None:
    """Not a 500 from the foreign key, and not a silently created orphan.

    The detail is asserted, not just the code. A 404 is also what an
    unregistered router returns, so a bare status assertion here passes whether
    or not the route exists — measured: with the router commented out, 11 of
    these 12 tests fail and this was the one that did not.
    """
    response = await client.post("/applications", json={"job_id": str(uuid.uuid4())})
    assert response.status_code == 404
    assert response.json()["detail"] == "job not found"


async def test_the_saved_application_carries_its_job(client: AsyncClient, job: Job) -> None:
    """The list page renders titles without an N+1 back to /jobs."""
    body = await _save(client, job)
    assert body["job"]["title"] == "Software Engineer"
    assert body["job"]["company"]["canonical_name"] == "Example Inc."
    assert body["current_stage"] == "saved"


async def test_the_list_counts_by_stage_and_names_what_is_deferred(
    client: AsyncClient, job: Job
) -> None:
    await _save(client, job)
    body = (await client.get("/applications")).json()
    assert body["total"] == 1
    assert body["stage_counts"]["saved"] == 1
    assert body["stage_counts"]["offer"] == 0
    # I7: the fields tracking cannot yet record are named, not hidden.
    names = {entry["name"] for entry in body["deferred_fields"]}
    assert {"Selected resume", "Contacts"} <= names


async def test_archived_applications_are_excluded_by_default(client: AsyncClient, job: Job) -> None:
    saved = await _save(client, job)
    await client.post(f"/applications/{saved['id']}/archive")

    default = (await client.get("/applications")).json()
    assert default["total"] == 0
    assert default["archived_count"] == 1

    included = (await client.get("/applications?archived=true")).json()
    assert included["total"] == 1


async def test_a_stage_change_appears_in_the_history(client: AsyncClient, job: Job) -> None:
    saved = await _save(client, job)
    response = await client.patch(
        f"/applications/{saved['id']}/stage",
        json={
            "to_stage": "applied",
            "applied_at": (NOW + timedelta(hours=1)).isoformat(),
            "application_url": "https://boards.example.test/apply/1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_stage"] == "applied"
    assert body["application_url"] == "https://boards.example.test/apply/1"
    kinds = [event["event_type"] for event in body["events"]]
    assert kinds == ["saved", "stage_changed"]
    assert body["events"][-1]["transition_class"] == "correction"


async def test_setting_the_stage_it_is_already_at_is_refused(client: AsyncClient, job: Job) -> None:
    """A no-op would bury the real transitions under rows that say nothing."""
    saved = await _save(client, job)
    response = await client.patch(f"/applications/{saved['id']}/stage", json={"to_stage": "saved"})
    assert response.status_code == 409
    assert "already" in response.json()["detail"]


async def test_a_note_is_appended(client: AsyncClient, job: Job) -> None:
    saved = await _save(client, job)
    response = await client.post(
        f"/applications/{saved['id']}/notes", json={"body": "Referred by Sam"}
    )
    assert response.status_code == 201
    assert response.json()["body"] == "Referred by Sam"

    detail = (await client.get(f"/applications/{saved['id']}")).json()
    assert [e["event_type"] for e in detail["events"]] == ["saved", "note_added"]


async def test_an_empty_note_is_rejected(client: AsyncClient, job: Job) -> None:
    saved = await _save(client, job)
    response = await client.post(f"/applications/{saved['id']}/notes", json={"body": ""})
    assert response.status_code == 422


async def test_an_interview_is_recorded_at_its_own_time(client: AsyncClient, job: Job) -> None:
    saved = await _save(client, job)
    when = NOW + timedelta(days=5)
    response = await client.post(
        f"/applications/{saved['id']}/interviews", json={"scheduled_for": when.isoformat()}
    )
    assert response.status_code == 201
    assert response.json()["occurred_at"].startswith(when.date().isoformat())

    detail = (await client.get(f"/applications/{saved['id']}")).json()
    # I5 again: recording the interview did not move the stage for the user.
    assert detail["current_stage"] == "saved"


async def test_a_patch_can_clear_a_date(client: AsyncClient, job: Job) -> None:
    """Explicit null clears; an absent key leaves alone. See ApplicationPatchIn."""
    saved = await _save(client, job)
    await client.patch(f"/applications/{saved['id']}", json={"next_action_at": NOW.isoformat()})
    cleared = await client.patch(f"/applications/{saved['id']}", json={"next_action_at": None})
    assert cleared.json()["next_action_at"] is None

    untouched = await client.patch(f"/applications/{saved['id']}", json={"priority": "high"})
    assert untouched.json()["priority"] == "high"
    assert untouched.json()["next_action_at"] is None


async def test_another_users_application_is_a_404(
    client: AsyncClient, job: Job, db_session: AsyncSession
) -> None:
    """A3: every query filters on user_id even though there is one user today."""
    saved = await _save(client, job)
    other = User(email=f"{uuid.uuid4()}@example.test")
    db_session.add(other)
    await db_session.flush()

    from nightshift.api.deps import current_user_id as dependency

    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _other() -> uuid.UUID:
        return other.id

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[dependency] = _other
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as intruder:
        response = await intruder.get(f"/applications/{saved['id']}")
    assert response.status_code == 404
