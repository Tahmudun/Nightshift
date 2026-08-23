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


async def test_the_internship_proposal_reaches_the_response(client: AsyncClient) -> None:
    """The detection existed, was unit-tested, and reached nobody.

    `propose()` has read "Intern" out of a title since the first commit, and
    `test_capture.py` asserts it does. The route returned a hardcoded `None`
    anyway, so the form opened on "Not stated" for every internship — a green
    unit test sitting on top of a feature no person could see.

    This asserts at the boundary the bug actually lived on. Internships are
    most of what this product is for, so defaulting them to "Not stated" is
    not a cosmetic miss.
    """
    body = await _paste(client, "Software Engineer Intern, Summer 2027\nRamp · New York, NY")
    assert body["proposed"]["employment_type"] == "internship"

    ordinary = await _paste(client, "Staff Backend Engineer\nRamp · New York, NY")
    assert ordinary["proposed"]["employment_type"] is None


async def test_an_assistants_quote_is_stored_apart_from_the_parsers(
    client: AsyncClient,
) -> None:
    """Both readings survive the round trip, and they are told apart (M5d).

    The parser reads line 2 as the employer. The assistant is asked for the
    same field and quotes it. They agree here, and the response still says
    which one said what — because the case that matters is the one where they
    do not, and a shape that only distinguishes them on disagreement is a shape
    that decided the answer before the reader did.
    """
    response = await client.post(
        "/capture",
        json={
            "raw_text": LINKEDIN_PASTE,
            "source_url": "https://www.linkedin.com/jobs/view/4012345678/",
            "assistant": {
                "title": "Staff Backend Engineer",
                "company_name": "Ramp",
                "location_text": "New York, NY",
            },
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["assistant"] == {
        "title": "Staff Backend Engineer",
        "company_name": "Ramp",
        "location_text": "New York, NY",
    }
    assert body["assistant_rejected_fields"] == []
    assert body["proposed"]["company_name"] == "Ramp"
    assert body["job_id"] is None


async def test_a_company_the_text_never_mentions_is_refused_and_named(
    client: AsyncClient,
) -> None:
    """The failure this whole feature is gated against.

    A model that answers "Stripe" about a Ramp posting gets nothing stored and
    the reader is told the quote did not match. The capture still succeeds:
    a refused field is the rule working, not a broken request, and turning it
    into a 4xx would make the model retry the paste rather than the quote.
    """
    response = await client.post(
        "/capture",
        json={
            "raw_text": LINKEDIN_PASTE,
            "assistant": {"title": "Staff Backend Engineer", "company_name": "Stripe"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["assistant"]["company_name"] is None
    assert body["assistant"]["title"] == "Staff Backend Engineer"
    assert body["assistant_rejected_fields"] == ["company_name"]
    # The parser is untouched by the assistant's mistake. Two readers, two
    # records, and one being wrong does not corrupt the other.
    assert body["proposed"]["company_name"] == "Ramp"


async def test_a_paste_with_no_assistant_reports_none_rather_than_nulls(
    client: AsyncClient,
) -> None:
    """The web form's own paste, unchanged from M5a.

    ``null`` rather than an object of nulls, so a client can tell "no assistant
    was involved" from "the assistant quoted nothing that survived" — only the
    second is worth putting in front of a reader.
    """
    body = await _paste(client)
    assert body["assistant"] is None
    assert body["assistant_rejected_fields"] == []


async def test_pasting_the_same_posting_twice_returns_the_same_proposal(
    client: AsyncClient,
) -> None:
    """One posting, one thing to review (M5d, ADR 0039 §3).

    **This narrows a position M5c stated.** `test_mcp_capture.py` argued that
    two captures of one posting are two honest records of a person pasting, and
    checked only that they do not become two jobs. That is right about the
    corpus and wrong about the queue: a review queue is a to-do list, and two
    identical to-do items is a defect in one. A model that is unsure whether
    its last call went through will call again, which is what makes this
    common rather than theoretical.

    The trailing whitespace on the second paste is deliberate — re-copying a
    page rarely produces byte-identical text.
    """
    body = {"raw_text": LINKEDIN_PASTE}
    first = await client.post("/capture", json=body)
    second = await client.post("/capture", json={"raw_text": LINKEDIN_PASTE + "\n\n  "})

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["already_existed"] is True
    assert first.json()["already_existed"] is False

    listed = await client.get("/capture", params={"status": "pending"})
    assert listed.json()["total"] == 1


async def test_a_different_posting_is_a_different_proposal(client: AsyncClient) -> None:
    first = await client.post("/capture", json={"raw_text": LINKEDIN_PASTE})
    second = await client.post(
        "/capture", json={"raw_text": LINKEDIN_PASTE.replace("Ramp", "Datadog")}
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first.json()["id"]


async def test_a_decided_capture_does_not_absorb_a_later_paste(client: AsyncClient) -> None:
    """Idempotence covers the pending queue only, and stops at a decision.

    Once a person has confirmed or discarded, the row is a record of what they
    decided. Folding a fresh paste into it would rewrite that record, and it
    would leave a reader who deliberately re-captured something with nothing to
    review. The corpus check (§4) is what tells them the re-capture is
    redundant; silence would not.
    """
    first = await client.post("/capture", json={"raw_text": LINKEDIN_PASTE})
    discarded = await client.post(f"/capture/{first.json()['id']}/discard")
    assert discarded.status_code == 200, discarded.text

    again = await client.post("/capture", json={"raw_text": LINKEDIN_PASTE})
    assert again.status_code == 201, again.text
    assert again.json()["id"] != first.json()["id"]


async def test_two_people_pasting_the_same_posting_get_their_own_proposals(
    client: AsyncClient, db_session: AsyncSession, other_user: User
) -> None:
    """The fingerprint is scoped to a person, and that is not an optimisation.

    A shared proposal id would hand one reader a row belonging to another and
    let them confirm or discard it — the isolation M5b exists to enforce,
    broken by a deduplication shortcut.
    """
    from nightshift.domain.capture import capture_paste

    mine = await client.post("/capture", json={"raw_text": LINKEDIN_PASTE})
    theirs = await capture_paste(
        db_session, user_id=other_user.id, raw_text=LINKEDIN_PASTE, source_url=None
    )

    assert theirs.created is True
    assert theirs.capture.id != uuid.UUID(mine.json()["id"])


async def test_reading_a_capture_back_carries_the_corpus_check(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4 has to hold for the reader, not only for the paste (M5d).

    A capture made through the MCP server is read for the first time by ``GET
    /capture/{id}`` — the person deciding never saw the paste response, because
    it went to their Claude. Answering without the duplicate check would leave
    ADR 0039 §4 protecting only whoever typed the text into the browser, which
    is the rarer half of this milestone.

    **Sabotage:** drop ``corpus_check=await _corpus_for(session, capture)`` from
    ``get_capture``. Fails with ``assert None is not None``.
    """
    from nightshift.adapters.greenhouse import normalize_title
    from nightshift.db.base import JobStatus
    from nightshift.db.types import utcnow
    from nightshift.domain.ingestion import get_or_create_company

    company = await get_or_create_company(db_session, "Ramp")
    now = utcnow()
    db_session.add(
        Job(
            company_id=company.id,
            title="Staff Backend Engineer",
            normalized_title=normalize_title("Staff Backend Engineer"),
            first_seen_at=now,
            last_seen_at=now,
            status=JobStatus.OPEN,
        )
    )
    await db_session.flush()

    pasted = await _paste(client)
    assert pasted["corpus_check"]["matches"], "the paste itself should have found it"

    read_back = await client.get(f"/capture/{pasted['id']}")
    assert read_back.status_code == 200, read_back.text
    check = read_back.json()["corpus_check"]
    assert check is not None
    assert [match["title"] for match in check["matches"]] == ["Staff Backend Engineer"]
    assert check["checked"] is True


async def test_a_decided_capture_is_read_back_without_a_corpus_check(
    client: AsyncClient,
) -> None:
    """The question is closed once somebody has answered it.

    A confirmed capture *is* a job in the corpus, so a check run against it
    would find the job it just created and report the reader's own decision
    back to them as a duplicate.

    **Sabotage:** delete the ``status is not PENDING`` guard in ``_corpus_for``.
    Fails with the confirmed capture's own job in ``matches``.
    """
    pasted = await _paste(client)
    confirmed = await client.post(
        f"/capture/{pasted['id']}/confirm",
        json={
            "title": "Staff Backend Engineer",
            "company_name": "Ramp",
            "location_text": "New York, NY",
            "employment_type": "full_time",
        },
    )
    assert confirmed.status_code == 200, confirmed.text

    read_back = await client.get(f"/capture/{pasted['id']}")
    assert read_back.json()["corpus_check"] is None
