"""The cache in front of a rung, and the one answer it refuses to keep.

`city.md` §4.3 and AMENDMENTS A4: *"Cache every geocode by normalized address
string, permanently. Never re-geocode an address you have already resolved."*

`CachingGeocoder` wraps any `Geocoder` and is one itself, so the ladder does not
know it is there and `resolve()` needs no cache-shaped argument. Wrapping rather
than embedding also means a rung can be exercised without a database, which is
what keeps the adapter's fixture tests honest.

**A miss is cached. An outage is not.** Invariant I3, one subsystem over. *"We
asked and NYC has no such address"* is a durable answer worth keeping. *"The
provider was unreachable"* is not an answer about the address at all, and
storing it would turn one bad afternoon into a permanent refusal to place a
building that was always placeable. The database refuses it too
(`ck_geocode_cache_an_outage_is_never_cached`) — this layer is where the
decision is *made*, and that one is where it cannot be got around.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nightshift.db.base import LocationConfidence, ResolutionMethod
from nightshift.db.models import GeocodeCache
from nightshift.domain.geocoding import (
    PROVIDER_UNAVAILABLE,
    GeocodeOutcome,
    Geocoder,
    GeocodeRefusal,
    Resolved,
    Unresolved,
)

_WHITESPACE = re.compile(r"\s+")


def normalize_query(address: str) -> str:
    """The cache key.

    Casefold and collapse whitespace, and nothing else. Deliberately not a
    street-abbreviation normaliser: "620 8th Ave" and "620 Eighth Avenue" are
    the same building and this will treat them as two entries, which costs one
    extra request and keeps the key something a person can read in a table.
    A normaliser that folded them would also fold things that are not the same,
    and the cost of that is a wrong building rather than a wasted request.
    """
    return _WHITESPACE.sub(" ", address.strip()).casefold()


class CachingGeocoder:
    """Wraps a rung. Is a rung."""

    def __init__(self, inner: Geocoder, session: AsyncSession) -> None:
        self._inner = inner
        self._session = session

    @property
    def method(self) -> ResolutionMethod:
        return self._inner.method

    async def geocode(self, address: str) -> GeocodeOutcome:
        key = normalize_query(address)

        cached = (
            await self._session.execute(
                select(GeocodeCache).where(
                    GeocodeCache.normalized_query == key,
                    GeocodeCache.resolution_method == self.method,
                )
            )
        ).scalar_one_or_none()
        if cached is not None:
            return _from_row(cached)

        outcome = await self._inner.geocode(address)

        if isinstance(outcome, Unresolved) and outcome.refusal == PROVIDER_UNAVAILABLE:
            # Not written. See the module docstring: this is not an answer about
            # the address, and the next caller deserves a fresh attempt.
            return outcome

        self._session.add(_to_row(address, key, self.method, outcome))
        await self._session.flush()
        return outcome


def _to_row(
    address: str, key: str, method: ResolutionMethod, outcome: GeocodeOutcome
) -> GeocodeCache:
    now = datetime.now(UTC)
    if isinstance(outcome, Resolved):
        return GeocodeCache(
            query=address,
            normalized_query=key,
            resolution_method=method,
            latitude=outcome.latitude,
            longitude=outcome.longitude,
            location_confidence=outcome.confidence,
            building_id=outcome.building_id,
            matched_text=outcome.matched_text,
            refusal=None,
            resolved_at=now,
        )
    return GeocodeCache(
        query=address,
        normalized_query=key,
        resolution_method=method,
        latitude=None,
        longitude=None,
        location_confidence=outcome.confidence,
        building_id=None,
        matched_text=None,
        refusal=str(outcome.refusal),
        resolved_at=now,
    )


def _from_row(row: GeocodeCache) -> GeocodeOutcome:
    if row.refusal is not None:
        return Unresolved(
            GeocodeRefusal(row.refusal),
            row.location_confidence or LocationConfidence.UNKNOWN,
        )
    # `a_row_is_a_hit_or_a_miss` guarantees the coordinates are here.
    assert row.latitude is not None and row.longitude is not None
    return Resolved(
        latitude=float(row.latitude),
        longitude=float(row.longitude),
        confidence=row.location_confidence or LocationConfidence.VERIFIED,
        method=row.resolution_method,
        matched_text=row.matched_text or "",
        building_id=row.building_id,
    )
