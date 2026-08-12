# ADR 0023 — The city is lit, and meaning moves from brightness into the beam

- **Status:** accepted
- **Date:** 2026-08-12
- **Milestone:** M4b (Task 3)
- **Supersedes:** `city.md` §2.2's "these images with the lights off", and the `ink-400` brightness cap that followed from it
- **Relates to:** `city.md` §2.1, §2.2, §3, §6; AMENDMENTS A7; PRODUCT-SPEC §4.2, §9.2

## Context

`city.md` §2.2 committed the milestone to a dark city, in one sentence:

> Nightshift's city is these images **with the lights off**, where a building is
> lit because a company there is hiring and for no other reason. The neon is the
> encoding, not the wallpaper.

The argument behind it is sound and still is: PRODUCT-SPEC §9.2 asks that *"most
of the city should remain dark so active data can breathe"*, and if every
building glows then glowing carries no information.

M4b Task 2 implemented that faithfully and the result was shown to the human on
2026-08-11. The verdict was "underwhelmed": it did not feel like the reference
images, and it did not read as a city.

Three separate things were wrong, and only one of them was the design.

**The window.** The map was a 70vh panel on a scrolling document. It read as a
widget because it was one.

**A bug that had been there since the first commit.** MapLibre's own stylesheet
sets `.maplibregl-map { position: relative }` and is imported after the app's
CSS, so it beat Tailwind's `absolute` on equal specificity and silently dropped
`inset-0`. The canvas had been 300 pixels tall the whole time, inside a box that
hid the fact.

**The camera never looked up.** At 55° of pitch the frame is entirely ground.
The `dusk-*` atmosphere — sky gradient, horizon glow, the haze between the
viewer and the far city — was built, tested, shipped, and permanently off the
top of the screen. It is also, on inspection of the reference images, where most
of their character actually comes from: the violet *field*, not the buildings.

So the design was being judged through a 300-pixel letterbox with the sky cut
off. But fixing all three still leaves the question of §2.2, because a city with
the lights off is a dark city however well it is framed.

## Decision

**The city is lit. Meaning moves out of brightness and into form and motion.**

The human, offered "lit city with dark meaning", "full synthwave", and "keep it
as designed", chose the full reference-image look for the baseline city — the
version with no jobs on it at all.

The encoding survives the change because it stops depending on the one channel
the scenery now occupies:

| | Before | Now |
|---|---|---|
| An unremarkable building | Unlit | Lit — edge light, window speckle. Static, cool, architectural |
| A hiring building | Lit | A **beam**: a narrow column of light leaving the roof and dissipating into the sky. Vertical where the city is horizontal, and it moves |
| Everything else, when you filter | Unchanged | **Recedes.** Dimming becomes a response to a question rather than a fixed property |

The ratio is what settles it. The extrusion layer renders on the order of tens
of thousands of footprints in view; the number that will ever be hiring is tens.
A brightness difference cannot carry 10-in-50,000 — a bright thing pops against
black and merges into a bright field. A beam carries it at any background
brightness, because it differs in *shape and behaviour* rather than in level.
`02-skyline-grid-plane` in `docs/design/references/` is that beam, drawn before
this product drew it.

### What this costs, stated plainly

**Colour stops being available for job state.** New, saved, applied,
interviewing, offer — none of these can be a hue any more, because hue is now
scenery. They move into the beam: its height, its pulse rate, rings and arcs
around it. §6's table already worked mostly that way, so this is a constraint
rather than a rewrite, but it is a real narrowing and future state has to fit
through it.

**Crowding is now a live risk.** A dense lit skyline is a busier background than
black, so a beacon must be tuned against the worst case rather than the empty
one. Dynamic dimming on filter is the mitigation, and it is now load-bearing
rather than a nicety.

### What does not change

**`alert-*` still means "something is wrong and you can act on it", and
`gold-400` still means urgency.** The violet in the sky is `dusk-*`, which §3
already ring-fenced as atmosphere: never a mark, never a building, never a
selection state, never text. That ring-fence is what makes a magenta sky
compatible with magenta meaning something, and it is enforced by two tests
rather than by this paragraph — one reads every source file for a `dusk-*`
utility class, one reads every map layer's paint.

**A job is still the brightest thing on the map.** The `ink-400` cap on the
basemap is replaced, not removed: the rule is now that atmosphere and scenery
stay a stated distance below `signal-400`. `colour-contrast.test.ts` asserts
every `dusk-*` shade is under a third of the beacon's luminance;
`darkStyle.test.ts` asserts the brightest colour any map layer paints is at
least 40 L\* clear of it.

**Nothing here touches an invariant.** I1 through I7 are about not lying —
never placing a job on a building nobody confirmed, never claiming a
qualification the user did not enter. How bright the sky is has no bearing on
any of them, which is why this is an ADR and not a fight.

## Consequences

**§2.2 is superseded and `city.md` says so** rather than quietly disagreeing
with the code.

**The brightness proxy in `colour-contrast.test.ts` is replaced.** It asserted
every `dusk-*` shade was below 3:1 on `ink-950` — "too dark to be text at all" —
as a second belt against misuse. It worked, and it also kept the sky too dark to
be a sky. The rule it stood in for is enforced directly by the two structural
tests above, so the proxy went and the signal-headroom bound took its place.

**Tuning is now a per-task obligation, not a one-off.** A lit city has to be
re-judged when buildings land, when beacons land, and at each quality tier. The
tests hold the invariants; they cannot hold the taste.

## What was rejected

| Option | Why not |
|---|---|
| **Keep §2.2 as written** | It was producing a product the person building it did not want to look at, for a benefit — maximum beacon contrast — that a beam achieves without it |
| **Light the city, distinguish hiring by brightness alone** | What was first proposed. Ten brighter buildings among fifty thousand lit ones do not read; the encoding would have quietly stopped working while looking like it worked, which is the failure mode I7 is about |
| **Light the city, keep colour for job state** | The two collide directly. A magenta building means "stale posting" and "there is a sunset" at the same time |
| **A brightness slider** | Defers the judgement to the viewer, doubles what M4d must test, and would have shipped a default nobody stood behind |
