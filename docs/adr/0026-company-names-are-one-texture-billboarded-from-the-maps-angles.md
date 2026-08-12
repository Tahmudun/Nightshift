# 0026 — Company names are one texture, billboarded from the map's own angles

- **Status:** accepted
- **Date:** 2026-08-12
- **Milestone:** M4c, Task 3
- **Supersedes:** nothing. Extends ADR 0025.

## Context

`city.md` §4.8 asks for a field of unresolved signals that is "legible,
navigable, sortable". §4.1 measured that no ATS posting in this corpus names a
street, so this field is not a corner of the design — it is the default view of
the whole product, and it has to be a good screen rather than a placeholder.

After Task 2 the field was drawn and illegible. A column of cyan octahedra says
that *an* employer is hiring and never which one. Two things were missing: a
name on each column, and a way to reach a column without hunting for it in a
city-sized scene.

Putting a name into this scene is harder than it looks, because ADR 0025 gave
the renderer no camera of its own. MapLibre hands the custom layer one composed
projection matrix per frame and the three.js camera is an identity. Every
ordinary way to draw text in a 3D scene assumes otherwise.

## Decision

**One canvas atlas for every name, sampled per instance.**

All company names are painted into a single 2048×2048 canvas at 512×64 per cell
and uploaded as one `CanvasTexture`. The plates are one `InstancedMesh` of unit
quads; `uvOffset` and `uvScale` are per-instance attributes, and a
`ShaderMaterial` adds them to the geometry's own `uv`. One texture, one draw
call, N names.

**The billboard is computed on the CPU from `map.getBearing()` and
`map.getPitch()`,** written into each instance matrix, and refreshed on the
map's `move` event.

**The plates write depth; the beacons do not.**

## Why not the alternatives

**A `CanvasTexture` per employer.** The obvious implementation, and correct at
the three companies in today's corpus. At the 2,605 board tokens M1 measured as
immediately discoverable it is roughly 160 MB of texture memory and 2,605 GPU
allocations — `CLAUDE.md` §8's one-object-per-job anti-pattern, one floor down.
The atlas costs one texture at any corpus size.

**HTML labels positioned over the canvas.** Crisp text, free font rendering,
and reachable by a screen reader. Rejected on two counts: MapLibre markers have
no concept of altitude and these plates hang 700–1,300 m up, so the position
would have to be projected by hand every frame; and a DOM overlay cannot be
occluded by a building, which is most of what makes the scene read as
three-dimensional. The accessibility argument is answered better by the roster
panel, which is real DOM and carries every name in full.

**`Sprite`, or three's usual billboard trick.** Both derive the facing from
`modelViewMatrix`. ADR 0025 left no view matrix to derive it from — there is one
composed projection and nothing else. A sprite in this scene faces mercator's
+Z, which is straight up: the names would lie flat over the city like stickers.

**`MeshBasicMaterial` with `onBeforeCompile`.** Would avoid hand-writing a
shader, but the injection points are undocumented and version-fragile, and the
whole shader here is nine lines. Note that three declares `instanceMatrix`,
`position`, `uv`, `projectionMatrix` and `modelViewMatrix` itself for a non-raw
`ShaderMaterial` — redeclaring any of them is a compile error.

## Consequences

**A ceiling of 128 named columns**, which is the atlas divided by the cell. Past
it a column is still drawn and still listed in the roster; it has no plate. The
count of unnamed columns is reported in the interface, because a column with no
name that is not accounted for anywhere reads as a rendering failure rather than
as a documented limit. Raising it means a larger atlas or a smaller cell, and
the cell height is what sets legibility.

**Names longer than 24 characters are cut on the plate**, with an ellipsis so
the cut is visible. The roster carries the full name. A silently shortened name
reads as the company's actual name, which is the class of small lie §5.3 refused
for building heights.

**The billboard's bearing sign was settled by looking, not by deriving.** The
scene reaches mercator through a transform that negates y, and a negated axis
reverses the apparent direction of every rotation about z. The paper derivation
produced plates that faced the camera at bearing 0 and turned the wrong way as
soon as the map was rotated — correct in every screenshot taken from the opening
pose. `signals.labelsOrientedTo` exists so a browser test can catch the
listener never firing, which is otherwise invisible: the plates keep their names
and their positions and simply face the wrong way.

**Depth writing is inverted from the beacons, and deliberately.** The beacons
are additive and transparent and must not write depth, or their invisible
corners occlude each other. The plates `discard` every fragment below 2% alpha,
so only glyphs reach the depth buffer — which buys correct near/far ordering
between plates. Without it they paint in instance order and an employer at the
back of the field draws its name over one at the front. Observed at bearing 90°,
where the columns line up.

**jsdom cannot paint an atlas**, so `paintAtlas` returns null there and the
field degrades to plates with no texture. The layout arithmetic is unit-tested
without a canvas; the pixels are checked in `city.spec.ts`, where there is a
real 2D context. The native `canvas` package was declined — it is a build on the
critical path of `make setup` to buy one assertion a browser test already makes
better.
