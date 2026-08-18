# ADR 0032 — The sky is ours, and the reference's framing is not reachable

- **Status:** accepted
- **Date:** 2026-08-18
- **Milestone:** M4e Task 3
- **Closes:** ADR 0029's "Still open" — the horizon glow, the sun and the
  starfield that the built-in `sky` block could not draw
- **Bounds:** ADR 0031's standing commitment, in one specific way stated below
- **Relates to:** ADR 0025 (a second library in MapLibre's context), ADR 0022
  (the pinned tiles), `city.md` §2.1, §3, §5.1

## Context

ADR 0029 lit the city and left the sky explicitly unfinished, with two
measurements attached to the refusal:

- Pitch is capped at 78, so the sky is a shallow strip by construction.
- The hard edge under the sky is drawn ground, and `fog-ground-blend` and
  `horizon-fog-blend` swept from 0 to 0.85 did not move it.

Both stand. A third was taken while building this task, and it is the one that
matters beyond this milestone.

**MapLibre's pitch is measured from straight down.** The view direction is
therefore `90 - pitch` degrees *below* horizontal, and with a 36.9° vertical
field of view the horizon lands near the top of the frame at every pose this
camera can reach:

| Pitch | Horizon, from the top of frame | Highest sky on screen |
|---|---|---|
| 70 | off the top — no sky at all | — |
| 76 (the opening pose) | 12% | 4.4° |
| 78 (`CAMERA_LIMITS.maxPitch`) | 17% | 6.4° |
| 85 (MapLibre's own ceiling) | 36% | 13.4° |

`02-skyline-grid-plane-light-columns.jpg` puts its horizon about **70%** down
the frame. Reaching that needs the camera to look *above* horizontal — a pitch
of roughly 94°, which is not a number MapLibre has. The reference is a
low-altitude shot across a plane; this is a map, and a map's camera looks down.

## Decision

**The sky is drawn by a custom layer of our own** — `map/skyLayer.ts`, one
full-screen triangle, one shader, raw WebGL rather than Three.js. It replaces
what the built-in `sky` block was doing and adds the three things that block
cannot express: a gradient authored across the elevations actually on screen, a
sun placed in the world, and a starfield.

Four parts, each answering something ADR 0029 left open:

1. **A gradient compressed into the visible strip.** Every stop sits below
   `sin(4.4°) = 0.077`. A gradient with its stops spread over a hemisphere puts
   one flat colour on screen at this pitch, which is ADR 0029's "neon purple
   rectangle placed at the top" rebuilt in a shader. The first draft did exactly
   that and was thrown away.

2. **The sun, fixed to the world.** Azimuth 285°, elevation 0.7° — west and a
   little north, which from Midtown is over the Hudson, and low enough that the
   city stands in front of it. It is a *stated lighting decision*, not a clock:
   a sun that tracked real time would make the map claim something about the
   world it has not measured, and at 3pm this city has no daylight palette. It
   is world-anchored rather than screen-anchored, so orbiting the city moves the
   camera and not the sun.

3. **A starfield from a hash, no sprite and no network.** The offline guarantee
   is untouched.

4. **Distance haze, and this is the part that is not "sky" at all.** The layer
   is inserted **below the buildings and above the roads**, and below the
   horizon it draws *over* ground MapLibre has already painted, with a density
   from the ray's real distance to the ground plane. That is what finally closes
   ADR 0029's hard edge — the fix could never come from above the horizon,
   because the band was drawn ground rather than void. The towers are drawn
   after this layer and are therefore unhazed until ADR 0031's building shader
   takes their share, which is the honest halfway state: weather behind the
   skyline rather than in front of it.

**The colours are held to ADR 0029's stack by test.** The sky's brightest
colour is the sun at 60.9 L\*, under `alert-400` at 63.6, under `signal-400` at
85.6 — scenery, then a hiring building, then an open role. `skyLayer.test.ts`
asserts it from both ends, over this file's own constants, and asserts that no
colour is typed straight into the GLSL where no test could read it. Nothing in
it pins a gradient stop, a haze density or where the sun sits in frame; those
are judged by eye, per ADR 0031.

**And the bound on ADR 0031's commitment, stated plainly:** the city will be
made of what reference 02 is made of — dark glass towers, lit edges, window
speckle, light columns, a graded sky with a sun in it. **Its framing cannot be
matched**, because the proportion of sky in that image requires a camera angle
MapLibre does not have. Where the two conflict, this ADR says which half of the
promise is deliverable, so that "it does not look like the reference" is never
again answered with a shrug about pitch.

## Consequences

**The cost was measured, and the first version was too expensive.** On the
Intel Iris Plus 645 this project is developed on, at 2880×1800 under a
continuous orbit: 50.6 ms p50 with the sky against 38.3 ms without — **12 ms a
frame** for one full-screen pass. Almost all of it was computing a sun, a glow
and a starfield for ground pixels where the haze is a fraction of one code
value. Computing the alpha *first* and returning early below 0.002, plus gating
the starfield's three hashes to above the horizon, took it to **25.8 ms with
against 26.2 ms without** — free within run-to-run noise. Both numbers are from
a real GPU in a headed browser; headless Chromium here is a software rasteriser
reporting ~600 ms frames and is evidence about nothing.

**A pitch cap raise is now a look decision, not only a tile-budget one.**
`CAMERA_LIMITS.maxPitch` is 78 because the tile budget explodes past it. Moving
to 85 roughly triples the sky in frame — 17% to 36% — which is the only lever
that exists for that proportion. Left open deliberately, as **Q9**, because it
trades frame cost against the look and both sides of that are the human's.

**The built-in `sky` block stays in the style.** It is drawn before the opaque
pass and this layer covers it, so it no longer decides anything visible; its fog
terms still tint the basemap's own layers. Removing it is a separate change with
its own before-and-after, and doing it inside this task would have mixed two
effects in one screenshot.

**What this does not license.** Nothing about placement, and nothing about the
`dusk-*` ring-fence: the sky is allowed to be this saturated *because* `dusk-*`
may never touch an object (`city.md` §3), so no mark can be confused with the
weather. A sky that reached for the signal cyan would put "an open role" across
several thousand square pixels of scenery, and the test file refuses it.
