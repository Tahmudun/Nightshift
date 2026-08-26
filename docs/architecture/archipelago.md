# The Archipelago — the M6 design

> Read before any M6 work: any landmass, any `landmass` column, any crossing.
> It decides why the geo spine comes before the water, what the Island is
> actually made of, and which spec'd features are deferred and why.
>
> Governing decisions: **Q14** (answered 2026-08-25, interim), **Q15** (the debt
> that answer took on), **A16** (M6 absorbs old M5's cinematic system), **I1**.

---

## 1. What M6 delivers, and why the Island is not the first slice

`CLAUDE.md` §6 describes M6 in one sentence: *"Regions, and the Island: a
Tron-blue landmass across the water housing every remote and address-unknown
role, reached by a cinematic crossing."*

That sentence was written before the corpus was real. It is now, and it does
not survive contact with the data intact. Two of its assumptions are wrong:

1. **"Every remote and address-unknown role" is not one population.** It is
   three, and they differ in what is actually known about where the work
   happens. Drawing them as one landmass would erase a fact the posting
   states — which is the failure mode I1 exists to prevent, pointed the other
   way round.
2. **The set is not measurable yet, because the parser is losing cities.**
   118 primary locations resolve to "nothing known" while their `raw_text`
   plainly reads `London`, `San Francisco`, `Barcelona`. Any Island built
   today would put 70% of its furthest district in the wrong place.

So M6 does not start with a landmass. It starts with **knowing where the roles
are**, which is A16's ordering rule (*data before rendering*) applied to the
one milestone most tempted to ignore it. The Island is M6b. §5 is M6a.

---

## 2. The corpus, measured

Measured 2026-08-25 against the live development database — 1200 jobs, 23
companies, 22 boards, filled by the first live polling pass (2026-08-24).

**Every job has exactly one primary location.** 1200 jobs, 1200 rows with
`is_primary`, 0 jobs with no location row at all. 260 jobs carry more than one
location; the widest carries ten.

**By the location that actually places a job on the map** — the primary, which
is what `placement.py:246` selects:

| Landmass | Jobs | Share | Made of |
|---|---|---|---|
| New York | 224 | 18.7% | `city_only`, city = New York |
| Elsewhere — city known | 568 | 47.3% | `city_only`, city ≠ New York |
| Elsewhere — broad only | 239 | 19.9% | country or subdivision, no city (156 `unknown` + 83 `remote`) |
| Unplaced | 169 | 14.1% | no city, no state, no country (118 `unknown` + 51 `remote`) |

**Nothing in the corpus is geocoded.** Zero rows at `verified` or
`approximate`; every location is `city_only`, `unknown` or `remote`. The
existing city therefore draws no role on a building, which is ADR 0024 working
as designed, and M6 changes none of it.

**Two numbers that are not in Q14 and matter more than the ones that are:**

- **71 New York roles are invisible to the map.** 295 jobs name New York in
  *some* location row; only 224 name it in the primary. A "London or New York"
  posting is hirable in New York, and the current rule places it in London
  because London was typed first. That is a 24% undercount of the city, caused
  by an artifact of how an employer filled in a form. §6.
- **The `unknown` bucket is two unrelated things.** 194 rows say `unknown` and
  carry a country — `Spain`, `Poland`, `United Kingdom` — and those are honest:
  the posting really does name only a country. 118 rows say `unknown` and carry
  nothing, and those are a parser gap, not a fact. §5.

**One skew worth naming before anyone reads meaning into the shares.** The
third-largest location in the corpus is Pangyo, South Korea, with 94 rows —
one employer. These proportions are a property of *which 23 boards are
registered*, not of the New York market. Q15 depends on this and says so.

---

## 3. What Q14 decided, and the shape of the debt

Q14 asked what to do with the roles that are physically in another city. The
answer, 2026-08-25, was **the Island absorbs them, for now** — *"we will need a
better system later."*

The recommendation on file was the other option (filter at the canonical-job
layer), and it is still the recommendation; Q15 holds it open. What matters
here is the constraint the interim answer does **not** relax:

> An interim decision does not license an untrue one. I1 does not bend for a
> placeholder.

A landmass holding both *"this role is in London"* and *"this role is anywhere
at all"* tells a reader neither. So the Island is built from the start with the
distinctions the data already contains, which costs a little more now and makes
the interim survivable — and, not incidentally, gives Q15 a seam to cut along:
whichever way Q15 goes, the work is **re-homing one district**, not redesigning
the Island.

---

## 4. The Archipelago is four landmasses, and the data chose the number

The organising question is not *where is this role* — for 807 of them the
answer is "not here", which is not a place. It is **how much is known about
where the work happens.** That is already a first-class idea in this codebase:
it is what `location_confidence` means.

So: **distance from the mainland encodes uncertainty.** The further out a role
sits, the less the posting told us. This is the whole visual grammar of the
milestone, it is honest by construction, and it makes the crossing in §7 mean
something — you sail away from what is known.

| `landmass` | UI name | Population | What it claims |
|---|---|---|---|
| `new_york` | New York | 295 (after §6) | Hirable in New York. Drawn over the city. |
| `elsewhere_city` | The Near Isles | 568 + ~118 (after §5) | A named city that is not New York. |
| `elsewhere_broad` | The Reach | 239 | A country or a state. No city. |
| `unplaced` | The Verge | ~51 (after §5) | Nothing. Remote-anywhere, or silent. |

**Why four and not two.** Two districts (place-known / place-unknown) would put
*"Remote — United States"* and *"Remote — anywhere on Earth"* in the same water.
Those differ on work authorisation and time zone, which are the two things a
reader of this product is actually filtering on, and the difference is already
in the database. Collapsing it would be discarding a known fact to save a
mesh.

**Why one archipelago and not three separate scenes.** They are zones of one
offshore geometry with one camera domain, not three destinations. The milestone
is called The Archipelago because there is a group of them; it is not called
The Archipelagos.

**Naming.** `landmass` in code, because `region` is already taken —
`scoring.py:195` uses it for a US state, and `matching.py:275` maps
`JobLocation.state` onto it. Inventing a second meaning for `region` would
break the one naming rule `CLAUDE.md` §7 states outright. UI names above are
UI-only; the enum values are the domain language.

---

## 5. M6a — the bare-city gap, on ADR 0008's own terms

**The defect.** `parse_location_segment` refuses to promote an uncorroborated
bare token to a city, which is what keeps `Global` and `Multiple Locations` out
of the city column. The one exception is `_DECIDED_BARE_PLACES`
(`locations.py:346`), an enumerated reviewed list — and it contains New York
and its boroughs and nothing else. Every other bare city name in the corpus
falls through to `unknown` with the city discarded:

| | rows |
|---|---|
| `London` | 50 |
| `San Francisco` | 29 |
| `Austin` | 11 |
| `Barcelona` | 9 |
| `HQ - Los Angeles` | 5 |
| `Miami` | 4 |
| `Atlanta`, `Chicago`, `Virginia Beach. VA` | 3 each |
| `Milton Keynes`, `Madrid`, `Buenos Aires` | 2 each |
| `Los Angeles`, `Toronto`, `Dallas`, `Shenzhen`, `Belfast` | 1 each |

17 distinct names, 128 rows, 118 of them primary.

**This is not fixed by adding London to the list.** ADR 0008 anticipated this
milestone and ruled on it in advance:

> If a future milestone wants worldwide bare-city resolution, it needs a real
> gazetteer, a provenance field on the resolution, and its own ADR. Extending
> this list to get there would be the slow version of the thing this ADR
> refuses.

M6 is that milestone. The three things 0008 requires:

1. **A real gazetteer.** GeoNames `cities15000` — every city over 15,000
   people, ~25k entries, CC-BY 4.0, offline, no key, no quota. It fits A4's
   "all free, no API keys" and it ships the way the basemap does (ADR 0022): a
   pinned artifact with a digest, fetched by `make setup`, never a live
   dependency. Attribution is required by the licence and belongs on the
   coverage page.
2. **A provenance field.** `resolution_method` already exists and already has
   six values. This adds `gazetteer`, so any row whose city came from a lookup
   rather than from the posting's own structure says so, and a later audit can
   find every one of them.
3. **Its own ADR.** ADR 0040, superseding 0008's list-only stance while
   keeping every one of its guardrails.

**The guardrails that do not move.** Output is `city_only` and never higher —
no coordinate is produced, so I1 is untouched exactly as 0008 argued. An
**ambiguous name resolves to nothing**: `Springfield` matches 30-odd places and
must stay `unknown`, and the rule is *refuse on ambiguity*, not *pick the
biggest*. `Global`, `Multiple Locations` and `Remote` are not in a gazetteer of
populated places and stay out by construction.

**The residual risk, named.** A gazetteer promotes names nobody on this project
reviewed — that is the whole point of using one, and it is what 0008 was
cautious about. The bound is that the promotion is city-only, provenanced, and
reversible from `source_job_records`, and that the ambiguity rule refuses
rather than guesses. `undecided_bare_name_stays_unknown` survives as a fixture
with a name that is genuinely ambiguous rather than merely foreign.

**Not in scope for M6a:** `HQ - Los Angeles` (a label prefix) and
`Virginia Beach. VA` (a period where a comma belongs). Eight rows between them.
They are separate parser gaps, they are not what the gazetteer is for, and
folding them in would hide two small decisions inside a large one.

---

## 6. Which location speaks for a job on the map

**The problem.** `_primary_location` returns one row per job, and `is_primary`
is assigned at ingestion from the *first segment the employer typed*
(`ingestion.py:243`). First-typed is not a statement about where the job mostly
is. It is a form-filling artifact, and it currently hides 71 New York roles —
24% of the city — behind cities they are also open in.

**The decision.** Placement selects a job's location by a stated preference
order, not by `is_primary` alone:

```
1. a New York location, if the job has one          <- the home city wins
2. the primary location
3. the first location
```

**Why this is not a fabrication.** The posting says New York. Every other
location the job carries is still stored, still returned by the API, and named
in the detail panel — *"also hiring in London, San Francisco"*. The reader is
told more than before, not less. What changes is only which of several true
statements the map speaks with, and preferring the one the product is about is
the least surprising rule available.

**Why not draw the job once per location.** 1200 jobs would become 1829 marks
and a reader counting spires would get a number that is not the number of jobs.
One job, one mark, stays.

`_primary_location`'s docstring warns that losing the ordering "would move a
beacon to Austin". This rule moves beacons deliberately and in one direction
only, and it gets a fixture per branch — including a job with no New York
location at all, which must be untouched.

---

## 7. The crossing — old M5's cinematic system, absorbed

A16 folded old M5's cinematic deliverables into M6, and the crossing is where
they land: *"whose sea-and-smoke crossing between regions **is** the cinematic
visual system."*

Design intent, to be settled properly in M6c with its own ADR:

- **The water is the instrument.** The mainland is warm (ADR 0033); the
  archipelago is cold. The sea between them carries the transition, and the
  distance is the uncertainty from §4.
- **The crossing is interruptible.** M4's acceptance already requires that a
  user can interrupt any camera animation. A cinematic that cannot be skipped
  fails that criterion, and the criterion wins.
- **There is a non-3D equivalent.** Also M4's rule, also unchanged: every map
  action has a list equivalent. Reaching The Reach is a filter as much as it is
  a voyage.
- **Reduced motion is not a degraded crossing, it is a cut.** Respecting
  `prefers-reduced-motion` by slowing a long flight is worse than not flying.

Deferred out of M6c and named here so it is not smuggled back in: hiring-pulse
propagation and replay, the skill-demand layer, and timeline scrubbing — all
still deferred from `city.md` §8, all still not this milestone.

---

## 8. The slice plan

**M6a — the geo spine.** The gazetteer (§5) and ADR 0040; `gazetteer` on
`resolution_method`; the `landmass` enum and column, written at ingestion by
one pure function and backfilled; the placement preference rule (§6); the
coverage page saying how many roles each landmass holds and **how many cities
the gazetteer refused as ambiguous**. No rendering. Ends with the four
populations in §4 measured, not estimated.

**M6b — the archipelago exists.** Offshore geometry, the four landmasses, roles
placed on them, districts legible without clicking, list and map synchronised,
non-3D equivalent, capture badge and confidence treatment carried over intact.

**M6c — the crossing.** §7. Camera choreography, the sea, interruptibility,
reduced motion, its ADR.

**M6d — acceptance.** The criteria walked with evidence, `docs/reviews/milestone-6-review.md`.

**Two repo gaps this milestone should not carry but somebody must fix**, both
recorded in PROGRESS and neither blocking M6a: `make ingest` reaches 2 of 23
registered boards because it hardcodes `pollable(ats="greenhouse")`, and
`make test-e2e` cannot pass on a machine where the API is running and says
nothing about why.

---

## 9. Deferred, and open

**Deferred, deliberately:**

- **Drawing real cities.** San Francisco and London as actual landmasses is
  Q15's third option and M12's (Continental) natural home. It needs building
  geometry for cities NYC Open Data does not cover, which is a per-city data
  hunt rather than a task.
- **Geocoding anything outside New York.** The archipelago places by landmass,
  not by coordinate. No `verified` or `approximate` row is produced outside the
  city in M6.
- **The `landmass` filter as a saved search facet.** M6a exposes it; making it
  a first-class filter alongside M2's is worth doing once the districts have
  been looked at.

**Open — Q15.** The Island's second and third districts are on loan. The
trigger to revisit is the registry passing ~100 boards, M12 being planned, or
the reader saying the archipelago is noisy — whichever comes first. Until then
the districts stay, and the coverage page says they are interim.

**Needing an ADR during M6**, decided here and recorded properly when built:
the gazetteer and its ambiguity rule (0040, §5), the placement preference order
(§6), and the crossing's camera and sea (M6c, §7).
