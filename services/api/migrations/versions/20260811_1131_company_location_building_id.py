"""The building the address is in, which arrives free and was not planned for.

Revision ID: 0021_company_location_bin
Revises: 0020_company_locations
Create Date: 2026-08-11 11:31

M4a Task 3. One column, and it exists because recording a fixture turned up
something the design had not accounted for.

AMENDMENTS A4 says to join company locations to the NYC building footprints by
BIN, and reads as though that join is work for PostGIS: store the point, then
find the footprint polygon containing it. The first recorded NYC GeoSearch
response shows the join key arriving in the geocode itself —
`addendum.pad.bin = "1087186"` for 620 Eighth Avenue, alongside the coordinates
and at no extra request.

That is better than the planned path rather than merely cheaper. A BIN is an
exact key; point-in-polygon is a geometric inference, and it is least reliable
in exactly the case this product cares most about — a Manhattan tower whose
footprint abuts three others, where a metre of geocoder error picks the wrong
neighbour and nothing downstream can tell. M4b's extrusion layer joins on this
column, and point-in-polygon becomes the fallback for rows that somehow have
coordinates without one.

**Nullable, and deliberately outside
`ck_company_locations_verified_requires_a_street_address`.** A real street
address outside NYC would be `verified` with no BIN, because the PAD only knows
about the five boroughs — and on the day this product covers a second city that
has to still be true. Tying `verified` to a BIN would quietly make the
invariant mean "in New York" instead of "somebody confirmed a street".
:28.320967+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0021_company_location_bin"
down_revision: str | None = "0020_company_locations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "company_locations", sa.Column("building_id", sa.String(length=20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("company_locations", "building_id")
