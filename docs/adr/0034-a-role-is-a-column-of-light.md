# 0034 — A role is a column of light, and cyan is what a role is

- **Status:** accepted
- **Date:** 2026-08-19
- **Supersedes:** ADR 0029's brightness stack as the *primary* separation
  between the city and its data. The stack itself is untouched and still
  asserted; it stops being the thing doing the work.
- **Touches:** `beacon.ts`, `markMesh.ts`, `roofBeamMesh.ts`, `treatments.ts`,
  `city.md` §6, `cityBuildings.ts`

## The problem, stated the way it actually arrived

The human approved a facade treatment that made the city polychrome — cyan,
blue, violet, magenta and amber windows over a navy and indigo mass. On the
first screenshot of it the beacons stopped winning. The proposed window cyan
measured 81.8 L\* against `signal-400` at 85.6: a window 3.8 L\* under an open
role, in the same hue.

The obvious fix was to dim the windows, and it is the wrong one. ADR 0029's
rule — every scenery colour stays 20 L\* below `signal-400` — was written for a
near-black city, and it is a *brightness* rule. The entire direction of M4e is
to make the city brighter and more saturated. Every future tuning pass will
push on that rule again, and each time the answer will be "dim the city," which
is the answer that made the city grey for two milestones (ADR 0029's own
finding, arrived at a second time).

**So brightness is the wrong channel to carry "this is a job."** It is a
channel that degrades every time the product gets prettier.

This is not a new argument in this repository. ADR 0023 made it one level up,
about hiring buildings: *"a brightness difference cannot carry ten in fifty
thousand — a bright thing pops against black and merges into a bright field."*
The beam was given shape and behaviour instead. The beacons never got the same
treatment, and they are the more important mark.

## What a role gets instead

Four channels the city structurally cannot use, in the order they do work:

1. **Motion.** Nothing in this scene animates. Not the buildings, not the sky,
   not the streets — the renderer is still by construction and only asks for a
   frame when a *signal* moves. Motion is the strongest separation available
   and it was being spent entirely on recency.
2. **Vertical continuity.** The city is horizontal bands and small rectangles.
   An unbroken vertical column is a different *kind* of mark, which is ADR
   0023's argument reused at the scale below it.
3. **Softness.** Every light in the city is hard-edged — a window has crisp
   mullions, an edge is a hairline. A glow with no edge is a different
   material.
4. **Position.** A role occupies sky. A window never does.

The body becomes a narrow vertical column of cyan light, in place of the
octahedron. The octahedron's original reason was sound — *"a diamond reads as a
signal rather than as a map pin"* — and it carried a flaw nobody wrote down: a
diamond has an orientation and a column does not. At the pitch this city is
read at you see the octahedron near edge-on, which is why a stack of roles
reads as a stack of rhombi rather than as one thing.

## The colour rule that replaces the brightness rule

**Cyan is a role. Nothing else in the city may be cyan.**

Narrow on purpose. The city is now genuinely polychrome — it has magenta
windows and amber rooflines, and a rule reserving every meaningful hue would
forbid the palette that was just approved. What is reserved is the one hue that
carries the product's central object, and it is reserved by a rule a test can
hold: a scenery colour within 20° of the signal hue must clear 25 L\*, against
the general 20. Same-hue confusion is the worse failure — a magenta window 20
L\* under a beacon is obviously not a beacon; a cyan one is a beacon somebody
turned down.

`aqua-400` #0096cc is the closest the scenery comes: 8° of hue away and 27.4
L\* down.

## The halo that was built and rejected

A soft dark disc drawn behind each beacon with multiply blending, so a mark
darkens the city around itself rather than adding light to it. It is how
signage reads at night, and it is the only channel here that gets *stronger*
as the city gets brighter.

It was prototyped, photographed and rejected by the human on sight. The
rejection was correct and the reason is instructive: each role in a stack got
its own quad, and where the quads overlapped their edges stacked into visible
horizontal bands — *"shadowy horizontal slits going across the beacons."* A
mark that darkens is right; a **separate object** that darkens is not, because
separate objects overlap.

What ships instead is the same idea bound to the geometry: a thin dark rim at
the column's own silhouette, computed per fragment. It cannot band, because
there is nothing to overlap.

## The pulse

The human's proposal was: whole, then slimmer, then dissipated, then back.

Shipped with one amendment — **the base never leaves.** What cycles is how far
up the column the light reaches before it thins out. The reason is that
disappearance is already spoken for: §6 spends it on *closed* (fading
afterimage) and *rejection* (dim neutral), and `beacon.ts` has carried a
comment since M4c saying a beacon that blinks out is a role that appears to
have closed, twice a second. A mark that periodically vanishes tells a lie
about a listing, which is I3's concern arriving through the renderer instead of
through the ingester.

The rise is **ambient and identical on every role** — it says "this is a job."
Recency stays on its own channels, the brightness pulse and `NEW_SCALE`, so the
two do not have to share one gesture. Two motions at different frequencies on
different quantities, rather than one motion carrying two meanings.

## Three vertical cyan things, resolved

Making a role a column created a collision that the prototype made visible: a
role, a hiring building, and an exceptional match all wanted to be a vertical
cyan bar.

- **Role** — narrow, hard-cored, cyan, rising. Many of them means many jobs.
- **Hiring building** — stops being a bar. The roof's own outline lights and a
  soft wash rises off it. A *place*, not a *thing*, so it can never be
  miscounted as a role. This is a change to ADR 0023's mark, not to its
  argument: the argument was "differ in shape and behaviour," and a beam that
  is now shaped like the thing it must be distinguished from has stopped doing
  that.
- **Exceptional match** — no separate mark at all. The role's own column gets a
  gold core running up inside it. The gold belongs to the job rather than
  floating beside it.

## The bug the last of those deletes

The gold match mark was drawn as a `CylinderGeometry` rotated to vertical in
world space — and then handed to `markMesh`'s billboard, which turns every mark
to face the camera *and* spins it about the view axis for the interview ring.
So §6's "gold vertical beacon" has been drawn as a slowly rotating diagonal bar
since M4c. The human spotted it in a screenshot before this ADR was written.

It is not fixed by correcting the orientation. It is fixed by the mark ceasing
to exist as a separate object.

## Consequences

- Every mark sized against `BEACON_RADIUS` is re-cut: the saved outline, the
  applied and offer cores, the interview arc, the selection reticle.
- Beacon size gains a pixel floor and a metre ceiling, which closes the M4c
  defect where a beacon is several times the size of the building it stands on
  at street zoom. It has been a fixed 34 m since M4c and nothing noticed while
  the whole field sat 700 m up.
- `city.md` §6's table gains a form column that is now load-bearing rather than
  descriptive.
- ADR 0029's stack stays, stays asserted, and stops being the argument.
