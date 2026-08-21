"""Capture through MCP creates a proposal, and there is no way to confirm one.

This is the milestone's I5 test and it is the one worth reading twice.

**The argument for a confirm tool is not stupid.** Claude Desktop shows the
reader an approval dialog before every tool call, so a human *did* approve.
It is still wrong, and the difference is the whole of M5a: approving "call
`confirm_capture`" is not reviewing a parsed job title, a company name and a
location string. `capture.py` recorded what is at stake —

    a one-shot endpoint that parses and commits in the same request […] makes
    the parser's reading indistinguishable from a person's decision, at exactly
    the point where the difference decides whether a job lands on the right
    building.

— and an MCP confirm tool is that endpoint with an extra process in the middle.

So the tests below assert over the **registered tool list** rather than over
the tools that exist today. A future milestone adding `confirm_capture` trips
them before it can be wired to anything.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mcp.server import MCPServer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user
from nightshift.api.main import create_app
from nightshift.db.base import CaptureStatus
from nightshift.db.models import CapturedPosting, Job, User
from nightshift.db.session import get_db_session
from nightshift.mcp.client import NightshiftClient
from nightshift.mcp.server import build_server
from tests.conftest import requires_db
from tests.test_mcp_server import connected

pytestmark = [requires_db]
_async = pytest.mark.asyncio(loop_scope="session")

LINKEDIN_PASTE = """Staff Backend Engineer
Ramp · New York, NY (Hybrid)

About the job
Build payment infrastructure. Python and Postgres.
"""


@pytest_asyncio.fixture(loop_scope="session")
async def account(db_session: AsyncSession) -> AsyncIterator[User]:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="MCP Reader")
    db_session.add(row)
    await db_session.flush()
    yield row


@pytest_asyncio.fixture(loop_scope="session")
async def server(db_session: AsyncSession, account: User) -> AsyncIterator[MCPServer]:
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[current_user] = lambda: account

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield build_server(NightshiftClient("", "unused", http=http))


# --------------------------------------------------------------------------
# The tool that does not exist
# --------------------------------------------------------------------------


@_async
async def test_no_tool_can_confirm_or_approve_anything(server: MCPServer) -> None:
    """Asserted over the tool list, so a future addition trips it.

    Naming the check "there is no `confirm_capture`" would pass while somebody
    added `approve_capture`, `accept_posting` or `capture_and_confirm`. The
    substring set is broader than today's vocabulary on purpose.
    """
    async with connected(server) as session:
        listed = await session.list_tools()

    forbidden = [
        tool.name
        for tool in listed.tools
        if any(word in tool.name.lower() for word in ("confirm", "approve", "accept", "commit"))
    ]
    assert forbidden == [], (
        f"a tool that decides on a reader's behalf was registered: {forbidden}. "
        "See ADR 0038 §4 — approving a tool call is not reviewing a parsed title."
    )


@_async
async def test_no_tool_can_change_an_application_stage_or_apply(server: MCPServer) -> None:
    """I5's other half. Suggest, surface, confirm — never act."""
    async with connected(server) as session:
        listed = await session.list_tools()

    forbidden = [
        tool.name
        for tool in listed.tools
        if any(word in tool.name.lower() for word in ("apply", "advance", "stage", "archive"))
    ]
    assert forbidden == [], f"a tool that takes an irreversible action was registered: {forbidden}"


# --------------------------------------------------------------------------
# What capture actually does
# --------------------------------------------------------------------------


@_async
async def test_capturing_creates_a_pending_proposal_and_no_job(
    server: MCPServer, db_session: AsyncSession
) -> None:
    """The two-step, held at the surface that could most easily route around it."""
    jobs_before = (await db_session.execute(select(func.count()).select_from(Job))).scalar_one()

    async with connected(server) as session:
        result = await session.call_tool("capture_posting", {"raw_text": LINKEDIN_PASTE})

    assert not result.is_error, result.content
    assert result.structured_content is not None
    assert result.structured_content["status"] == CaptureStatus.PENDING.value

    row = (
        await db_session.execute(
            select(CapturedPosting).where(
                CapturedPosting.id == uuid.UUID(result.structured_content["capture_id"])
            )
        )
    ).scalar_one()
    assert row.status is CaptureStatus.PENDING
    assert row.job_id is None, "a capture through MCP must not produce a job"

    jobs_after = (await db_session.execute(select(func.count()).select_from(Job))).scalar_one()
    assert jobs_after == jobs_before, "capturing created a canonical job without a person"


@_async
async def test_the_result_tells_the_model_that_nothing_was_added(server: MCPServer) -> None:
    """The wording is the enforcement, so the wording is tested.

    A model reporting a successful write will say "I've added that job" unless
    the result says otherwise — and that sentence is false in three separate
    ways. This is the only place that can be corrected.
    """
    async with connected(server) as session:
        result = await session.call_tool("capture_posting", {"raw_text": LINKEDIN_PASTE})

    assert result.structured_content is not None
    happened = result.structured_content["what_just_happened"]
    assert "NOT in Nightshift's job corpus" in happened
    assert "NOT on the map" in happened
    assert "/operate/capture" in result.structured_content["review_url"]


@_async
async def test_a_field_the_parser_declined_is_named_rather_than_left_blank(
    server: MCPServer,
) -> None:
    """`null` means the parser declined, and a reader has to be told which.

    `CaptureProposalOut` makes every field nullable precisely so a client
    cannot render a guess. A model seeing a blank will otherwise either invent
    a value or report a bug, and both are worse than "it could not read this".
    """
    async with connected(server) as session:
        result = await session.call_tool(
            "capture_posting", {"raw_text": "A posting with no useful structure at all."}
        )

    assert result.structured_content is not None
    assert result.structured_content["could_not_read"], (
        "nothing was parseable from that text, so the tool must say which fields it declined"
    )


@_async
async def test_capturing_the_same_posting_twice_creates_no_duplicate(
    server: MCPServer, db_session: AsyncSession
) -> None:
    """M5's acceptance names this in as many words.

    Two captures of one posting are two *records of a person pasting*, which is
    honest — but they must not become two jobs, and neither is confirmed here,
    so the corpus count is the thing that must not move.
    """
    jobs_before = (await db_session.execute(select(func.count()).select_from(Job))).scalar_one()

    async with connected(server) as session:
        first = await session.call_tool("capture_posting", {"raw_text": LINKEDIN_PASTE})
        second = await session.call_tool("capture_posting", {"raw_text": LINKEDIN_PASTE})

    assert not first.is_error and not second.is_error
    jobs_after = (await db_session.execute(select(func.count()).select_from(Job))).scalar_one()
    assert jobs_after == jobs_before
