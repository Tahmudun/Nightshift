"""rename ten check constraints the naming convention prefixed twice

``NAMING_CONVENTION`` in ``nightshift/db/base.py`` renders a check constraint as
``ck_%(table_name)s_%(constraint_name)s``. A model declaring
``name="closed_at_matches_status"`` therefore means
``ck_jobs_closed_at_matches_status``.

Five migrations — ``0001``, ``0002``, ``0009`` among them — wrote the *rendered*
name into ``name=`` instead of the bare one, and ``op.create_table`` applies the
convention to whatever it is given. The database has carried
``ck_jobs_ck_jobs_closed_at_matches_status`` since 2026-07-29 while the metadata
went on calling it ``ck_jobs_closed_at_matches_status``.

**The constraints were never wrong, only misnamed**, which is why no behavioural
test noticed: each one enforces exactly what it was written to enforce. What was
wrong is that no migration can reliably drop or alter a constraint whose name
the models do not know — and for two of the ten, nobody could even predict the
name, because the doubled prefix pushed them past PostgreSQL's 63-character
identifier limit and SQLAlchemy truncated them with a hash suffix
(``ck_job_locations_ck_job_locations_confidence_matches_co_b8be``).

Found by CI, not locally, and the gap is worth recording: alembic did not
compare check constraints during autogenerate until 1.19.0. CI installs
unpinned, picked that release up on 2026-08-05, and the drift probe emitted
forty operations. The developer venv was on 1.18.5 and emitted zero. Both were
measured before this migration was written.

``tests/test_check_constraint_names.py`` is the guard that does not depend on
an alembic version — it reads ``pg_constraint`` and ``Base.metadata`` directly.

Renaming is metadata-only in PostgreSQL: ``ALTER TABLE ... RENAME CONSTRAINT``
does not revalidate rows and does not take a long lock on a table this size.
No data moves and no check changes meaning.

Revision ID: 0012_check_constraint_names
Revises: 0011_job_requirements
Create Date: 2026-08-05 18:10:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_check_constraint_names"
down_revision: str | None = "0011_job_requirements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: ``(table, name written by the old migration, name the models declare)``.
#:
#: Derived by comparing ``pg_constraint`` against ``Base.metadata`` rather than
#: transcribed by hand — this project has twice shipped a defect that came from
#: hand-copying names between two places that never meet (see
#: ``tests/test_enum_parity.py``).
RENAMES: tuple[tuple[str, str, str], ...] = (
    (
        "users",
        "ck_users_ck_users_graduation_month_is_a_month",
        "ck_users_graduation_month_is_a_month",
    ),
    (
        "users",
        "ck_users_ck_users_graduation_month_needs_a_year",
        "ck_users_graduation_month_needs_a_year",
    ),
    (
        "ingestion_runs",
        "ck_ingestion_runs_ck_ingestion_runs_finished_at_matches_status",
        "ck_ingestion_runs_finished_at_matches_status",
    ),
    (
        "jobs",
        "ck_jobs_ck_jobs_closed_at_matches_status",
        "ck_jobs_closed_at_matches_status",
    ),
    (
        "jobs",
        "ck_jobs_ck_jobs_salary_range_ordered",
        "ck_jobs_salary_range_ordered",
    ),
    # The two SQLAlchemy truncated. The old names end in a hash of the full
    # name, so they are reproducible but not readable, and not guessable from
    # the model.
    (
        "job_locations",
        "ck_job_locations_ck_job_locations_confidence_matches_co_b8be",
        "ck_job_locations_confidence_matches_coordinates",
    ),
    (
        "job_locations",
        "ck_job_locations_ck_job_locations_coordinates_are_paired",
        "ck_job_locations_coordinates_are_paired",
    ),
    (
        "job_locations",
        "ck_job_locations_ck_job_locations_latitude_in_range",
        "ck_job_locations_latitude_in_range",
    ),
    (
        "job_locations",
        "ck_job_locations_ck_job_locations_longitude_in_range",
        "ck_job_locations_longitude_in_range",
    ),
    (
        "job_source_links",
        "ck_job_source_links_ck_job_source_links_match_confidenc_c1de",
        "ck_job_source_links_match_confidence_is_a_probability",
    ),
)


def _rename(table: str, old: str, new: str) -> None:
    op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old}" TO "{new}"')


def upgrade() -> None:
    for table, old, new in RENAMES:
        _rename(table, old, new)


def downgrade() -> None:
    """Reversible, and deliberately so even though the old names are worse.

    CLAUDE.md §7 asks every migration to work in both directions and CI runs
    ``upgrade → downgrade base → upgrade`` on every push, so a one-way rename
    would fail the second upgrade with "constraint does not exist".
    """
    for table, old, new in RENAMES:
        _rename(table, new, old)
