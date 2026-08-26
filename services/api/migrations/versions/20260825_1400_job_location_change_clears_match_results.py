"""A location change clears the job's scores.

`docs/architecture/matching.md` §4.2 names *a new or changed job* as one of the
three things that invalidate a stored score, and `matching.py`'s module
docstring records that it is served by triggers rather than by a sweep. Four
were written at M3b Task 2 — on `jobs.description_text`, `job_requirements`,
`user_skills` and `user_projects`.

**`job_locations` was not among them, and the score has a location component.**
`scoring.py` reads a job's cities and its remote policy, worth up to 10 points,
and emits evidence rows naming them. So a job whose locations changed kept a
stored score computed against the old ones, and `current_result_for` filters on
`ruleset_version` alone — it has no way to know the inputs moved underneath a
version that did not. §4.2's own principle, *a stale result is never silently
served*, was being violated by the one route the design did not cover.

Found by M6a's gazetteer backfill (ADR 0040), which changed 111 location rows
and left **218 stored results** describing cities those jobs no longer state —
several of them literally reading *"this posting states no location"* about a
job now known to be in Chicago. The defect predates that backfill: the
2026-08-24 parenthetical repair changed 80 rows the same way and left the same
kind of wreckage, unnoticed.

The existing trigger function needs no change. It reads `job_id` off NEW/OLD and
deletes that job's results, and `job_locations` has a `job_id` — so this is one
more table on a mechanism that already works, not a new mechanism.

**INSERT included, unlike `user_skills`.** That trigger is UPDATE/DELETE-only
because an added skill can only make a score too low, never wrong. A location is
not like that: adding one to a single-location job changes what the location
component compares against, and ingestion writes locations one row at a time for
a job whose score, if any, was computed before the first of them landed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0029_job_location_clears_scores"
down_revision: str | None = "0028_gazetteer_resolution_method"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIGGER = "job_locations_change_clears_match_results"


def upgrade() -> None:
    op.execute(
        f"CREATE TRIGGER {_TRIGGER} "
        "AFTER INSERT OR UPDATE OR DELETE ON job_locations "
        "FOR EACH ROW EXECUTE FUNCTION nightshift_match_results_follow_the_job()"
    )
    # The one-time repair of what the gap already let through. A stale row is
    # indistinguishable from a fresh one by any column, so this cannot select
    # only the damaged ones — but deleting a *current* score costs a recompute
    # and nothing else, while keeping a stale one serves a number computed
    # against a city the job no longer states. Scores are derived data; the
    # sweep in `recompute_pending` rebuilds them within the minute.
    op.execute(
        "DELETE FROM match_results WHERE job_id IN "
        "(SELECT job_id FROM job_locations WHERE resolution_method = 'gazetteer')"
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON job_locations")
