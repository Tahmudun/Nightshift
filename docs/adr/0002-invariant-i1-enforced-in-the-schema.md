# ADR 0002 — Enforce invariant I1 in the database, not in application code

- **Status:** accepted
- **Date:** 2026-07-29
- **Milestone:** M0

## Context

Invariant I1 says never fabricate a location: every coordinate carries a
`location_confidence`, and if we cannot resolve honestly the value is `unknown`.

An invariant that lives only in application code is a convention. It survives
exactly as long as nobody writes a well-meaning helper that defaults a missing
confidence to `city_only` so a map feature can ship, and it fails silently rather
than loudly. The failure mode is also the worst possible one for this product:
the data looks fine, the map looks fine, and a user is told a job is somewhere it
is not.

## Decision

I1 is enforced by three mechanisms, at three different layers, each of which can
fail independently without the invariant being lost.

**1. The schema (`job_locations`).** Four check constraints:

```sql
-- coordinates travel as a pair
(latitude IS NULL) = (longitude IS NULL)
-- and within the possible range
latitude  IS NULL OR latitude  BETWEEN  -90 AND  90
longitude IS NULL OR longitude BETWEEN -180 AND 180
-- and agree with the precision claimed
CASE
  WHEN location_confidence IN ('verified','approximate') THEN latitude IS NOT NULL
  WHEN location_confidence IN ('city_only','remote','unknown') THEN latitude IS NULL
END
```

The last one is the important one. It makes two states physically unstorable: a
point labelled `unknown`, and a `verified` claim with nothing to back it. A bug
that tries either gets a constraint violation.

`location_confidence` is a PostgreSQL enum, so a sixth value cannot be invented
without a migration.

**2. The parser's type.** `ParsedLocation` in `citysignal/domain/locations.py`
has no `latitude` or `longitude` field at all. A parser that *could* return a
coordinate is a parser that eventually will, so the type makes it impossible.
Geocoding (M1) is a separate stage that produces its own type and writes its own
audit trail. `tests/test_locations.py` asserts the absence structurally, so
adding those fields to make a map feature easier fails the suite.

**3. The API schema.** `jobLocationSchema` in the web app carries a
`superRefine` that repeats the database's confidence/coordinate agreement check.
Duplicating it there means a bug in the API cannot put a point on a map without a
precision claim that justifies it. `src/lib/schemas.test.ts` covers both
directions.

## Related decision: coarser information never rounds up

`city_only` means "resolved to city granularity". A country is coarser than a
city, so `"Germany"` on its own resolves a country, no city, and reports
`unknown` — not `city_only`. Reporting `city_only` would overstate what we know,
which is the same failure as fabricating a point, just smaller.

Likewise `city_only` carries no coordinates. A city centroid is not where the job
is. §9.7's unresolved-signal district is where those roles belong on the map, not
a pin on the middle of Manhattan.

## Consequences

- In M0 every location is `city_only`, `remote`, or `unknown`, and
  `mappable_locations` is zero. This is surfaced prominently in the UI rather
  than hidden — the confidence ladder on every row and the corpus readout both
  show it.
- M1's geocoder must write `latitude`, `longitude`, and a promoted
  `location_confidence` in the same statement. A two-step update that sets
  coordinates first will violate the constraint. This is intended.
- The check constraint is slightly awkward to change. Good: changing it should
  require reading this ADR.
