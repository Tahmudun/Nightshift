# 0036 — A confirmed office is seeded, not remembered

- **Status:** accepted
- **Date:** 2026-08-19
- **Depends on:** ADR 0004 (the fixture adapters, and why `make demo` is
  offline), ADR 0024 (a role is drawn at its employer's office), ADR 0030 (a
  roof is inherited; an altitude is merely drawn), ADR 0035 (the column is a
  spire)
- **Touches:** `cli.py`, `verify.py`, `scripts/record_office_geocodes.py`,
  `tests/fixtures/geosearch/office_addresses.json`, `test_fixture_geocoder.py`

## What was reported

> *"the beacons look better but should be attached to real buildings and not
> just floating in air."*

They were floating. Every one of them. And the renderer was correct.

## The state of the world when that was written

`GET /city/signals` returned **31 signals, 31 of them `unresolved`**.
`unresolvedField.ts`'s rule 2 is that nothing in that field touches the
ground — the absence of a ground connection is the entire message — so
thirty-one untethered columns is the honest picture of a corpus where nobody
has said where anything is. The layer that draws a role on a roof had nothing
to draw.

`select count(*) from company_locations` was **0**. So was `geocode_cache`.

## Why the offices vanished

`company_locations` is filled by exactly one thing: `make offices`. It reads
the worksheet a human filled in, geocodes each address through NYC GeoSearch,
and writes the rows that reach `verified`. It is not part of `seed`, `demo`,
`reset-db` or `acceptance` — it is a separate command, run by hand, once, on
2026-08-17.

The database was re-seeded on 2026-08-19. Nothing re-ran `offices`, so the
offices were gone.

That alone is an operator error with an obvious fix. What makes it an ADR is
the second half: **there was no way to fix it offline.** `CachingGeocoder`
promises that "every address is requested once ever" and `cmd_offices`'s
docstring says "after a run the answers live in `geocode_cache` and `make demo`
stays offline". Both are true, and both are void the moment somebody runs
`make reset-db`, because `geocode_cache` is a Postgres table and `reset-db` is
`docker compose down -v`. The cache that was protecting the offline path lived
inside the thing being destroyed.

So a clean clone could never have had a role on a building at all. The city as
committed was the floating city, and had been since the day the addresses were
typed in.

## The shape of the failure, which is the part worth keeping

Nothing was red. Not one unit test, not one browser test, not `make verify`,
not CI. Every hop of the promotion path had a test:

- `read_worksheet` refuses four kinds of bad entry — tested.
- `parse_search_response` rejects Pelias's confident garbage — tested against
  two committed recordings.
- `load_offices` writes the rows that reach `verified` — tested.
- `buildingField.ts` stands a role on a roof — tested with no GPU.
- `arrangeUnresolved` floats a role that has no position — tested.

**Four hops, each tested in isolation, and the chain between them tested
nowhere.** The renderer drew the right thing for the data it had; the data was
empty; and "empty" is a legitimate state that the product is specifically
designed to render gracefully. A subsystem whose degraded mode is beautiful
cannot be trusted to report its own starvation.

## Decision

### 1. The seed loads the offices

`cmd_seed` now runs `read_worksheet` and `load_offices` alongside the three
fixture boards. Not a Makefile change: `seed` is the command that owns "make
the committed fixtures into a database", and putting it there means `demo`,
`reset-db` and `acceptance` all inherit it without anybody remembering to.

The loader is the production one, with every refusal rule intact. Only the
geocoder is swapped.

### 2. A fixture rung, because the Protocol always said there would be one

`domain/geocoding.py`'s `Geocoder` docstring has said since M4a:

> *"That is also what makes the offline path real rather than mocked:
> `make demo` wires a fixture-backed implementation through the same interface,
> not around it."*

Nothing implemented it for three milestones. `FixtureNycGeoSearchGeocoder` does
now, on exactly the terms `FixtureGreenhouseAdapter` set: no client, so it
cannot reach the network if the kill switch were flipped; overrides only the
fetch, so `parse_search_response` — where every acceptance rule lives — is the
production code path unmodified.

`scripts/record_office_geocodes.py` is the recording half. It asks the live
service the *exact* question the loader asks (`OfficeEntry.geocoder_query`,
through `PoliteClient`) and writes the response verbatim with provenance. All
eight confirmed addresses resolved to real BINs; Datadog → 1087186 and
Ramp → 1080672 are the same two the live run produced on 2026-08-17, which is
the corroboration that the recording is of the same question.

**A missing recording is `PROVIDER_UNAVAILABLE`, not "no building found."**
That is I3's distinction one subsystem over: *we could not look* is not
evidence that there is no building there. It also matters mechanically —
`CachingGeocoder` writes every outcome to `geocode_cache` **except** that one,
so getting the refusal wrong would let an offline run poison the cache with a
permanent wrong answer about a perfectly real address.

### 3. Two assertions, at the two altitudes the failure needed

**`test_every_confirmed_address_in_the_worksheet_has_a_recording`** — the
worksheet is the input and the fixture set is the answer key, and this asserts
they cover the same addresses. It is the guard for how this breaks next:
somebody fills in a ninth address, `make seed` cannot geocode it, that
company's roles quietly go back to floating, and nothing is red. Verified able
to fail by deleting Ramp's recording.

**`check_city_placement`** in `verify.py` — the end-to-end one, and the one
that was actually missing. It asserts that at least one role stands on a real
building, that every placed role carries a `verified` coordinate *and* a BIN,
and that no unplaced role acquired a coordinate on its way to the map.

It deliberately does **not** assert that every role is placed. Eleven of the
thirty-one are at an employer whose address nobody has confirmed, and I1 says
those float. What it asserts is that the path can carry anything at all.

## Consequences

- **`make seed` now states the office count out loud**, and warns in words when
  no role will stand on a building — "every beacon will float, which is what
  `city.md` §4.8 says an unplaced role looks like, not a rendering fault." A
  fresh clone with a blank worksheet is a legitimate state; it should not have
  to be diagnosed from a screenshot.
- The seeded city is **20 roles on 2 buildings, 11 floating**, restored from a
  committed file rather than from somebody's memory of a command.
- `make offices` is unchanged and is still the live path. It is now also
  cheaper: the seed has already warmed `geocode_cache`, so a run finds every
  answer cached. It still refuses to start without `OUTBOUND_HTTP_ENABLED`,
  which is now slightly conservative and deliberately left alone — it is the
  *refresh* command, and a refresh that silently served cache would not be one.
- **The data-supply cap that ADR 0031's audit named is unchanged.** Two
  confirmed offices is still two buildings that can ever light. This ADR
  restores the two; it does not add a third. Six of the eight recorded
  addresses belong to companies whose boards have never been polled.
- Evidence: `docs/reviews/milestone-4e-beacons-on-buildings.png` and
  `-close.png` — a spire descending into Midtown and terminating on the roof of
  28 West 23rd Street.
