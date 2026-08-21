"""A session learns what kind of client is holding it, and what it is called.

Revision ID: 0025_session_origin
Revises: 0024_identity
Create Date: 2026-08-21 13:28:31.435550+00:00


M5c. The MCP server needs a credential a person can paste into a config file:
long-lived, revocable, and nameable. The decision this migration implements is
that **it is not a new table**.

`0024` built `user_sessions` and, with it, `resolve_session` — the single
function that answers "who is this". A `user_api_tokens` table would have made
that two, in the milestone immediately after the one that spent itself getting
it to one, and two answers to that question is how one of them ends up wrong.

The two things are the same thing. A session is a proven identity with a
lifetime; an MCP token is a proven identity with a longer lifetime and a name.
So this migration adds a label and a kind, not a table.

**`origin` arrives with a server default and that is load-bearing.** Every row
already in `user_sessions` is a browser sign-in, and a NOT NULL column added
without a default cannot land on a populated table. The default is also the
correct value for every one of them, so the backfill and the constraint are the
same statement.

**`label` is nullable because a browser sign-in has nothing to say.** It exists
for one reason: a revocation list somebody can aim. Ending one of four MCP
tokens by picking a UUID out of a column of UUIDs is how a person ends the
wrong one.

**The type is created and dropped by hand, and the first draft of this file
could not run.** Autogenerate emitted a bare `sa.Enum` inside `add_column`,
which produces the `ALTER TABLE` and *not* the `CREATE TYPE` before it —
`type "session_origin" does not exist`, immediately. `0023` and `0024` never
met this because `create_table` does emit it; **this is the first migration in
the project to add an enum column to a table that already exists**, and the
house pattern inherited from them did not cover the case.

The downgrade drops the type explicitly, which is the pattern those two *did*
establish: a type left behind makes the next upgrade fail with "already
exists" — the defect `0020` recorded, `0023` avoided, `0024` avoided, and this
one does not get to be the fourth time. CI's `migrations` job runs exactly that
cycle — up, down, up, and no drift — which is the gate both halves of this
answer to, and running it by hand is what caught the first draft.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_session_origin"
down_revision: str | None = "0024_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: Created and dropped by hand rather than left to the column.
#:
#: ``create_type=False`` is the half of this that is easy to get wrong. A bare
#: ``sa.Enum`` inside ``add_column`` emits the ``ALTER TABLE`` **without**
#: emitting the ``CREATE TYPE`` first — autogenerate wrote exactly that, and it
#: failed with *type "session_origin" does not exist*. `0024` never hit this
#: because ``create_table`` does emit it; this is the first migration in the
#: project to add an enum column to a table that already exists.
session_origin = sa.Enum("browser", "mcp", name="session_origin", create_type=False)


def upgrade() -> None:
    session_origin.create(op.get_bind(), checkfirst=False)
    op.add_column(
        "user_sessions",
        sa.Column("origin", session_origin, server_default="browser", nullable=False),
    )
    op.add_column("user_sessions", sa.Column("label", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("user_sessions", "label")
    op.drop_column("user_sessions", "origin")
    # See the module docstring: the columns are gone but the type is not.
    op.execute("DROP TYPE IF EXISTS session_origin")
