"""Every check constraint the models declare exists in the database, by name.

This guards a defect that shipped in M0 and stayed invisible for eleven
migrations. `NAMING_CONVENTION` renders ``ck_%(table_name)s_%(constraint_name)s``,
so a model declaring ``name="closed_at_matches_status"`` means
``ck_jobs_closed_at_matches_status``. Five migrations wrote the *rendered* name
into ``name=`` instead of the bare one, and ``op.create_table`` applied the
convention on top — producing ``ck_jobs_ck_jobs_closed_at_matches_status`` in
the database while the metadata went on calling it something else.

**Nothing could see it.** The constraints worked, so every behavioural test
passed. Alembic did not compare check constraints during autogenerate until
1.19.0, so the drift check was blind to it too, and CI only found it because
`pip install -e` is unpinned and picked that release up. A guard that depends on
a library's autogenerate behaviour is not a guard; this one reads the database
and the metadata directly and holds on any alembic version.

Two of the ten were long enough that the doubled prefix pushed them past
PostgreSQL's 63-character identifier limit, so SQLAlchemy truncated them and
appended a hash — ``ck_job_locations_ck_job_locations_confidence_matches_co_b8be``.
A name nobody can predict is a name no migration can reliably drop.
"""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint, text
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import Base
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.asyncio(loop_scope="session")]


def _declared_check_constraints() -> dict[str, set[str]]:
    """table -> the check constraint names the models expect, convention applied."""
    declared: dict[str, set[str]] = {}
    for table in Base.metadata.sorted_tables:
        names = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint) and constraint.name is not None
        }
        if names:
            declared[table.name] = {str(name) for name in names}
    return declared


async def _actual_check_constraints(session: AsyncSession) -> dict[str, set[str]]:
    rows = (
        await session.execute(
            text(
                "SELECT conrelid::regclass::text AS tbl, conname "
                "FROM pg_constraint WHERE contype = 'c'"
            )
        )
    ).all()
    actual: dict[str, set[str]] = {}
    for table_name, constraint_name in rows:
        actual.setdefault(str(table_name), set()).add(str(constraint_name))
    return actual


async def test_every_declared_check_constraint_exists_under_its_declared_name(
    db_session: AsyncSession,
) -> None:
    """The assertion the drift check could not make on its own.

    Failing here means a migration and a model disagree about what a constraint
    is called. The constraint may well be doing its job — that is exactly why
    no other test notices.
    """
    declared = _declared_check_constraints()
    actual = await _actual_check_constraints(db_session)

    missing: list[str] = []
    for table_name, names in declared.items():
        for name in sorted(names):
            if name not in actual.get(table_name, set()):
                missing.append(f"{table_name}.{name}")

    assert missing == [], (
        "these check constraints are declared by the models but absent from the "
        f"database under that name: {missing}"
    )


async def test_no_check_constraint_carries_its_prefix_twice(
    db_session: AsyncSession,
) -> None:
    """Names the specific failure mode, so a regression reads as itself.

    The test above would catch this too, but it reports the *absence* of the
    right name rather than the presence of the wrong one, and the wrong one is
    the clue that says which migration to look at.
    """
    actual = await _actual_check_constraints(db_session)
    doubled = [
        f"{table_name}.{name}"
        for table_name, names in actual.items()
        for name in sorted(names)
        if name.startswith(f"ck_{table_name}_ck_{table_name}_")
    ]
    assert doubled == [], f"the naming convention was applied twice to: {doubled}"
