# 0028 — What a beacon is allowed to claim, and the four rows that could not honestly claim it

- **Status:** accepted
- **Date:** 2026-08-12
- **Milestone:** M4c, Task 5
- **Supersedes:** nothing. Applies ADR 0027's standing instruction and constrains M4d.

## Context

`city.md` §6 is a table of thirteen rows. Each gives a state of a role a visual
treatment, and PRODUCT-SPEC §4.3's last line makes documenting those meanings
**in the interface** a deliverable rather than a note. Task 5 draws them.

Three things about that table are not obvious until you try to implement it.

**It is a table about the reader, not about the corpus.** Six of its rows —
saved, applied, assessment/interview, offer, rejection, and half of gold —
encode what has happened between *this person* and a posting. The city endpoint
knows none of that. It is in `/applications` and `/matches`, which the rest of
the product already fetches.

**Four rows cannot be drawn honestly on this corpus**, for four different
reasons, and each reason is a fact rather than an excuse.

**And one row collides with something that is not in the table at all.** ADR
0027 drew selection as a white ring and left a standing instruction: §6's white
belongs to *saved*, and if the two stop being distinguishable **the reticle
changes shape — §6 is the spec and the reticle is not.**

## Decision

**§6 is one table in one file, read by three consumers.** `treatments.ts` holds
the rows and one pure function that resolves a role's marks from its signal, its
application stage, its ranking and the clock. The renderer reads it to choose a
colour, the legend reads it to explain that colour, the detail panel reads it to
say the same thing in a sentence. A shader that decided its own encoding would
be a second copy of the table, free to disagree with the legend that claims to
document it — and a legend that disagrees with the city is worse than no legend,
because it is believed.

**Intensity tracks what you can act on** (A7). `archived` suppresses the pulse
and the beam rather than layering over them; an applied role stops pulsing,
because "new" is an invitation to look and a role you have acted on is not one.
Nothing in this encoding gets brighter as a process goes badly.

**Two refusals are invariants, not taste.** A `fraction` of `null` earns no gold
— nothing could be assessed, and reading that as a score is a qualification
claimed from no evidence (I2). And a verdict that is not `eligible` earns none
either, however high the number: `matching.md` §5.2 keeps the state beside the
score and never inside it, so a 99 that is `uncertain` gets nothing. The beam is
a pointer to a role's own page, where the decomposition I4 requires actually
lives; it is never the evidence.

**The pulse is not the only thing that says "new".** `prefers-reduced-motion`
zeroes every pulse *in the instance buffer* rather than behind a uniform the
shader ignores — the data says the city is still, because it is. A new role stays
drawn larger, and the roster and legend name it in words, so the treatment does
not disappear for the people who asked for less motion.

**The gold beam floats.** §4.8 says the unresolved field touches nothing and that
"the absence of a ground connection is the entire message". A vertical shaft long
enough to reach the street would draw a line from a floating role to a building
nobody confirmed — I1 broken by a decoration. The beam is 460 m centred on a
field whose base is 700 m, and the test asserts that relationship rather than the
number.

**Saved keeps §6's white, and the reticle keeps its shape** — because they turned
out to be distinguishable by *kind* rather than by colour. The outline is a
wireframe on the beacon's own body at 46 m; the reticle is a camera-facing
annulus in the air around it at 62–78 m, touching nothing. One is a property of
the role, the other a cursor. The first draft of this task changed the outline to
cyan instead, which is precisely the resolution ADR 0027 ruled out.

**Four rows are not drawn, and the legend says so with its reasons.**

| Row | Why not |
|---|---|
| Approximate location — translucent radius | No role in this corpus resolves to an area. It takes a confirmed office at approximate confidence and there are none, so there is nothing to draw and no test could see it on screen. |
| Closed — fading afterimage | An afterimage belongs to the session that watched a role close. Closed listings are absent from a cold load by design (`city.py`), so there is nothing on screen to fade. It arrives with live polling. |
| Applied — "solid illuminated **building**" | Nothing in this corpus stands on a building. The beacon's own body fills in instead: a core at three-quarters of its radius, at full strength. |
| Urgent deadline | Drawn, but no posting in the seeded corpus carries one — `application_deadline` is almost always null across all three providers. The legend counts it rather than implying it is live. |

**A legend that listed only the drawable rows would document the renderer rather
than the language**, and would quietly shrink every time something was deferred.
I7 in the one place a product is most tempted to commit it.

## Consequences

The seed now creates five applications, one at each stage the city draws, through
`save_job` and `change_stage` and no shortcut. Without them every lifecycle row
was unreachable in `make demo` and unassertable in the seeded browser suite — an
implemented encoding that reads exactly like an unimplemented one. Inserting
`Application` rows directly would have skipped the append-only event trail M2
built the subsystem around, which is the mock I7 forbids.

`/city/signals` gained `last_seen_at`, `last_verified_at` and
`application_deadline`. The first two are deliberately separate: ADR 0007's
phase-2 polling never refetches an unchanged posting, so "the board listed it"
and "we read its text" diverge by design, and §6's stale row asks the panel to
say *which* it has.

Two rows share one instanced mesh and are kept apart by per-instance colour and
size — applied fills its beacon, an offer's core stays soft. A closed torus was
the first draft of the interview ring and its rotation was **invisible by
construction**: a circle spun about its own axis draws the same pixels every
frame. §6's own words are "rotating ring / orbiting arcs", and it is an arc now.

M4d inherits two things from this. The pulses are the first thing in this layer
that asks for frames, so the frame-time instrumentation has something to measure
that is not a still image. And the four undrawn rows are the honest list of what
M5's cinematic pass has left to do.
