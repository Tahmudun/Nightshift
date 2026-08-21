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
