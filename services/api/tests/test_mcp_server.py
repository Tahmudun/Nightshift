"""The MCP server, driven by a real MCP client, against the real FastAPI app.

Nothing here is mocked, and that is the point of the seam. `NightshiftClient`
takes an injectable `httpx.AsyncClient`, so the tests hand it an
``ASGITransport`` pointed at `create_app()` — a tool call then runs through the
real router, the real `require_session`, and the real `/auth/me` handler, with
no network and no port to start. A mocked client would be testing the mock
(`CLAUDE.md` §8), and a live port would make the suite depend on something
somebody started by hand.

The protocol half is equally real: `create_client_server_memory_streams` gives
a genuine `ClientSession` talking to a genuine server over in-memory pipes, so
`initialize`, `tools/list` and `tools/call` are exercised as Claude Desktop
exercises them.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

import anyio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mcp.client.session import ClientSession
from mcp.server import MCPServer
from mcp.shared.memory import create_client_server_memory_streams
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import current_user
from nightshift.api.main import create_app
from nightshift.db.models import User
from nightshift.db.session import get_db_session
from nightshift.mcp.client import NightshiftClient
from nightshift.mcp.server import build_server
from tests.conftest import requires_db

pytestmark = [requires_db]
_async = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def account(db_session: AsyncSession) -> AsyncIterator[User]:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="MCP Reader")
    db_session.add(row)
    await db_session.flush()
    yield row


@pytest_asyncio.fixture(loop_scope="session")
async def server(db_session: AsyncSession, account: User) -> AsyncIterator[MCPServer]:
    """The real server, over the real app, as the signed-in ``account``.

    ``current_user`` is overridden rather than a session being minted and a
    bearer token threaded through, because the token path is `test_identity.py`
    and `test_two_users_cannot_see_each_other.py`'s subject and is proven
    there. What these tests are about is the layer above it.

    The override is on `current_user` **and** `get_db_session`, and both are
    needed: `require_session` is attached at the router and resolves through
    `current_user_id`, which depends on `current_user` — overriding only the
    handler's dependency would leave the router guard resolving a session that
    is not there, and every call would 401. `deps.py` records that exact
    mistake from M5b.
    """
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db_session
    app.dependency_overrides[current_user] = lambda: account

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield build_server(NightshiftClient("", "unused-in-this-transport", http=http))


@asynccontextmanager
async def connected(server: MCPServer) -> AsyncIterator[ClientSession]:
    """An initialized `ClientSession` speaking to ``server`` over memory pipes.

    This is what `run_stdio_async` does with a pipe swapped in for the process's
    stdin and stdout — the same low-level server, the same initialization
    options, the same session on the other end.

    ``_lowlevel_server`` is private and reached here anyway, in exactly one
    place, because the SDK offers no public way to run a server over supplied
    streams. If a future version renames it these tests fail loudly at import
    of the attribute rather than passing while testing nothing, which is the
    acceptable version of this bargain.
    """
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams

        low = server._lowlevel_server
        async with anyio.create_task_group() as tg:
            tg.start_soon(
                partial(
                    low.run,
                    server_read,
                    server_write,
                    low.create_initialization_options(),
                    raise_exceptions=True,
                )
            )
            async with ClientSession(client_read, client_write) as session:
                await session.initialize()
                yield session
            tg.cancel_scope.cancel()


@_async
async def test_a_client_can_connect_and_list_tools(server: MCPServer) -> None:
    """The handshake, which is the first thing Claude Desktop does and the first
    thing that can be silently broken by a bad instructions string or a tool
    whose type hints do not produce a schema."""
    async with connected(server) as session:
        listed = await session.list_tools()

    names = {tool.name for tool in listed.tools}
    assert "whoami" in names


@_async
async def test_the_handshake_names_a_version(server: MCPServer) -> None:
    """Claude Desktop prints `serverInfo.version` beside the connector's name.

    The SDK defaults it to the empty string, so the first real Claude Desktop
    connection showed a nameless version — the kind of detail a person reads as
    "this is broken" before calling a single tool. Asserting non-empty rather
    than asserting `"0.1.0"`: the number moves, the promise that there is one
    does not.
    """
    async with connected(server) as session:
        info = session.server_info

    assert info is not None
    assert info.name == "nightshift"
    assert (info.version or "").strip(), "serverInfo.version is blank in the handshake"


@_async
async def test_every_tool_carries_a_description(server: MCPServer) -> None:
    """A description is not documentation here — see `nightshift/mcp/__init__.py`.

    It is how the model is told what a result licenses it to say, and it is
    also how the model chooses a tool at all. An undescribed tool is one Claude
    either never calls or calls wrongly, and neither failure raises anything.
    """
    async with connected(server) as session:
        listed = await session.list_tools()

    undescribed = [tool.name for tool in listed.tools if not (tool.description or "").strip()]
    assert undescribed == [], f"tools with no description: {undescribed}"


@_async
async def test_whoami_returns_the_account_the_connection_belongs_to(
    server: MCPServer, account: User
) -> None:
    """The whole path in one call: protocol, client, bearer header, router
    guard, handler. When the link is broken, this is the tool that says so."""
    async with connected(server) as session:
        result = await session.call_tool("whoami", {})

    assert not result.is_error, result.content
    assert result.structured_content is not None
    assert result.structured_content["email"] == account.email


#: What each tool is allowed to do to the reader's data, and every registered
#: tool must appear here exactly once.
#:
#: ``reads``
#:     Answers a question. Writes nothing.
#: ``proposes``
#:     Creates a row the reader must still act on. `capture_posting` is the
#:     only one, and what it creates is `pending`.
#:
#: **There is deliberately no third kind.** I5 says no irreversible action is
#: taken for the reader, and M5's fourth criterion turns on a captured posting
#: staying a proposal — so "decides" is not a category a tool may be filed
#: under. Adding one means editing this comment, which is an argument somebody
#: has to make in a diff rather than a parameter somebody forgets.
_TOOL_KINDS: dict[str, str] = {
    "whoami": "reads",
    "search_jobs": "reads",
    "get_job": "reads",
    "explain_match": "reads",
    "list_applications": "reads",
    "capture_posting": "proposes",
}


@_async
async def test_every_tool_is_classified_and_none_of_them_decides(server: MCPServer) -> None:
    """M5's *"no parsed fact is stored as confirmed without a user action"*,
    made structural on the surface most likely to erode it.

    The prose already says it — `capture_posting`'s own description tells the
    model *"You cannot confirm it yourself. There is no tool for that, and its
    absence is deliberate"*. Prose is not a guard. The failure this catches is
    a `confirm_capture` tool added in M8 by somebody who read the queue as a
    chore rather than as the consent step, and nothing in the suite noticing.

    Enumerated rather than spot-checked, for M5b's reason: a list of the tools
    that exist today proves nothing about the one added tomorrow. An unlisted
    tool fails here on the day it is registered.
    """
    async with connected(server) as session:
        listed = await session.list_tools()

    registered = {tool.name for tool in listed.tools}

    unclassified = registered - set(_TOOL_KINDS)
    assert not unclassified, (
        "these tools have no entry in `_TOOL_KINDS` — add one, and note that "
        "'decides' is not an available kind (I5): " + str(sorted(unclassified))
    )

    stale = set(_TOOL_KINDS) - registered
    assert not stale, f"`_TOOL_KINDS` names tools that no longer exist: {sorted(stale)}"

    assert sorted(name for name, kind in _TOOL_KINDS.items() if kind == "proposes") == [
        "capture_posting"
    ], "a second tool now writes on the reader's behalf; M5's consent step needs re-arguing"


@_async
async def test_the_capture_tool_tells_the_model_it_cannot_confirm(server: MCPServer) -> None:
    """The other half, and it is not redundant with the test above.

    A tool surface can be correct and still mislead: `capture_posting` could
    exist, write only `pending` rows, and be described in a way that lets a
    model announce *"I've added it to Nightshift"*. The reader would then
    believe a decision was made that was not. The description is the only place
    that misunderstanding can be prevented, so its content is asserted rather
    than assumed — it must say the reader decides, and it must say this tool
    cannot.
    """
    async with connected(server) as session:
        listed = await session.list_tools()

    capture = next(tool for tool in listed.tools if tool.name == "capture_posting")
    description = (capture.description or "").lower()

    assert "cannot confirm it yourself" in description
    assert "proposal" in description
