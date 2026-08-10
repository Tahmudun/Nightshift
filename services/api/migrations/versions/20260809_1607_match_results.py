"""match_results, match_evidence, user_skills.skill_id — and the guards on a score

`matching.md` §4.2, §4.3, §4.4. Three new database types, two new tables, one
new column, and seven triggers. The tables are the easy part; the triggers are
what make invariant I4 a property of the schema instead of a claim about the
code that writes it.

**The two evidence guards, in the two tiers §4.3 asks for.**

1. `match_results_component_needs_evidence` and its twin on `match_evidence` —
   a **deferrable constraint trigger**, checked at commit. Any component with a
   positive score must have at least one `match_evidence` row filed under it.
   Deferred rather than immediate because a score and its evidence are written
   in one transaction and the score has to exist before a row can reference it;
   an immediate check would fail on every correct write. The twin on
   `match_evidence` exists because deleting the last evidence row for a
   component is the same violation approached from the other side, and a trigger
   that only watches the parent cannot see it.

   Consequence worth knowing before writing a test: **a transaction that never
   commits never runs this check.** The suite rolls back rather than commits, so
   the tests force it with `SET CONSTRAINTS ALL IMMEDIATE`, which is also how
   the guard is shown able to fail.

2. `ck_match_evidence_a_person_claim_quotes_both_sides` and
   `ck_match_evidence_only_a_person_claim_quotes_a_person` — plain CHECKs, and
   two of them because a single biconditional was written first and a test found
   the half it did not cover. A `role`, `skill` or `project` row asserts
   something about *a person* and must quote both sides; `location`, `freshness`
   and `priority` assert something about the posting or about arithmetic and may
   not carry a user-side span at all. They may still quote the *posting* — the
   priority component reads a posting's own seniority and quoting the sentence
   it read is more auditable, not less. §2.1's distinction, in a constraint
   rather than in a convention, because requiring a quoted span where none
   exists would mean inventing one and that is the failure the whole section is
   arranged around.

A third guard, `match_evidence_span_must_quote`, is the same pattern
`job_requirements` and `resume_extractions` already carry: the job-side span
must literally quote `jobs.description_text` at the offsets it claims. The M3c
plan filed this under "test + verify.py" (§2's grading table) and it is a
trigger here instead, because it is the strictly stronger version of the same
assertion and the pattern was already written twice. M3d's hallucination
equality still runs over both sides — this one cannot see `user_span_text`,
which points into several different tables.

**Four `*_clears_match_results` triggers, and why deletion rather than
recompute.** A score is a statement about a posting and a person at a version.
When any of those move, the stored row is not stale-but-usable, it is wrong:
`match_evidence` holds character offsets into a description that has been
rewritten, or quotes a skill that has been deleted. §4.2 says a stale result is
never silently served and the API refuses one whose `ruleset_version` is not
current — but a description rewrite does not change the ruleset version, so
version-checking alone cannot catch this class. Deleting can. An absent score
reads as not-yet-computed, which is true, and M3c Task 8's ARQ task recomputes.

There is a second reason, and it is the one that makes the triggers mandatory
rather than tidy: without them, ingestion breaks. `_apply_normalized_fields()`
rewrites `jobs.description_text` on every re-poll of a changed job, which fires
`jobs_description_change_clears_requirements` (M3a), which deletes
`job_requirements`, which cascades to `match_evidence` — leaving a
`match_results` row with a positive component and no evidence, and failing the
deferred check at commit. Reproduced before these were written. The ordering
among the triggers does not matter precisely because the evidence check is
deferred: what is asserted is the state at commit, not the state between two
statements.

**What autogenerate got wrong this time**, run rather than predicted:

* It emitted `nightshift.db.types.UTCDateTime(timezone=True)` for
  `match_evidence.created_at` and imported no `nightshift` — a `NameError` on
  import, which is M2c's finding 2 in its exact recorded form, now on its fourth
  appearance. Replaced with the real import.
* It emitted no `DROP TYPE` on downgrade for any of the three new enums, so the
  next upgrade would fail with "type already exists". M2c's finding 3, added by
  hand below, following `0011_job_requirements`.
* It produced a random hex revision id (`47e471205cf4`) rather than this
  project's sequential `NNNN_name`. Renamed by hand.

Everything else came through correctly, including all eight check constraints
and both composite indexes — which is more than the last three attempts
managed, and is worth recording so the next reader does not assume the tool is
uniformly untrustworthy.

Revision ID: 0016_match_results
Revises: 0015_internship_season
Create Date: 2026-08-09 16:07:50.086590+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from nightshift.db.types import UTCDateTime

revision: str = "0016_match_results"
down_revision: str | None = "0015_internship_season"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Duplicated from `nightshift.db.base` on purpose, for the reason
#: `0015_internship_season` records: a migration that imports a model stops
#: describing the schema as of its own revision and starts describing today's.
#: `test_enum_vocabularies_agree` is the defence that makes the copy safe.
ELIGIBILITY_STATE_VALUES = (
    "eligible",
    "likely_eligible",
    "uncertain",
    "likely_ineligible",
    "ineligible",
)
MATCH_COMPONENT_VALUES = ("role", "skill", "project", "location", "freshness", "priority")
EVIDENCE_SOURCE_VALUES = ("rule", "embedding")

#: The six (component, score column) pairs the evidence guard walks. Written
#: once here and rendered into the trigger function, so a component added to the
#: enum without a score column — or the reverse — is a visible edit to this list
#: rather than a silently unchecked component.
COMPONENT_SCORE_COLUMNS = (
    ("role", "role_score"),
    ("skill", "skill_score"),
    ("project", "project_evidence_score"),
    ("location", "location_score"),
    ("freshness", "freshness_score"),
    ("priority", "priority_score"),
)


def _component_values_clause() -> str:
    return ",\n                ".join(
        f"('{component}', result.{column})" for component, column in COMPONENT_SCORE_COLUMNS
    )


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "match_results",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("resume_id", sa.UUID(), nullable=True),
        sa.Column("overall_score", sa.SmallInteger(), nullable=False),
        sa.Column(
            "eligibility_status",
            sa.Enum(*ELIGIBILITY_STATE_VALUES, name="eligibility_state"),
            nullable=False,
        ),
        sa.Column("role_score", sa.SmallInteger(), nullable=False),
        sa.Column("skill_score", sa.SmallInteger(), nullable=False),
        sa.Column("project_evidence_score", sa.SmallInteger(), nullable=False),
        sa.Column("location_score", sa.SmallInteger(), nullable=False),
        sa.Column("freshness_score", sa.SmallInteger(), nullable=False),
        sa.Column("priority_score", sa.SmallInteger(), nullable=False),
        sa.Column("penalty_score", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=True),
        sa.Column("ruleset_version", sa.String(length=80), nullable=False),
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
            "overall_score = GREATEST(0, role_score + skill_score + project_evidence_score"
            " + location_score + freshness_score + priority_score + penalty_score)",
            name=op.f("ck_match_results_the_total_is_its_parts"),
        ),
        sa.CheckConstraint(
            "penalty_score <= 0", name=op.f("ck_match_results_a_penalty_never_adds")
        ),
        sa.CheckConstraint(
            "role_score >= 0 AND skill_score >= 0 AND project_evidence_score >= 0"
            " AND location_score >= 0 AND freshness_score >= 0 AND priority_score >= 0",
            name=op.f("ck_match_results_components_are_not_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_match_results_job_id_jobs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["resume_id"],
            ["resumes.id"],
            name=op.f("fk_match_results_resume_id_resumes"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_match_results_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_results")),
        sa.UniqueConstraint(
            "user_id", "job_id", "ruleset_version", name="uq_match_results_user_job_ruleset"
        ),
    )
    op.create_index(op.f("ix_match_results_job_id"), "match_results", ["job_id"], unique=False)
    op.create_index(
        "ix_match_results_user_ranking",
        "match_results",
        ["user_id", "eligibility_status", "overall_score"],
        unique=False,
    )
    op.create_table(
        "match_evidence",
        sa.Column("match_result_id", sa.UUID(), nullable=False),
        sa.Column(
            "component",
            sa.Enum(*MATCH_COMPONENT_VALUES, name="match_component"),
            nullable=False,
        ),
        sa.Column("job_requirement_id", sa.UUID(), nullable=True),
        sa.Column("job_span_text", sa.Text(), nullable=True),
        sa.Column("job_char_start", sa.Integer(), nullable=True),
        sa.Column("job_char_end", sa.Integer(), nullable=True),
        sa.Column("user_skill_id", sa.UUID(), nullable=True),
        sa.Column("user_project_id", sa.UUID(), nullable=True),
        sa.Column("user_span_text", sa.Text(), nullable=True),
        sa.Column(
            "compared",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "proposed_by",
            sa.Enum(*EVIDENCE_SOURCE_VALUES, name="evidence_source"),
            server_default=sa.text("'rule'"),
            nullable=False,
        ),
        sa.Column("points", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "component NOT IN ('role', 'skill', 'project')"
            " OR (job_span_text IS NOT NULL AND user_span_text IS NOT NULL)",
            name=op.f("ck_match_evidence_a_person_claim_quotes_both_sides"),
        ),
        sa.CheckConstraint(
            "component IN ('role', 'skill', 'project') OR user_span_text IS NULL",
            name=op.f("ck_match_evidence_only_a_person_claim_quotes_a_person"),
        ),
        sa.CheckConstraint(
            "(job_span_text IS NULL) = (job_char_start IS NULL)"
            " AND (job_char_start IS NULL) = (job_char_end IS NULL)",
            name=op.f("ck_match_evidence_the_job_span_travels_together"),
        ),
        sa.CheckConstraint(
            "job_char_end IS NULL OR job_char_end > job_char_start",
            name=op.f("ck_match_evidence_the_job_span_runs_forwards"),
        ),
        sa.CheckConstraint(
            "job_char_start IS NULL OR job_char_start >= 0",
            name=op.f("ck_match_evidence_job_char_start_is_not_negative"),
        ),
        sa.CheckConstraint("points >= 0", name=op.f("ck_match_evidence_evidence_never_subtracts")),
        sa.ForeignKeyConstraint(
            ["job_requirement_id"],
            ["job_requirements.id"],
            name=op.f("fk_match_evidence_job_requirement_id_job_requirements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["match_result_id"],
            ["match_results.id"],
            name=op.f("fk_match_evidence_match_result_id_match_results"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_project_id"],
            ["user_projects.id"],
            name=op.f("fk_match_evidence_user_project_id_user_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_skill_id"],
            ["user_skills.id"],
            name=op.f("fk_match_evidence_user_skill_id_user_skills"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_evidence")),
    )
    op.create_index(
        "ix_match_evidence_match_result_id_component",
        "match_evidence",
        ["match_result_id", "component"],
        unique=False,
    )
    op.add_column("user_skills", sa.Column("skill_id", sa.String(length=120), nullable=True))
    op.create_index(op.f("ix_user_skills_skill_id"), "user_skills", ["skill_id"], unique=False)
    # ### end Alembic commands ###

    # -- Guard 1: a component with no evidence is not a component -------------
    #
    # One function, called by two triggers, because the violation is reachable
    # from both tables and a rule written twice is a rule that will be corrected
    # once. It re-reads the row rather than trusting the trigger's NEW record:
    # a deferred trigger fires at commit with the record it was queued with, and
    # the row may have been updated or deleted since.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION nightshift_components_have_evidence(result_id uuid)
        RETURNS void AS $$
        DECLARE
            result match_results%ROWTYPE;
            gap record;
        BEGIN
            SELECT * INTO result FROM match_results WHERE id = result_id;
            IF NOT FOUND THEN
                -- Deleted later in the same transaction. Nothing to assert.
                RETURN;
            END IF;
            SELECT component, score INTO gap
            FROM (VALUES
                {_component_values_clause()}
            ) AS scored(component, score)
            WHERE scored.score > 0
              AND NOT EXISTS (
                  SELECT 1 FROM match_evidence
                  WHERE match_evidence.match_result_id = result.id
                    AND match_evidence.component::text = scored.component
              )
            ORDER BY scored.component
            LIMIT 1;
            IF FOUND THEN
                RAISE EXCEPTION
                    'match_result % scores % for % and has no % evidence row',
                    result.id, gap.score, gap.component, gap.component;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_score_needs_evidence()
        RETURNS trigger AS $$
        BEGIN
            PERFORM nightshift_components_have_evidence(NEW.id);
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_evidence_removal_rechecks_the_score()
        RETURNS trigger AS $$
        BEGIN
            PERFORM nightshift_components_have_evidence(OLD.match_result_id);
            IF TG_OP = 'UPDATE' AND NEW.match_result_id <> OLD.match_result_id THEN
                PERFORM nightshift_components_have_evidence(NEW.match_result_id);
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER match_results_component_needs_evidence "
        "AFTER INSERT OR UPDATE ON match_results "
        "DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_score_needs_evidence()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER match_evidence_removal_rechecks_the_score "
        "AFTER UPDATE OR DELETE ON match_evidence "
        "DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_evidence_removal_rechecks_the_score()"
    )

    # -- Guard 3: the job-side span literally quotes the description ----------
    #
    # `job_requirements` and `resume_extractions` carry the same trigger against
    # their own substrate. The 0-indexed-Python vs. 1-indexed-Postgres offset in
    # `substring` is the same, and so is the reason an inverted span returns
    # early: BEFORE ROW triggers fire before CHECK constraints are validated, so
    # a negative FOR count would reach `substring()` first and raise Postgres's
    # own error instead of the one the CHECK exists to raise.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_evidence_span_must_quote_the_text()
        RETURNS trigger AS $$
        DECLARE
            source_text text;
        BEGIN
            IF NEW.job_span_text IS NULL THEN
                RETURN NEW;
            END IF;
            SELECT jobs.description_text INTO source_text
              FROM match_results
              JOIN jobs ON jobs.id = match_results.job_id
             WHERE match_results.id = NEW.match_result_id;
            IF source_text IS NULL THEN
                RAISE EXCEPTION
                    'match_result % scores a job with no description text',
                    NEW.match_result_id;
            END IF;
            IF NEW.job_char_end <= NEW.job_char_start THEN
                RETURN NEW;
            END IF;
            IF NEW.job_char_end > length(source_text) THEN
                RAISE EXCEPTION
                    'span [%,%) runs past the % characters of the job description',
                    NEW.job_char_start, NEW.job_char_end, length(source_text);
            END IF;
            IF substring(source_text FROM NEW.job_char_start + 1
                         FOR NEW.job_char_end - NEW.job_char_start) <> NEW.job_span_text THEN
                RAISE EXCEPTION
                    'span [%,%) does not quote the job description',
                    NEW.job_char_start, NEW.job_char_end;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER match_evidence_span_must_quote "
        "BEFORE INSERT OR UPDATE ON match_evidence "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_evidence_span_must_quote_the_text()"
    )

    # -- A score dies with its inputs ----------------------------------------
    #
    # Four triggers, one function each side of the join, because the four tables
    # reach `match_results` by two different keys. See the module docstring for
    # why this is deletion rather than recomputation, and why ingestion does not
    # work without it.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_match_results_follow_the_job()
        RETURNS trigger AS $$
        DECLARE
            target uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                target := OLD.job_id;
            ELSE
                target := NEW.job_id;
            END IF;
            DELETE FROM match_results WHERE job_id = target;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_match_results_follow_the_description()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.description_text IS DISTINCT FROM OLD.description_text THEN
                DELETE FROM match_results WHERE job_id = NEW.id;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_match_results_follow_the_profile()
        RETURNS trigger AS $$
        DECLARE
            target uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                target := OLD.user_id;
            ELSE
                target := NEW.user_id;
            END IF;
            DELETE FROM match_results WHERE user_id = target;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER jobs_description_change_clears_match_results "
        "AFTER UPDATE OF description_text ON jobs "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_match_results_follow_the_description()"
    )
    op.execute(
        "CREATE TRIGGER job_requirements_change_clears_match_results "
        "AFTER INSERT OR UPDATE OR DELETE ON job_requirements "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_match_results_follow_the_job()"
    )
    # UPDATE and DELETE only. An *added* skill cannot invalidate a stored
    # evidence row — it can only mean the score is now too low — so the rescore
    # it deserves is M3c Task 8's ARQ task rather than a trigger that throws away
    # the whole corpus mid-import while a resume's confirmed skills are being
    # written one row at a time.
    op.execute(
        "CREATE TRIGGER user_skills_change_clears_match_results "
        "AFTER UPDATE OR DELETE ON user_skills "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_match_results_follow_the_profile()"
    )
    op.execute(
        "CREATE TRIGGER user_projects_change_clears_match_results "
        "AFTER UPDATE OR DELETE ON user_projects "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_match_results_follow_the_profile()"
    )


def downgrade() -> None:
    for table, trigger in (
        ("user_projects", "user_projects_change_clears_match_results"),
        ("user_skills", "user_skills_change_clears_match_results"),
        ("job_requirements", "job_requirements_change_clears_match_results"),
        ("jobs", "jobs_description_change_clears_match_results"),
        ("match_evidence", "match_evidence_span_must_quote"),
        ("match_evidence", "match_evidence_removal_rechecks_the_score"),
        ("match_results", "match_results_component_needs_evidence"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for function in (
        "nightshift_match_results_follow_the_profile()",
        "nightshift_match_results_follow_the_description()",
        "nightshift_match_results_follow_the_job()",
        "nightshift_evidence_span_must_quote_the_text()",
        "nightshift_evidence_removal_rechecks_the_score()",
        "nightshift_score_needs_evidence()",
        "nightshift_components_have_evidence(uuid)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}")

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f("ix_user_skills_skill_id"), table_name="user_skills")
    op.drop_column("user_skills", "skill_id")
    op.drop_index("ix_match_evidence_match_result_id_component", table_name="match_evidence")
    op.drop_table("match_evidence")
    op.drop_index("ix_match_results_user_ranking", table_name="match_results")
    op.drop_index(op.f("ix_match_results_job_id"), table_name="match_results")
    op.drop_table("match_results")
    # ### end Alembic commands ###
    # Autogenerate does not emit DROP TYPE, leaving the enums behind and the next
    # upgrade failing with "type already exists" — M2c's finding 3, and the same
    # hand-addition `0011_job_requirements` carries.
    for enum_name in ("evidence_source", "match_component", "eligibility_state"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
