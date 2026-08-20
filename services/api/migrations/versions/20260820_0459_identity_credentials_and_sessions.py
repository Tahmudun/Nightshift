"""Who somebody is, and the proof they are still that person.

Revision ID: 0024_identity
Revises: 0023_captured_postings
Create Date: 2026-08-20 04:59:59.462558+00:00


M5b / ADR 0037. AMENDMENTS A3 deferred authentication to this milestone and
promised the bill would be small — *"an adapter plus a middleware, not a
migration of every table in the schema"*. This is that bill. Every user-owned
table has carried a real `user_id` since its own first migration, so nothing
below alters an existing table: identity arrives as two new ones.

**`users` does not gain a `password_hash` column, and that is the decision.**
Sign-in is expected to change, so a credential is a row keyed by method rather
than a column on the account. Adding Google later is an INSERT and a new enum
value; it is not an `ALTER TABLE users`, and it does not make a person who
signs in two ways into two people.

**`user_sessions` stores a hash, not a token.** A database dump is then a list
of expiry times rather than a set of live logins. The hash is SHA-256 while a
password's is argon2id, and the asymmetry is deliberate: a password is short
and human-chosen, so slowness is the defence; a session token is 256 bits from
a CSPRNG, so there is no dictionary to slow down and argon2 on every
authenticated request would cost a page load and buy nothing.

Sessions are rows rather than signed tokens because a JWT cannot be revoked,
and both "sign out" and account deletion have to actually end a session rather
than wait for one to lapse. `revoked_at` stamps rather than deletes, so
"this ended deliberately" stays distinguishable from "this was never here" —
the same distinction invariant I3 draws for a listing that stopped appearing.

Following `0023_captured_postings`: the downgrade drops `credential_method`
explicitly. `create_type=True` makes it on the way up and nothing removes it on
the way down, and a type left behind makes the *next* upgrade fail with
"type credential_method already exists" — the defect `0020` recorded, `0023`
avoided, and this one does not get to repeat.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import nightshift.db.types

revision: str = "0024_identity"
down_revision: str | None = "0023_captured_postings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("method", sa.Enum("password", name="credential_method"), nullable=False),
        sa.Column("secret", sa.String(length=255), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(secret) >= 16", name=op.f("ck_user_credentials_credential_secret_is_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_credentials")),
        sa.UniqueConstraint("user_id", "method", name="uq_user_credentials_user_id_method"),
    )
    op.create_index(
        op.f("ix_user_credentials_user_id"), "user_credentials", ["user_id"], unique=False
    )
    op.create_table(
        "user_sessions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", nightshift.db.types.UTCDateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", nightshift.db.types.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_user_sessions_session_expires_after_it_began")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False)
    op.create_index(
        "ix_user_sessions_user_id_expires_at",
        "user_sessions",
        ["user_id", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_user_id_expires_at", table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index(op.f("ix_user_credentials_user_id"), table_name="user_credentials")
    op.drop_table("user_credentials")
    # See the module docstring: the table is gone but its type is not.
    op.execute("DROP TYPE IF EXISTS credential_method")
