"""What each penalty cost, and the guard that makes the two add up to the one column.

Revision ID: 0019_match_penalties
Revises: 0018_match_component_assessments
Create Date: 2026-08-10

M3c Task 10 — the task where the score first reaches a *person* rather than a
test, and the last place a number was still bare turns out to be the penalty.

`matching.md` §4.2 stores the two §5.1 penalties as one column and gives a good
reason: `match_evidence.component` has no penalty member, so a split score column
would imply an evidence link that does not exist. That reasoning is unchanged and
`match_results.penalty_score` keeps its single column — `the_total_is_its_parts`
still adds it once.

What §4.2 also said, and left to somebody else, is *"what each penalty cost
belongs to the explanation"*. Nothing carried it. A reader saw `-18` under a
score with no way to learn that 12 of it came from three unmet technologies and
6 from a title pitched above their stated years — which is invariant I4's
*"stores its components, **its penalties**, its ruleset_version, and its
evidence"* going unmet in exactly the place a person reads. PROGRESS assigned the
call to this task; this is the call.

**This is `0018`'s table, one row down.** Same argument, same shape: the rule's
own sentence, produced by the same call as the points beside it, stored rather
than re-derived at render time. It is not the `explanation` column §4.2 refused,
which would have been a narrative assembled *from* the rows and able to disagree
with them.

**Two things `0018`'s guard has no analogue for**, and they are why this migration
carries a trigger rather than only a table:

1. **The parts sum to the column.** `sum(match_penalties.points) =
   match_results.penalty_score`, asserted at commit. Without it the table is a
   second version of the same claim, free to disagree with the number the total
   was actually computed from — which is the whole failure mode a split is
   supposed to avoid, arriving by the other door.
2. **Exactly one row per name.** `score_match` always produces both penalties,
   applicable or not, because *"there was nothing to ask"* and *"nothing was
   missing"* are different sentences and both are worth printing. A missing row
   is a penalty with no statement, and `penalty_score` would still add up.

`applicable = false` implies `points = 0` is a check constraint rather than a
trigger clause: it is a property of one row, so it does not need to see another
table, and `Penalty.__post_init__` refuses the same thing in Python.

**Existing rows are deleted rather than backfilled**, in both directions, exactly
as `0017` and `0018` did. There is no honest `why` to invent for a score written
before this revision, and inventing `applicable = false, points = 0` for both
would state that no posting in the corpus penalised anybody — which is false of
the corpus and is precisely the kind of default this table exists to stop. An
absent score reads as not-yet-computed, which is true of it, and the sweep
rebuilds it within the minute.

Written by hand: autogenerate cannot see a trigger body.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from nightshift.db.types import UTCDateTime

revision: str = "0019_match_penalties"
down_revision: str | None = "0018_match_component_assessments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Duplicated from `nightshift.db.base.PenaltyName` for the reason
#: `0015_internship_season` records: a migration that imports a model stops
#: describing the schema as of its own revision and starts describing today's.
#: `test_the_penalty_migration_creates_exactly_the_type_the_model_declares` is
#: what makes the copy safe.
PENALTY_NAME_VALUES = ("missing_requirement", "seniority_mismatch")


def upgrade() -> None:
    # See the module docstring. `0018` deleted what there was and the sweep has
    # only run against test databases since, so this deletes nothing today.
    op.execute("DELETE FROM match_results")

    penalty_name = postgresql.ENUM(*PENALTY_NAME_VALUES, name="penalty_name", create_type=False)
    penalty_name.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "match_penalties",
        sa.Column("match_result_id", sa.UUID(), nullable=False),
        sa.Column("name", penalty_name, nullable=False),
        sa.Column("points", sa.SmallInteger(), nullable=False),
        sa.Column("applicable", sa.Boolean(), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column(
            "compared",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        # The same assertion `match_results.a_penalty_never_adds` makes about the
        # total, made about the part. That a penalty subtracts is not a tunable;
        # the ceilings in `data/matching.yaml` are.
        sa.CheckConstraint("points <= 0", name=op.f("ck_match_penalties_a_penalty_never_adds")),
        # "There was nothing to ask" and "nothing was missing" are different
        # sentences and only the second may cost anything — and it costs zero too.
        # `Penalty.__post_init__` refuses this in Python; this is the same refusal
        # for anything reaching the table another way.
        sa.CheckConstraint(
            "applicable OR points = 0",
            name=op.f("ck_match_penalties_an_inapplicable_penalty_costs_nothing"),
        ),
        # §5.1.1's argument one table over: the reason is the point, not the fact
        # that there is one. A blank `why` renders as a subtraction for no stated
        # reason, which is the shape of a page nobody can check.
        sa.CheckConstraint(
            "length(btrim(why)) > 0", name=op.f("ck_match_penalties_a_reason_is_never_blank")
        ),
        sa.ForeignKeyConstraint(
            ["match_result_id"],
            ["match_results.id"],
            name=op.f("fk_match_penalties_match_result_id_match_results"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_penalties")),
        # What makes "exactly two rows" checkable as a count rather than as a set
        # comparison — and what makes the count an assertion at all, given the
        # column's domain is closed by the enum above.
        sa.UniqueConstraint("match_result_id", "name", name="uq_match_penalties_result_name"),
    )

    # One function, two triggers, because the violation is reachable from both
    # tables — `0016`'s and `0018`'s guards have the same shape for the same
    # reason. It re-reads the score row rather than trusting a deferred trigger's
    # queued NEW record, which may have been updated or deleted since.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION nightshift_penalties_account_for_the_column(result_id uuid)
        RETURNS void AS $$
        DECLARE
            result match_results%ROWTYPE;
            stated integer;
            charged integer;
        BEGIN
            SELECT * INTO result FROM match_results WHERE id = result_id;
            IF NOT FOUND THEN
                -- Deleted later in the same transaction. Nothing to assert.
                RETURN;
            END IF;

            SELECT count(*), coalesce(sum(points), 0)
              INTO stated, charged
              FROM match_penalties
             WHERE match_result_id = result.id;

            IF stated <> {len(PENALTY_NAME_VALUES)} THEN
                RAISE EXCEPTION
                    'match_result % states % of % penalties; one with no statement still subtracts',
                    result.id, stated, {len(PENALTY_NAME_VALUES)};
            END IF;

            IF charged <> result.penalty_score THEN
                RAISE EXCEPTION
                    'match_result % subtracted % and its penalties account for %',
                    result.id, result.penalty_score, charged;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_score_needs_penalties()
        RETURNS trigger AS $$
        BEGIN
            PERFORM nightshift_penalties_account_for_the_column(NEW.id);
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_penalty_change_rechecks_the_score()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                PERFORM nightshift_penalties_account_for_the_column(OLD.match_result_id);
                RETURN NULL;
            END IF;
            PERFORM nightshift_penalties_account_for_the_column(NEW.match_result_id);
            IF TG_OP = 'UPDATE' AND NEW.match_result_id <> OLD.match_result_id THEN
                PERFORM nightshift_penalties_account_for_the_column(OLD.match_result_id);
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER match_results_penalties_are_accounted_for "
        "AFTER INSERT OR UPDATE ON match_results "
        "DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_score_needs_penalties()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER match_penalties_recheck_the_score "
        "AFTER INSERT OR UPDATE OR DELETE ON match_penalties "
        "DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_penalty_change_rechecks_the_score()"
    )


def downgrade() -> None:
    # Symmetrical with the upgrade, and for the same reason: a score that
    # survived down would state a penalty total nothing accounts for.
    op.execute("DELETE FROM match_results")
    op.execute(
        "DROP TRIGGER IF EXISTS match_results_penalties_are_accounted_for ON match_results"
    )
    op.execute("DROP TRIGGER IF EXISTS match_penalties_recheck_the_score ON match_penalties")
    op.execute("DROP FUNCTION IF EXISTS nightshift_score_needs_penalties()")
    op.execute("DROP FUNCTION IF EXISTS nightshift_penalty_change_rechecks_the_score()")
    op.execute("DROP FUNCTION IF EXISTS nightshift_penalties_account_for_the_column(uuid)")
    op.drop_table("match_penalties")
    postgresql.ENUM(name="penalty_name").drop(op.get_bind(), checkfirst=False)
