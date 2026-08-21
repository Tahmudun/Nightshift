"""MCP tokens are sessions with a name. M5c, task 1.

The design decision under test is the one in the plan's §1: an MCP token and a
browser session are **the same thing** — a proven identity with a lifetime —
and so they live in one table behind one resolver. The alternative considered
and rejected was a second `user_api_tokens` table, which would have meant two
identity-resolution paths in the milestone right after M5b spent itself getting
that number down to one.

So the property these tests hold is not "MCP tokens work". It is
**``resolve_session`` is still the only function that answers "who is this"**,
and `origin` is a label on the answer rather than a second way to reach it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import SessionOrigin
from nightshift.db.models import User, UserSession
from nightshift.domain.identity import (
    MCP_TOKEN_LIFETIME,
    SESSION_LIFETIME,
    create_session,
    resolve_session,
    revoke_session,
)
from tests.conftest import requires_db

pytestmark = [requires_db]
_async = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def user(db_session: AsyncSession) -> AsyncIterator[User]:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="Token Holder")
    db_session.add(row)
    await db_session.flush()
    yield row


@_async
async def test_an_mcp_token_resolves_through_the_one_resolver(
    db_session: AsyncSession, user: User
) -> None:
    """The whole design in one assertion.

    If this ever needs a second function to pass, the second identity path the
    plan rejected has been built anyway.
    """
    issued = await create_session(
        db_session,
        user.id,
        lifetime=MCP_TOKEN_LIFETIME,
        origin=SessionOrigin.MCP,
        label="claude desktop",
    )
    await db_session.flush()

    resolved = await resolve_session(db_session, issued.token)

    assert resolved is not None
    assert resolved.id == user.id


@_async
async def test_origin_and_label_round_trip(db_session: AsyncSession, user: User) -> None:
    issued = await create_session(
        db_session,
        user.id,
        lifetime=MCP_TOKEN_LIFETIME,
        origin=SessionOrigin.MCP,
        label="claude desktop — laptop",
    )
    await db_session.flush()

    row = (
        await db_session.execute(select(UserSession).where(UserSession.id == issued.session_id))
    ).scalar_one()

    assert row.origin is SessionOrigin.MCP
    assert row.label == "claude desktop — laptop"


@_async
async def test_a_browser_session_is_still_a_browser_session(
    db_session: AsyncSession, user: User
) -> None:
    """The default is not `mcp`, and sign-in did not have to learn a new word.

    `auth.py` calls `create_session` with no `origin`. If the default were
    anything else, every browser login in the product would be mislabelled and
    the revocation list would be a lie.
    """
    issued = await create_session(db_session, user.id)
    await db_session.flush()

    row = (
        await db_session.execute(select(UserSession).where(UserSession.id == issued.session_id))
    ).scalar_one()

    assert row.origin is SessionOrigin.BROWSER
    assert row.label is None


@_async
async def test_an_mcp_token_outlives_a_browser_session(
    db_session: AsyncSession, user: User
) -> None:
    """Not a round number for its own sake.

    Thirty days is right for "stay signed in" and wrong for a config file: a
    token that expires quarterly is a feature somebody stops using. The
    assertion is the *relationship*, so tuning either constant keeps it true.
    """
    assert MCP_TOKEN_LIFETIME > SESSION_LIFETIME

    browser = await create_session(db_session, user.id)
    mcp = await create_session(
        db_session, user.id, lifetime=MCP_TOKEN_LIFETIME, origin=SessionOrigin.MCP
    )
    await db_session.flush()

    assert mcp.expires_at > browser.expires_at


@_async
async def test_revoking_one_origin_leaves_the_other_signed_in(
    db_session: AsyncSession, user: User
) -> None:
    """Sharing a table must not mean sharing a fate.

    Revoking a laptop's MCP token is not signing out of the website, and
    signing out of the website is not unplugging Claude Desktop.
    """
    browser = await create_session(db_session, user.id)
    mcp = await create_session(
        db_session,
        user.id,
        lifetime=MCP_TOKEN_LIFETIME,
        origin=SessionOrigin.MCP,
        label="claude desktop",
    )
    await db_session.flush()

    await revoke_session(db_session, mcp.token)
    await db_session.flush()

    assert await resolve_session(db_session, mcp.token) is None
    assert await resolve_session(db_session, browser.token) is not None
