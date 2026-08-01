# ADR 0008 — Decided bare place names

- **Status:** accepted
- **Date:** 2026-07-30
- **Milestone:** M1

## Context

`parse_location_field("New York")` returns `unknown`. The parser requires
corroboration before accepting a token as a city — a recognised state or
country in the same segment, or a preceding comma part — which is what keeps
`"Global"` and `"Multiple Locations"` out of the city column.

`"New York"` alone is genuinely ambiguous: it names both a city and a state.

The cost of leaving it `unknown` is concrete. `docs/architecture/board-discovery.md`
§8 derives NYC-ness from parsed locations, and ADR 0007 assigns a board to the
hourly `hot` tier when it has produced an NYC posting. A board whose postings
say `"New York"` would poll daily instead of hourly, so the product's stated
goal — same-day knowledge of an NYC opening — would fail on exactly the
strings most likely to name New York.

## Decision

A short, explicit, committed list of bare place names that resolve without
corroboration. It contains New York City, its five boroughs, and their common
spellings — nothing else.

Resolution yields `city_only` and never higher. No coordinate is produced, so
invariant I1 is untouched: I1 forbids inventing a *position*, and `city_only`
is the confidence value that exists to say "we know the city and nothing
finer."

Every other bare token keeps the existing behaviour and resolves to `unknown`.

`"New York"` collides with the US-state table (`"new york"` is also a state
name), so the parser's subdivision lookup would otherwise consume the lone
token as a state before the decided-place check ever ran, leaving no
candidate left to resolve as a city. `_strip_tail_tokens` special-cases this
one collision: a single bare part that matches the decided-place table skips
the generic subdivision consumption and falls through to the decided lookup
instead. No other entry on the list collides with a state, province, or
country name, so this guard changes behaviour for exactly one string.

## Why this is not the guessing I1 forbids

Three properties distinguish it from a general gazetteer:

1. **It is enumerated and committed.** A reader can see the entire list. A
   fuzzy matcher or a downloaded gazetteer would make the same promotion for
   thousands of names nobody reviewed.
2. **It cannot manufacture precision.** The output is `city_only` with null
   coordinates. Geocoding is a separate stage with its own audit trail.
3. **The residual error is bounded and named.** If a posting saying
   `"New York"` meant the state, we record city "New York", state "New York" —
   which at `city_only` precision places nothing and misstates nothing that a
   later geocode would not correct. `ashby_bare_foreign_city_stays_unknown`
   and `undecided_bare_name_stays_unknown` are the fixtures that keep the list
   a list.

## Consequences

- `"London"`, `"Toronto"`, `"Springfield"` and every other bare city name stay
  `unknown`. This is a real coverage gap and belongs on the coverage page
  (`board-discovery.md` §11) under named blind spots, not in a footnote.
- Adding a name to the list is a code review with a fixture, deliberately.
- If a future milestone wants worldwide bare-city resolution, it needs a real
  gazetteer, a provenance field on the resolution, and its own ADR. Extending
  this list to get there would be the slow version of the thing this ADR
  refuses.
- **A decided name plus `Remote` resolves the city; the same name plus an
  explicit country does not.** `"New York, Remote"` yields city "New York";
  `"New York, USA, Remote"` yields state "New York" and no city
  (`statewide_remote`). The difference is that `raw_part_count` is counted
  after `Remote` is stripped, so `"New York, Remote"` is one bare part and
  takes the decided-place path, while adding `"USA"` makes it two parts and
  the state-corroboration path wins instead — adding a country to the string
  removes its city. This asymmetry was noticed during review, not designed,
  and is accepted rather than fixed: no coordinate is produced either way,
  confidence stays `remote` in both cases, `infer_remote_policy` keys off
  confidence rather than city, and the string genuinely does name New York —
  nothing is invented that the source did not write. It has a live
  consequence worth naming plainly: `ParsedLocation.is_nyc` returns `True` for
  `"New York, Remote"` and `"Brooklyn, Remote"`, which feeds the `hot`-tier
  decision in ADR 0007. `decided_bare_place_plus_remote_resolves_city` and
  `decided_bare_borough_plus_remote_resolves_city` pin the behaviour so a
  future refactor cannot silently flip it in either direction.
- **This does not close the corroboration gap already tracked as `TODO(M1)`
  in `locations.py`.** A second, unresolved comma part still corroborates the
  first into a city — `"Global, XX"` still produces city `"Global"`. That
  gap predates this ADR, is a different mechanism (corroboration by presence,
  not an enumerated table), and is not fixed by adding a decided-name list.
  The parser's guarantee after this change is narrower than "never fabricates
  a city": it is "never fabricates a city except through the one named,
  ticketed gap above, and the enumerated list this ADR adds." Closing the
  `TODO(M1)` gap needs a real gazetteer of city names, same as worldwide
  bare-city resolution would.

## Alternatives rejected

**Leave it `unknown`.** Honest but breaks the hot tier on the most common way
of naming New York, which defeats the product goal that M1d exists to serve.

**Treat any capitalised unmatched token as a city.** Restores the exact bug
Task 4 removed, at scale.

**Infer from sibling postings on the same board.** Makes parsing depend on
order and on other rows, so the same string parses differently in different
runs — and `test_parse_is_deterministic` exists to forbid that.
