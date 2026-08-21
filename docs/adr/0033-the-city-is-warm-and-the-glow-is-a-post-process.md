# ADR 0033 — The city is allowed a second hue, and the glow is a post-process

- **Status:** accepted
- **Date:** 2026-08-18
- **Milestone:** M4e Task 7 (bloom), and the tuning pass ADR 0031 left open on Task 10
- **Amends:** `lib/map/palette.ts`'s standing rule that scenery gets exactly one
  saturated hue. ADR 0029's brightness stack is untouched and is tightened.
- **Relates to:** ADR 0025 (Three in MapLibre's context), ADR 0029 (the city is
  neon), ADR 0031 (the buildings are ours; screenshot-first for aesthetics),
  ADR 0032 (the sky is ours)

## Context

The human's verdict on ADR 0031's city, on 2026-08-18: *"much, much closer to
the vision. It's just missing color and glow."*

Both halves were right, and they turned out to be **one** problem rather than
two.

### Why there was no colour

`palette.ts` carried this rule, in its own words:

> Electric indigo, because every other saturated hue in this product is spoken
> for: cyan is a job, magenta is something you can act on, gold is urgency,
> green is an offer, and violet is the weather. A lit street has to be a colour
> that means nothing, or the encoding pays for the scenery.

The premise is true and the conclusion does not follow. It left **one**
saturated hue for every lit surface in New York — streets, corners, rooflines,
crowns, windows, the lot — and a city lit in one hue is a monochrome no amount
of tuning fixes. The frame had violet scenery, a violet-to-magenta sky and cyan
data: everything in it sat inside a 60° arc of the wheel, with no warm anywhere.

That rule was written when the city was grey and hue was the only channel
carrying the scenery/data distinction. It is not any more. A role today is
distinguished by **five** things before colour is reached: it floats above the
roofline, it pulses, it is far brighter, it wears a name plate, and it stands on
a beam. A 3 px amber square inside a wall shares none of them.

### Why there was no glow

Nothing in the renderer had ever drawn light *wider than the geometry emitting
it*. A window was a 2 px square, a roofline a 1 px line, and both stopped dead
at their own edge. Every one of `docs/design/references/` is built the other
way round — the halo is most of what the eye reads as brightness. A lamp with no
halo does not look dim; it looks like a drawing of a lamp.

## Decision

### 1. Bloom is a post-process over the whole composited frame

`lib/city/bloom.ts`, run at the end of the signal layer's render: a hardware
downsample of the colour buffer, a soft-knee bright pass, three blurred octaves,
added back additively.

**Over the finished frame, not over our scene.** The obvious implementation
blooms the Three scene into an offscreen target and composites it back — and it
would leave out the two brightest things on screen, because the streets are
MapLibre `line` layers and the sun is `map/skyLayer.ts`. Reference 02 *is* a
glowing ground plane and a horizon glow; blooming everything except those is
blooming the wrong half of the picture.

This works only because the signal layer is the last layer in the style, which
is now a load-bearing fact that nothing asserts. A `beforeId` added in
`CityMap.tsx` would break it silently.

**Cost, measured on the real GPU** at the opening pose, both samples in the same
window and the same run, camera spinning: **p50 37.9 ms with, 35.8 ms without —
2.1 ms.** It is behind `setBloom()` so M4d Task 2's quality tiers can drop it,
and so the A/B above can be run at all.

### 2. The scenery may be warm — an `ember-*` family, for windows and edges only

Four tokens, same discipline as `neon-*`: they carry no meaning, no mark may
ever be drawn in them, and they clear the palette's headroom rule.

Warm rather than a second cool, because warmth was the whole gap. Reference 02
is built on the opposition between an amber-lit tower and a cyan ground plane;
two neighbouring blues cannot make that picture at any saturation.

### 3. ADR 0029's brightness stack is not touched, and one margin is tightened

`city < hiring building < open role` stands. `ember-400` sits 29.2 L* under
`signal-400` and 7.2 under `alert-400`.

**The first draft of this ADR cleared the second of those by 0.8 L*.** It passed
`cityBuildings.test.ts` and defeated what that test is for: a difference the eye
cannot see is not a stack. The assertion now demands a stated margin of 3 L*
rather than a bare `<`, which is the change of the two that will still be
protecting something in a year.

## What this cost to find, and what it is worth writing down

**Three of these went wrong in ways that produce no error.**

1. **The effect ran for an hour drawing nothing.** Three leaves one of its own
   vertex arrays bound when `render` returns, so setting an attribute pointer
   without binding ours wrote into *its* array — and inherited the instancing
   divisor the beacon mesh sets. A divisor of 1 on the position attribute
   collapses the fullscreen triangle to a point. Every pass ran, every
   framebuffer was complete, the frame counter climbed, nothing errored, and the
   image was unchanged. A post-process is *supposed* to be subtle, so "no
   visible change" reads as "the constants are too low" rather than as "it never
   drew". It has its own vertex array now, and the comment saying why is longer
   than the fix.

2. **The first threshold excluded the entire city.** 0.5 luminance, against a
   palette whose brightest colour — `neon-400` — is 0.488. Nothing in New York
   could pass it. The number was picked from what a threshold usually is rather
   than from what this frame contains.

3. **Warm windows were invisible from where the city is actually looked at.**
   A bay is a third of a pixel at the opening pose and the shader had already
   replaced the speckle with its average, so the first two attempts at colour —
   warm windows, then warm crowns — changed nothing in the frame that matters
   most. The edge light is what draws the city at that distance, and warming a
   third of the towers is what finally put colour in it. **Windows are still
   worth having**: they are what the mid and close poses are made of.

The general lesson, which is ADR 0031's working method earning itself again:
**at each of these three the code was correct, the tests passed, and the picture
was wrong.** Only looking caught them.

## Consequences

- `palette.ts`'s one-hue rule is gone; its headroom rule is not. Any future
  scenery colour clears 20 L* under `signal-400` *and* 3 L* under `alert-400`,
  and `palette.test.ts` and `cityBuildings.test.ts` hold both.
- Bloom is a per-pixel cost over the entire viewport and is the first thing a
  quality tier should drop. M4d Task 2 owns that; `setBloom()` is the handle.
- The signal layer must remain the last layer in the style. Nothing enforces it.
- **The beam redesign, which M4e Task 7 also owns, is not in this ADR and is not
  done.** The diamond stack is still a diamond stack, and
  `docs/reviews/milestone-4e-roofs-close.png` — a beacon several times the size
  of the building it stands on at street zoom — is still open.
