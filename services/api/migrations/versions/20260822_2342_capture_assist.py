"""A capture learns who proposed each field.

Revision ID: 0026_capture_assist
Revises: 0025_session_origin
Create Date: 2026-08-22 23:42:11.559467+00:00


M5d / ADR 0039 §2. ``captured_postings`` has carried ``proposed_*`` since
``0023`` — what the line parser read out of the pasted text. This migration
adds a second proposer's columns beside them rather than merging into them.

**The separation is the whole decision.** ADR 0039 §1 forbids this server
loading a LinkedIn page, so the party that actually saw the posting rendered is
the reader's own Claude, and it is a far better reader than a line parser. It
also fails differently: a parser can misread the text, and an assistant can
produce a company that was never in the text at all. One column holding either
would erase which one said what at exactly the moment a person is deciding
whether to believe it.

Every value that lands in ``assistant_*`` has already passed the quoting rule —
it appears verbatim in ``raw_text``. ``assistant_rejected_fields`` holds the
**names** of fields that did not, never their values: storing the value would
put a hallucinated company name in this database, which is what the rule exists
to prevent. The names are kept because they are the only measurement there will
be of whether the gate is set too tight.

All four columns are additive and nullable-or-defaulted, so this lands on a
populated table without a backfill: an existing capture had no assistant, and
NULL is the true answer for every one of them.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0026_capture_assist"
down_revision: str | None = "0025_session_origin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "captured_postings", sa.Column("assistant_title", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "captured_postings",
        sa.Column("assistant_company_name", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "captured_postings",
        sa.Column("assistant_location_text", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "captured_postings",
        sa.Column(
            "assistant_rejected_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("captured_postings", "assistant_rejected_fields")
    op.drop_column("captured_postings", "assistant_location_text")
    op.drop_column("captured_postings", "assistant_company_name")
    op.drop_column("captured_postings", "assistant_title")
