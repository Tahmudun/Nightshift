"""jobs.role_family and jobs.seniority become PostgreSQL enums

Revision ID: 0013_role_family_and_seniority
Revises: 0012_check_constraint_names
Create Date: 2026-08-05 21:30:45.991311+00:00

M1 created both columns as `String` placeholders with a comment saying M3's
classifier would fill them. M3b is that classifier, so they become real types
(CLAUDE.md §7: enums as PG enums or check constraints, never bare strings).

**Both columns are empty and that was checked rather than assumed** — a grep
found no writer anywhere in `nightshift/`, `scripts/` or the web app, and
`select count(role_family), count(seniority) from jobs` returned 0 and 0 against
a freshly seeded database. So the conversion cannot lose a value, and the
`USING` clauses below cast nothing in practice. They are still written out,
because a migration that only works on an empty table is a migration that fails
the first time it meets a populated one.

Three things autogenerate got wrong, all three of which this project has
recorded before:

1. **`op.alter_column` does not create the enum type**, exactly as
   `op.add_column` does not (M2c's review, finding 2). The generated migration
   fails with `type "role_family" does not exist`.
2. **A VARCHAR to enum change needs an explicit `USING`.** PostgreSQL will not
   cast between them implicitly, whatever the column holds.
3. **The downgrade emitted no `DROP TYPE`**, which leaves both types behind and
   makes the *next* upgrade fail with "type already exists" (M2c finding 3).
   The migrations CI job's up/down/up sequence exists to catch precisely this.

`null` still means "not yet classified" and is distinct from `unclear`, which is
the classifier having read the posting and declined to guess. Keeping them apart
is what makes a coverage figure readable — otherwise an unrun classifier and a
corpus of ambiguous titles look identical.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_role_family_and_seniority"
down_revision: str | None = "0012_check_constraint_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_FAMILY_VALUES = (
    "software_engineering",
    "data_engineering",
    "ml_ai",
    "infrastructure",
    "security",
    "quant_trading",
    "hardware",
    "product",
    "design",
    "not_tech",
    "unclear",
)

SENIORITY_VALUES = (
    "internship",
    "new_grad",
    "junior",
    "mid",
    "senior",
    "staff",
    "director",
    "unclear",
)

_ROLE_FAMILY = sa.Enum(*ROLE_FAMILY_VALUES, name="role_family")
_SENIORITY = sa.Enum(*SENIORITY_VALUES, name="seniority")


def upgrade() -> None:
    bind = op.get_bind()
    # create_type defaults to True but only fires when the type is attached to a
    # CREATE TABLE. An alter_column never triggers it, so both are explicit.
    _ROLE_FAMILY.create(bind, checkfirst=True)
    _SENIORITY.create(bind, checkfirst=True)

    op.alter_column(
        "jobs",
        "role_family",
        existing_type=sa.VARCHAR(length=100),
        type_=_ROLE_FAMILY,
        existing_nullable=True,
        postgresql_using="role_family::role_family",
    )
    op.alter_column(
        "jobs",
        "seniority",
        existing_type=sa.VARCHAR(length=50),
        type_=_SENIORITY,
        existing_nullable=True,
        postgresql_using="seniority::seniority",
    )


def downgrade() -> None:
    op.alter_column(
        "jobs",
        "seniority",
        existing_type=_SENIORITY,
        type_=sa.VARCHAR(length=50),
        existing_nullable=True,
        postgresql_using="seniority::text",
    )
    op.alter_column(
        "jobs",
        "role_family",
        existing_type=_ROLE_FAMILY,
        type_=sa.VARCHAR(length=100),
        existing_nullable=True,
        postgresql_using="role_family::text",
    )
    # Autogenerate does not emit these, and without them the next upgrade fails
    # with "type already exists" — which is what the CI migrations job's
    # up, down, up sequence is for.
    bind = op.get_bind()
    _SENIORITY.drop(bind, checkfirst=True)
    _ROLE_FAMILY.drop(bind, checkfirst=True)
