"""What each component has to say for itself, and the six-row guard on it.

Revision ID: 0018_match_component_assessments
Revises: 0017_match_score_denominator
Create Date: 2026-08-09

M3c Task 9 — the task where a score first had a **reader**, which is the point at
which a missing column stops being invisible. `0017` landed the two columns Task
8 discovered by writing scores; this lands the one Task 9 discovered by reading
them.

`matching.md` §5.1.1 requires the page to name the components that could not be
assessed and why. Neither half survives in `match_results` alone:

* **`assessable` cannot be recovered from the points.** A component that scored
  zero and a component the posting said too little to assess both store `0`, and
  telling those apart is the whole of §5.1.1. `assessed_out_of` does not resolve
  it either — the six weights are 20, 30, 20, 10, 10, 10, and several subsets of
  them sum to the same number, so the denominator names *how much* was assessed
  and can never name *which*.
* **`why` is the only sentence a component ever produces.** The three exempt
  components quote nobody and record their compared values in
  `match_evidence.compared`; an assessable component that scored zero has no
  evidence row at all. Without this text those components reach the page as bare
  numbers, which is invariant I4 one level below the total.

**This is not §4.2's refused `explanation` column.** That one would have held a
narrative assembled *from* `match_evidence`, able to disagree with the rows it
was built from. `why` is the scoring rule's own output, produced by the same call
and the same inputs as the points beside it. The alternative — re-deriving the
sentence by re-running the scorer on read — is the second-derivation failure
`matching.posting_for` is written about, and it can disagree with the stored
number while looking entirely plausible.

**The trigger asserts three things at commit**, and each of them is a mistake
this table makes possible rather than a restatement of one already prevented:

1. **Exactly six rows, one per component.** The database's copy of
   `MatchScore.__post_init__`. Five rows means one component silently has no
   statement, and the page then renders five of six with nothing looking wrong.
2. **An unassessable component scored nothing.** `ComponentScore.__post_init__`
   refuses this in Python; this is the same refusal for anything that reaches the
   table another way.
3. **The denominator agrees with the rows.** `assessed_out_of = 100` exactly when
   every component was assessable — which holds because the six weights sum to
   100 and each is at least 1, both asserted by `matching_weights.parse_weights`.
   This is the strongest form expressible without the weights being in the
   database, and it is the one that matters: without it the page can name three
   unassessable components beside a denominator of 100, and the ranked list then
   sorts on a fraction that contradicts the breakdown printed under it.

Deferred rather than immediate, for the reason guard 1 of `0016` already carries:
the score has to exist before its assessments can reference it.

**Existing rows are deleted rather than backfilled**, in both directions, exactly
as `0017` did and for the same reason. There is no honest `why` to invent for a
row written before this revision, and `assessable = true` for all six is
precisely the claim §5.1.1 exists to stop anybody making by default. An absent
score reads as not-yet-computed, which is true of it, and the recompute sweep
rebuilds it within the minute.

Written by hand: autogenerate cannot see a trigger body.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from nightshift.db.types import UTCDateTime

revision: str = "0018_match_component_assessments"
down_revision: str | None = "0017_match_score_denominator"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Duplicated from `nightshift.db.base.MatchComponent` for the reason
#: `0015_internship_season` records: a migration that imports a model stops
#: describing the schema as of its own revision and starts describing today's.
#: `test_enum_vocabularies_agree` is what makes the copy safe.
MATCH_COMPONENT_VALUES = ("role", "skill", "project", "location", "freshness", "priority")

#: The six (component, score column) pairs, as `0016` writes them. Rendered into
#: the trigger so a component added to the enum without a score column — or the
#: reverse — is a visible edit here rather than a silently unchecked component.
COMPONENT_SCORE_COLUMNS = (
    ("role", "role_score"),
    ("skill", "skill_score"),
    ("project", "project_evidence_score"),
    ("location", "location_score"),
    ("freshness", "freshness_score"),
    ("priority", "priority_score"),
)

#: What the weights sum to. `matching_weights.WEIGHT_TOTAL`, duplicated for the
#: same reason as the enum above.
WEIGHT_TOTAL = 100


def _component_values_clause() -> str:
    return ",\n                ".join(
        f"('{component}', result.{column})" for component, column in COMPONENT_SCORE_COLUMNS
    )


def upgrade() -> None:
    # Nothing has written a score that survives to a reader yet — `0017` deleted
    # what there was and the sweep has only run against test databases — so this
    # deletes nothing today. See the module docstring for why it is a delete.
    op.execute("DELETE FROM match_results")

    op.create_table(
        "match_component_assessments",
        sa.Column("match_result_id", sa.UUID(), nullable=False),
        sa.Column(
            "component",
            # `postgresql.ENUM` rather than `sa.Enum`: only the dialect type
            # honours `create_type=False`, and `match_component` is `0016`'s
            # type. `sa.Enum` re-emits `CREATE TYPE` and the migration dies on
            # "type already exists".
            postgresql.ENUM(*MATCH_COMPONENT_VALUES, name="match_component", create_type=False),
            nullable=False,
        ),
        sa.Column("assessable", sa.Boolean(), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            UTCDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "length(btrim(why)) > 0",
            name=op.f("ck_match_component_assessments_a_reason_is_never_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["match_result_id"],
            ["match_results.id"],
            name=op.f("fk_match_component_assessments_match_result_id_match_results"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_component_assessments")),
        sa.UniqueConstraint(
            "match_result_id",
            "component",
            name="uq_match_component_assessments_result_component",
        ),
    )

    # One function, two triggers, because the violation is reachable from both
    # tables — `0016`'s evidence guard has the same shape for the same reason. It
    # re-reads the score row rather than trusting a deferred trigger's queued
    # NEW record, which may have been updated or deleted since.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION nightshift_components_are_assessed(result_id uuid)
        RETURNS void AS $$
        DECLARE
            result match_results%ROWTYPE;
            stated integer;
            unassessable integer;
            wrong record;
        BEGIN
            SELECT * INTO result FROM match_results WHERE id = result_id;
            IF NOT FOUND THEN
                -- Deleted later in the same transaction. Nothing to assert.
                RETURN;
            END IF;

            SELECT count(*), count(*) FILTER (WHERE NOT assessable)
              INTO stated, unassessable
              FROM match_component_assessments
             WHERE match_result_id = result.id;

            IF stated <> {len(COMPONENT_SCORE_COLUMNS)} THEN
                RAISE EXCEPTION
                    'match_result % states % of % components; a score is all of them or it is not a score',
                    result.id, stated, {len(COMPONENT_SCORE_COLUMNS)};
            END IF;

            SELECT scored.component, scored.score INTO wrong
            FROM (VALUES
                {_component_values_clause()}
            ) AS scored(component, score)
            JOIN match_component_assessments a
              ON a.match_result_id = result.id
             AND a.component::text = scored.component
            WHERE NOT a.assessable AND scored.score <> 0
            ORDER BY scored.component
            LIMIT 1;
            IF FOUND THEN
                RAISE EXCEPTION
                    'match_result % could not assess % and scored % for it',
                    result.id, wrong.component, wrong.score;
            END IF;

            -- The weights sum to {WEIGHT_TOTAL} and each is at least 1, both
            -- asserted on load, so a full denominator and a named unassessable
            -- component cannot both be true.
            IF unassessable = 0 AND result.assessed_out_of <> {WEIGHT_TOTAL} THEN
                RAISE EXCEPTION
                    'match_result % assessed every component and is scored out of %, not %',
                    result.id, result.assessed_out_of, {WEIGHT_TOTAL};
            END IF;
            IF unassessable > 0 AND result.assessed_out_of >= {WEIGHT_TOTAL} THEN
                RAISE EXCEPTION
                    'match_result % could not assess % components and is still scored out of %',
                    result.id, unassessable, result.assessed_out_of;
            END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_score_needs_assessments()
        RETURNS trigger AS $$
        BEGIN
            PERFORM nightshift_components_are_assessed(NEW.id);
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION nightshift_assessment_change_rechecks_the_score()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                PERFORM nightshift_components_are_assessed(OLD.match_result_id);
                RETURN NULL;
            END IF;
            PERFORM nightshift_components_are_assessed(NEW.match_result_id);
            IF TG_OP = 'UPDATE' AND NEW.match_result_id <> OLD.match_result_id THEN
                PERFORM nightshift_components_are_assessed(OLD.match_result_id);
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER match_results_components_are_assessed "
        "AFTER INSERT OR UPDATE ON match_results "
        "DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_score_needs_assessments()"
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER match_component_assessments_recheck_the_score "
        "AFTER INSERT OR UPDATE OR DELETE ON match_component_assessments "
        "DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_assessment_change_rechecks_the_score()"
    )


def downgrade() -> None:
    # Symmetric to the upgrade: a score whose assessments have just been dropped
    # is a breakdown that has lost half of itself, and there is no honest way to
    # put the sentences back.
    op.execute("DELETE FROM match_results")

    op.execute(
        "DROP TRIGGER IF EXISTS match_component_assessments_recheck_the_score "
        "ON match_component_assessments"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS match_results_components_are_assessed ON match_results"
    )
    for function in (
        "nightshift_assessment_change_rechecks_the_score()",
        "nightshift_score_needs_assessments()",
        "nightshift_components_are_assessed(uuid)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}")
    op.drop_table("match_component_assessments")
    # No `DROP TYPE`: `match_component` is `0016`'s and `match_evidence` still
    # uses it. Dropping an enum this revision did not create is how a downgrade
    # takes something with it that it does not own.
