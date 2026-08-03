"""profile and resumes — proposals on one side, confirmed facts on the other

The boundary invariant I2 rests on. ``resume_extractions`` holds proposals;
``users`` / ``user_skills`` / ``user_projects`` hold what a person confirmed.
Promotion crosses the two, which is why no bug in the extractor can produce a
confirmed fact.

``resume_extractions_span_must_quote`` is the trigger that makes a lying span
unstorable. A check constraint cannot do this job: the text it must compare
against lives in another table. Postgres ``substring(... FROM n FOR count)`` is
1-indexed and the spans are 0-indexed Python slices, hence ``char_start + 1``.

Autogenerate emitted ``nightshift.db.types.UTCDateTime`` with no import for it
again — a ``NameError`` at upgrade time, and the **fourth** migration in this
project to do it. It is ``sa.DateTime(timezone=True)`` below, which is what the
type compiles to anyway. Autogenerate also omitted both ``users`` check
constraints, because it does not emit table constraints for a table it is only
adding columns to; they are written by hand here.

Revision ID: 0009_profile_and_resumes
Revises: 0008_application_tracking
Create Date: 2026-08-03 21:00:00+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_profile_and_resumes"
down_revision: str | None = "0008_application_tracking"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


#: Every enum this revision introduces, created once at the top of
#: ``upgrade()``. ``op.add_column`` does **not** create a type on
#: PostgreSQL the way ``create_table`` does, so an inline ``sa.Enum``
#: on a new column fails with "type does not exist" — measured, on the
#: first run of this migration. The house pattern from ``0001`` and
#: ``0004`` avoids it by declaring them here.
ENUMS: dict[str, tuple[str, ...]] = {
    "resume_variant": ('general_swe', 'backend', 'full_stack', 'data_ml', 'infrastructure', 'custom'),
    "resume_source_kind": ('paste', 'txt', 'pdf'),
    "project_status": ('active', 'completed', 'archived'),
    "proficiency_level": ('unspecified', 'beginner', 'intermediate', 'advanced'),
    "skill_source_type": ('manual', 'resume', 'project', 'coursework', 'assessment', 'github', 'inferred_pending_confirmation'),
    "extraction_kind": ('skill', 'graduation', 'degree', 'school', 'project'),
    "extraction_status": ('pending', 'confirmed', 'rejected'),
    "work_authorization": ('unspecified', 'us_citizen', 'permanent_resident', 'f1_student', 'other_authorized', 'needs_sponsorship'),
    "remote_preference": ('no_preference', 'on_site', 'hybrid', 'remote'),
}


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created type. ``create_type=False`` prevents a duplicate CREATE."""
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    for name, labels in ENUMS.items():
        postgresql.ENUM(*labels, name=name, create_type=False).create(
            op.get_bind(), checkfirst=False
        )
    op.create_table(
        "resumes",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "variant_type",
            _enum("resume_variant"),
            server_default=sa.text("'custom'"),
            nullable=False,
        ),
        sa.Column(
            "source_kind", _enum("resume_source_kind"), nullable=False
        ),
        sa.Column("original_filename", sa.String(length=300), nullable=True),
        sa.Column("parsed_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            ["user_id"], ["users.id"], name=op.f("fk_resumes_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resumes")),
        sa.UniqueConstraint("user_id", "content_hash", name="uq_resumes_user_id_content_hash"),
    )
    op.create_index(op.f("ix_resumes_user_id"), "resumes", ["user_id"], unique=False)
    op.create_table(
        "user_projects",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("repository_url", sa.String(length=500), nullable=True),
        sa.Column("demo_url", sa.String(length=500), nullable=True),
        sa.Column(
            "technologies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            _enum("project_status"),
            server_default=sa.text("'completed'"),
            nullable=False,
        ),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_projects_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_projects")),
        sa.UniqueConstraint("user_id", "name", name="uq_user_projects_user_id_name"),
    )
    op.create_index(op.f("ix_user_projects_user_id"), "user_projects", ["user_id"], unique=False)
    op.create_table(
        "user_skills",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column(
            "proficiency_level",
            _enum("proficiency_level"),
            server_default=sa.text("'unspecified'"),
            nullable=False,
        ),
        sa.Column(
            "source_type",
            _enum("skill_source_type"),
            nullable=False,
        ),
        sa.Column("source_reference", sa.String(length=200), nullable=True),
        sa.Column("vocabulary_version", sa.String(length=40), nullable=True),
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
            "source_type <> 'inferred_pending_confirmation'",
            name=op.f("ck_user_skills_confirmed_only"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_skills_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_skills")),
        sa.UniqueConstraint("user_id", "normalized_name", name="uq_user_skills_user_id_name"),
    )
    op.create_index(op.f("ix_user_skills_user_id"), "user_skills", ["user_id"], unique=False)
    op.create_table(
        "resume_extractions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("resume_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            _enum("extraction_kind"),
            nullable=False,
        ),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("extractor_version", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            _enum("extraction_status"),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
            "(status = 'pending') = (decided_at IS NULL)",
            name=op.f("ck_resume_extractions_decided_rows_carry_a_time"),
        ),
        sa.CheckConstraint(
            "char_end > char_start", name=op.f("ck_resume_extractions_span_is_not_empty")
        ),
        sa.CheckConstraint(
            "char_start >= 0", name=op.f("ck_resume_extractions_span_starts_in_the_text")
        ),
        sa.ForeignKeyConstraint(
            ["resume_id"],
            ["resumes.id"],
            name=op.f("fk_resume_extractions_resume_id_resumes"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_resume_extractions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resume_extractions")),
    )
    op.create_index(
        "ix_resume_extractions_resume_id_status",
        "resume_extractions",
        ["resume_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_resume_extractions_user_id"), "resume_extractions", ["user_id"], unique=False
    )
    op.add_column("applications", sa.Column("selected_resume_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_applications_selected_resume_id_resumes"),
        "applications",
        "resumes",
        ["selected_resume_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("users", sa.Column("graduation_year", sa.SmallInteger(), nullable=True))
    op.add_column("users", sa.Column("graduation_month", sa.SmallInteger(), nullable=True))
    op.add_column("users", sa.Column("degree", sa.String(length=200), nullable=True))
    op.add_column("users", sa.Column("school", sa.String(length=300), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "work_authorization",
            _enum("work_authorization"),
            server_default=sa.text("'unspecified'"),
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("home_location_text", sa.String(length=300), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "remote_preference",
            _enum("remote_preference"),
            server_default=sa.text("'no_preference'"),
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("minimum_salary", sa.Integer(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "preferred_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "preferred_locations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    # Autogenerate does not emit table constraints for a table it is only
    # adding columns to, so these are by hand. A month with no year is not a
    # date, it is a fragment (I1).
    op.create_check_constraint(
        "ck_users_graduation_month_needs_a_year",
        "users",
        "graduation_month IS NULL OR graduation_year IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_users_graduation_month_is_a_month",
        "users",
        "graduation_month IS NULL OR graduation_month BETWEEN 1 AND 12",
    )

    # Invariant I2, at the lowest level available. A proposal must literally
    # quote the resume text it points at, so the highlight a person sees and
    # the claim being confirmed cannot disagree.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_resume_span_must_quote_the_text()
        RETURNS trigger AS $$
        DECLARE
            source_text text;
        BEGIN
            SELECT parsed_text INTO source_text FROM resumes WHERE id = NEW.resume_id;
            IF source_text IS NULL THEN
                RAISE EXCEPTION 'resume % has no parsed text', NEW.resume_id;
            END IF;
            IF NEW.char_end > length(source_text) THEN
                RAISE EXCEPTION
                    'span [%,%) runs past the % characters of resume %',
                    NEW.char_start, NEW.char_end, length(source_text), NEW.resume_id;
            END IF;
            IF substring(source_text FROM NEW.char_start + 1
                         FOR NEW.char_end - NEW.char_start) <> NEW.quoted_text THEN
                RAISE EXCEPTION
                    'span [%,%) does not quote the resume text (invariant I2)',
                    NEW.char_start, NEW.char_end;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER resume_extractions_span_must_quote "
        "BEFORE INSERT OR UPDATE ON resume_extractions "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_resume_span_must_quote_the_text()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS resume_extractions_span_must_quote ON resume_extractions"
    )
    op.execute("DROP FUNCTION IF EXISTS nightshift_resume_span_must_quote_the_text()")
    op.drop_constraint("ck_users_graduation_month_is_a_month", "users", type_="check")
    op.drop_constraint("ck_users_graduation_month_needs_a_year", "users", type_="check")
    op.drop_column("users", "preferred_locations")
    op.drop_column("users", "preferred_roles")
    op.drop_column("users", "minimum_salary")
    op.drop_column("users", "remote_preference")
    op.drop_column("users", "home_location_text")
    op.drop_column("users", "work_authorization")
    op.drop_column("users", "school")
    op.drop_column("users", "degree")
    op.drop_column("users", "graduation_month")
    op.drop_column("users", "graduation_year")
    op.drop_constraint(
        op.f("fk_applications_selected_resume_id_resumes"), "applications", type_="foreignkey"
    )
    op.drop_column("applications", "selected_resume_id")
    op.drop_index(op.f("ix_resume_extractions_user_id"), table_name="resume_extractions")
    op.drop_index("ix_resume_extractions_resume_id_status", table_name="resume_extractions")
    op.drop_table("resume_extractions")
    op.drop_index(op.f("ix_user_skills_user_id"), table_name="user_skills")
    op.drop_table("user_skills")
    op.drop_index(op.f("ix_user_projects_user_id"), table_name="user_projects")
    op.drop_table("user_projects")
    op.drop_index(op.f("ix_resumes_user_id"), table_name="resumes")
    op.drop_table("resumes")
    # A downgrade that forgets DROP TYPE leaves the enums behind and the next
    # upgrade fails with "type already exists". M0 acceptance row 3 catches it.
    for enum_name in (
        "extraction_status",
        "extraction_kind",
        "project_status",
        "proficiency_level",
        "skill_source_type",
        "resume_source_kind",
        "resume_variant",
        "remote_preference",
        "work_authorization",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
