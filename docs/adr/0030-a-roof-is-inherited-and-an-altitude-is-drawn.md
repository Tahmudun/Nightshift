# ADR 0030 — A roof is inherited; an altitude is merely drawn

**Status:** Accepted
**Date:** 2026-08-17
**Milestone:** M4e Task 6
**Supersedes:** nothing. **Depends on:** ADR 0023 (the beam), ADR 0024 (a role is
drawn at its employer's office and says so), ADR 0025 (Three.js in MapLibre's
context)

## Context

The worksheet came back filled on 2026-08-17 and twenty of the thirty-one seeded
roles resolved to `kind: building`. The renderer drew none of them: it had one
field, `arrangeUnresolved`, and that field's first rule is that nothing in it
has a position.

Standing a role on a building needs three numbers — where the building is, how
tall it is, and how far above the roof the marker hangs — and they are not the
same kind of number. Treating them as one is how a renderer starts fabricating.

## Decision

**Split the three numbers by who is allowed to have made them up.**

### 1. The ground position is inherited and never adjusted

`x` and `y` come from `placement.latitude` / `placement.longitude` — the
coordinate NYC GeoSearch returned for an address a named human wrote down and
dated — and pass through `sceneFromLngLat` unmodified.

**No nudging apart of overlapping stacks. No jitter for legibility. No snapping
to a grid.** Two employers in one tower get one stack, not two stacks a hundred
metres apart, because a hundred metres is a different address. A role that
cannot be drawn where its office is does not get drawn on a roof at all.

This is the inverse of `unresolvedField.ts`'s rule 1, and stating both out loud
is what keeps the two modules from drifting into each other. There, position
encodes employer and nothing about New York. Here, position encodes New York and
nothing else.

### 2. The roof height is read, and its absence is a documented default

`height_roof` is read off the building tiles the map has already loaded — the
same attribute `darkStyle.ts` extrudes the city from. No new source, no request,
no second copy of NYC's building table.

`querySourceFeatures` answers from loaded tiles, so a building the camera has
never approached has no measured roof. **`DEFAULT_ROOF_METRES` (250 m) fills in,
and the substitution can only move a marker up or down its own building.** It
can never move one off a building, which is the property that keeps a partial
lookup clear of I1.

The default is high rather than average on purpose. Too low buries a beacon
inside its own tower and hides the role completely; too high briefly resembles
the untethered field. Only one of those two failures is silent.

A footprint NYC never measured is **left out** rather than recorded as zero.
`darkStyle.ts` gives such a building a 25 ft default body so it has some mass;
doing the same here would put a marker at street level on a building that
plainly has a roof — a wrong number that looks measured, where an absent one
falls through to a number documented as a guess.

### 3. The vertical arrangement is ours, and is labelled as ours

Clearance above the roof, spacing between two roles, where the plate goes, how
far the beam overshoots: all chosen, none measured. They are drawing decisions
about a *marker*, not assertions about a *place*, and `buildingField.ts` says
so at the top so the next person who wants a prettier layout knows which numbers
are theirs to move.

### 4. The building is marked by a beam, not by being brighter

ADR 0023 already decided this and the slice plan asked for a BIN-filtered
extrusion layer anyway. **The extrusion layer was not built.** The ratio
argument has not changed: tens of thousands of footprints in view, tens ever
hiring, and a brightness difference cannot carry ten in fifty thousand against
a city that is now itself lit (ADR 0029). Building both would spend the encoding
twice and the second copy would be the invisible one.

One beam per *building*, not per role. A beam says "somebody is hiring here",
which is one fact about a structure however many openings sit behind it — and
two beams in one column would also be twice as bright as one, encoding a count
nobody asked the light to carry. How many roles are open is what the stack of
beacons standing in the beam is for.

### 5. A tower with two employers is labelled by count, not by the first name

`2 employers`, counted by `company_id` rather than by display name. The
alternative puts "Datadog" over the New York Times Building, which asserts an
address for the other tenant that nobody made. 620 8th Avenue is exactly that
kind of building, so this is a real case rather than a hypothetical one.

## Alternatives considered

| Option | Why not |
|---|---|
| **Ask the API for the roof height** | The height lives in a pmtiles archive the *web* has. Adding it to `company_locations` would put a copy of NYC's building table in Postgres, stale from the day it was written, to save a lookup that is already local and free |
| **Fan overlapping stacks apart** | Legible and false. The distance between two fanned stacks is a distance nobody measured, and the whole argument for this field is that its distances are real |
| **Wait for the measured height before drawing** | A role invisible until its tile loads is a role the person cannot find, and on a still map the tile may never load. A documented default that settles is better than an honest absence nobody can act on |
| **Light the hiring building's footprint** | ADR 0023, on the ratio above. Also spends colour, which ADR 0029 already moved into scenery |
| **Light the building for an applied role** (§6's literal wording) | It would make the same fact about you look like two facts, and would make the loudest version the one that happens to have a street address. The beacon fills instead, identically in both fields |

## Consequences

**The promotion path runs end to end for the first time**: a line typed in
`data/company-locations.yaml` → `make offices` → NYC GeoSearch → a BIN in
`company_locations` → a beacon on a roof in Manhattan. Four milestones of
machinery, connected.

**A partial roof-height lookup is now a permanent state, not a transient one.**
Any building outside the camera's history sits at the default. This is correct
and it is also the kind of thing that looks like a bug to somebody who has not
read this file, so the constant carries its own explanation.

**`BEACON_RADIUS` is now wrong at close range and was not before.** A fixed 40 m
beacon was fine while the entire field sat 700 m up and could never be
approached. Standing roles on roofs is what made the camera able to get near
one, and at street-level zoom a beacon is several times the size of the building
it stands on. Recorded in PROGRESS with a screenshot rather than guessed at —
it is a tuning decision, and tuning it without looking is how the city got grey
the first time (ADR 0029).

**§6's "Applied" row stays translated, for a new reason.** The old reason —
nothing stands on a building — expired the moment this shipped. The new one is
in the table above and is stronger.
