"""Where a role is drawn on the city, decided once, in one place.

`office_loading.py` ends with the sentence this module exists to honour: the
inheritance of an employer's office is **a read-time join, not a stored fact**,
and `ResolutionMethod.COMPANY_OFFICE` is what that join reports rather than
something written to `job_locations`. It deferred building it to M4c on the
grounds that a renderer's data path shaped before the renderer comes out wrong.

Two functions, split along the line that matters for testing:

- ``resolve_placement`` is pure. The decision *"is this role on a building?"*
  is a function of two rows and needs no database to check, so every rule below
  is covered by a test that runs in milliseconds.
- ``primary_offices`` is the join, and it is the only part that touches
  Postgres.

**The invariant, restated as code.** I1 says a job whose location text is
"New York, NY" does not get placed on a building — and `city.md` §4.1 measured
that *every* posting in this corpus says exactly that. So nothing in this file
can produce a coordinate from a job alone. A coordinate arrives from one of
exactly two places:

1. The posting stated an address of its own and a geocoder resolved it. Zero
   postings in the corpus do; the path exists because the schema permits it and
   a path that exists untested is a path that is wrong.
2. The posting's employer has an office **a human confirmed** (§4.4), and the
   placement says so — ``inherited`` is true, ``office_label`` names it, and
   ``stated`` still carries what the posting itself claimed.

The distance between those two is the whole of §4.4, and it is why ``inherited``
is a field rather than an implementation detail. ``location_confidence``
describes the *coordinate* — an office resolved by GeoSearch really is verified.
It does not describe the claim that this role sits at it. A consumer that
collapses those two sentences is reporting a fact the product does not have,
and the detail panel is required to keep them apart.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import LocationConfidence, RemotePolicy, ResolutionMethod
from nightshift.db.models import CompanyLocation, Job, JobLocation


class PlacementKind(enum.StrEnum):
    """What the renderer is permitted to draw, and there is no fourth value.

    These are `city.md` §6's three spatial treatments, named for the treatment
    rather than for the data, because the renderer chooses a mesh from this and
    nothing else. A kind that had to be re-derived from a confidence plus a
    coordinate plus a remote policy at draw time would be re-derived differently
    in the two places that draw.
    """

    #: A beacon standing on a specific structure. Earned only by `verified`.
    BUILDING = "building"
    #: A translucent radius. §6: an area, never a point.
    AREA = "area"
    #: Untethered, floating, with no line drawn to any ground (§4.8). On this
    #: corpus this is the default rather than the exception.
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Placement:
    """One role's position, with everything needed to explain it.

    Frozen because a placement is an answer about a moment, and a renderer that
    can edit one is a renderer that can disagree with the database it came from.
    """

    kind: PlacementKind
    latitude: float | None
    longitude: float | None
    #: NYC's Building Identification Number, when the office carried one. The
    #: extrusion layer joins on this key rather than guessing which of four
    #: abutting footprints a point landed in (§4.3.2). Null is normal: a
    #: verified address outside NYC has no BIN, and point-in-polygon is the
    #: documented fallback.
    building_id: str | None
    #: The precision of the *coordinate*. Never the confidence of the claim
    #: that this role is at it — see the module docstring.
    location_confidence: LocationConfidence
    resolution_method: ResolutionMethod
    #: Exactly what the posting said about where it is, verbatim, or None when
    #: it said nothing at all. Shown next to an inherited placement so the two
    #: claims can be read together.
    stated: str | None
    #: True when the coordinate came from the employer rather than the posting.
    inherited: bool
    office_label: str | None
    office_address: str | None

    def __post_init__(self) -> None:
        """I1 in the constructor, because a wrong placement must not exist.

        A test can only check the cases it thought of. This checks all of them,
        including the ones a future caller invents — and it runs on every
        placement the API ever serialises, which is the property that matters
        when the alternative is a beacon standing on a building nobody
        confirmed.
        """
        has_point = self.latitude is not None and self.longitude is not None

        if self.kind is PlacementKind.UNRESOLVED:
            if has_point:
                raise ValueError("an unresolved placement cannot carry coordinates")
            if self.building_id is not None:
                raise ValueError("an unresolved placement cannot name a building")
            return

        if not has_point:
            raise ValueError(f"a {self.kind} placement needs both coordinates")

        if self.kind is PlacementKind.BUILDING:
            if self.location_confidence is not LocationConfidence.VERIFIED:
                raise ValueError(
                    "only a verified coordinate can stand on a building; "
                    f"got {self.location_confidence}"
                )
        elif self.building_id is not None:
            # A BIN is not a promotion. An approximate point that happens to
            # have landed a building number is still an approximation, and
            # letting it keep the key invites a join that draws it as a tower.
            raise ValueError("only a building placement may name a building")


#: Coordinates exist at these confidences and nowhere else — enforced by
#: `confidence_matches_coordinates` on both location tables, so this is a
#: restatement rather than a second opinion.
_PLACEABLE = {
    LocationConfidence.VERIFIED: PlacementKind.BUILDING,
    LocationConfidence.APPROXIMATE: PlacementKind.AREA,
}


_NOWHERE = Placement(
    kind=PlacementKind.UNRESOLVED,
    latitude=None,
    longitude=None,
    building_id=None,
    location_confidence=LocationConfidence.UNKNOWN,
    resolution_method=ResolutionMethod.NOT_ATTEMPTED,
    stated=None,
    inherited=False,
    office_label=None,
    office_address=None,
)


def resolve_placement(job: Job, *, office: CompanyLocation | None) -> Placement:
    """Decide where one role is drawn. Reads two rows, writes nothing.

    Order of preference, and it is not arbitrary: **what the posting said beats
    what its employer's office says**, even when the office is the more precise
    of the two. Preferring the office would silently upgrade a posting's own
    approximate claim into a building by way of a different row, which is the
    promotion §4.4 refuses.
    """
    primary = _primary_location(job)

    stated = primary.raw_text if primary is not None else None

    # 1. The posting placed itself. Zero postings in this corpus do.
    if primary is not None and primary.latitude is not None and primary.longitude is not None:
        kind = _PLACEABLE.get(primary.location_confidence)
        if kind is not None:
            return Placement(
                kind=kind,
                latitude=float(primary.latitude),
                longitude=float(primary.longitude),
                # `job_locations` carries no BIN — a posting-stated address is
                # geocoded to a point, and §4.3.2's key arrives only with a
                # confirmed office. Point-in-polygon is the fallback here.
                building_id=None,
                location_confidence=primary.location_confidence,
                resolution_method=primary.resolution_method,
                stated=stated,
                inherited=False,
                office_label=None,
                office_address=None,
            )

    # 2. A fully-remote role is not in the building, and drawing it there says
    # it is. The office is a real verified fact and the coordinate would be
    # true; the sentence it puts on screen would not be. This is the one rule
    # in this module that is a product judgement rather than a restatement of
    # I1, and `remote` being its own `location_confidence` value is the spec
    # already saying so.
    if job.remote_policy is RemotePolicy.REMOTE:
        return _unresolved(primary)

    # 3. The employer's confirmed office, said out loud.
    if office is None or office.latitude is None or office.longitude is None:
        return _unresolved(primary)

    kind = _PLACEABLE.get(office.location_confidence)
    if kind is None:
        return _unresolved(primary)

    return Placement(
        kind=kind,
        latitude=float(office.latitude),
        longitude=float(office.longitude),
        building_id=office.building_id if kind is PlacementKind.BUILDING else None,
        location_confidence=office.location_confidence,
        resolution_method=ResolutionMethod.COMPANY_OFFICE,
        stated=stated,
        inherited=True,
        office_label=office.label,
        office_address=_address_of(office),
    )


def _unresolved(primary: JobLocation | None) -> Placement:
    """Nowhere, keeping whatever the posting did manage to say.

    The confidence is the posting's own — `city_only` and `remote` are
    different facts about a role and the legend distinguishes them, so
    flattening both to `unknown` would lose the difference on the way to the
    layer that has to draw it.
    """
    if primary is None:
        return _NOWHERE
    return Placement(
        kind=PlacementKind.UNRESOLVED,
        latitude=None,
        longitude=None,
        building_id=None,
        location_confidence=primary.location_confidence,
        resolution_method=primary.resolution_method,
        stated=primary.raw_text,
        inherited=False,
        office_label=None,
        office_address=None,
    )


def _primary_location(job: Job) -> JobLocation | None:
    """The row that speaks for a multi-location posting (A2).

    The relationship is ordered `is_primary` first, but this does not lean on
    that: an ordering declared in the model is an ordering a future `selectinload`
    or a manual list assignment can lose, and losing it here would move a beacon
    to Austin.
    """
    if not job.locations:
        return None
    for row in job.locations:
        if row.is_primary:
            return row
    return job.locations[0]


def _address_of(office: CompanyLocation) -> str | None:
    parts = [office.street_address, office.city, office.state]
    present = [part for part in parts if part]
    return ", ".join(present) if present else None


async def primary_offices(
    session: AsyncSession, company_ids: Sequence[UUID] | Iterable[UUID]
) -> dict[UUID, CompanyLocation]:
    """The confirmed primary office of each company that has one.

    One query for the whole map. The obvious alternative — a lazy relationship
    load per job — is a few thousand round trips to answer a question about
    twenty-odd employers.

    Companies with no confirmed office are simply absent, which is the majority
    case and not an error (§4.8).
    """
    ids = list(dict.fromkeys(company_ids))
    if not ids:
        return {}

    rows = (
        await session.execute(
            select(CompanyLocation).where(
                CompanyLocation.company_id.in_(ids),
                CompanyLocation.is_primary.is_(True),
            )
        )
    ).scalars()

    return {row.company_id: row for row in rows}
