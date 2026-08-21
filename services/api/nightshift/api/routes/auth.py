"""Signing in, signing out, and asking who you are.

ADR 0037. This is the only router in the application not behind
``require_session``, for the obvious reason: it is how a request stops being
anonymous. `/health` is the other, because it has to answer while the database
is down.

Routes validate and delegate (CLAUDE.md §3). Every rule about hashing, expiry
and revocation lives in `nightshift.domain.identity`.

**There is no ``POST /auth/register``, and its absence is a decision rather
than an omission.** Registration is closed: accounts are made by
``nightshift users create``. Invite-only and then open sign-up are the stated
next two steps, and both are additive — a token table and a form. A registration
endpoint built now and left disabled would be a half-built feature sitting on
the one surface where half-built is least acceptable.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import SESSION_COOKIE, CurrentUser, session_token
from nightshift.api.schemas import IdentityOut, SessionOut, SignInIn, TokenOut
from nightshift.config import Settings, get_settings
from nightshift.db.session import get_db_session
from nightshift.db.types import utcnow
from nightshift.domain.identity import (
    IssuedSession,
    authenticate,
    create_session,
    revoke_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])

#: One message for every way sign-in can fail — no such address, no password
#: credential, wrong password. Distinguishing them turns this endpoint into a
#: way to ask whether somebody has an account here, which is a fact about a
#: person that this system has no business confirming to a stranger.
_REJECTED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="that email and password do not match an account",
)


def _lifetime(settings: Settings) -> timedelta:
    """How long a session issued right now should last.

    `Settings.session_lifetime_days` is the authority and both routes read it
    through here, so "how long is a sign-in" has one answer rather than one per
    endpoint. `identity.SESSION_LIFETIME` stays the domain's own default, for
    callers with no `Settings` to hand.
    """
    return timedelta(days=settings.session_lifetime_days)


def _set_cookie(response: Response, issued: IssuedSession, settings: Settings) -> None:
    """Put the session token where a browser will carry it and script will not.

    ``httponly`` is the one that matters: it is what stops an XSS on any page
    of this application from reading a login and posting it elsewhere.

    ``secure`` is set for ``production`` **only**, and the negative case is the
    one worth stating: a `Secure` cookie is not stored by a browser talking
    plain HTTP, so setting it in `test` would silently sign out CI — the seeded
    Playwright suite runs against `http://localhost:3000`, and the failure
    would read as "every page is signed out" rather than as a cookie flag.
    Chrome happens to make an exception for `localhost`; relying on one
    browser's exception to keep CI green is not a policy.

    ``samesite=lax`` is correct **because the browser reaches the API through
    the web app's own origin** — the Next.js rewrite added in M5b.2. Were it
    cross-site, this cookie would simply never be sent, which is the trap that
    decided the proxy.

    ``max_age`` is computed from the session that was actually minted, not from
    the setting a second time. The M5b review found those were two independent
    sources of truth for one fact: the cookie read `session_lifetime_days` and
    the row read `identity.SESSION_LIFETIME`, related by a comment saying they
    mirror each other and by nothing else. Setting the value to 7 produced a
    cookie the browser dropped after a week naming a session the server kept
    for thirty days. Deriving one from the other is what makes them agree by
    construction rather than by anybody remembering to.
    """
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        httponly=True,
        secure=settings.nightshift_env == "production",
        samesite="lax",
        max_age=max(0, int((issued.expires_at - utcnow()).total_seconds())),
        path="/",
    )


@router.post("/sign-in", response_model=SessionOut)
async def sign_in(
    payload: SignInIn,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SessionOut:
    """Exchange an email and a password for a session cookie."""
    user = await authenticate(db, payload.email, payload.password)
    if user is None:
        raise _REJECTED

    issued = await create_session(db, user.id, lifetime=_lifetime(settings))
    # `get_db_session` commits nothing — read paths get a plain session and
    # write routes commit explicitly, so a handler's body says whether it
    # writes. Signing in writes. Without this the token goes back to the
    # client and the row it names is rolled back when the request ends: a
    # 200 carrying a credential that was never real.
    await db.commit()
    _set_cookie(response, issued, settings)
    return SessionOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        expires_at=issued.expires_at,
    )


@router.post("/token", response_model=TokenOut)
async def issue_token(
    payload: SignInIn,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenOut:
    """The same exchange, for a client that has no cookie jar.

    `scripts/verify.py` and M5c's MCP server. The token goes in the body
    because that is the only place a non-browser can read it from; it is the
    same row in the same table, so revoking it and revoking a browser's session
    are one operation.
    """
    user = await authenticate(db, payload.email, payload.password)
    if user is None:
        raise _REJECTED

    issued = await create_session(db, user.id, lifetime=_lifetime(settings))
    await db.commit()  # See `sign_in`. A minted session that is not committed is a lie.
    return TokenOut(access_token=issued.token, expires_at=issued.expires_at)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """End this session and clear the cookie.

    Deliberately **not** behind a session. Signing out is idempotent and always
    succeeds: a 401 here would leave a browser holding a cookie it cannot get
    rid of, for a session that a moment ago it could not use anyway.
    """
    token = session_token(request)
    if token is not None:
        await revoke_session(db, token)
        # Revocation is a write. Uncommitted, "sign out" would clear the cookie
        # and leave the session usable by anybody holding the token.
        await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=IdentityOut)
async def read_me(user: CurrentUser) -> IdentityOut:
    """Who the caller is. A 401 when nobody.

    This is what the web app asks on load to decide between the application and
    the sign-in page, so it is the one route whose 401 is an ordinary answer
    rather than an error.

    `IdentityOut` and not `SessionOut`: this route knows the account, not the
    session row, and has no expiry to report. Reporting one anyway is what the
    first draft did, using `created_at`, which is a fabricated field.
    """
    return IdentityOut(id=user.id, email=user.email, display_name=user.display_name)
