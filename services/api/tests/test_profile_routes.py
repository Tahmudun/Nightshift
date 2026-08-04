"""Profile and resume routes against a real database and a real ASGI app.

The `client` fixture follows `test_application_routes.py`: it overrides both
`get_db_session` (so the app sees this test's uncommitted rows) and
`current_user_id` (so the app acts as a user this test created).

The invariant under test throughout is I2. Every assertion about the profile
after a paste is really the same assertion: **reading a resume changed nothing
about this person.** Only a decision does.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user_id
from nightshift.api.main import create_app
from nightshift.api.routes.applications import DEFERRED_FIELDS
from nightshift.db.base import JobStatus
from nightshift.db.models import Company, Job, User
from nightshift.db.session import get_db_session
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
FIXTURES = Path(__file__).parent / "fixtures" / "resumes"
RESUME_TEXT = (FIXTURES / "nadia_okonkwo.txt").read_text(encoding="utf-8")
PROSE_TEXT = (FIXTURES / "prose_only.txt").read_text(encoding="utf-8")


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


async def _paste(client: AsyncClient, text: str = RESUME_TEXT) -> dict[str, Any]:
    response = await client.post("/resumes/paste", json={"name": "my resume", "text": text})
    assert response.status_code in (200, 201), response.text
    return response.json()  # type: ignore[no-any-return]


def _skill_proposals(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in detail["extractions"] if row["kind"] == "skill"]


async def test_the_profile_starts_empty_and_says_what_is_not_confirmed(
    client: AsyncClient,
) -> None:
    response = await client.get("/profile")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["graduation_year"] is None
    assert body["graduation_month"] is None
    assert body["degree"] is None
    assert body["school"] is None
    assert body["work_authorization"] == "unspecified"
    assert body["skills"] == []
    assert body["projects"] == []
    # I7: what this slice does not do is named on the page, not hidden.
    assert body["deferred_fields"], "the profile must name what it cannot infer"
    assert all({"name", "blocked_on", "reason"} <= set(row) for row in body["deferred_fields"])


async def test_pasting_a_resume_returns_proposals_and_confirms_nothing(
    client: AsyncClient,
) -> None:
    detail = await _paste(client)

    assert detail["extractions"], "the fixture resume proves several things"
    assert all(row["status"] == "pending" for row in detail["extractions"])
    assert all(row["char_end"] > row["char_start"] for row in detail["extractions"])
    assert detail["nothing_proven"] is False

    # The whole point: the resume said "Bachelor of Science, May 2027" and the
    # profile still says nothing.
    profile = (await client.get("/profile")).json()
    assert profile["degree"] is None
    assert profile["graduation_year"] is None
    assert profile["skills"] == []
    assert profile["projects"] == []


async def test_every_proposal_in_the_response_quotes_the_parsed_text(
    client: AsyncClient,
) -> None:
    """The API's own copy of the trigger's promise.

    The database refuses a row whose span does not quote the text. This asserts
    the same thing at the boundary the browser reads, so a serialisation bug
    that shifts an offset by one is caught where it would be seen.
    """
    detail = await _paste(client)
    text = detail["parsed_text"]

    for row in detail["extractions"]:
        assert text[row["char_start"] : row["char_end"]] == row["quoted_text"], (
            f"{row['kind']} proposal quotes {row['quoted_text']!r} but its span "
            f"covers {text[row['char_start'] : row['char_end']]!r}"
        )


async def test_uploading_a_pdf_returns_the_same_facts_as_pasting_it(
    client: AsyncClient,
) -> None:
    """Not the same spans — a PDF has no line-wrap fidelity to promise. The
    same *facts*, which is what a person is being asked to confirm."""
    response = await client.post(
        "/resumes/upload",
        files={
            "file": (
                "nadia_okonkwo.pdf",
                (FIXTURES / "nadia_okonkwo.pdf").read_bytes(),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()
    assert uploaded["source_kind"] == "pdf"
    assert uploaded["original_filename"] == "nadia_okonkwo.pdf"

    pasted = await _paste(client)

    def facts(detail: dict[str, Any]) -> list[tuple[str, str]]:
        return sorted(
            (row["kind"], repr(sorted(row["value"].items()))) for row in detail["extractions"]
        )

    assert facts(uploaded) == facts(pasted)


async def test_uploading_a_docx_is_refused_with_a_message_naming_the_format(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/resumes/upload",
        files={"file": ("resume.docx", b"PK\x03\x04 not really a docx", "application/octet")},
    )
    assert response.status_code == 415, response.text
    assert ".docx" in response.json()["detail"]


async def test_uploading_a_scan_is_refused_and_offers_paste(client: AsyncClient) -> None:
    """422, not 500: the file is the problem and the message says how to get
    past it. §6.2 — failure is stated, never filled."""
    response = await client.post(
        "/resumes/upload",
        files={
            "file": (
                "scan.pdf",
                (FIXTURES / "no_text_scan.pdf").read_bytes(),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 422, response.text
    assert "paste" in response.json()["detail"].lower()


async def test_confirming_promotes_only_what_was_confirmed(client: AsyncClient) -> None:
    detail = await _paste(client)
    skills = _skill_proposals(detail)
    assert len(skills) >= 2

    confirmed, rejected = skills[0], skills[1]
    response = await client.post(
        f"/resumes/{detail['id']}/confirm",
        json={
            "decisions": [
                {"extraction_id": confirmed["id"], "decision": "confirm"},
                {"extraction_id": rejected["id"], "decision": "reject"},
            ]
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["confirmed"] == 1
    assert result["rejected"] == 1
    assert result["skills_added"] == 1

    profile = (await client.get("/profile")).json()
    assert [row["name"] for row in profile["skills"]] == [confirmed["value"]["name"]]

    # And the proposals now carry the decision, so the screen can show it.
    after = (await client.get(f"/resumes/{detail['id']}")).json()
    by_id = {row["id"]: row["status"] for row in after["extractions"]}
    assert by_id[confirmed["id"]] == "confirmed"
    assert by_id[rejected["id"]] == "rejected"


async def test_confirming_an_unknown_extraction_is_404_and_promotes_nothing(
    client: AsyncClient,
) -> None:
    detail = await _paste(client)
    real = _skill_proposals(detail)[0]

    response = await client.post(
        f"/resumes/{detail['id']}/confirm",
        json={
            "decisions": [
                {"extraction_id": real["id"], "decision": "confirm"},
                {"extraction_id": str(uuid.uuid4()), "decision": "confirm"},
            ]
        },
    )
    assert response.status_code == 404, response.text

    # Nothing partial: the real decision in the same request did not land.
    profile = (await client.get("/profile")).json()
    assert profile["skills"] == []


async def test_a_resume_that_proves_nothing_says_so(client: AsyncClient) -> None:
    """I7: an extraction that proves nothing states it and hands over the
    manual form. It never fills a field to look successful."""
    detail = await _paste(client, PROSE_TEXT)
    assert detail["extractions"] == []
    assert detail["nothing_proven"] is True

    profile = (await client.get("/profile")).json()
    assert profile["skills"] == []


async def test_deleting_a_resume_keeps_the_skills_it_produced(client: AsyncClient) -> None:
    """A confirmed fact belongs to the person, not to the file it arrived in."""
    detail = await _paste(client)
    skill = _skill_proposals(detail)[0]
    await client.post(
        f"/resumes/{detail['id']}/confirm",
        json={"decisions": [{"extraction_id": skill["id"], "decision": "confirm"}]},
    )

    deleted = await client.delete(f"/resumes/{detail['id']}")
    assert deleted.status_code == 204, deleted.text
    assert (await client.get(f"/resumes/{detail['id']}")).status_code == 404
    assert (await client.get("/resumes")).json()["items"] == []

    profile = (await client.get("/profile")).json()
    assert [row["name"] for row in profile["skills"]] == [skill["value"]["name"]]


async def test_an_application_can_select_a_resume(client: AsyncClient, job: Job) -> None:
    detail = await _paste(client)
    saved = await client.post("/applications", json={"job_id": str(job.id)})
    assert saved.status_code in (200, 201), saved.text
    application_id = saved.json()["id"]

    response = await client.patch(
        f"/applications/{application_id}", json={"selected_resume_id": detail["id"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["selected_resume_id"] == detail["id"]

    # It is a detail change like any other, so it has history.
    events = [event["event_type"] for event in response.json()["events"]]
    assert "detail_updated" in events


async def test_another_users_resume_cannot_be_selected(
    client: AsyncClient, db_session: AsyncSession, job: Job
) -> None:
    """A3: the foreign key permits it, so the route has to refuse it.

    Without this check a guessed UUID attaches somebody else's resume to this
    person's application, and every later read of that application leaks it.
    """
    stranger = User(email=f"{uuid.uuid4()}@example.test")
    db_session.add(stranger)
    await db_session.flush()

    from nightshift.db.base import ResumeSourceKind
    from nightshift.domain.profile import create_resume

    theirs, _ = await create_resume(
        db_session,
        user_id=stranger.id,
        name="not yours",
        source_kind=ResumeSourceKind.PASTE,
        original_filename=None,
        text=RESUME_TEXT,
    )

    saved = await client.post("/applications", json={"job_id": str(job.id)})
    application_id = saved.json()["id"]
    response = await client.patch(
        f"/applications/{application_id}", json={"selected_resume_id": str(theirs.id)}
    )
    assert response.status_code == 404, response.text


async def test_the_deferred_list_no_longer_names_the_resume(client: AsyncClient) -> None:
    """The feature shipped, so the UI must stop claiming it is missing."""
    assert all("resume" not in field.name.lower() for field in DEFERRED_FIELDS)

    listed = (await client.get("/applications")).json()
    assert all("resume" not in row["name"].lower() for row in listed["deferred_fields"])
