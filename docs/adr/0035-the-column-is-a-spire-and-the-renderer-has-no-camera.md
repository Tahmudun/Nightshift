# 0035 — The column is a spire, and this renderer has no camera to ask

- **Status:** accepted
- **Date:** 2026-08-19
- **Amends:** ADR 0034, which decided a role is a column of light. The decision
  stands. Its shader asked two questions that have no answer in this renderer,
  its geometry stopped carrying a size anything could pick, and its height was
  the width rule applied to the wrong axis.
- **Touches:** `beacon.ts`, `signalLayer.ts`, `markMesh.ts`, `selectionMesh.ts`,
  `city-acceptance.spec.ts`, `.rise.mjs`

## What was reported

> *"the beacons are short. they dont spire up to the sky, which makes them not
> really beacons. at large city scale it can be hard to spot beacons. also they
> arent animated like we said."*

Three complaints. All three were true, and the second and third had a cause
nobody had guessed: **the beacon bodies were not on the screen at all.** What
had been looked at for two days were §6's marks and the roof beams, which are
also vertical cyan things standing on the same anchors.

## The first two defects, and why each hid the other

ADR 0034's shader asked for two things that a conventional Three.js scene
provides and this one does not. ADR 0025 is explicit about why: MapLibre hands
the custom layer **one composed matrix** taking scene metres straight to clip
space, and the model-view is left alone. There is no view matrix in this
renderer. `selectionMesh.ts` and `labelMesh.ts` have said so in prose since
M4c, and both push the map's bearing and pitch in by hand because of it.

**The soft edge.** `vThickness = abs(normalize(normalMatrix * normal).z)` is
the standard way to ask "is this surface facing me" — in a renderer with a view
matrix. Here `normalMatrix` carries no view rotation, so that `.z` is the
*world's* up rather than the camera's forward. A cylinder standing on end has
purely horizontal normals. The expression was **exactly zero at every vertex**,
and every beacon body multiplied out to alpha 0.

**The pixel floor.** `projectionMatrix[1][1]` was read as `1/tan(fov/2)`, which
is true of a perspective projection and false of a matrix that folds the whole
world transform in and carries a scale of about 1e-7 there. The growth factor
came out in the thousands. Every column was scaled to tens of kilometres across
and hundreds of kilometres tall.

Neither raised an error. Neither produced a broken-looking frame, because the
first one made the second one invisible: with alpha 0 you cannot see that the
geometry is a continent. Fixing only the size gives a solid white window;
fixing only the edge gives a city that looks exactly as it did. **The two
defects were each other's alibi**, and that is the general shape worth
remembering, not the specific arithmetic.

Both are now measured rather than assumed. The horizontal direction to the
camera comes from the eye position `signalLayer` already computes out of the
frame's own matrix for the building haze; the two pixel floors come from
projecting one metre and looking at where it lands. Neither needs to know what
the matrix contains, which is the property worth having when the matrix belongs
to somebody else.

## The third defect, found by running a suite nobody had run

Neither of the two above breaks a test, which is how they survived. The one
that does had been failing since the day ADR 0034 merged, in a suite that needs
a database and had not been run since: **every beacon was unclickable**, and
ten seeded browser tests said so.

Same root, one level over. `pick.ts` raycasts three's own geometry, and ADR
0034 moved the column's size out of the geometry and into the vertex shader —
which it had to, because the pixel floor needs to know how far away the column
is and the geometry does not. What was left on the CPU was a *unit* cylinder: a
metre across and a metre tall, in a city where a metre is a sixth of a pixel.
The octahedron it replaced carried its 34 m in its constructor.

The fix is that the geometry carries the **click target's** size — 24 m across,
and the role's own 45 m slot of the column — and the shader scales from that to
the light. One size on the CPU, one shape on the screen, each written once.

A whole-spire target was tried first and is wrong for a reason worth recording:
roles at one employer stack **coaxially**, 45 m apart on the same axis. Give
each a 1.65 km tube and every tube in the stack occupies the same sky as every
other, a ray through any of them passes through all of them, three returns the
nearest, and one role answers for the whole company. At 45 m the targets *tile*
— role *n* owns the 45 m above its own anchor and nothing else — and the test
that picks two roles at one company goes green. The cost is that most of a
spire is not clickable, which is the right trade: the light is a flag visible
from twelve kilometres, and the role is at its foot.

## The height, which was a design error rather than a bug

`COLUMN_HEIGHT` was 90 m — "about twenty storeys", chosen so a role would
belong to the building it stands on. That reasoning is right for the *width*
and it does not transfer. A mark whose width belongs to its building reads as
standing on it; a mark whose height belongs to its building reads as part of
it. At the pose the city opens on, 90 m is about fifty pixels.

`docs/design/references/02-skyline-grid-plane-light-columns.jpg` is
unambiguous: the columns leave the buildings, cross the skyline and run out of
the top of the frame. `city.md` §2.1 already described the target in words — *"a
narrow column of light leaving a rooftop and dissipating with height"* — and 90
metres does not dissipate anywhere.

So the column is cut against two heights now:

- **`COLUMN_HEIGHT` = 1,650 m — the spire.** Three times One World Trade's
  spire, so a role is never in competition with the architecture under it. The
  test that pinned a ceiling of 120 m now pins a floor of twice 541 m: the rule
  inverted, and it is a better rule because it is the one the reference states.
- **`COLUMN_BASE` = 90 m — the body.** Everything that decorates a role rides
  the bottom of the column. The job is at the bottom; the spire is the flag.
  The interview arc was lifted to a third of the column's height and would
  otherwise be a hoop parked 560 m above the role it describes.

The reticle stops being derived from the column's height at all. It enclosed
the body end to end, which was legible at 90 m and would be a kilometre-wide
hoop at 1,650. What that derivation was really protecting is clearance from the
interview arc, and that is now asserted directly.

## The animation, and where an animation has to be

Two things were wrong, and only one of them was the gate.

**The gate.** ADR 0034 made the rise ambient and identical on every role. The
repaint request still asked whether some role was *new*. On the seeded corpus
27 of 30 roles are inside `NEW_WINDOW_DAYS`, so frames kept arriving and it
never showed — but the same corpus a week later is a city that goes completely
still in front of a shader fully able to animate it.

**The gesture.** The rise cycles how far up the spire the light reaches, and at
1,650 m the top of a column is off the top of the frame at every pose this city
is read at. The one part of the shaft the envelope changes is the one part that
is not on screen. Measured: two frames 2.5 s apart, pixel-identical along the
whole visible length.

So the envelope keeps its meaning and stops being the whole of it. Bands scroll
up the shaft — nine over its length, one passing a fixed point every 2.2 s — so
there is always motion in the first few hundred metres above the roof, where
the role is and where the eye already is.

**And they modulate rather than add.** Adding light at the bands is the obvious
way to write a travelling glow and it is invisible here: the core is already at
full strength, the material is additive, and light added to a clipped pixel
changes nothing. Dimming *between* the bands has headroom wherever the shaft is
bright, which is exactly where the motion has to be seen.

Under `prefers-reduced-motion` the whole thing is switched off by a uniform and
the column is drawn **whole**. Unlike the pulses, which are zeroed in the
instance buffer because they are facts about particular roles, the rise is not a
fact about anything — every column rises identically — so there is nothing in
the buffer for it to be honest about, and freezing the clock would leave a field
of columns cut off a third of the way up.

The cost is stated plainly: a city with one role on it now repaints
continuously. That is what an ambient animation is. `setMotion(false)` is the
way out and reduced motion takes it.

## What now fails if this regresses

The failure mode here is a mesh that draws nothing and a uniform that advances
in front of a shader ignoring it. Neither has a natural assertion, which is why
neither had one.

`city-acceptance.spec.ts` now serves a corpus chosen to make the beacon the
only thing on the city that can move: every role **old**, so no recency pulse,
and **unresolved and untouched**, so §6 draws no outline, no core, no ring, no
arc, and no roof beam stands under it. It then keeps a frame and counts what
fraction of the map changes — once when the field is taken away, and once with
the field left alone.

Every threshold was calibrated by running the test against the broken renderer:

| state | field paints | moves per frame |
|---|---|---|
| as shipped (both defects) | 0.5% | **0.0%** |
| size fixed, soft edge broken | 0.5% | 0.0% |
| soft edge fixed, size broken | **100%** | — (solid white) |
| both fixed | 2.9% | 0.46% |

The 0.5% is three name plates. The bodies contributed nothing at all — which is
also why an earlier draft of the test, comparing whole screenshots for
inequality, passed with the bodies invisible: the plates vanishing was
difference enough. Counting is what separates a field of columns from a field of
captions.

One more thing the table forced: the city has to have **finished assembling**
before any frame is compared to another. New York arrives over hundreds of
frames on a build budget, and a frame taken mid-build differs from the next by
two thirds of the canvas — 354,665 pixels against the 4,257 a field of columns
moves. Every assertion would have passed, for the wrong reason, forever.

`.rise.mjs` is the looking half: four stills across one cycle, to be flipped
through. `docs/reviews/milestone-4e-spires-motion.png` is one.

## Consequences

- Any shader added to this layer inherits the constraint. **The composed matrix
  is not a projection and the model-view is not a view.** Anything a shader
  wants to know about the camera is either pushed in as a uniform or measured
  by projecting a known quantity.
- The pixel floors gain a growth ceiling. It is a guard rather than a design
  parameter — behind the camera the perspective divide is meaningless, and a
  column that has left the frame should leave it rather than become a
  continent.
- `BEAM_LENGTH_FACTOR` drops from 1.55 to 1.08. Half again was 50 m of gold tip
  on a 90 m column and is 900 m of gold standing alone above a spire, which is
  the separate floating mark ADR 0034 deleted, rebuilt out of the thing that
  replaced it.
- ADR 0034's colour rule, its four channels and its argument are untouched. What
  changed is that three of the four are now actually drawn.
- **`make test-e2e-seeded` is not optional after a renderer change.** It needs a
  database, so it is the suite that gets skipped, and it is also the only one
  that clicks a beacon. It went from 18 passed / 10 failed to 28 passed here,
  and the ten had been red for two days.
