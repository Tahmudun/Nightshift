"""Request-scoped dependencies.

``current_user_id`` is the single place the codebase learns who is acting.
AMENDMENTS A3 deferred auth to M5 and this is what made that a one-file change:
every route already filters on whatever it returns, so M5b replaced the body of
one function rather than sweeping the schema.

**It raises rather than falls back.** Until M5b it returned the seeded dev user
for every request; now an unauthenticated request gets a 401 and there is no
setting, no environment and no code path that restores the old behaviour. A
fallback here would make an anonymous request act as a person, silently, on
every route in the application at once — which is the worst bug this milestone
could ship, and the reason `test_identity_has_no_fallback` exists.

The decision itself is ADR 0037.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.models import User
from nightshift.db.session import get_db_session
from nightshift.domain.identity import resolve_session

#: The browser's copy of the session token. Set httpOnly, so script on the page
#: cannot read it and an XSS cannot walk off with a login.
SESSION_COOKIE = "nightshift_session"

#: `WWW-Authenticate` names the scheme a client should retry with. The cookie is
#: how a browser actually carries the token, but a bearer token is the form a
#: non-browser client — `scripts/verify.py`, and M5c's MCP server — can use.
_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="not signed in",
    headers={"WWW-Authenticate": "Bearer"},
)


def session_token(request: Request) -> str | None:
    """The session token this request carries, from either place it may live.

    Cookie first, then ``Authorization: Bearer``. Order matters only when both
    are present, which happens when a signed-in browser session also sends an
    explicit header; preferring the cookie makes the browser's own identity the
    one that wins in its own tab.
    """
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        return cookie

    header = request.headers.get("Authorization", "")
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()
    return None


async def current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    """The signed-in user, or a 401. Never anything else."""
    token = session_token(request)
    if token is None:
        raise _UNAUTHENTICATED

    user = await resolve_session(db, token)
    if user is None:
        raise _UNAUTHENTICATED

    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def current_user_id(user: CurrentUser) -> UUID:
    return user.id


CurrentUserId = Annotated[UUID, Depends(current_user_id)]


async def require_session(user_id: CurrentUserId) -> None:
    """Router-level default-deny. Attached in ``main.py``, not per route.

    It depends on ``CurrentUserId`` rather than on ``CurrentUser``, and that is
    a correctness choice rather than a convenience. Those are two entry points
    into the same question, and anything that replaces one — a test override, a
    future impersonation path — leaves the other reading the real request. The
    first draft did exactly that: 145 route tests overrode `current_user_id`,
    the router guard went on resolving a session that was not there, and every
    one of them 401ed. Worse than the failure is the shape it implies, where a
    handler can believe it is serving A while the guard believes nobody is
    signed in. One seam, so the two cannot disagree.

    Before M5b a route was protected because its handler happened to declare
    ``CurrentUserId``; a handler that forgot was open, and nothing said so.
    PROGRESS named the risk in as many words — *"routes filter by convention
    today, and one missed filter leaks another person's applications."*

    This inverts it. A route added in M5c, M8 or M13 is behind a session
    because it exists, and opening one is a deliberate edit to `main.py` that
    shows up in a diff. The two routers not behind it are `/health`, which has
    to answer while the database is down, and `/auth`, which is how a person
    gets a session in the first place.
    """
    return None
