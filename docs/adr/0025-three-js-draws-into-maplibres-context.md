# ADR 0025 — Three.js draws into MapLibre's context, as one custom layer

- **Status:** accepted
- **Date:** 2026-08-12
- **Milestone:** M4c (Task 2)
- **Relates to:** `city.md` §5.1, §5.5, §4.8; `CLAUDE.md` §2, §8; ADR 0022, ADR 0024

## Context

`city.md` §5.1 names this "the single most consequential technical decision in
M4" and asks for an ADR when it is built. It is built; this is that ADR.

The product needs two renderers in one picture. MapLibre owns the projection,
the camera, the basemap and a million extruded buildings. Three.js is the tool
for everything else the milestone wants — instanced beacons, pulses, rings,
eventually a whole cinematic layer in M5. There are two ways to put them on the
same screen.

## Decision

**One WebGL context. Three.js renders into MapLibre's, through MapLibre's
`CustomLayerInterface`, using MapLibre's matrix.**

`apps/web/src/lib/city/signalLayer.ts`. The Three renderer is constructed with
MapLibre's canvas *and* its context, `autoClear` off; each frame the Three
camera's projection matrix is set to MapLibre's own matrix composed with an
anchor transform, and `renderer.resetState()` is called before drawing because
each library caches GL state the other has since changed.

### The alternative, and why it loses

Two stacked canvases — MapLibre below, a transparent Three canvas above, camera
kept in sync from MapLibre's move events. It is simpler to write and it fails on
two things that are not negotiable:

- **Register.** The overlay camera is synchronised by event, so it is always a
  frame behind during a gesture. At 76° of pitch, one frame of lag on a fast pan
  separates a beacon from its building by tens of pixels. It reads as the
  beacons sliding around on top of the city, which is precisely the "widget"
  quality M4b spent a task escaping.
- **Depth.** Two canvases have two depth buffers, so nothing in one can be
  occluded by anything in the other. Every beacon would draw over every
  building, including the ones standing in front of it. **Occlusion is most of
  what makes a scene read as three-dimensional**, and without it the signals
  stop being *in* New York and become stickers on a photograph of it.

`renderingMode: '3d'` is the half of the decision that cashes the second point:
it places the layer after the extrusions with the depth buffer live. As `'2d'`
the code would be identical, the tests would pass, and the beacons would float
over every tower.

## Consequences

**A shared context means shared state, and neither library expects it.**
`renderer.resetState()` before every draw is not defensive; without it the scene
renders correctly with somebody else's blend mode and depth settings. It is one
line and it is load-bearing.

**Teardown is ours.** `onRemove` disposes the geometry, the material and the
mesh. A leaked context outlives the page and the browser's limit is around
sixteen, after which the *next* map fails to create with an error naming none of
this — the same failure mode `CityMap`'s `map.remove()` comment already records.

**The scene is written in metres, not mercator.** Mercator units are a fraction
of the world and vary in metres-per-unit with latitude, which makes every number
in the layout code unreadable. An anchor transform converts the whole scene once
per frame, so `unresolvedField.ts` can say "700 metres above the ground" and
mean it.

**React never enters the render loop.** Zustand holds the scene state
(`lib/city/scene.ts`); the layer subscribes to it *outside* React and pushes
into an instance buffer. A fetch resolving updates a buffer rather than
re-rendering a component that owns a WebGL context. §5.5 asks for one geometry,
one draw call, N transforms, and `CLAUDE.md` §8 names the alternative as an
anti-pattern by name.

**The layer attaches on `styledata`, not `load`.** This is M4b's scar
reappearing one floor down: `load` and `isStyleLoaded()` both wait for every
source in the viewport, and at this pitch the viewport reaches past the edge of
a city-sized archive, so neither ever fires. Attaching to `load` produced a map
with a full instance buffer and no layer in its style — no error, no beacons.
Caught by a seeded browser test asking `getLayer` for it.

## The failure that took the longest, recorded because it will recur

MapLibre v5 hands the render method **two** 4×4 matrices. Both typecheck, both
look right, and they are in different spaces:

| Argument | Space | Anchor at the opening pose |
|---|---|---|
| `defaultProjectionData.mainMatrix` | Spherical mercator 0..1 | clip x ≈ 0, y = 0.41 — **centre frame** |
| `modelViewProjectionMatrix` | MapLibre's internal world space | clip x = **-3.02** — three screens off to the left |

`modelViewProjectionMatrix` is the better-sounding name and the wrong one. Its
failure is silent and total: every count is correct, the layer is in the style,
the buffer is full, `drawn` reports 31, five browser assertions pass — and the
canvas shows nothing whatsoever. It reads as "the beacons are not drawing" and
sends you to inspect the material, the blending and the depth test, none of
which are wrong.

What settled it was measuring rather than reading: a temporary probe applying
both matrices to the same scene point and printing the clip coordinates. Two
numbers, and the question was over. **Every count in this layer can be right
while nothing is on screen**, which is worth knowing before the next person
spends an evening on it.
