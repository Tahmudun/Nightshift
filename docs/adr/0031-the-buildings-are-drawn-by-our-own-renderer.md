# ADR 0031 — The buildings are drawn by our own renderer, and the reference is the acceptance test

- **Status:** accepted
- **Date:** 2026-08-18
- **Milestone:** M4e (new Task 10; changes the shape of Tasks 7 and 9)
- **Supersedes:** `city.md` §5.3's building *material* — the `fill-extrusion`
  colour ramp and the crown layer as the way a tower gets its look. The geometry
  pipeline in the same section (the pinned tiles, the measured heights, the 25 ft
  default) is untouched and load-bearing.
- **Relates to:** ADR 0022 (the tiles), ADR 0023 (the beam), ADR 0025 (Three.js
  in MapLibre's context), ADR 0029 (the neon city, and whose restraint kept it
  grey), `docs/design/references/02-skyline-grid-plane-light-columns.jpg`

## Context

M4e Tasks 2, 4 and 5 recoloured the city: neon ground, near-black mass, lit
rooflines. On 2026-08-18 the human reviewed the result and said what it is:

> "even the 'neon buildings now' are just the same old grey buildings with a
> neon slab placed on top."

That is not an impression to be managed. It is technically accurate. The crown
is a second `fill-extrusion` layer stacked on the same box, and the box's
*material* never changed — a flat-shaded solid whose only expressive channel is
a colour ramp. Everything the reference images actually build a tower out of is
beyond that material, and each limit has already been measured in this repo
rather than assumed:

- **Windows.** `fill-extrusion-pattern` overrides `fill-extrusion-color`, so a
  texture cannot coexist with the height ramp (M4e Task 5, recorded in
  PROGRESS). §5.3 itself already deferred the speckle "to the Three.js layer".
- **Edge light.** MapLibre has no outline for an extrusion; a line layer on the
  same footprints draws on the ground underneath the building (M4b Task 4).
- **Shading.** The one light is MapLibre's own — white, fixed, added to every
  face (ADR 0029's first "wrong diagnosis"). There is no rim light, no vertical
  falloff we author, no per-face anything.

Meanwhile the same page already runs a full renderer that has none of these
ceilings. The Three.js layer (ADR 0025) draws the beacons, the marks, the
labels and the roof beams with instanced geometry and its own shaders, inside
MapLibre's WebGL context, off the same mercator math and the same building
tiles (`roofHeights.ts` reads them today). The capability was always one
decision away. This is the decision.

There is also a standing commitment attached to it, made to the human on
2026-08-18 in exchange for their continuing on the project at all: **the city
ends up looking like reference 02 — not "inspired by" it.** An ADR is where
this project writes down things it does not intend to renegotiate.

## Decision

**Building rendering moves out of MapLibre's `fill-extrusion` layers and into
the Three.js custom layer.** Same geometry source — the pinned tile artifact
(ADR 0022), the measured `heightroof`, the documented 25 ft default. MapLibre
keeps the ground, the water, the roads, the shoreline and the labels. The two
extrusion layers (mass and crown) retire the day the Three.js buildings reach
visual parity, and not before — the city never goes buildingless in between.

What the shader owes, taken from what reference 02 is actually made of:

1. **Dark glass mass** — near-black, saturated toward indigo, with the vertical
   gradient authored by us rather than inherited from MapLibre's light.
2. **Procedural window speckle** — a sparse grid of emissive dots computed in
   the shader from world position, no sprite, no network, density a
   quality-tier knob. This closes §5.3's deferred item without the baked-sprite
   workaround and without touching the offline guarantee.
3. **Edge light** — rim lighting on silhouette edges, which is the read all
   four references are built from and the thing `fill-extrusion` can never do.
4. **Distance haze** — fog in the same shader, behind the skyline and in front
   of nothing near (§2.1's "careful"), which is most of the atmosphere the
   audit found missing.

**The acceptance test for the look is the human, holding the reference.** Not
an assertion suite. Screenshots of the running city are judged against
`02-skyline-grid-plane-light-columns.jpg` by the person who filed it, and the
task is done when they say it is. Tests pin only the semantics that must
survive any material: ADR 0029's brightness stack (city < hiring building <
open role, floor and margin), `neon-*` carrying no meaning, `dusk-*` never
touching an object. A test that pins taste is how the city stayed grey for two
milestones; this ADR declines to rebuild that mechanism on a new layer.

**The working method for aesthetic tasks changes with it, and Task 8 writes it
into the docs:** visual tuning runs on a screenshot loop — render, look, adjust
— with the frame timer running and the semantic tests as the only gate. Full
rigor stays exactly where it has always earned its keep: the data, the
placement rules, the honesty machinery.

## Consequences

**Performance must be re-measured, and the quality tiers stop being optional.**
The visible-set at the opening pose is ~25,000 footprints (ADR 0029's count);
chunked, merged buffer geometry handles that, but window density, haze and
(later) bloom all scale with tier, so M4d Task 2 becomes load-bearing for this
ADR rather than a follow-up. The M4d Task 1 instrument is the referee before
and after every step. **The top tier is allowed to require a real GPU.** On the
Intel Iris this project is developed on, the full look at full density may not
hold 60fps; the tiered look must. That is a stated trade, not a failure to be
discovered later.

**Culling and level-of-detail become our problem.** MapLibre was silently doing
tile-level culling for the extrusions; the Three.js buildings need chunked
loading by camera distance and a far cutoff into the haze. The haze is not only
mood — it is what makes the cutoff honest to the eye.

**Picking is unaffected.** Roles, marks and beams pick against their own
meshes (ADR 0027); nothing ever picked a building.

**What this does not license.** Nothing about placement moves. A building still
lights only because a confirmed office is in it — I1, ADR 0024 — and the
unresolved layer stays the default for everything unplaced. This ADR changes
what a building is made of, never what it is allowed to claim.

**What it costs if wrong.** If the Three.js buildings cannot reach parity at
acceptable frame cost on tiered settings, the extrusion layers are still there
until parity day, and the fallback is the status quo — grey boxes with a neon
slab, plus a written record of exactly what was tried. The geometry pipeline is
shared either way, so the experiment risks render code only.
