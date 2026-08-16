# ADR 0029 — The city is neon, and the restraint that kept it grey was mine

- **Status:** accepted
- **Date:** 2026-08-16
- **Milestone:** M4e (Tasks 2, 4, 5)
- **Supersedes:** `city.md` §2.2's *"every building glows — that is the one thing this city may never do"*; PRODUCT-SPEC §9.2's *"buildings should not all glow"*; `docs/design/references/README.md`'s *"they are reference, not target"*; the `ink-400` ground cap and the 40 L\* headroom rule in `darkStyle.test.ts`
- **Relates to:** ADR 0023 (which reversed the other half of this rule), ADR 0028, `city.md` §2.1, §2.2, §3, §5.3

## Context

M4b and M4c shipped a city that renders offline, takes its heights from
measurements New York made, refuses to place a job it cannot place, and reports
its own frame times honestly. All of that is intact and none of it is at issue.

It also did not look like the thing it was specified to look like.

Four reference images were filed at `docs/design/references/` on 2026-08-11 to
set the target. On 2026-08-13 one of them —
`04-edge-outlined-towers-starfield.jpg` — was handed back with the note that the
vision had not been met. **Byte-for-byte the same file.** That is the finding
this ADR is built on: the target was recorded correctly and the implementation
did not reach it. This is follow-through, not a change of taste.

What was actually on screen, against what was asked for:

| Asked for | Delivered |
|---|---|
| Near-black towers with saturated neon edges | Pale blue-grey blocks; the brightest pixel on the map was `ink-450`, a desaturated grey |
| A sky with a gradient, a sun, stars | A flat magenta band with a hard edge across the top |
| A neon tiled ground | Streets at `ink-400`, barely visible; water indistinguishable from land |
| Hiring buildings bright enough to find | No building has ever been lit, because none can be |

**Three documents caused this and all three were mine rather than the spec's.**

- `city.md` §2.2 — *"**Every building glows.** That is the one thing this city
  may never do."* ADR 0023 already reversed half of it on the human's call.
- `docs/design/references/README.md` — *"They are reference, not target… all
  four light every building and Nightshift lights only the ones with something
  to say."*
- Two assertions in `darkStyle.test.ts`, which turned the above into a build
  failure: a cap pinning every colour outside the buildings source at `ink-400`,
  and a rule that the brightest colour anywhere sit 40 L\* below `signal-400`.

The argument was never wrong in its aim. If everything glows, glowing carries no
information, and PRODUCT-SPEC §9.2's *"most of the city should remain dark so
active data can breathe"* is a real constraint. What was wrong is that both
assertions protected that aim **through a proxy** — a token that happened to be
dim — and the proxy became the design.

## Decision

**The city is neon. Illumination is not the encoding and has not been since ADR
0023; shape, hue and level are.**

Four parts.

### 1. A `neon-*` family, which means nothing

The design tension is real and worth stating rather than dodging. Lighting the
streets in `signal-*` dilutes "cyan means an open role", which four milestones
have established. `dusk-*` is forbidden on objects (`city.md` §3), and that
ring-fence is the only reason the sky is allowed to be magenta at all.
`alert-*` means "something you can act on" and is what a hiring building is
drawn in. `gold-*` is urgency; `verdant-*` is an offer.

So the city's own light gets a family of its own, and the defining property is
that **it carries no meaning**. Electric indigo at hue ~252 — 64° off the signal
cyan, 81° off the alert magenta — on roads, rail, the shoreline and the
rooflines. It says "this is the city", the way a streetlight does.

```
--color-neon-900: #2f2170   L* 19.5   footpaths, rail
--color-neon-700: #4733ad   L* 31.2   minor roads
--color-neon-500: #6547d1   L* 41.0   major roads
--color-neon-400: #8a6bff   L* 55.2   motorways, shoreline, tower crowns
```

### 2. The two assertions are replaced by the rule they stood in for

Stated from both ends, so neither half can be satisfied alone:

- **Structural.** The style may paint only with colours from `MAP_PALETTE`, and
  every `MAP_PALETTE` entry is held to the headroom rule at the source
  (`palette.test.ts`). A neon cannot reach a layer by being typed inline, and
  cannot reach one through the palette either.
- **Numeric.** Every colour keeps **at least 20 L\* below `signal-400`**.

**20 is not a round guess.** `alert-400` — the hiring building, the brightest
thing the city itself is allowed to draw — sits 22.0 L\* below `signal-400`. A
margin of 20 admits it and admits nothing above it. The stack the product
depends on, brightest last:

> **city (≤55.2 L\*) < hiring building (63.6) < open role (85.6)**

### 3. A floor, which is the half that never existed

Every assertion this suite has ever held about brightness is **satisfied
perfectly by a map drawn entirely in `ink-950`.** For four milestones a suite of
exactly those assertions was green over exactly that city. A one-sided bound
cannot fail in the direction the product actually went wrong, and CLAUDE.md §7
says a test that cannot fail is not a test.

So: the brightest colour in the style must exceed **50 L\***, which only
`neon-400` reaches. The first draft of this floor said 40 and passed on
`ink-400` at 40.2 — the exact grey being replaced. It would have gone green over
the unlit city it was written to catch.

### 4. The mass goes dark and the light moves to the edges

The height ramp drops from `ink-800`→`ink-450` to `ink-950`→`ink-600`, and a
second `fill-extrusion` layer lights the top seven metres of anything over 400
feet. That is what reference 04 actually is: dark saturated silhouettes with the
neon on the outlines, over a ground bright enough to read them against.

## Consequences

**The encoding costs nothing.** Illumination stopped being the signal at ADR
0023, when a hiring building became a beam. A beam is vertical where the city is
horizontal; a hiring building is magenta where the city is indigo; a beacon is
cyan and 22 L\* brighter than either. None of those distinctions depend on the
scenery being dark — they depend on it being a *different shape and hue*, which
it now is by construction and by test.

**Three things were learned by building it, and each cost a wrong diagnosis.**

- **A style that omits `light` does not get no light — it gets MapLibre's**:
  white, `intensity: 0.5`, added to every extrusion face, setting a floor no
  paint can go below. The ramp was dropped four full shades and the towers came
  back the same pale grey. Found by hiding the crown layer and looking at what
  was left, after two rounds of reasoning correctly about the wrong component.
- **A `let`/`var` expression is fine in `paint` and matches everything in a
  `filter`.** The crown drew on every structure in New York and nothing errored;
  a sub-threshold building still draws its top cap, which with base equal to
  height is invisible from the side and a solid lit polygon from above. It
  looked deliberate.
- **The crown threshold came from a count**, after being picked by eye twice and
  being wrong twice. Of 25,176 footprints at the opening pose: 3,181 over 150
  ft, 1,107 over 250, 408 over 400, 103 over 600.

**PRODUCT-SPEC §9.2 loses on precedence, deliberately.** CLAUDE.md §0 puts
`docs/adr/` above `PRODUCT-SPEC.md`, and this is that mechanism being used for
what it is for. §9.2 was written before there was a renderer to look at. The
sentence it is judged against now is the human's, on 2026-08-13, holding one of
this repository's own reference images.

**What this does not license.** A building still may not be lit because a
company is in it — only because a *confirmed office* is in it, which is I1 and
ADR 0024 and is untouched. The `neon-*` family may never appear in the
interface, may never carry a state, and may never be used as text;
`colour-contrast.test.ts` reads the source and fails if it does.

## Still open

The sky is not fixed by this ADR and is not claimed to be. Two things were
measured while trying:

- **More sky needs more pitch, and pitch is capped at 78.** Higher pitch tips
  the horizon into frame; at 70 it leaves the viewport entirely. The sky is a
  shallow strip by construction.
- **The hard edge under the sky is far ground, and fog does not reach it.**
  `fog-ground-blend` and `horizon-fog-blend` were swept from 0 to 0.85 and the
  band did not move; recolouring `background` did not move it either.

`sky-horizon-blend` went from 0.8 to 0.55, which puts the gradient inside the
strip a person can see. The horizon glow that would close the gap, the synthwave
sun and the starfield need a custom layer, which is M4e Task 3.
