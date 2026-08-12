# 0027 — Selection is interface state, picked by raycast against the frame's own matrix

- **Status:** accepted
- **Date:** 2026-08-12
- **Milestone:** M4c, Task 4
- **Supersedes:** nothing. Extends ADR 0025 and constrains Task 5.

## Context

`city.md` §5.6 asks selection to do seven things: highlight the thing selected,
move the camera only if needed, open a detail panel, preserve filters, work from
the keyboard, write to the URL so it is shareable, and return cleanly on escape.
It then states the rule the whole M4c acceptance criterion rests on — *"the list
and the map cannot disagree"*.

Two facts about this codebase make the obvious implementation of the first of
those seven impossible, and both fail silently rather than loudly.

**The beacons are not MapLibre features.** ADR 0025 draws them as Three.js
instances inside a custom layer. MapLibre's feature index has never heard of
them, so `queryRenderedFeatures` returns nothing for a beacon under any pose,
with no error.

**And even for features it does know about, that query is useless here.** M4b
measured the whole-viewport form returning **zero** at the 76° pitch this city
opens at, with 30,573 building features loaded and visibly drawn — the viewport
rectangle is mostly sky, and the corners above the horizon have no ground to
unproject onto.

Separately, §6 already spends the palette. Every colour a highlight might
naturally use is assigned a meaning: white is *saved*, gold is *an exceptional
match or an urgent deadline*, green is *an offer*, pink is this product's alert
colour. Task 5 draws that table.

## Decision

**Picking is a raycast, and it inverts the matrix the layer actually drew
with.** The custom layer keeps the composed `mainMatrix · anchorTransform` from
its last `render` call; `pick.ts` inverts it, unprojects the pointer's near and
far clip points into scene metres, and raycasts that ray against the instanced
mesh. The nearest hit's `instanceId` indexes the same placement array the buffer
was written from, which is what turns an instance back into a `job_id`.

**Before the first frame, `pick` answers null.** There is no matrix yet and no
honest answer.

**Selection is one value in the scene store**, `selected: string | null`. The
beacons, the roster rows, escape, the panel's close button and the URL all read
and write that one value. The custom layer subscribes to it outside React, so a
selection moves one mesh rather than re-rendering anything holding a WebGL
context.

**The URL is synchronised in exactly one component**, `CityDetail`, through a
single effect that decides direction by which side changed.

**The reticle is a white ring, and it is deliberately not one of §6's marks.**
§6's table encodes *states of a role*. Selection is a state of the *interface* —
which role the panel is currently describing. So the mark is a different kind of
thing: an annulus in the air around the beacon, at roughly twice its radius,
touching nothing.

## Why not the alternatives

**`queryRenderedFeatures`.** Cannot see a custom layer's instances at all, and
was separately measured returning zero at this city's opening pitch. Both
failures are silent.

**Recomputing the projection from the map's pose.** Would let picking work
without the layer keeping anything, and would be a second implementation of
MapLibre's camera — free to disagree with the first by a few pixels near the
horizon and by a whole building next to it. The bug it produces is "clicking
sometimes selects the wrong role", which is the hardest kind to notice.

**Colouring the selected beacon instead of ringing it.** Cheaper — `setColorAt`
on the instance, no second mesh. Rejected because it makes the city claim
something about the *job* that is not true: every colour in this palette is
spoken for by §6, and a person who has learned that white means saved would read
a whited-out beacon as a saved role. A ring is a cursor, the way a marquee
around an icon is not a claim about the file.

**Gold, which reads best against cyan.** §6 gives gold to "exceptional match or
urgent deadline". Selecting a role would appear to promote it.

**`push` rather than `replace` for the URL.** Clicking through a field of
beacons would fill the back stack with one entry per role, and the back button
would walk backwards through a browsing session instead of leaving the page.
`/explore`'s filters made the same choice for the same reason.

**A store selection cleared on unmount.** `reset()` deliberately does not touch
it. The selection lives in the URL, so clearing it on unmount would make
navigating away rewrite the address bar, and a link followed and then returned
to would have lost its `?job=`.

## Consequences

**The layer's bounding sphere must be invalidated on every buffer rewrite.**
three caches `InstancedMesh.boundingSphere` on first raycast and gates every
later one on it, so a field that grows keeps a sphere too small to admit its new
columns — and picking stops working, silently, for exactly the employers that
just arrived. `setSignals` nulls it; `pick.test.ts` demonstrates the trap rather
than describing it.

**The reticle has to be re-placed whenever the field moves.** Every sort
reorders the columns, so a mark written once at selection time ends up ringing
whichever employer now stands there — right role selected, wrong beacon marked.
`setSignals` re-places it, and `selectionAt` is exposed so a test can see the
difference.

**A selected role can exist with no mark on the city.** A shared link to a role
that has since closed, or a poll that removed one while the panel was open. The
selection survives — it is in the URL — the reticle does not, and the panel says
which case it is. `selected` and `selectionAt` are therefore separate readings.

**Task 5 inherits a constraint.** When the §6 treatments arrive, the saved
outline and the selection reticle must stay distinguishable: §6's white is a
*thin line on the body* of a beacon, this is a *ring in the air around* it. If
that stops being legible at a glance, the reticle changes shape rather than the
saved treatment changing colour — §6 is the spec and this is not.

**The hover cursor costs a raycast per `mousemove`.** It is the only thing on
the canvas that says a beacon is clickable at all. The raycaster is hoisted to
module scope so a trackpad does not allocate a hundred a second, and the pick is
skipped while the map is moving — MapLibre puts `grabbing` on the canvas
container during a drag and a `pointer` set on the canvas itself would win over
it.

**A drag does not clear the selection.** MapLibre's own event handler suppresses
`click` when the pointer moves further than `clickTolerance` between press and
release. Checked in the library rather than assumed: the failure — losing your
selection every time you move the map — would have been blamed on almost
anything else.
