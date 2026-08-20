"""A posting somebody handed us, and the job it is not yet allowed to be.

Revision ID: 0023_captured_postings
Revises: 0022_geocode_cache
Create Date: 2026-08-19 23:39:57.714632+00:00


M5a / AMENDMENTS A16. The first source of postings in this product that nobody
polled. A person pastes a job they found — on LinkedIn, on Indeed, in a Slack
message, from a friend — and it becomes a real row in the corpus with real
provenance, or it does not become anything.

**The constraint worth reading is `confirmed_rows_carry_a_job`**, and it is the
same argument `resume_extractions` makes one subsystem over. A parser reading
free text has to decide which string is the employer, and that decision is not
cosmetic: a company name resolves to a company, a company resolves to that
company's confirmed office, and an office puts a beacon on a **building**. A
misparsed employer is invariant I1 violated through the side door.

So the biconditional is deliberate and runs in both directions. A row cannot
say it is confirmed without naming the job it produced, and it cannot name a
job without being confirmed. No parser bug reaches `jobs` without a person, and
the guarantee is a property of the schema rather than a claim about a code path.

`source_type` gains `manual_capture`, and it is kept distinct from the ATS
values for a reason that outlives this migration: **nothing can re-read a
captured posting.** There is no board to poll, so the freshness machinery has
no signal here and must never be pointed at these rows. I3 says silence is not
evidence a listing closed; for a captured posting, silence is the only thing
there will ever be.

Following `0021_company_location_bin`'s precedent for the enum: PostgreSQL has
`ALTER TYPE ... ADD VALUE` and no `DROP VALUE`, so the downgrade recreates the
type rather than leaving the value behind. `sources` is the only table using it.
**The downgrade fails loudly if any surviving row is a `manual_capture` source**,
which is correct — you cannot downgrade past data that needs the value, and
rewriting those rows to something else would be losing information to make a
command succeed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import nightshift.db.types

revision: str = "0023_captured_postings"
down_revision: str | None = "0022_geocode_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADDED_SOURCE_TYPE = "manual_capture"

#: `source_type` exactly as it stood before this migration. The downgrade
#: rebuilds it from this list, so it is the definition of "before" rather than a
#: comment about it.
_SOURCE_TYPE_BEFORE = (
    "ats_greenhouse",
    "ats_lever",
    "ats_ashby",
    "government",
    "fixture",
)


def upgrade() -> None:
    op.execute(f"ALTER TYPE source_type ADD VALUE IF NOT EXISTS '{_ADDED_SOURCE_TYPE}'")

    op.create_table(
        "captured_postings",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "confirmed", "discarded", name="capture_status"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("proposed_title", sa.String(length=500), nullable=True),
        sa.Column("proposed_company_name", sa.String(length=300), nullable=True),
        sa.Column("proposed_location_text", sa.String(length=500), nullable=True),
        sa.Column("parser_version", sa.String(length=40), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", nightshift.db.types.UTCDateTime(timezone=True), nullable=True),
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
            "(status = 'confirmed') = (job_id IS NOT NULL)",
            name=op.f("ck_captured_postings_confirmed_rows_carry_a_job"),
        ),
        sa.CheckConstraint(
            "(status = 'pending') = (decided_at IS NULL)",
            name=op.f("ck_captured_postings_decided_rows_carry_a_time"),
        ),
        sa.CheckConstraint(
            "length(btrim(raw_text)) > 0", name=op.f("ck_captured_postings_capture_has_text")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_captured_postings_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_captured_postings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_captured_postings")),
    )
    op.create_index(
        op.f("ix_captured_postings_user_id"), "captured_postings", ["user_id"], unique=False
    )
    op.create_index(
        "ix_captured_postings_user_id_status",
        "captured_postings",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_captured_postings_user_id_status", table_name="captured_postings")
    op.drop_index(op.f("ix_captured_postings_user_id"), table_name="captured_postings")
    op.drop_table("captured_postings")
    # The table is gone but its type is not: `create_type=True` made it on the
    # way up and nothing removes it on the way down. Leaving it behind makes the
    # *next* upgrade fail with "type capture_status already exists", which is
    # the defect `0020_role_family_and_seniority` recorded and this one does not
    # get to repeat.
    op.execute("DROP TYPE IF EXISTS capture_status")

    # `source_type` has no DROP VALUE, so recreate it. `sources` is the only
    # table that uses it and it carries no default to preserve.
    #
    # The USING cast fails loudly if a surviving row is a `manual_capture`
    # source. That is intended: the value is in use, so the schema that lacks it
    # is not a schema this data fits.
    values = ", ".join(f"'{value}'" for value in _SOURCE_TYPE_BEFORE)
    op.execute("ALTER TYPE source_type RENAME TO source_type_old")
    op.execute(f"CREATE TYPE source_type AS ENUM ({values})")
    op.execute(
        "ALTER TABLE sources ALTER COLUMN source_type "
        "TYPE source_type USING source_type::text::source_type"
    )
    op.execute("DROP TYPE source_type_old")
