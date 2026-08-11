"""The office table, and the first enum value this project has ever had to add.

Revision ID: 0020_company_locations
Revises: 0019_match_penalties
Create Date: 2026-08-11

M4a Task 2. PRODUCT-SPEC §6.6 specified `company_locations` and nothing built
it for four milestones, because nothing needed it. M4a Task 1 gave it a reason
that is a measurement rather than a preference: **no ATS posting names a
street.** 0 of 247, across 139 distinct location strings, 10 location-bearing
fields and all three providers — including Ashby's structured
`address.postalAddress`, whose key set is only ever some subset of
`{addressCountry, addressLocality, addressRegion}`.

Under invariant I1 that decides where a building can come from. A job cannot
place itself, because its own text tops out at a city name, and a city name
places nothing. So a beacon reaches a building only by inheriting the office of
the company that posted it, and this table is the set of offices that exist.

**`confirmed_by` and `confirmed_at` are NOT NULL and that is the point.**
`city.md` §4.4 ruled out the alternatives — scraping is out on policy
(`CLAUDE.md` §8), and OSM and Wikidata are of uneven quality and unknown
currency, good enough to propose and never to confirm. A row here means a human
wrote an address down. Making the provenance columns mandatory is what turns *a
lit building is a verified fact* from a habit into a property of the schema.

`ck_company_locations_verified_requires_a_street_address` is the other half.
`verified` is the confidence that puts a beacon on one specific building, and
the only input that earns it is a street. Without this constraint a row
geocoded from "New York, NY" could be stored as `verified` and the renderer
would place it on whichever building the city centroid happened to land in —
which is precisely the fabrication I1 exists to forbid, arriving through the
one door the existing `confidence_matches_coordinates` check leaves open. That
check asks whether coordinates are present. This one asks whether they could
have been earned.

---

**The enum value, and why the downgrade is long.**

`resolution_method` gains `company_office`: a job sitting at its employer's
confirmed office because it named no address of its own. It is deliberately
distinct from the rung that resolved the office itself, because *"this posting
stated this address"* and *"this posting stated a city, and its employer's
office is here"* are different claims and the detail panel has to be able to say
which one placed the beacon.

This is the first time this project has added a value to an existing PostgreSQL
enum, so there was no precedent in `migrations/versions/` to copy. PostgreSQL
has `ALTER TYPE ... ADD VALUE` and **no** corresponding `DROP VALUE`, so a
reversible migration cannot simply undo it. The two options were:

1. `ADD VALUE IF NOT EXISTS` on the way up and leave the value behind on the way
   down. Short, and makes up/down/up idempotent — but the downgrade stops being
   an inverse, and the next person to add an enum value copies a migration that
   quietly does not reverse itself.
2. Recreate the type on the way down, converting every column that uses it.
   Longer, and actually reversible.

This takes (2). `resolution_method` is used by `job_locations` as well as by
this table, so the downgrade drops this table first and then converts the one
column that remains. **It will fail if any surviving row uses `company_office`**,
which is correct: you cannot downgrade past data that needs the value, and a
migration that silently rewrote those rows to something else would be losing
information to make a command succeed.
"""

from __future__ import annotations

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import nightshift.db.types

revision: str = "0020_company_locations"
down_revision: str | None = "0019_match_penalties"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The values `resolution_method` held before this migration, in order. Written
# out rather than imported from the enum class: a migration describes the
# database at a point in time, and one that imports today's code stops
# describing history the moment the code moves.
_RESOLUTION_METHOD_BEFORE = (
    "not_attempted",
    "source_text_parse",
    "nyc_geosearch",
    "nominatim",
    "neighborhood_centroid",
    "manual",
)
_ADDED_VALUE = "company_office"

# Both enums already exist in the database. `create_type=False` stops the
# CREATE TABLE below from trying to create them a second time.
_location_confidence = postgresql.ENUM(
    "verified",
    "approximate",
    "city_only",
    "remote",
    "unknown",
    name="location_confidence",
    create_type=False,
)
_resolution_method = postgresql.ENUM(
    *_RESOLUTION_METHOD_BEFORE,
    _ADDED_VALUE,
    name="resolution_method",
    create_type=False,
)


def upgrade() -> None:
    # ADD VALUE must land before any DDL that references it. PostgreSQL 12+
    # permits this inside a transaction; what it forbids is *using* the new
    # value in the same transaction, which nothing here does — the column's
    # server default is `not_attempted`.
    op.execute(f"ALTER TYPE resolution_method ADD VALUE IF NOT EXISTS '{_ADDED_VALUE}'")

    op.create_table(
        "company_locations",
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("street_address", sa.String(length=300), nullable=True),
        sa.Column("city", sa.String(length=200), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("latitude", sa.NUMERIC(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.NUMERIC(precision=9, scale=6), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                geometry_type="POINT",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
            ),
            nullable=True,
        ),
        sa.Column(
            "location_confidence",
            _location_confidence,
            server_default="unknown",
            nullable=False,
        ),
        sa.Column(
            "resolution_method",
            _resolution_method,
            server_default="not_attempted",
            nullable=False,
        ),
        sa.Column("resolved_at", nightshift.db.types.UTCDateTime(timezone=True), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("confirmed_by", sa.String(length=200), nullable=False),
        sa.Column("confirmed_at", nightshift.db.types.UTCDateTime(timezone=True), nullable=False),
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
            "\n            CASE\n                WHEN location_confidence IN ('verified', 'approximate')\n                    THEN latitude IS NOT NULL\n                WHEN location_confidence IN ('city_only', 'remote', 'unknown')\n                    THEN latitude IS NULL\n            END\n            ",
            name=op.f("ck_company_locations_confidence_matches_coordinates"),
        ),
        sa.CheckConstraint(
            "location_confidence <> 'verified' OR street_address IS NOT NULL",
            name=op.f("ck_company_locations_verified_requires_a_street_address"),
        ),
        sa.CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name=op.f("ck_company_locations_coordinates_are_paired"),
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude BETWEEN -90 AND 90)",
            name=op.f("ck_company_locations_latitude_in_range"),
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude BETWEEN -180 AND 180)",
            name=op.f("ck_company_locations_longitude_in_range"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_company_locations_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_locations")),
    )
    op.create_index(
        "ix_company_locations_company_id", "company_locations", ["company_id"], unique=False
    )
    op.create_index(
        "ix_company_locations_geom",
        "company_locations",
        ["geom"],
        unique=False,
        postgresql_using="gist",
    )
    op.create_index(
        "ix_company_locations_location_confidence",
        "company_locations",
        ["location_confidence"],
        unique=False,
    )
    # One primary office per company. A second would make "the building" a
    # question the renderer has to answer arbitrarily.
    op.create_index(
        "uq_company_locations_one_primary",
        "company_locations",
        ["company_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_company_locations_one_primary",
        table_name="company_locations",
        postgresql_where=sa.text("is_primary"),
    )
    op.drop_index("ix_company_locations_location_confidence", table_name="company_locations")
    op.drop_index(
        "ix_company_locations_geom", table_name="company_locations", postgresql_using="gist"
    )
    op.drop_index("ix_company_locations_company_id", table_name="company_locations")
    op.drop_table("company_locations")

    # PostgreSQL has no DROP VALUE, so the type is rebuilt without it and every
    # remaining column converted across. `job_locations` is the only one left
    # once the table above is gone.
    #
    # The USING cast fails loudly if a surviving row holds `company_office`.
    # That is the intended behaviour: the value is in use, so the schema that
    # lacks it is not a schema this data fits.
    values = ", ".join(f"'{value}'" for value in _RESOLUTION_METHOD_BEFORE)
    op.execute("ALTER TYPE resolution_method RENAME TO resolution_method_old")
    op.execute(f"CREATE TYPE resolution_method AS ENUM ({values})")
    op.execute("ALTER TABLE job_locations ALTER COLUMN resolution_method DROP DEFAULT")
    op.execute(
        "ALTER TABLE job_locations ALTER COLUMN resolution_method "
        "TYPE resolution_method USING resolution_method::text::resolution_method"
    )
    op.execute(
        "ALTER TABLE job_locations ALTER COLUMN resolution_method "
        "SET DEFAULT 'not_attempted'::resolution_method"
    )
    op.execute("DROP TYPE resolution_method_old")
