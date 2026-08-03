"""application tracking — applications and their append-only events

The append-only trigger reuses ``nightshift_refuse_mutation()``, created by
``0002``. It is not re-created here: ``0002`` is an ancestor, so on downgrade
this revision is reversed first and the function is still there. Dropping it
here would break ``job_status_events`` and ``job_merge_events``.

Autogenerate emitted ``nightshift.db.types.UTCDateTime`` five times in this
file with no import for it — a ``NameError`` at upgrade time, and the third
migration in this project to do it. Every one is ``sa.DateTime(timezone=True)``
below, which is what the type compiles to anyway.

Revision ID: 0008_application_tracking
Revises: 0007_salary_min_index
Create Date: 2026-08-03 18:00:00+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_application_tracking"
down_revision: str | None = "0007_salary_min_index"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column(
            "current_stage",
            sa.Enum(
                "discovered",
                "saved",
                "preparing",
                "applied",
                "assessment",
                "interview",
                "offer",
                "rejected",
                "withdrawn",
                "closed",
                name="application_stage",
            ),
            server_default=sa.text("'saved'"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("high", "normal", "low", name="application_priority"),
            server_default=sa.text("'normal'"),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("application_url", sa.String(length=1000), nullable=True),
        sa.Column("source_of_application", sa.String(length=200), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_applications_job_id_jobs"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_applications_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint("user_id", "job_id", name="uq_applications_user_id_job_id"),
    )
    op.create_index(
        "ix_applications_next_action_at", "applications", ["next_action_at"], unique=False
    )
    op.create_index(
        "ix_applications_user_id_current_stage",
        "applications",
        ["user_id", "current_stage"],
        unique=False,
    )
    op.create_table(
        "application_events",
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "saved",
                "stage_changed",
                "note_added",
                "detail_updated",
                "interview_scheduled",
                "archived",
                "restored",
                "listing_closed",
                name="application_event_type",
            ),
            nullable=False,
        ),
        sa.Column("actor", sa.Enum("user", "system", name="event_actor"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "from_stage",
            sa.Enum(
                "discovered",
                "saved",
                "preparing",
                "applied",
                "assessment",
                "interview",
                "offer",
                "rejected",
                "withdrawn",
                "closed",
                name="application_stage",
            ),
            nullable=True,
        ),
        sa.Column(
            "to_stage",
            sa.Enum(
                "discovered",
                "saved",
                "preparing",
                "applied",
                "assessment",
                "interview",
                "offer",
                "rejected",
                "withdrawn",
                "closed",
                name="application_stage",
            ),
            nullable=True,
        ),
        sa.Column(
            "transition_class",
            sa.Enum("advance", "correction", "reopen", name="transition_class"),
            nullable=True,
        ),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "to_stage IS NULL OR actor = 'user'",
            name=op.f("ck_application_events_only_a_user_moves_a_stage"),
        ),
        sa.CheckConstraint(
            "(to_stage IS NULL AND transition_class IS NULL)"
            " OR (to_stage IS NOT NULL AND transition_class IS NOT NULL)",
            name=op.f("ck_application_events_stage_fields_travel_together"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_application_events_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
    )
    op.create_index(
        "ix_application_events_application_id_occurred_at",
        "application_events",
        ["application_id", "occurred_at"],
        unique=False,
    )
    # CLAUDE.md §7: append-only is a trigger, not a convention. It fires on a
    # cascading delete too, which is why an application cannot be deleted while
    # it has history — see test_an_application_cannot_be_deleted_either.
    op.execute(
        "CREATE TRIGGER application_events_append_only "
        "BEFORE UPDATE OR DELETE ON application_events "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_refuse_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS application_events_append_only ON application_events")
    op.drop_index(
        "ix_application_events_application_id_occurred_at", table_name="application_events"
    )
    op.drop_table("application_events")
    op.drop_index("ix_applications_user_id_current_stage", table_name="applications")
    op.drop_index("ix_applications_next_action_at", table_name="applications")
    op.drop_table("applications")
    # A downgrade that forgets DROP TYPE leaves the enums behind, and M0
    # acceptance row 3 is the check that catches it.
    for enum_name in (
        "application_event_type",
        "event_actor",
        "transition_class",
        "application_priority",
        "application_stage",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
