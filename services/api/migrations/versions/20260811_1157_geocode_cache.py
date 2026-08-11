"""Every address ever geocoded, and the outage that must never become one.

Revision ID: 0022_geocode_cache
Revises: 0021_company_location_bin
Create Date: 2026-08-11 11:57:25.538871+00:00


M4a Task 4. A4 asks for a permanent cache keyed on the normalised address, and
this is it — a table rather than a dict, because it has to survive a restart and
because it has to be *inspectable*. When somebody says a beacon sits on the
wrong building, the question is what the provider actually returned for that
string on that day, and a cache nobody can query cannot answer it.

**The constraint worth reading is `an_outage_is_never_cached`**, and it is
invariant I3's reasoning applied one subsystem over.

"We asked, and NYC has no such address" is an answer. It will not change
tomorrow, and re-asking it every poll spends a request to learn nothing, so it
is cached like any other result. "The provider was unreachable" is not an answer
about the address at all. Caching it would turn one bad afternoon into a
permanent refusal to place a building that was always placeable — the geocoding
form of closing a listing because a source timed out, which is what I3 exists to
forbid.

`a_row_is_a_hit_or_a_miss` is the smaller guard beside it: a row carries
coordinates or a refusal, never both and never neither. Without it a bug that
wrote both would produce a row whose meaning depends on which column the reader
happened to look at first.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import nightshift.db.types

revision: str = "0022_geocode_cache"
down_revision: str | None = "0021_company_location_bin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "geocode_cache",
        sa.Column("query", sa.String(length=500), nullable=False),
        sa.Column("normalized_query", sa.String(length=500), nullable=False),
        sa.Column(
            "resolution_method",
            postgresql.ENUM(
                "not_attempted",
                "source_text_parse",
                "nyc_geosearch",
                "nominatim",
                "neighborhood_centroid",
                "manual",
                "company_office",
                name="resolution_method",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("latitude", sa.NUMERIC(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.NUMERIC(precision=9, scale=6), nullable=True),
        sa.Column(
            "location_confidence",
            postgresql.ENUM(
                "verified",
                "approximate",
                "city_only",
                "remote",
                "unknown",
                name="location_confidence",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("building_id", sa.String(length=20), nullable=True),
        sa.Column("matched_text", sa.String(length=500), nullable=True),
        sa.Column("refusal", sa.String(length=50), nullable=True),
        sa.Column("resolved_at", nightshift.db.types.UTCDateTime(timezone=True), nullable=False),
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
            "refusal IS NULL OR refusal <> 'provider_unavailable'",
            name=op.f("ck_geocode_cache_an_outage_is_never_cached"),
        ),
        sa.CheckConstraint(
            "(latitude IS NULL) <> (refusal IS NULL)",
            name=op.f("ck_geocode_cache_a_row_is_a_hit_or_a_miss"),
        ),
        sa.CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name=op.f("ck_geocode_cache_coordinates_are_paired"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_geocode_cache")),
    )
    op.create_index(
        "uq_geocode_cache_query",
        "geocode_cache",
        ["normalized_query", "resolution_method"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_geocode_cache_query", table_name="geocode_cache")
    op.drop_table("geocode_cache")
