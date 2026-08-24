"""A capture learns the identity of the paste it holds.

Revision ID: 0027_capture_fingerprint
Revises: 0026_capture_assist
Create Date: 2026-08-22 23:51:04.118902+00:00


M5d / ADR 0039 §3. ``POST /capture`` has created a row per call since ``0023``,
which means one posting reviewed twice whenever a reader — or a model unsure
whether its last call landed — pastes it again. This column is the lookup that
stops it: sha256 of the whitespace-collapsed, casefolded ``raw_text``.

**Normalised rather than raw**, because re-copying a page rarely produces
byte-identical text and a trailing newline is not a second posting.

**Not the same thing as ``capture_source_job_id``.** That one is content-
derived across *all* users so two people capturing one opening land on one job.
This one is scoped to a person's own pending queue and answers a narrower
question: have you already pasted this. The index carries ``user_id`` first for
exactly that reason — a shared proposal would hand one reader a row belonging
to another, which is M5b's isolation broken by a deduplication shortcut.

**The backfill is the interesting part.** The column is NOT NULL and the table
is populated, so this cannot be one statement. Add it nullable, compute every
existing row's fingerprint here rather than with a server-side ``digest()``
(pgcrypto is not an extension this database has, and adding one to backfill a
column would be a heavier decision than the column), then tighten. The
normalisation below is a transcription of ``capture_assist._flatten`` and
``capture.text_fingerprint``; it is duplicated on purpose, because a migration
that imports application code computes whatever that code means *later* rather
than what it meant when the migration ran.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_capture_fingerprint"
down_revision: str | None = "0026_capture_assist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WHITESPACE = re.compile(r"\s+")


def _fingerprint(raw_text: str) -> str:
    flattened = _WHITESPACE.sub(" ", raw_text).strip().casefold()
    return hashlib.sha256(flattened.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column(
        "captured_postings", sa.Column("text_fingerprint", sa.String(length=64), nullable=True)
    )

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, raw_text FROM captured_postings")).fetchall()
    for row_id, raw_text in rows:
        connection.execute(
            sa.text(
                "UPDATE captured_postings SET text_fingerprint = :fingerprint WHERE id = :id"
            ),
            {"fingerprint": _fingerprint(raw_text), "id": row_id},
        )

    op.alter_column("captured_postings", "text_fingerprint", nullable=False)
    op.create_index(
        "ix_captured_postings_user_id_fingerprint",
        "captured_postings",
        ["user_id", "text_fingerprint"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_captured_postings_user_id_fingerprint", table_name="captured_postings")
    op.drop_column("captured_postings", "text_fingerprint")
