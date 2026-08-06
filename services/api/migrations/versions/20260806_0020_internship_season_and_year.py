"""jobs.internship_season and jobs.internship_year

Revision ID: 0015_internship_season
Revises: 0014_profile_experience
Create Date: 2026-08-06 00:20:11.402887+00:00

PRODUCT-SPEC §6.9 names a single `internship_season` field. This is two columns,
and the corpus is the reason rather than a preference. Across the 153 recorded
postings, 19 are internships by title and:

    a season in the title        8 / 19     every one of them "Summer"
    a year in the title         10 / 19
    both                         8 / 19

**Two postings state a year and no season** — *"Software Engineer – 2027
Internship Program (June Start)"* and *"2026 Warsaw MI Data – Web Scraping
Internship"*. A single `summer_2027` value can hold those only by inventing the
season or by discarding the year, and neither is something to do to a fact an
employer stated. So the season keeps the spec's name and the year sits beside
it, both nullable, null meaning the posting did not say.

`internship_year` is a SmallInteger rather than a date or a string: it is a
calendar year and nothing else. There is deliberately **no check constraint
bounding it to a plausible window.** "Plausible" can only mean "near now", which
would make the same posting classify differently next year and break M3's
determinism criterion — and it guards nothing observed, since every year stated
in a corpus internship title is 2026 or 2027. The implausible years (2011, 2015,
2029) all occur in *descriptions*, which the rule refuses to read at all.

**Autogenerate got this wrong in both directions, and it was run rather than
predicted.** The draft of this docstring claimed the opposite — that an
`add_column` introducing a new `sa.Enum` would emit its `CREATE TYPE` because
the type is new rather than swapped in under an existing column. That was a
guess, so it was checked: autogenerate's version was generated, applied, and

    sqlalchemy.exc.ProgrammingError: type "internship_season" does not exist
    [SQL: ALTER TABLE jobs ADD COLUMN internship_season internship_season]

which is M2c's finding 2 for the third time in this project, and 0013's for the
second. The downgrade it wrote emitted no `DROP TYPE` either, which is M2c's
finding 3. Hence the explicit `.create()` and `.drop()` below.

The pattern was known, written down, and cited in the file directly above this
one — and knowing it still did not prevent writing the wrong sentence. Only
running it did.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_internship_season"
down_revision: str | None = "0014_profile_experience"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Duplicated from `nightshift.db.base.InternshipSeason` on purpose. A migration
#: that imports a model stops describing the schema as of its own revision and
#: starts describing today's. `test_enum_vocabularies_agree` is the defence that
#: makes the copy safe.
INTERNSHIP_SEASON_VALUES = (
    "summer",
    "fall",
    "winter",
    "spring",
)

_INTERNSHIP_SEASON = sa.Enum(*INTERNSHIP_SEASON_VALUES, name="internship_season")


def upgrade() -> None:
    _INTERNSHIP_SEASON.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "jobs",
        sa.Column("internship_season", _INTERNSHIP_SEASON, nullable=True),
    )
    op.add_column("jobs", sa.Column("internship_year", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "internship_year")
    op.drop_column("jobs", "internship_season")
    _INTERNSHIP_SEASON.drop(op.get_bind(), checkfirst=True)
