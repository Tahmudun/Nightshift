"""Re-resolve bare city names that predate the gazetteer (ADR 0040).

ADR 0007's conditional polling means an unchanged board answers `304` and
re-parses nothing, so rows parsed before the gazetteer existed would keep their
`unknown` verdict through every future poll. `RawJob.payload`'s docstring
promises this case: *a normalization bug is a backfill rather than a re-crawl*.

**Row-wise, deliberately.** The obvious shape — re-parse a job's location field
and rewrite its rows — is the shape that went wrong in the 2026-08-24 repair: a
merged job's locations are a union across several source records, so rebuilding
them from one record silently drops the others (that dry run caught a job losing
`Toronto, ON`). This script never reconstructs a set. It re-parses each row's own
`raw_text` and corrects that row in place, so a job's location *set* is
identical before and after — only the contents of individual rows change.

**Selection is on the defect's signature**, not on "everything the parser would
now do differently": a row with no city, no state, no country and `unknown`
confidence. Those are exactly the rows the gazetteer can improve, and a row that
already carries any geography is left alone.

Dry run by default. `--apply` writes.

    cd services/api && ./.venv/bin/python scripts/backfill_gazetteer_cities.py
    cd services/api && ./.venv/bin/python scripts/backfill_gazetteer_cities.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select

from nightshift.db.base import LocationConfidence, ResolutionMethod
from nightshift.db.models import JobLocation
from nightshift.db.session import dispose_engine, session_scope
from nightshift.domain.locations import parse_location_segment


@dataclass(slots=True)
class Change:
    row_id: object
    raw_text: str
    city: str


async def _collect(session) -> tuple[list[Change], Counter[str]]:
    rows = (
        (
            await session.execute(
                select(JobLocation).where(
                    JobLocation.city.is_(None),
                    JobLocation.state.is_(None),
                    JobLocation.country.is_(None),
                    JobLocation.location_confidence == LocationConfidence.UNKNOWN,
                )
            )
        )
        .scalars()
        .all()
    )

    changes: list[Change] = []
    refused: Counter[str] = Counter()
    for row in rows:
        parsed = parse_location_segment(row.raw_text, is_primary=row.is_primary)

        if parsed.resolution_method is not ResolutionMethod.GAZETTEER:
            refused["gazetteer declined the name"] += 1
            continue
        # Belt and braces. The gazetteer branch cannot produce any of these,
        # and if it ever starts to, this refuses to write rather than trusting
        # the docstring.
        if parsed.city is None:
            refused["resolved to no city"] += 1
            continue
        if parsed.confidence is not LocationConfidence.CITY_ONLY:
            refused[f"confidence would become {parsed.confidence}"] += 1
            continue
        if parsed.state is not None or parsed.country is not None:
            refused["would invent a state or country"] += 1
            continue
        if hasattr(parsed, "latitude") or hasattr(parsed, "longitude"):
            refused["would carry a coordinate (I1)"] += 1
            continue

        changes.append(Change(row_id=row.id, raw_text=row.raw_text, city=parsed.city))

    return changes, refused


async def run(apply: bool) -> int:
    async with session_scope() as session:
        changes, refused = await _collect(session)

        by_name = Counter(c.raw_text for c in changes)
        print(f"candidate rows resolved: {len(changes)}")
        for raw, count in by_name.most_common():
            print(f"  {count:>4}  {raw}")
        if refused:
            print("\nrefused:")
            for reason, count in refused.most_common():
                print(f"  {count:>4}  {reason}")

        if not apply:
            print("\ndry run — nothing written. Re-run with --apply.")
            return 0

        ids = {c.row_id: c.city for c in changes}
        rows = (
            (await session.execute(select(JobLocation).where(JobLocation.id.in_(ids))))
            .scalars()
            .all()
        )
        assert len(rows) == len(ids), "row disappeared between read and write"

        for row in rows:
            row.city = ids[row.id]
            row.location_confidence = LocationConfidence.CITY_ONLY
            row.resolution_method = ResolutionMethod.GAZETTEER
            # Stated for the reader rather than needed: `city_only` requires
            # null coordinates by check constraint, and nothing above sets one.
            assert row.latitude is None and row.longitude is None

        await session.flush()
        print(f"\napplied to {len(rows)} rows.")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()
    try:
        return await run(args.apply)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
