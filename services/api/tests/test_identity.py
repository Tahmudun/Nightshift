"""Passwords, sessions, and the front door. M5b, ADR 0037.

`test_two_users_cannot_see_each_other.py` proves the *property* the milestone
is judged on. This module tests the machinery underneath it, where a wrong
answer is quiet: a hash that verifies anything, an expired session that still
resolves, a sign-out that does not sign out.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.api.deps import SESSION_COOKIE, current_user, session_token
from nightshift.api.main import create_app
from nightshift.db.models import User, UserCredential, UserSession
from nightshift.db.session import get_db_session
from nightshift.db.types import utcnow
from nightshift.domain.identity import (
    MIN_PASSWORD_LENGTH,
    authenticate,
    create_session,
    hash_password,
    hash_token,
    normalize_email,
    resolve_session,
    revoke_session,
    set_password,
    verify_password,
)
from tests.conftest import requires_db

pytestmark = [requires_db]
_async = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "a-password-long-enough"


class _FakeRequest:
    """The two attributes `session_token` reads, and nothing else.

    A real `Request` needs an ASGI scope to construct. Standing one up here
    would test Starlette's parsing rather than ours, and the point of these
    assertions is which of the two places a token may come from wins.
    """

    def __init__(self, cookies: dict[str, str], headers: dict[str, str]) -> None:
        self.cookies = cookies
        self.headers = headers


@pytest_asyncio.fixture(loop_scope="session")
async def user(db_session: AsyncSession) -> User:
    row = User(email=f"{uuid.uuid4()}@example.test", display_name="Test User")
    db_session.add(row)
    await db_session.flush()
    await set_password(db_session, row.id, PASSWORD)
    return row


@pytest_asyncio.fixture(loop_scope="session")
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


# -- hashing ----------------------------------------------------------------


def test_a_password_verifies_only_against_itself() -> None:
    secret = hash_password(PASSWORD)
    assert verify_password(secret, PASSWORD)
    assert not verify_password(secret, PASSWORD + "!")
    assert not verify_password(secret, "")


def test_two_hashes_of_one_password_differ() -> None:
    """Salting, asserted rather than assumed.

    Two identical passwords hashing to the same string would mean a stolen
    table shows which accounts share a password, which is most of what an
    attacker wants from one.
    """
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_a_short_password_is_refused_where_it_is_written() -> None:
    with pytest.raises(ValueError, match=str(MIN_PASSWORD_LENGTH)):
        hash_password("x" * (MIN_PASSWORD_LENGTH - 1))


def test_a_malformed_secret_matches_nothing() -> None:
    """A broken credential row must read as "no match", never as "match".

    argon2 raises `InvalidHashError` rather than returning False for a secret
    it cannot parse. An implementation that let that propagate would 500; one
    that caught the wrong exception set could let it through.
    """
    assert not verify_password("not-an-argon2-hash", PASSWORD)
    assert not verify_password("", PASSWORD)


def test_a_token_hash_is_deterministic_and_specific() -> None:
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")
    assert len(hash_token("abc")) == 64


def test_email_normalisation_is_case_and_space_only() -> None:
    assert normalize_email("  Person@Example.TEST ") == "person@example.test"
    # Deliberately *not* folded: that is one provider's rule, and applying it
    # would merge two addresses a person considers distinct.
    assert normalize_email("a.b+tag@gmail.com") == "a.b+tag@gmail.com"


# -- sessions ---------------------------------------------------------------


@_async
async def test_a_session_resolves_to_the_person_it_was_minted_for(
    db_session: AsyncSession, user: User
) -> None:
    issued = await create_session(db_session, user.id)
    resolved = await resolve_session(db_session, issued.token)
    assert resolved is not None
    assert resolved.id == user.id


@_async
async def test_the_plaintext_token_is_never_stored(db_session: AsyncSession, user: User) -> None:
    """The row must hold the hash and not the token. ADR 0037's whole point."""
    issued = await create_session(db_session, user.id)
    row = (
        await db_session.execute(select(UserSession).where(UserSession.id == issued.session_id))
    ).scalar_one()
    assert row.token_hash != issued.token
    assert row.token_hash == hash_token(issued.token)


@_async
async def test_an_unknown_token_resolves_to_nobody(db_session: AsyncSession) -> None:
    assert await resolve_session(db_session, "a token nobody issued") is None


@_async
async def test_an_expired_session_resolves_to_nobody(db_session: AsyncSession, user: User) -> None:
    issued = await create_session(db_session, user.id, lifetime=timedelta(minutes=5))
    later = utcnow() + timedelta(minutes=6)
    assert await resolve_session(db_session, issued.token, now=later) is None


@_async
async def test_a_session_expiring_exactly_now_resolves_to_nobody(
    db_session: AsyncSession, user: User
) -> None:
    """The boundary, because `<` and `<=` are one character apart.

    A session whose expiry has arrived is over. Written as a test because the
    off-by-one here is silent in both directions and reviewable in neither.
    """
    issued = await create_session(db_session, user.id, lifetime=timedelta(minutes=5))
    assert await resolve_session(db_session, issued.token, now=issued.expires_at) is None


@_async
async def test_a_revoked_session_resolves_to_nobody(db_session: AsyncSession, user: User) -> None:
    issued = await create_session(db_session, user.id)
    assert await revoke_session(db_session, issued.token) is True
    assert await resolve_session(db_session, issued.token) is None


@_async
async def test_revoking_twice_is_not_an_error(db_session: AsyncSession, user: User) -> None:
    issued = await create_session(db_session, user.id)
    assert await revoke_session(db_session, issued.token) is True
    assert await revoke_session(db_session, issued.token) is False


@_async
async def test_revoking_one_session_leaves_the_others_alone(
    db_session: AsyncSession, user: User
) -> None:
    """Signing out of one browser must not sign out of the other."""
    first = await create_session(db_session, user.id)
    second = await create_session(db_session, user.id)
    await revoke_session(db_session, first.token)
    assert await resolve_session(db_session, first.token) is None
    assert await resolve_session(db_session, second.token) is not None


# -- credentials ------------------------------------------------------------


@_async
async def test_authenticate_accepts_the_right_password(
    db_session: AsyncSession, user: User
) -> None:
    found = await authenticate(db_session, user.email, PASSWORD)
    assert found is not None and found.id == user.id


@_async
async def test_authenticate_refuses_a_wrong_password(db_session: AsyncSession, user: User) -> None:
    assert await authenticate(db_session, user.email, "not the password") is None


@_async
async def test_authenticate_refuses_an_unknown_address(db_session: AsyncSession) -> None:
    assert await authenticate(db_session, "nobody@example.test", PASSWORD) is None


@_async
async def test_authenticate_is_case_insensitive_on_the_address(
    db_session: AsyncSession, user: User
) -> None:
    found = await authenticate(db_session, user.email.upper(), PASSWORD)
    assert found is not None and found.id == user.id


@_async
async def test_an_account_with_no_credential_cannot_be_signed_into(
    db_session: AsyncSession,
) -> None:
    """A `users` row on its own is not an account anybody can use.

    `make seed` and the CLI both set a password; nothing else creates a user.
    But a row inserted by a migration or by hand must not be reachable, and the
    join in `authenticate` is what makes that true rather than a convention.
    """
    row = User(email=f"{uuid.uuid4()}@example.test")
    db_session.add(row)
    await db_session.flush()
    assert await authenticate(db_session, row.email, PASSWORD) is None


@_async
async def test_setting_a_password_twice_replaces_it(db_session: AsyncSession, user: User) -> None:
    await set_password(db_session, user.id, "a-different-password")

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(UserCredential)
            .where(UserCredential.user_id == user.id)
        )
    ).scalar_one()
    assert count == 1, "a password change must replace the credential, not add one"

    assert await authenticate(db_session, user.email, "a-different-password") is not None
    assert await authenticate(db_session, user.email, PASSWORD) is None


# -- the dependency, and the fallback that must not exist -------------------


@_async
async def test_the_identity_dependency_has_no_fallback(db_session: AsyncSession) -> None:
    """No session means 401. Not the dev user, not anonymous, not a default.

    Until M5b this dependency returned `settings.dev_user_id` for every
    request. If that behaviour were ever restored — by a flag, an environment
    check, or a well-meant "make local development easier" — every route in the
    application would serve one person's data to anybody at once. This asserts
    the dependency raises, which no configuration can turn into a user.
    """

    with pytest.raises(HTTPException) as raised:
        await current_user(_FakeRequest({}, {}), db_session)  # type: ignore[arg-type]
    assert raised.value.status_code == 401


@_async
async def test_a_garbage_token_is_401_and_not_a_500(db_session: AsyncSession) -> None:
    request = _FakeRequest({SESSION_COOKIE: "%%not-a-token%%"}, {})
    with pytest.raises(HTTPException) as raised:
        await current_user(request, db_session)  # type: ignore[arg-type]
    assert raised.value.status_code == 401


def test_the_token_is_read_from_a_cookie_or_a_bearer_header() -> None:
    def read(cookies: dict[str, str], headers: dict[str, str]) -> str | None:
        return session_token(_FakeRequest(cookies, headers))  # type: ignore[arg-type]

    assert read({SESSION_COOKIE: "from-cookie"}, {}) == "from-cookie"
    assert read({}, {"Authorization": "Bearer from-header"}) == "from-header"
    assert read({}, {"Authorization": "bearer lowercase"}) == "lowercase"
    # A cookie wins, so a browser's own identity is the one that acts in its tab.
    assert read({SESSION_COOKIE: "cookie"}, {"Authorization": "Bearer header"}) == "cookie"
    # Neither, and the malformed near-misses.
    assert read({}, {}) is None
    assert read({}, {"Authorization": "Bearer "}) is None
    assert read({}, {"Authorization": "Basic abc"}) is None


# -- the routes -------------------------------------------------------------


@_async
async def test_signing_in_sets_an_httponly_cookie(client: AsyncClient, user: User) -> None:
    response = await client.post("/auth/sign-in", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text

    raw = response.headers["set-cookie"]
    assert SESSION_COOKIE in raw
    assert "HttpOnly" in raw, "script on the page must not be able to read a login"
    assert "SameSite=lax" in raw.replace("samesite", "SameSite")

    assert response.json()["email"] == user.email
    assert "token" not in response.text, "the token belongs in the cookie, not the body"


@_async
async def test_a_signed_in_cookie_reaches_a_protected_route(
    client: AsyncClient, user: User
) -> None:
    await client.post("/auth/sign-in", json={"email": user.email, "password": PASSWORD})
    assert (await client.get("/auth/me")).status_code == 200
    assert (await client.get("/profile")).status_code == 200


@_async
async def test_a_wrong_password_and_an_unknown_address_answer_identically(
    client: AsyncClient, user: User
) -> None:
    """Sign-in must not be usable to ask whether somebody has an account."""
    wrong = await client.post(
        "/auth/sign-in", json={"email": user.email, "password": "not the password"}
    )
    unknown = await client.post(
        "/auth/sign-in", json={"email": "nobody@example.test", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@_async
async def test_a_bearer_token_reaches_a_protected_route(client: AsyncClient, user: User) -> None:
    """The path `scripts/verify.py` and M5c's MCP server take."""
    issued = await client.post("/auth/token", json={"email": user.email, "password": PASSWORD})
    assert issued.status_code == 200, issued.text
    token = issued.json()["access_token"]
    assert issued.json()["token_type"] == "bearer"

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == user.email


@_async
async def test_signing_out_ends_the_session_it_was_holding(client: AsyncClient, user: User) -> None:
    await client.post("/auth/sign-in", json={"email": user.email, "password": PASSWORD})
    assert (await client.get("/auth/me")).status_code == 200

    assert (await client.post("/auth/sign-out")).status_code == 204
    assert (await client.get("/auth/me")).status_code == 401


@_async
async def test_signing_out_without_a_session_still_succeeds(client: AsyncClient) -> None:
    """A 401 here would leave a browser stuck holding a cookie it cannot shed."""
    assert (await client.post("/auth/sign-out")).status_code == 204


@_async
async def test_anonymous_health_still_answers(client: AsyncClient) -> None:
    """`/health` reports on a database that may be down; a session would stop it."""
    response = await client.get("/health/live")
    assert response.status_code != 401
    assert response.status_code < 400
