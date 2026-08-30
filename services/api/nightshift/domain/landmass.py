"""Which landmass a location belongs to. One pure function, no I/O.

Written at ingestion and backfilled, never computed on read — a reader
filtering to New York is running a WHERE clause, and a Python property cannot
be indexed.
"""

from __future__ import annotations

from nightshift.db.base import Landmass
from nightshift.domain.locations import ParsedLocation


def landmass_for(location: ParsedLocation) -> Landmass:
    """Sort one parsed location into its landmass.

    Order matters and is the whole rule: a known city decides first, because
    what is known about *place* is the question. ``confidence`` does not
    appear — a role written "Remote — New York, NY" names a city, and sorting
    it offshore would discard a fact the posting stated.
    """
    if location.is_nyc:
        return Landmass.NEW_YORK
    if location.city is not None:
        return Landmass.ELSEWHERE_CITY
    if location.state is not None or location.country is not None:
        return Landmass.ELSEWHERE_BROAD
    return Landmass.UNPLACED
