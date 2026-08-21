"""Passwords, sessions, and the one function that answers "who is this?".

ADR 0037. Everything about proving identity lives here; ``api/deps.py`` calls
into it and holds no logic of its own, so there is exactly one place to read
when the question is whether a request could be somebody else's.

Two rules this module exists to make structural rather than remembered:

* **A failure to authenticate returns ``None``, never a user.** Every function
  below that could plausibly "fall back to the dev user" instead returns
  ``None`` and lets the caller raise. There is no configuration, no
  environment, and no code path in which an unauthenticated request acts as a
  person — which is the single worst bug available in this milestone.
* **The plaintext password never leaves this module**, and the plaintext
  session token exists exactly once: at the moment it is minted, as the return
  value of :func:`create_session`. What reaches the database is a hash.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import CredentialMethod, SessionOrigin
from nightshift.db.models import User, UserCredential, UserSession
from nightshift.db.types import utcnow

#: Bytes of entropy in a session token, before hex encoding. 32 bytes is 256
#: bits — far past the point where guessing is the attack anybody would choose.
TOKEN_BYTES = 32

#: How long a session lives without being renewed. Thirty days is the ordinary
#: "stay signed in" span; a shorter one would sign a person out mid-week for no
#: security this product currently benefits from, and a longer one makes a
#: stolen token a longer-lived problem.
SESSION_LIFETIME = timedelta(days=30)

#: How long an MCP token lives. M5c.
#:
#: A year rather than thirty days, and the asymmetry is the point rather than a
#: relaxation. :data:`SESSION_LIFETIME` is tuned for a browser, where signing in
#: again costs a password field. This one is tuned for a file on disk that a
#: person edits once and forgets, where the cost of expiry is opening
#: `claude_desktop_config.json`, finding the CLI, and re-pasting — which is not
#: a cost anybody pays quarterly. They stop using the feature instead.
#:
#: What makes a year acceptable is that it is **revocable and named**. A stolen
#: browser session and a stolen MCP token are equally bad; the difference is
#: that `nightshift tokens --list` can show you the second one and let you end
#: it, which no expiry window provides.
MCP_TOKEN_LIFETIME = timedelta(days=365)

#: The shortest password this system will store. Deliberately a floor on length
#: and nothing else — no character-class rules, which NIST SP 800-63B stopped
#: recommending because they push people toward `Passw0rd!` and away from
#: length, which is the property that actually matters.
MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return the argon2id encoded hash of ``password``.

    Raises ``ValueError`` for a password below :data:`MIN_PASSWORD_LENGTH`, so
    the rule is enforced at the only place that can write one rather than at
    each of the callers that might.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters, got {len(password)}"
        )
    return _hasher.hash(password)


def verify_password(secret: str, password: str) -> bool:
    """``True`` if ``password`` produced ``secret``.

    Every argon2 failure mode collapses to ``False``. That includes
    ``InvalidHashError`` — a malformed row in ``user_credentials`` is a broken
    credential, and the safe reading of a credential nobody can parse is that
    it does not match, never that it does.
    """
    try:
        return _hasher.verify(secret, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    """SHA-256 of a session token, hex.

    Fast on purpose — see :class:`~nightshift.db.models.UserSession`. The input
    is 256 bits of CSPRNG output, so there is no dictionary to defend against
    and a slow hash would buy nothing while costing a request.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """A freshly minted session, and the only time the token is in memory."""

    token: str
    session_id: uuid.UUID
    expires_at: datetime


async def create_session(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    now: datetime | None = None,
    lifetime: timedelta = SESSION_LIFETIME,
    origin: SessionOrigin = SessionOrigin.BROWSER,
    label: str | None = None,
) -> IssuedSession:
    """Mint a session for ``user_id`` and return its plaintext token.

    The token is returned and not stored. The caller hands it to the client;
    nothing can recover it afterwards, which is the point.

    ``origin`` and ``label`` are M5c, and they are the whole of what an MCP
    token is: this function already took a ``lifetime``, so a credential for a
    config file needed a name and a kind and nothing else. **Neither is read by
    :func:`resolve_session`** — they describe the session, they do not
    authenticate it, and a future caller that branches on ``origin`` to decide
    whether somebody is signed in has built the second identity path M5c was
    designed to avoid.

    The default is ``BROWSER`` because sign-in must not have to learn a new
    word: `api/routes/auth.py` calls this with neither argument, and a
    different default would mislabel every login in the product.
    """
    moment = now or utcnow()
    token = secrets.token_urlsafe(TOKEN_BYTES)
    row = UserSession(
        user_id=user_id,
        token_hash=hash_token(token),
        expires_at=moment + lifetime,
        origin=origin,
        label=label,
    )
    session.add(row)
    await session.flush()
    return IssuedSession(token=token, session_id=row.id, expires_at=row.expires_at)


async def set_password(
    session: AsyncSession,
    user_id: uuid.UUID,
    password: str,
) -> UserCredential:
    """Give ``user_id`` a password, replacing any it already had.

    An upsert rather than an insert, because "change my password" and "set one
    for the first time" are the same operation against a table whose unique
    constraint is ``(user_id, method)``. Replacing the secret in place also
    means old sessions survive a password change — which is wrong for a
    compromised account and right for a person who simply chose a better one.
    Revoking on change is a deliberate follow-on, not an accident of this
    function; it needs a "sign out my other devices" affordance to sit behind,
    and there is nowhere to put one until the account page exists.
    """
    secret = hash_password(password)
    credential = (
        await session.execute(
            select(UserCredential).where(
                UserCredential.user_id == user_id,
                UserCredential.method == CredentialMethod.PASSWORD,
            )
        )
    ).scalar_one_or_none()

    if credential is None:
        credential = UserCredential(
            user_id=user_id, method=CredentialMethod.PASSWORD, secret=secret
        )
        session.add(credential)
        await session.flush()
    else:
        credential.secret = secret
    return credential


async def authenticate(
    session: AsyncSession,
    email: str,
    password: str,
    *,
    method: CredentialMethod = CredentialMethod.PASSWORD,
) -> User | None:
    """Return the user those credentials belong to, or ``None``.

    ``None`` for every failure — no such email, no credential of that method,
    wrong password — and deliberately without saying which. The caller turns
    all three into one message, so this endpoint cannot be used to ask whether
    an address has an account.

    The hash is verified even when no user was found, against a throwaway
    value. Skipping it would make "no such email" measurably faster than "wrong
    password" and hand back the same distinction the shared message withholds.
    """
    normalized = normalize_email(email)
    row = (
        await session.execute(
            select(User, UserCredential)
            .join(UserCredential, UserCredential.user_id == User.id)
            .where(User.email == normalized, UserCredential.method == method)
        )
    ).first()

    if row is None:
        _burn_a_verification()
        return None

    # Annotated because `.first()` on a two-entity select is `Row[Any]` to
    # mypy, and an unannotated unpack would silently make this function's
    # declared return type unenforced.
    user: User = row[0]
    credential: UserCredential = row[1]
    if not verify_password(credential.secret, password):
        return None
    return user


async def resolve_session(
    session: AsyncSession,
    token: str,
    *,
    now: datetime | None = None,
) -> User | None:
    """Return the signed-in user behind ``token``, or ``None``.

    ``None`` covers every reason a token might not name somebody: unknown,
    expired, revoked. The caller cannot tell them apart and does not need to —
    all three mean "sign in", and distinguishing them tells an attacker holding
    a stolen token whether it was once real.

    **This function writes nothing, and an earlier draft did.** It stamped a
    `last_seen_at` on every resolution, for a future "signed in on these
    devices" screen. `get_db_session` commits nothing on a read path by design,
    so that stamp was never persisted — and on any request that *did* commit
    for its own reasons, it would have been. A column written non-
    deterministically is worse than no column, so it is gone; M13 can add one
    with a write path that actually runs.
    """
    moment = now or utcnow()
    row = (
        await session.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(UserSession.token_hash == hash_token(token))
        )
    ).first()

    if row is None:
        return None

    user_session: UserSession = row[0]
    user: User = row[1]
    if user_session.revoked_at is not None:
        return None
    if user_session.expires_at <= moment:
        return None

    return user


async def revoke_session(
    session: AsyncSession,
    token: str,
    *,
    now: datetime | None = None,
) -> bool:
    """End the session ``token`` names. ``True`` if one was actually ended.

    Signing out twice is not an error and returns ``False`` the second time.
    The row is stamped rather than deleted, so "ended deliberately" stays
    distinguishable from "never existed" — the same distinction invariant I3
    draws for a listing.
    """
    moment = now or utcnow()
    user_session = (
        await session.execute(
            select(UserSession).where(UserSession.token_hash == hash_token(token))
        )
    ).scalar_one_or_none()

    if user_session is None or user_session.revoked_at is not None:
        return False

    user_session.revoked_at = moment
    return True


def normalize_email(email: str) -> str:
    """Trim and lower-case an address for storage and lookup.

    Only case and surrounding whitespace. Gmail's dot-and-plus folding is
    deliberately not applied: it is one provider's rule, it is not true of
    addresses generally, and applying it would silently merge two accounts a
    person considers distinct.
    """
    return email.strip().lower()


#: A real argon2id hash of a value nobody holds, used to keep a failed lookup
#: as slow as a failed password. Computed once at import rather than per call.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(TOKEN_BYTES))


def _burn_a_verification() -> None:
    """Spend the time a real verification would have spent. See `authenticate`."""
    try:
        _hasher.verify(_DUMMY_HASH, "not the password")
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        pass
