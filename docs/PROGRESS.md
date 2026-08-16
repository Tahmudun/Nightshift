# PROGRESS

> Read this first, every session. If the repo state does not match what this
> file claims, fix this file before writing code.

**M0: COMPLETE — 6 of 6 acceptance criteria verified at commit `4c1643f`.**
**M1: COMPLETE — all four parts, 15 of 15 criteria verified.**
**M1a: COMPLETE, CI-green at `430347a`, merged to `main` as PR #1 (`54ef35a`).**
**M1b: COMPLETE and reviewed. Merged to `main` as PR #2 (`cf48719`).**
**M1c: COMPLETE, reviewed, CI-green at `19236f5`, merged to `main` as PR #3 (`f377303`).**
**M1d: COMPLETE, reviewed, CI-green at `75d9ab7`, merged to `main` as PR #4 (`044189e`).**
**M2a: COMPLETE, reviewed, CI-green at `76190c8`, merged to `main` as PR #5 (`910027a`).**
**M2b: COMPLETE, reviewed, CI-green at `6a10bb6`, merged to `main` as PR #6 (`2f984f3`).**
**M2c: COMPLETE, reviewed, CI-green at `e63ec2f`, merged to `main` as PR #7 (`e42d612`).**
**M2d: COMPLETE, reviewed, CI-green at `c6e5a97`, merged to `main` as PR #8 (`77e52ea`).**
**M2: CLOSED. All four acceptance criteria verified, all four PRs merged.**
**Q4 (CI pinning): ANSWERED and shipped. ADR 0016, merged to `main` as PR #10 (`0c5bcbd`).**
**M3a: COMPLETE, reviewed, CI-green at `3fbffd6`, merged to `main` as PR #9 (`452ec90`).**
**M3a.1: COMPLETE. Recall 0.459 → 0.861, precision 0.659 → 0.847, necessity 0.668 → 0.915.**
**M3b: COMPLETE, reviewed, CI-green at `7bfbf2d`, merged to `main` as PR #11 (`d2273e7`). `main` green after the merge.**
**M3c: COMPLETE, reviewed, CI-green at `42b989e`, merged to `main` as PR #12 (`03fa035`). All five CI jobs passed with no findings — the first slice in this project where CI found nothing. Review: `docs/reviews/milestone-3c-review.md`.**
**Q5 (relevance ratings): ANSWERED 2026-08-10. Thirty rated, profile filled — 12 good / 11 acceptable / 7 poor. M3d has a held-out set.**
**M3d: COMPLETE, reviewed, CI-green at `ade217b`, merged to `main` as PR #14 (`7b480e9`). `main` green after the merge.**
**M3: CLOSED. All six acceptance criteria walked with evidence — see "M3 acceptance" below. Two of the six carry a stated limit rather than a clean pass.**
**M4a: COMPLETE, CI-green, merged to `main` as PR #15 (`3a68bad`). All five CI jobs passed.**
**M4b: COMPLETE, reviewed, CI-green at `7dfdaef`, merged to `main` as PR #16 (`dfd4973`) together with M4c.** All six tasks done on `m4b-dark-city`. Tasks 1 (the artifact and its route, ADR 0022), 2 (MapLibre and the dark style), 3 (fullscreen, the sky, and the lights coming on — ADR 0023), 4 (New York's own measured skyline), 5 (the camera controller and its gesture surface) and 6 (the acceptance walk, in a browser) done. New York renders offline, full-window, under a violet horizon, 1,083,024 structures at heights the city measured, with no jobs on it — and it can be driven by mouse, trackpad, touch, keyboard and a control panel.**
**M4b's three criteria are walked with evidence from a real browser — 19 new tests in `apps/web/e2e/city.spec.ts`, each one shown able to fail. Two carry a stated limit: no physical touch device, and no Safari.** See "M4b acceptance" below, and `docs/reviews/milestone-4b-review.md`, which found two defects the first draft of the walk had passed over.
**The buildings artifact is published**: release `buildings-20260812`, 109,555,308 bytes, the size the manifest pins. Verified the clean-clone path by deleting the local copy and re-fetching it from the public URL — it downloads and clears its digest, so `make setup` gets the skyline anywhere.
**ADR 0023 reversed `city.md` §2.2 on the human's call: the city is lit, and hiring is carried by a beam rather than by being the only thing bright.**
**M4b's acceptance chain is fully green.** It was run step by step against still-serving containers while Docker's daemon was wedged — `migrate`, `drift`, `seed`, `test-e2e` (24 passed), `verify` and `test-e2e-seeded` (56 passed, 1 skipped) — leaving only container *startup* unproven. **That gap is now closed**: on 2026-08-12 Docker was force-quit and relaunched, the containers were removed outright with `docker compose down`, and `make up` created both from scratch to healthy with exit 0.
**M4c: COMPLETE, reviewed, CI-green at `7dfdaef`, merged to `main` as PR #16 (`dfd4973`).** All six tasks, all seven of `city.md` §7's deliverables, and its three acceptance claims walked in a browser.** See "M4c acceptance" below and `docs/reviews/milestone-4c-review.md`. Task 6 built the instrument the seeded corpus could not be: `apps/web/e2e/city-acceptance.spec.ts` serves a corpus this repo *chooses* — a fabricated placement, five thousand roles, a role at a confirmed building — against the real map, the real archives and the real instance buffers, with no API. It found three defects on its first run, all fixed: a page that counted roles the renderer does not draw and never said so (I7 in the form it actually arrives in), two ceilings coupled only by a comment (`MAX_BEACONS` vs `MAX_SIGNALS` — raise the API's and the surplus vanishes silently), and a `WebGLRenderer` whose compiled programs outlived the layer. **The milestone's lesson: a corpus that cannot produce a failure cannot test the guard against it.**
**The scale claim is an equality, not a bound.** 100 roles → 5,000 roles at a fixed 20 employers: **364 DOM elements before, 364 after**, 5,000 of 5,000 in the buffer, one canvas, one custom layer. One `<span hidden />` per role turns 364 into 5,264 and the test red. `docs/reviews/milestone-4c-scale.png` is the 5,000-role city — and it is also the evidence for the one limit this review records rather than fixes: **the field is legible at 31 roles and not at 5,000**, which is deferred to M4d beside the adaptive quality tiers it belongs with.
**M4c Task 5 is done: the city speaks §6, and says what it is saying.** The table is one pure function (`treatments.ts`), the beacons carry per-instance colour, strength and pulse rate through a shader, four instanced meshes draw the marks §6 puts *on* a body, and an in-interface legend documents all thirteen rows — including the four that are not drawn, each with its reason. ADR 0028. `docs/reviews/milestone-4c-treatments.png` is the screenshot. Three defects were found by looking rather than by a test: a closed torus whose rotation was invisible by construction, a spin folded into the billboard that rolled every arc out of the camera plane, and a saved outline drawn cyan — which is exactly what ADR 0027's standing instruction ruled out.
**M4c: Tasks 1, 2, 3 and 4 are done. The placement join and `GET /city/signals` (ADR 0024, which resolves a real conflict between I1 and `city.md` §4.4 rather than papering over it), the Three.js signal layer in MapLibre's own context (ADR 0025), and the field made legible, navigable and sortable. New York now has every open role floating above it, untethered, and none on a building — see `docs/reviews/milestone-4c-signals.png` and `docs/reviews/milestone-4c-roster.png`. Task 4 then made a role reachable: picking by raycast against the frame's own matrix, a reticle, a detail panel, and one selection shared by the list and the map (ADR 0027) — `docs/reviews/milestone-4c-selection.png`.**
**Docker's daemon is no longer wedged.** It was force-quit and relaunched on 2026-08-12. `make up` was then run **from cold** — containers removed with `docker compose down` first — and created both from scratch to healthy, exit 0. **That closes the last open step in M4b's acceptance chain**; container startup is now proven rather than assumed. The seeded corpus survived and matches what this file records: 31 canonical jobs, 62 `job_locations`, 44 `city_only` + 18 `remote`, 0 mappable.
**Current milestone: M4 — the living city, and the shippable checkpoint (A15). M4a, M4b and M4c are closed and on `main`; M4d is what remains.**
**PR #16 was the largest thing this project has merged — 43 commits, 106 files, ~20,700 lines, two milestones — because M4b and M4c are one renderer and merging a map with nothing on it would have been merging half of it.**
**The finding that shaped the milestone: no ATS posting names a street. 0 of 247, 139 distinct location strings, 10 fields, three providers. A job can never place itself on a building, so every building comes from an address a human confirmed.**
**Task 11 measured the embedding proposal path and declined to ship it — ADR 0018.**
**Task 12 gave the seed a reader to be about, and found three false claims on the page — ADR 0019.**
**M4e — the synthwave city — is sequenced ahead of M4d Tasks 2–7, on the human's call.** The city renders, is honest and is measured, and does not look like the thing it was specified to look like. One of the reference images filed at `docs/design/references/` on 2026-08-11 was handed back on 2026-08-13 with the note that the vision has not been met — **the target was recorded correctly and the implementation did not reach it.** Task 1 (the worksheet and its loader) is done; see "M4e Task 1" below.
**Last updated: 2026-08-16**

---


## Next exact action

### M4e — the synthwave city — is under way on `m4d-measured`, draft PR #17. Task 1 is done; next is Task 2.

**M4d Task 1 (the frame timer) is done and M4d Tasks 2–7 are deliberately
paused.** The overhaul below changes what a frame costs, so tuning the adaptive
quality tiers and the field-at-scale fix against the grey renderer would mean
measuring twice and believing the wrong number. The frame timer stays the
instrument every M4e task reports against.

**M4e Tasks 1, 2, 4 and 5 are done. Next is Task 3 (the sky) or Task 6 (the
hiring building).**

- **Task 1 — the worksheet, and the loader that was never wired up.**
  `data/company-locations.yaml` covers all 23 registry boards, and `make offices`
  runs it, verified live against NYC GeoSearch. See "M4e Task 1" below.
- **Tasks 2, 4, 5 — the city is neon.** ADR 0029. A `neon-*` family that carries
  no meaning; the two assertions that made the city grey replaced by the rule
  they stood in for, plus the floor that never existed; the road ramp and the
  shoreline lit; the building mass dropped four shades with the light moved to
  the roofline. Screenshots: `docs/reviews/milestone-4e-ground.png`,
  `milestone-4e-buildings.png`.
- **Task 3 — the sky — is not done, and `sky-horizon-blend` 0.8 → 0.55 is an
  improvement rather than the fix.** Two things were measured while tuning it,
  and neither can be solved from MapLibre's `sky` block: **more sky needs more
  pitch and pitch is capped at 78** (at 70 the horizon leaves the viewport
  entirely), and **the hard edge under the sky is far ground that fog does not
  reach** — `fog-ground-blend` and `horizon-fog-blend` swept 0 → 0.85 with no
  movement, and recolouring `background` did not move it either, because the
  band is drawn ground rather than void. The horizon glow, the synthwave sun and
  the starfield need a custom layer.
- **Task 6 — the hiring building — is unblocked by Task 1 and blocked by the
  human.** The pipeline runs end to end; what it needs is a street address in
  the worksheet. Zero are filled.

**The M4e task order**, from the slice plan:

1. ~~**The worksheet and its loader.**~~ **Done** (`3c25704`). First because the
   human is typing addresses now and the file they type into must lead somewhere.
2. ~~**A `neon-*` palette family**, and replacing the two `darkStyle.test.ts`
   assertions that turn "the city stays grey" into a build failure.~~ **Done**
   (`c8b9e0d`). ADR 0029.
3. **A sky, not a rectangle** — a custom layer with a gradient, a starfield, and
   a sun fixed due west over the Hudson. **Not done**; the two constraints
   measured while trying are above and in `darkStyle.ts`'s `sky` block.
4. ~~**The ground** — neon streets at graded intensity, a glowing shoreline.~~
   **Done** (`c8b9e0d`).
5. ~~**The buildings** — near-black saturated mass, neon crowns via a second
   extrusion layer.~~ **Done** (`1413c02`). **Window speckle was not built and is
   not currently planned**: `fill-extrusion-pattern` overrides
   `fill-extrusion-color`, so a patterned layer cannot also carry the height
   ramp, and the edge-lit read the references are actually built from came from
   the crown instead. If it is revisited it needs a same-origin baked sprite on
   the ADR 0022 pattern, or the offline guarantee goes.
6. **The hiring building** — `arrangeOnBuildings`, a BIN-filtered extrusion
   layer, roof beacons. Depends on Task 1 having placed an office.
7. **Bloom**, behind the quality tier, measured before and after.
8. **The documents that said not to do this** — ADR 0029 and the rewrites it
   forces in `city.md` §2.2/§3/§5.3 and `docs/design/references/README.md`.
9. **Addresses without typing** — `make propose-offices`, OSM proposes and a
   human confirms. May slip past this slice; if it does, this file says so
   rather than implying the pipeline exists.

**M4d Task 1's numbers, which still stand**: p50 16.6–16.7 ms in every scenario
at both 200 and 5,000 roles on an Intel Iris Plus 645, 0–3% of frames missing
the next refresh. See "M4d Task 1" below for the tables, the method, the one
191.7 ms hitch it found, and the defect it found **in the instrument** before it
found anything in the city.

**PR #16 is in `main` (`dfd4973`), all five CI jobs green at `7dfdaef` and green again on `main` after the merge.** M4a,
M4b and M4c are closed. `city.md` §7's remaining slice is the last one in this
milestone, and it is the one that turns impressions into numbers.

**M4d's tasks, in order. Tasks 2–7 resume after M4e.** Deliverables from
`city.md` §7 and `CLAUDE.md` §6.

1. ~~**Frame-time instrumentation, and a machine that admits what it is.**~~ **Done** — see "M4d Task 1" below. The criterion is met on this machine at both 200 and 5,000 roles, and the first run caught the instrument itself reporting a 60fps city as missing half its frames.
2. **Adaptive quality tiers** — Ultra / High / Balanced / Battery saver, over
   pixel ratio, animation density and label detail (§5.5). Chosen from what
   Task 1 measures, overridable by hand, and **named on screen**: a tier that
   silently downgrades the city is a city quietly lying about what it can do.
3. **The field at scale**, which is the limit M4c recorded rather than fixed
   (`docs/reviews/milestone-4c-review.md` §4.1): legible at 31 roles, not at
   5,000. Level-of-detail on the name plates, a camera that can frame the whole
   field, clustering. Third rather than first because the right fix depends on
   Task 1's numbers.
4. **Reduced motion, end to end.** The camera and the layer both honour it and
   both are asserted from data rather than a flag. What is not walked is the
   rest of the page — panels, transitions, the roster's fly-to.
5. **A keyboard path to every map action.** Most exists; this is the audit that
   earns the word *every*, and names what is missing rather than implying it is
   complete.
6. **Automated accessibility tests** (A14). The largest genuinely-absent piece.
7. **The M4 review, the deploy, and the case study.** **Q2 blocks the deploy and
   nothing else**: a paid target (~$5–10/month) ends M4d with a live link;
   local-only ends it with a recorded walkthrough and A9's $0 target held
   literally. An ADR gets written either way.

**Start by branching off `main`** — `m4d-measured` or similar — and by reading
`docs/architecture/city.md` §7's M4d entry and §8's deferred list before
writing code.

---

**Task 5, done: the city speaks §6, and says what it is saying.**
`docs/reviews/milestone-4c-treatments.png` is the screenshot. Six things
arrived:

| Piece | Where |
|---|---|
| **§6's table, as one pure function** — thirteen rows, and the resolver every consumer shares | `lib/city/treatments.ts` |
| **The beacon buffer** — per-instance colour, strength, pulse rate and size, through a `ShaderMaterial` | `lib/city/beacon.ts` |
| **The four marks §6 puts *on* a body** — outline, core, arc, beam, one instanced mesh each | `lib/city/markMesh.ts` |
| **The legend** — all thirteen rows, live counts, the four undrawn ones named as undrawn, and the archive toggle | `components/CityLegend.tsx` |
| **The non-3D equivalents** — the panel's "how this role is drawn", the freshness sentence, the roster's row marks | `CityDetail.tsx`, `CityRoster.tsx` |
| **The data it needed** — `last_seen_at`, `last_verified_at`, `application_deadline`, and five seeded applications | `api/routes/city.py`, `nightshift/cli.py` |

**Nine of §6's thirteen rows are drawn; four are not, and the legend says which
and why.** The four are in `city.md` §6.1 and ADR 0028. The short version: no
role in this corpus resolves to an area, an afterimage belongs to the session
that watched a role close, nothing stands on a building to illuminate, and no
posting carries a deadline. **A legend listing only the live rows would document
the renderer rather than the language** — I7 in the one place a product is most
tempted to commit it.

**Three defects found by looking rather than by a test, all in my own work.**

*A rotating ring whose rotation was invisible by construction.* A closed torus
is rotationally symmetric about its own axis: spinning it draws an identical
image every frame. §6's own words are "rotating ring / **orbiting arcs**", and
the second half of that phrase is load-bearing. It is a 240° arc now.

*A spin folded into the billboard.* The mark's own rotation was passed as the
`y` component of the same Euler that faces it at the camera, which inserts it
between the tilt and the turn and rolls the arc out of the camera plane. On
screen it stopped being a ring around a beacon and became a flat ellipse lying
across it. The billboard and the spin are now two quaternions composed in that
order, and `markMesh.test.ts` asserts the thing that distinguishes them: a spin
must not change where a mark faces.

*A saved outline drawn in cyan.* ADR 0027 left a standing instruction — §6's
white is spent on saved, and if the reticle and the outline stop being
distinguishable **the reticle changes shape, because §6 is the spec and the
reticle is not**. The first draft resolved the collision by changing the saved
treatment's colour, which is the one move that note rules out. It is white
again; the two are distinguishable by kind, and a test now pins the radius
relationship that makes them so.

**A fourth defect, found by a screenshot: "applied" read as nothing.** §6 asks
for "solid illuminated", and a small cyan core inside an additive cyan beacon is
invisible. Marks carry a per-instance size now, so an applied role's core fills
three-quarters of its body while an offer's stays soft — two rows of §6 sharing
one mesh, kept apart by colour *and* size.

**The seed had no applications, so every lifecycle row was unreachable.**
`make seed` creates five now, one at each stage the city draws, through
`save_job` and `change_stage` and no shortcut — a demo database whose
applications have no event history is a demo of something this product does not
do. The Makefile's own description of the command has claimed applications since
M0; it is true now.

**A tautological assertion of mine, caught before it shipped.** The dimming test
compared a role's alpha against `alpha / DIM_FACTOR`, which is true for every
positive number. It now compares a stale role against an open one at the same
employer.

**Two API fields, kept apart on purpose.** `last_seen_at` is "the board listed
it"; `last_verified_at` is "we refetched its content and read it". ADR 0007's
phase-2 polling never refetches an unchanged posting, so the two diverge by
design — a role can be listed daily while its text was last read months ago.
Collapsing them would let the panel print "verified" about the weaker fact. The
`max` across a merged role's source records was, in its first version, a test
that passed just as happily against `min`, because every seeded job has exactly
one record; it now builds a second board's record so the aggregate has something
to choose between.

**Three existing browser tests failed, correctly, and were rewritten rather than
relaxed.** "Every unresolved role reaches the instance buffer" stopped being
true the moment the archive toggle became real: one seeded role is rejected, so
the endpoint returns 31 and the city draws 30. The tests now read
`/applications` and subtract what §6 hides, which states the rule instead of
contradicting it — and still catches a beacon that fails to reach the buffer,
which is what they were for. The roster's per-employer count moved with them,
because the roster reads the same filtered list.

**A false alarm worth writing down: 1 failure and 21 errors that were nobody's
defect.** The Python suite was run while the seeded Playwright suite was
running against the same Postgres. Re-run alone: **1,940 passed, 0 failed**.
The seeded browser suite in that same window reported "14 did not run" and took
11.3 minutes; alone it is 5.4 minutes and complete. Neither suite is isolated
from the other's database, and nothing warns you — the failures name real tests
and look exactly like a regression. Run them one at a time.

**Evidence.** 187 unit tests in `lib/city` (up from 107), 43 web test files /
618 tests green, **1,940 Python tests green** (run alone), `make lint` and
`make typecheck` clean, 24 offline browser tests green, and **83 seeded browser
tests green, 1 skipped** — four of them new and covering the marks reaching the
GPU path, the archive toggle moving the *buffer* rather than only a list,
reduced motion zeroing the pulses in the instance data rather than behind a
uniform, and the legend listing its undrawable rows.

**Eight mutations, each shown to turn a named assertion red:**

| Mutation | Test that went red |
|---|---|
| `max` → `min` over a job's source records | a verified source record reaches the signal |
| marks not rewritten when a sort moves the field | moves every mark when a sort moves the field under it |
| `reducedMotion` ignored when writing the pulse | stops every animation under reduced motion |
| new roles not scaled up | pulses a role first seen this morning, and swells it besides |
| the beam never pushed | beams a role whose deadline is inside the window |
| dimming removed | dims a stale role without changing its colour |
| the saved outline drawn cyan | draws the saved outline in §6's white |
| the spin folded back into the billboard Euler | spins a mark without changing where it faces |
| deferred rows filtered out of the legend | three of the legend's assertions |

**Task 4, done: a role can be reached, and it says what its position means.**
`docs/reviews/milestone-4c-selection.png` is the screenshot. Five things
arrived:

| Piece | Where |
|---|---|
| **Picking** — a raycast that inverts the matrix the last frame drew with | `lib/city/pick.ts` |
| **The reticle** — a camera-facing white ring around the selected beacon | `lib/city/selectionMesh.ts` |
| **One shared selection** — `selected` in the scene store, read by the layer outside React and by every panel inside it | `lib/city/scene.ts` |
| **The detail panel, and the only place the URL is written** | `components/CityDetail.tsx` |
| **Roles in the roster** — every employer opens into its stack, and the selected row is marked | `components/CityRoster.tsx` |

**`queryRenderedFeatures` was never an option, for two separate reasons.** The
beacons are Three.js instances in a custom layer, so MapLibre's feature index
has never heard of them — no pose returns one. And M4b measured the
whole-viewport form returning zero at this city's opening pitch even for the
30,573 building features that *were* loaded and drawn. Both failures are
silent. So the layer keeps the composed `mainMatrix · anchorTransform` from its
last `render` and picking inverts it. Recomputing a projection from the map's
pose instead would be a second implementation of MapLibre's camera, free to
disagree with the first by a few pixels near the horizon — a bug that reads as
"clicking sometimes selects the wrong role".

**Three traps, all of which produce a plausible wrong answer rather than
nothing.**

*three caches the bounding sphere and gates every raycast on it.* A field that
*grows* keeps a sphere too small to admit its new columns, so picking silently
stops working for exactly the employers that just arrived. `setSignals` nulls
it. `pick.test.ts` demonstrates the trap in five lines rather than describing
it.

*A sort moves every beacon under the reticle.* A mark written once at selection
time stays at the old coordinates and ends up ringing whichever employer now
stands there — right role selected, wrong beacon marked. The reticle is
re-placed on every buffer rewrite, and `selectionAt` is exposed so a test can
see the difference rather than just that a mark exists.

*Two effects syncing a URL and a store ping-pong.* The store→URL effect closes
over the selection from the render **before** the URL→store effect adopted a
deep link, so `?job=…` is adopted and then immediately rewritten away. The link
works for one frame and destroys itself. One effect, one `agreed` ref, and the
direction decided by which side changed.

**The reticle is deliberately not one of §6's marks, and that is a product
decision rather than a rendering one.** §6's table encodes *states of a role* —
white is saved, gold is an exceptional match, green is an offer. Selection is a
state of the *interface*: which role the panel is describing. Colouring the
beacon would make the city claim something about the job that is not true, and
every colour in the palette is already spoken for. A ring in the air around the
beacon is a cursor, the way a marquee around an icon is not a claim about the
file. ADR 0027.

**A drag does not clear the selection**, and that was checked in MapLibre's
source rather than assumed: its event handler suppresses `click` when the
pointer moves further than `clickTolerance` between press and release. The
failure it would have caused — losing your selection every time you move the
map — would have been blamed on almost anything else.

**Two defects found while writing this, one in the product's tests and one in
mine.**

*A green assertion that compared unrelated numbers.* `reordering the field
changes the order and not the roles` returned the per-column role counts
**sorted**, then indexed that sorted array by a name's position — so the
"tallest first" check compared each employer's position against somebody else's
height. It could only pass or fail by accident. Found while replacing
`FieldColumn.roles` with `jobIds`; the counts are now parallel to the names.

*A test that clicked a pixel no mouse can reach.* The empty-sky test verified
the pixel picked nothing and clicked it, and failed — (30, 130) is inside the
title card, so the click never got to the map. That is Task 3's occlusion bug
arriving in the test rather than in the product. The scan now requires
`document.elementFromPoint` to be the canvas, and a new browser test clicks
every rail control **with a role selected**, which the existing occlusion test
could not see: the detail panel is the fourth panel in that rail and it is
absent unless something is selected.

**Two small things that turned out to be dead or wrong.** `writeRotation()` in
the reticle's `moveTo` looked prudent and could not be made to fail — the layer
orients the ring on attach and on every move, so it is always already facing
the camera by the time anything is selected. It is gone. And `selectionHref`
now `append`s rather than `set`s the parameter: `set` papered over a broken
filter by silently collapsing a duplicate, which left the test that says a
selection replaces rather than doubles with nothing to catch.

**Evidence.** 107 unit tests in `lib/city` (up from 66), 23 component tests
across `CityDetail` and `CityRoster`, and 24 seeded browser tests in
`e2e-seeded/city.spec.ts` (up from 13). Full suite green on 2026-08-12:
`make check` (1,936 Python, 518 web, format, lint, typecheck), `make test-e2e`
(24 passed), and the seeded browser suite (22 passed before the rail test, 24
after).

**Twelve mutations, each shown to turn a named assertion red:**

| Mutation | Test that went red |
|---|---|
| `ndcFromPointer`'s y flip removed | five, across the ray maths and the layer's own pick |
| ray direction negated | points away from the viewer rather than towards them |
| `mesh.boundingSphere = null` deleted | can still pick the roles that arrived after the last pick |
| `placeReticle()` dropped from `setSignals` | moves the reticle when a sort moves the field under it |
| reticle `BEARING_SIGN` flipped | turns to the camera, in the direction a rotating map actually turns |
| the `key !== SELECTION_PARAM` filter removed | three of `selectionHref`'s assertions |
| the deep-link adopt's `return` removed | does not immediately delete the deep link it just adopted |
| the map's `click` handler emptied | clicking a beacon selects the role it draws; clicking empty sky puts it down |
| `layer.setSelected` dropped from the store subscription | the reticle moves with the field when the ordering changes |
| the escape listener removed | escape clears the selection, and the URL with it |
| every other query parameter dropped | a selection keeps the query it was made under |
| the detail panel given `absolute inset-0` | the rail is still usable with a role selected |

**Task 3, done: the field is legible, navigable and sortable.**
`docs/reviews/milestone-4c-roster.png` is the screenshot. Three things arrived:

| Piece | Where |
|---|---|
| **Name plates in the scene** — one instanced quad per employer, all sampling one 2048×2048 canvas atlas | `lib/city/labelAtlas.ts`, `lib/city/labelMesh.ts` |
| **Three orderings** — employer name, most openings, newest role — reordering the instance buffer rather than the component tree | `lib/city/unresolvedField.ts` |
| **The roster rail** — every employer, its count, and a fly-to; also the field's non-3D equivalent under §5.6 | `components/CityRoster.tsx` |

`first_seen_at` was added to `CitySignalOut` because "newest" cannot be derived
from anything else the model carried. It is named for what it is — when
ingestion first saw the role, not when the employer posted it, which no ATS in
this corpus reports reliably.

**Four traps, three of which are silent.**

*One texture, not one per employer.* The obvious implementation gives each
company its own `CanvasTexture`. That is fine at three companies and roughly
160 MB of texture memory at the 2,605 boards M1 measured as discoverable — the
one-object-per-job anti-pattern of `CLAUDE.md` §8, one floor down. Everything
goes in one atlas; the per-instance UV is what makes that work, and it is why
this needs a `ShaderMaterial` rather than a `MeshBasicMaterial`.

*Nothing billboards on its own here.* `Sprite` and three's usual billboard trick
both work off `modelViewMatrix`, and ADR 0025 left no view matrix to work off —
MapLibre hands over one composed projection. The orientation is pushed in from
the map's own bearing and pitch. **The sign of the bearing was derived on paper,
through a transform that negates y, and paper was not good enough**; it was
settled by rotating a real map and looking, the same way the `mainMatrix` trap
was. A plate that is not oriented is not invisible — it lies flat over the city
like a sticker and reads as a broken texture.

*The plates write depth and the beacons do not.* The usual rule for a
transparent material is not to write depth, but this shader `discard`s its empty
fragments so only the glyphs ever reach the buffer. Without it the plates paint
in instance order and an employer at the **back** of the field draws its name
over one at the front. Seen at bearing 90°, where the columns line up.

*`-0` reached a public interface.* `-row * COMPANY_SPACING` is negative zero for
the first row. It renders identically, compares equal under `===`, and fails an
`Object.is` deep-equal in a caller's test with a diff reading `0` versus `-0`.

**Two defects found by looking rather than by a test.** The plates were sized
55 m, which was legible in a screenshot and small on a screen — they are read
from kilometres away at 76° of pitch, and 72 m is as large as they can be before
a name reaches into the neighbouring employer's airspace (`labelMesh.test.ts`
asserts that relationship, not the number). And `focusOn`'s default 18% margin
is narrower than this rail, which is ~26% of a laptop window: a column drawn
**behind the roster** counted as "already visible", so the camera declined to
move and clicking a row appeared to do nothing.

**One test of mine was wrong and failed correctly.** The first fly-to assertion
clicked a row from the opening pose and expected the camera to move. §5.6 says
selection "moves the camera only if needed" and the column was already on
screen, so `focusOn` correctly returned false. The test now drives the camera
away first, and a second test covers the other half — the `aria-current` mark,
which is what makes a no-op click legible instead of looking broken.

**The worst defect of this task, and a green suite sat on top of it.** The new
rail was put at `top-24 right-4`. `CameraControls` had been placing *itself*
there since M4b, so the rail covered it completely — every button, at full
size, with its label, unreachable by any pointer.

**Nothing went red.** Playwright's `toBeVisible` means a non-empty bounding box,
not a reachable element, and `openCity` asserts exactly that on "Reset view" as
its readiness check — so 68 seeded browser tests passed *through* the broken
control while using it as the signal that the page was ready. It surfaced only
when a test in the **offline** suite tried to `click` one, which is the suite
with no API behind it and the one easiest to assume covers less.

Two panels that each position themselves absolutely cannot know about each
other, and a third would have repeated it. `CityRail` now owns placement for
that whole side of the screen and the panels are flex children with no opinion
about where they sit. A new test clicks every control in the rail — Playwright
fails a click another element would intercept, so each is an occlusion
assertion — and it was shown able to fail by giving the roster `absolute
inset-0`.

**A second layout bug behind it.** With the panels competing for a fixed
height, the five camera buttons, the sort control and the counts paragraph left
about ninety pixels for the list on a 720px window: a corpus of *three*
employers scrolled and showed two. The rail is now the single scroll container
and every panel keeps its natural height.

**A jsdom limitation moved into test setup rather than product code.**
`HTMLCanvasElement.getContext` is unimplemented without the native `canvas`
package, and jsdom logs through its virtual console *and then* throws — so code
that degrades correctly still filled the output with stack traces. `getContext`
now returns null in `vitest.setup.ts`, which is what the DOM specifies for an
unsupported context type. The `canvas` package was declined: a native build on
the critical path of `make setup` to buy one assertion a browser test already
makes better.

**Evidence.** 66 unit tests in `lib/city` (up from 34) and 13 seeded browser
tests in `e2e-seeded/city.spec.ts` (up from 5). **Five of the new browser
assertions were each shown able to fail** by breaking the mechanism they name:

| Mutation | Test that went red |
|---|---|
| `map.on('move', faceCamera)` removed | the name plates keep facing the camera as it turns |
| `labels.setColumns(...)` removed | every column carries a name plate in the scene |
| `arrangeUnresolved(signals)` — sort argument dropped | reordering the field changes the order and not the roles |
| `camera?.focusOn(...)` made unreachable | the roster flies the camera to a column that is not on screen |
| roster given `absolute inset-0` | every control in the right rail can actually be clicked |

Full suite green on 2026-08-12: `make check` (1,936 Python, 454 web, format,
lint, typecheck), `make test-e2e` (24 passed), and the seeded browser suite
(69 passed, 1 skipped).

**One limit, stated.** At bearing 90° and 270° the columns line up behind one
another and the field reads as a single stack. That is inherent to a row of
columns in three dimensions rather than a defect in the layout — the grid wraps
at seven employers and this corpus has three — but it is worth knowing before
Task 5 decides how the field is arranged at scale.

**Task 2, done: New York has signals on it.**
`docs/reviews/milestone-4c-signals.png` is the screenshot — untethered cyan
columns above the skyline, one column per employer, connected to nothing.
`lib/city/signalLayer.ts` is a Three.js `CustomLayerInterface` sharing MapLibre's
canvas, context and matrix; `lib/city/unresolvedField.ts` decides where each
role goes; `lib/city/scene.ts` is the Zustand store the layer subscribes to
outside React; `lib/city/mercator.ts` is the projection, written out rather than
imported. ADR 0025 records the decision and both traps. 24 unit tests, 5 seeded
browser tests, 1 more in the offline suite.

**The trap worth knowing before Task 3.** MapLibre v5 hands the render method
two 4×4 matrices, both of which typecheck and only one of which is in the space
this scene is anchored in. Measured at the opening pose:

| Argument | Anchor projects to |
|---|---|
| `defaultProjectionData.mainMatrix` | clip x ≈ 0, y = 0.41 — **centre frame** |
| `modelViewProjectionMatrix` | clip x = **-3.02** — three screens off to the left |

`modelViewProjectionMatrix` is the better-sounding name and the wrong one, and
its failure is silent and total: every count right, the layer in the style, the
buffer full, `drawn` reporting 31, five browser assertions green — and nothing
whatsoever on the canvas. It reads as "the beacons are not drawing" and sends
you to inspect the material. What settled it was a probe printing the clip
coordinates from both matrices; two numbers ended it.

**A second trap, and it is M4b's scar one floor down.** The layer first attached
on `map.once('load')`, and `load` never fires here — it waits for every source in
the viewport, and at 76° of pitch the viewport reaches past the edge of a
city-sized archive. `CityMap` already carried that comment for its loading card;
attaching the signal layer to the same event reproduced it, producing a map with
a full instance buffer and no layer in its style. `styledata` is the event
`addLayer` actually needs.

**Task 1, done:** `services/api/nightshift/domain/placement.py` decides where a
role is drawn; `GET /city/signals` serves it; `placementSchema` in the browser
refuses to draw what it should not. 24 Python tests and 6 web ones. The
assertion that matters most is the boring one — with no confirmed office in the
database, **every role comes back unresolved**, which is the honest render of
this corpus today.

**ADR 0024 exists because Task 1 hit a real contradiction, not a design gap.**
I1 says a job whose location text is "New York, NY" does not get placed on a
building; §4.1 measured that *every* posting in this corpus says exactly that.
Read strictly, no role may ever stand on a building and the skyline stays dark
permanently. The resolution: a role is drawn at its employer's **confirmed**
office — traceable to a street address a human signed for, enforced below the
code by `ck_company_locations_verified_requires_a_street_address` — and
`inherited`, `office_label` and `stated` travel with the coordinate so that
"this posting named no address; its employer's office is here" can never be
flattened into "this role's location is verified". One rule in it is a product
judgement rather than I1: a fully-remote role is not placed at its employer's
office, because the coordinate would be true and the sentence on screen would
not be.

**One defect found on the way, and it had been latent for a milestone.**
`ResolutionMethod` gained `company_office` in M4a; the browser's copy in
`schemas.ts` did not. Nothing failed because nothing had ever sent the value —
`/city/signals` is the first endpoint that emits it, and it would have met a Zod
refusal to parse, i.e. a blank city page. `test_enum_parity.py` exists to catch
exactly this and did not, because that enum was not in its list. Nor were the
four other oldest enums in the product. All six are now.

### M4b is walked and reviewed.

**M4b's three criteria are met, with two limits stated rather than papered
over.** The evidence is in "M4b acceptance" below, and it comes from Chromium
driving the real map rather than from jsdom driving a fake one: 19 tests in
`apps/web/e2e/city.spec.ts`, run by `make test-e2e` and by `make acceptance`,
each shown able to fail by breaking the thing it names.

**The review is written: `docs/reviews/milestone-4b-review.md`.** It found two
defects that this walk's first draft had passed over — a test that stayed green
with the mechanism it names deleted, and a map whose accessible name was the
word "Map" — and both are fixed. §2 of that file has them in full.

**The acceptance chain has now been run, and every step of it that does not need
`docker compose` is green.** Docker's daemon is still wedged — `docker ps` hangs
— but the containers it started never stopped serving, so the chain was run
step by step against them:

| Step | Result |
|---|---|
| `make up` | **green, 2026-08-12** — see below. Was "not run" while the daemon was wedged |
| `make migrate` | green |
| `make drift` | green — no model/migration drift |
| `make seed` | green — 62 job locations over 31 jobs, 44 `city_only`, 18 `remote`, 0 mappable |
| `make test-e2e` | green — 24 passed, 3.5 min |
| `make verify` | green |
| `make test-e2e-seeded` | green — 56 passed, 1 skipped, 3.0 min |

What remained unproven was **container startup**, not the stack, and not
anything in this repository. **It is now proven.** On 2026-08-12 Docker Desktop
was force-quit and relaunched; `docker compose down` removed both containers
outright; `make up` then created them from scratch, waited for both
healthchecks, and exited 0. The database volume survived and the corpus still
matches the row above.

The wedge had also left five processes hanging — two `docker ps` calls and
their shells, still running two hours later, because a wedged daemon does not
time out. Any `docker` command inherits that: it hangs rather than failing.
**The tell that it had cleared** was `docker ps` answering "Cannot connect to
the Docker daemon" *quickly* — an error, not a hang, is the daemon coming back.

One correction to what this file said on 2026-08-12: **"62 jobs" was wrong.**
The seed reports 31 canonical jobs and 62 `job_locations`, and 44 + 18 = 62 is
the location count, not the job count. The row above now says which.

**Two tests failed on the way and neither was a regression — the instrument was
wrong, and it is fixed.** `make acceptance` went red on the wheel zoom and the
trackpad pinch, with `zoom` at exactly its opening value, and both passed on
their own seconds later. MapLibre's scroll zoom is animated and driven by
`requestAnimationFrame`, headless Chromium has no GPU, and two workers
rasterising a million footprints between them can starve rAF for longer than the
800 ms the assertion allowed. The event had arrived; the frame that would have
acted on it had not.

Seven gesture assertions now **poll for the pose they are waiting for** rather
than sleeping and looking once. Verified they can still fail: with
`scrollZoom.disable()` both zoom tests go red, they just spend twenty seconds
finding out. Separately, both Playwright configs get a fifteen-second assertion
budget, after a *navigation* test failed waiting five seconds for a heading
while the other worker drew New York — `next dev` compiles a route on first
request, and that compile is not five seconds on a busy machine. **Capping
workers at two was not enough on its own**, and one worker is not the same thing
as an idle machine.

**One finding from the walk changes how M4c should be written**, and it is worth
reading before that task starts rather than after: MapLibre's whole-viewport
`queryRenderedFeatures` returns **zero** at the pitch this city opens at, while
thirty thousand building features are loaded and visibly drawn. Measured:

| Pose | Viewport query | Box below the horizon | Features in the source |
|---|---|---|---|
| z13.6, pitch 76 (the opening view) | **0** | 1,599 | 30,573 |
| z15, pitch 76 | **0** | 351 | 18,533 |
| z13.6, pitch 0 | 9,225 | — | 38,408 |

The viewport rect at 76° is mostly sky, and the corners above the horizon have
no ground to unproject onto. M4c needs picking and list↔map sync, and the
obvious implementation of *"which roles are on screen"* is a viewport query —
which will answer nothing, silently, in the view the product opens in.

**The release is published and the pin resolves.** `buildings-20260812`, 104 MB,
109,555,308 bytes. Checked the way that actually proves something rather than
the way that looks like it does: the local copy was deleted and re-fetched from
the public URL, which is the clean-clone path, and it cleared its digest before
being installed.

**Committing that manifest before creating the release broke `make setup` on
every machine but this one, and the fix stands on its own merits rather than
being overtaken by the upload.** A 404 on the pinned URL made `make tiles` exit
non-zero, which took `make setup` down with it — and `CLAUDE.md` §4 calls a
broken `make demo` from a clean clone the highest-priority task in the repo. The
two archives are no longer equally load-bearing: **the basemap is required and
the buildings archive is not**, because the product already degrades from a
missing skyline honestly. Verified in both directions against the real 404 while
it was still a real 404. That window will open again on every future re-bake.

**CI runs `make tiles-strict`**, which refuses an unpublished pin — leniency is
for a developer's clone, not for the check that exists to notice a dangling
reference.

**Also open, unchanged:** whether the basemap is too dark to read on a real
display. Measured again with buildings on it — ground L\* 8.3, low-rise L\* 26.1,
tower faces L\* 37.4, sky L\* 34.1 — so the skyline now carries the read that the
roads were carrying alone, and this may have answered itself. Still wants a look
on a real display.

Four things carry in from M4a and Tasks 1-2:

- **MapLibre is pinned to v5 and it is load-bearing.** v6.3.0 builds the map,
  resolves the pmtiles TileJSON, fires `sourcedataloading`, and then hangs
  forever with no tile request, no `load` and no `error`. Tile fetches go
  through a worker and v6's worker-side custom-protocol bridge does not reach
  `pmtiles@4.5.0`. Upgrading needs a pmtiles release that names v6.

- **The BIN join is a key, not a computation.** `company_locations.building_id`
  holds NYC's Building Identification Number, returned free by GeoSearch. The
  extrusion layer joins on it; point-in-polygon is the fallback, not the path.
- **The basemap's own `buildings` layer must not be extruded.** The Protomaps
  archive carries one, and it is OSM's height guesses. §5.3 uses NYC Open Data's
  `heightroof` precisely so the skyline is measured rather than estimated, and a
  wrong building height is a small lie this project does not keep a category of.
  Both archives call their layer `buildings`, so the test that guards this names
  the **source** — the version that matched on `source-layer` alone started
  failing the moment the real skyline arrived, and the tempting fix is to delete
  it.
- **Nominatim is still unbuilt** and stays deferred. Rung 1 is the only rung
  that can produce a building, and rungs 2–3 produce `approximate` points the
  office loader refuses by design.

**`data/company-locations.yaml` is with the human and blocks nothing.** All 23
registry boards as of M4e Task 1, `street_address` blank, and blank is a correct
answer. Until a row is filled the honest render is every job in the unresolved
layer, which §4.8 designs as the default view rather than the sad one. **It now
leads somewhere**: `make offices` reads it, geocodes it and writes
`company_locations` — which was true of nothing before 2026-08-16.

**Q2 (deployment target) is the only open question that blocks anything**, and
only M4d.

---

## M4e Tasks 2, 4, 5 — the city is neon, and three wrong diagnoses on the way

**Done 2026-08-16.** ADR 0029. Screenshots: `docs/reviews/milestone-4e-ground.png`
(the ground), `milestone-4e-buildings.png` (the whole thing).

**What was wrong, and it was not an oversight.** Three documents I wrote forbade
the look the reference images set, and two assertions in `darkStyle.test.ts`
turned that into a build failure. The proxy those assertions used — "stay below
`ink-400`" — became the design, and `ink-450`, a desaturated blue-grey, ended up
the brightest pixel on the map. On 2026-08-13 the human handed back
`04-edge-outlined-towers-starfield.jpg`, **byte-for-byte the same file this
repository filed on 2026-08-11**, saying the vision had not been met. The target
was recorded correctly and the implementation did not reach it.

**What shipped:**

| Piece | Where |
|---|---|
| A `neon-*` family — electric indigo, hue ~252, carrying **no meaning** | `globals.css`, `lib/map/palette.ts` |
| The road ramp and the shoreline lit; the water fill still `ink-950` | `lib/map/darkStyle.ts` |
| The building mass dropped `ink-800`→`ink-450` to `ink-950`→`ink-600` | `HEIGHT_STOPS` |
| `buildings-crown` — a second extrusion lighting the top 7 m of anything over 400 ft | `crownLayer()` |
| A declared `light`, at `intensity: 0.18` | the style's `light` block |
| The two grey-enforcing assertions replaced, **and a floor added** | `darkStyle.test.ts`, `palette.test.ts`, `colour-contrast.test.ts` |

**The brightness stack, asserted at both ends**: city (≤55.2 L\*) < hiring
building (`alert-400`, 63.6) < open role (`signal-400`, 85.6). The margin is 20
L\* because `alert-400` sits 22.0 below `signal-400` — 20 admits it and admits
nothing above it.

**The floor is the half that never existed, and it is the finding worth keeping
from this slice.** Every brightness assertion this suite has ever held is
satisfied perfectly by a map drawn entirely in `ink-950` — and for four
milestones a suite of exactly those assertions was green over exactly that city.
A one-sided bound cannot fail in the direction the product actually went wrong.
The floor now requires something in the style to exceed 50 L\*. **The first draft
said 40 and passed on `ink-400` at 40.2** — the exact grey being replaced. It
would have gone green over the city it was written to catch.

**Three wrong diagnoses, each of which cost a round.**

*A style that omits `light` does not get no light — it gets MapLibre's.* White,
`intensity: 0.5`, viewport-anchored, added to every extrusion face, setting a
floor no paint can go below. The ramp was dropped four full shades and the
towers came back the same pale grey, because what was on screen was mostly the
light and not the colour. Found by hiding the crown layer and looking at what was
left. One attempt to tint the light `neon-700` turned the whole city olive —
roughly the complement of the light colour — so it ships white until that is
understood rather than worked around.

*A `let`/`var` expression is fine in `paint` and matches everything in a
`filter`.* The crown filtered on `HEIGHT_FEET`, which wraps the lookup in a
`let`, and every structure in New York got a neon roof: a sub-threshold building
still draws its top cap, and with base equal to height that is invisible from the
side and a solid lit polygon from above. **Nothing errored. It looked
deliberate.**

*The crown threshold came from a count, after being picked by eye twice and being
wrong twice.* Of 25,176 footprints at the opening pose: 3,181 over 150 ft, 1,107
over 250, 408 over 400, 103 over 600; tallest 1,550. At 150 the frame is a carpet
of lit roofs; at 400 it is Midtown and the Financial District glowing over a dark
city.

**Not measured yet: what this costs a frame.** The crown is a second full
extrusion pass, and M4d Task 1's tables were taken against the grey renderer. The
headed Playwright readout during these screenshots showed 26–30 ms typical at
1600×1000, but that is a screenshot harness competing with a dev server and is
**not** the measurement config. Re-running `e2e/city-metrics.spec.ts --headed` at
200 and 5,000 roles is the next number this milestone owes, and it is the reason
M4d Tasks 2–7 were paused rather than done first.

---

## M4e Task 1 — the worksheet, and the loader that was never wired up

**Done 2026-08-16.** The promotion path in `city.md` §4.4 has four steps between
a human typing an address and a beacon standing on a roof. Steps 1 and 3 shipped
in M4a, `read_worksheet` and `load_offices` shipped tested in M4b — and
**nothing outside the test suite called either of them.** The worksheet was a
file you could fill in that led nowhere.

That is the finding worth keeping, because it is I7's shape without a mock in
sight: two complete modules, two green test files, a documented design, and a
subsystem that could not run. From the outside it read exactly like a working
feature. `docs/QUESTIONS.md` Q7 asked the human how many addresses to curate,
and the honest answer at the time was that **no number would have changed a
single pixel.**

**What landed:**

| Piece | Where |
|---|---|
| The worksheet, widened from 9 entries to all **23** registry boards | `data/company-locations.yaml` |
| `nightshift offices` — read, refuse, geocode, write, report per row | `services/api/nightshift/cli.py` |
| `make offices` | `Makefile` |
| The two files held equal in both directions | `tests/test_company_locations_worksheet.py` |
| The command's own tests — five, offline, no database | `tests/test_offices_command.py` |

`read_worksheet` and `load_offices` were **not** rewritten. They were correct;
the wiring around them was what was missing.

**The 23 are two groups, and the second is the change of mind.** The file held
only the nine boards whose *posting text* parses to NYC. `nyc_presence` is
derived from posting text, and posting text is not a company directory — a board
whose postings all say "Remote" can still be run out of an office on Lafayette
Street. The other fourteen are listed with `city` and `state` left **blank**
rather than pre-filled with "New York", because a prefilled locality on a
company headquartered in Oslo is a small lie that would send the geocoder
looking in the wrong place.

**Three properties, each one a decision:**

- **A human runs it; it is never scheduled, and it is in neither `make demo` nor
  `make acceptance`.** Geocoding is a live request to
  `geosearch.planninglabs.nyc`, gated on `OUTBOUND_HTTP_ENABLED` exactly as
  `ingest` and `poll` are. `CachingGeocoder` writes every answer to
  `geocode_cache`, so an address is requested once ever and the buildings it
  placed survive into an offline `make demo` — ADR 0022's guarantee for tiles,
  applied to addresses.
- **The network gate is checked lazily**, only when an entry actually names an
  address. The committed file is all-blank today, so `make offices` on a clean
  clone reports what it is asking for and exits 0 with no database and no
  network. A command that demanded both before it could tell you the file is
  empty would be unusable for the first thing anybody uses it for.
- **A refusal exits 1; an unresolved address exits 0.** A refused entry is a
  defect in a file a person wrote — an address with no date, a "New York, NY"
  that names no street — and the exit code is what makes it as loud as a failing
  test. An unresolved one is the world answering. Most of the registry has no NYC
  office; conflating the two would make the command red by default and therefore
  ignored.

**Verified end to end against the live geocoder**, on a scratch worksheet, one
run:

```
  placed on a building
    Datadog                  620 8th Ave  ->  verified, BIN 1087186
  address recorded but the company has no jobs yet (board not polled)
    1Password, 1X
  refused — fix these in the worksheet
    Stripe    'New York, NY' names no street, so it cannot reach `verified`…
    Ramp      an address with no `confirmed_on` date is a claim with no age…
  blank (1) — a correct answer; these jobs stay unplaced
    Abound
```

One HTTP request was made, for Datadog. `load_offices` looks the company up
*before* it geocodes, so the two not-yet-ingested rows cost nothing. **The
scratch row was deleted afterwards** — the address is the human's to confirm,
and a verification run must not leave a `confirmed_by` behind naming nobody
real.

**The BIN question is settled, and Task 6 depends on it.** A probe against the
live buildings archive at the opening pose returned **3,110 of 3,110 rendered
features carrying a `bin`**; the property set is `feature_code`, `height_roof`,
`last_status_type`, `bin`. So the hiring-building layer can filter on the real
footprint rather than fall back to a column at a coordinate. Two details that
each cost a debugging session:

- **`bin` is a string** (`"1086193"`), as is `height_roof` (`"339.64"`). A
  MapLibre filter must compare string literals or wrap in `['to-number', …]` the
  way `HEIGHT_FEET` already does.
- The first probe returned **0 features** — at pitch 76 a whole-viewport
  `queryRenderedFeatures` returns nothing while 30,000 features are loaded and
  visibly drawn, because the corners above the horizon unproject onto no ground.
  `e2e/city.spec.ts:143-160` had already written this down and it caught me
  anyway. Query a box below the horizon.

**Not verified**: whether BIN 1087186 in particular is present in the baked
archive. GeoSearch and the NYC footprint dataset share the identifier, but
whether that specific building survived the extract is a Task 6 check, not a
Task 1 claim.

**`make check`**: lint and typecheck green; 1943 Python tests passed with one
error, `test_closure_pipeline.py::test_three_misses_makes_a_job_stale_not_closed`
— a `TRUNCATE` deadlock against the live dev stack sharing the same Postgres,
which is the trap this file already records. Re-run alone: **11 passed.** Web
unit tests green.

---

## M4d Task 1 — the frame timer, and the first number it caught being wrong

**M4's desktop criterion is met, with numbers rather than an impression.**
Measured on 2026-08-12 on this machine, headed, on a real GPU:

**ANGLE (Intel, ANGLE Metal Renderer: Intel(R) Iris(TM) Plus Graphics 645)** —
an integrated GPU from 2018, which makes the result stronger rather than weaker.

### 200 roles

| Scenario | Frames | p50 ms | p95 ms | Worst ms | Missed |
|---|---|---|---|---|---|
| Idle, pulses only | 120 | 16.7 | 17.6 | 18.5 | 0% |
| Pan | 120 | 16.6 | 21.9 | 79.3 | 3% |
| Orbit (right-drag) | 120 | 16.6 | 19.0 | 64.7 | 1% |
| Zoom | 120 | 16.7 | 17.8 | 18.9 | 0% |
| Re-sort the whole field | 120 | 16.6 | 18.0 | 27.6 | 1% |

### 5,000 roles — the ceiling, `MAX_BEACONS`

| Scenario | Frames | p50 ms | p95 ms | Worst ms | Missed |
|---|---|---|---|---|---|
| Idle, pulses only | 120 | 16.7 | 18.1 | 18.5 | 0% |
| Pan | 120 | 16.7 | 19.3 | 33.1 | 3% |
| Orbit (right-drag) | 120 | 16.7 | 17.7 | 27.0 | 1% |
| Zoom | 120 | 16.6 | 17.7 | 18.1 | 0% |
| Re-sort the whole field | 120 | 16.6 | 17.9 | **191.7** | 2% |

**p50 is 16.6–16.7 ms in every scenario at both sizes** — pinned to the 60 Hz
refresh — and **the 5,000-role city is not measurably slower than the 200-role
one**, which is what one geometry and N transforms was for (§5.5). Reproduce
with:

```
cd apps/web && NIGHTSHIFT_METRICS=1 npx playwright test e2e/city-metrics.spec.ts --headed
```

**`--headed` is the measurement, not a convenience.** Headless Chromium has no
GPU and rasterises through SwiftShader on the CPU. The run prints its renderer
with every table, the page prints it beside every number, and
`city-acceptance.spec.ts` asserts that a software rasteriser is *named as one*
on screen — so the caveat cannot be lost between the machine and the document.

**One hitch the numbers found, and it is real:** re-sorting 5,000 roles costs a
single **191.7 ms** frame. Every beacon, mark, plate and the label atlas are
rewritten in one synchronous pass. It is one frame per deliberate action rather
than a sustained cost, which is why it does not move p95 — and it is exactly the
kind of thing task 2's quality tiers and task 3's field work should be judged
against.

**And one defect in the instrument, caught by the first real run.** The first
table reported *"53% over budget"* beside a p50 of 16.7 ms — a city pinned at
exactly 60fps, reported as missing half its frames. Both numbers were computed
correctly and one was nonsense: a 60 Hz display presents frames 16.67 ms apart
and the intervals jitter either side, so counting everything strictly greater
than the budget counts vsync noise as failure. A missed frame is the renderer
failing to present in time for the *next refresh* — `MISS_FACTOR = 1.5` — and
the corrected column reads 0–3%. **The instrument was wrong before the product
was, for the second milestone running.**

Also in this task: the timer refuses to report from fewer than twelve frames,
discards gaps over a second as pauses rather than counting a backgrounded tab as
the worst frame of the window, reports percentiles instead of a mean, and lives
outside React — the panel polls it twice a second, because a frame time written
into the store would re-render every subscriber sixty times a second and the
instrument would become the largest thing it measures.

---

## M4c acceptance — the three claims, walked

`city.md` §7: *"Done when: no placement is fabricated at any confidence,
thousands of markers are not thousands of components, and the list and the map
cannot disagree."*

Walked on 2026-08-12 at the tip of `m4b-dark-city`. **All three pass.** The
review is `docs/reviews/milestone-4c-review.md`.

**The instrument is new, and the reason is the whole of this milestone's
lesson.** The seeded corpus is 31 roles, every one of them `unresolved`, none
carrying a coordinate, none at a confirmed office. Against that corpus the first
claim tests what happens when nothing lies rather than what happens when
something does; the second would pass against an implementation that renders one
`<div>` per marker; and the branch that handles a role the renderer cannot place
has never executed. So Task 6 added a second corpus, **chosen rather than
found** — `apps/web/e2e/city-acceptance.spec.ts` stubs `/city/signals` and runs
in the *offline* config, because everything except the corpus is real: the
archives, MapLibre, Three.js, the instance buffers.

### 1. No placement is fabricated at any confidence — PASS

| Claim | Evidence |
|---|---|
| Nothing in the real corpus claims a position | Every signal is one of the three kinds and the three counts sum to the total — `e2e-seeded/city.spec.ts`, "nothing on the city claims a precision the corpus does not have (I1)" |
| A payload that *does* lie is refused **whole**, in three shapes | An unresolved role carrying coordinates, a building placement below `verified`, an area placement naming a BIN. Each takes the entire corpus off the city and the page says the roles could not be loaded — not an empty sky |
| The refusal is about the lie, not about the stub | The same twelve roles with nothing fabricated draw twelve beacons, in the same test, before the fabrications |
| A person reading about a role is told what its position means | The panel: its position means its employer and *"nothing whatsoever about where in New York"* |
| A role the renderer cannot place is counted **and named** | Fixed this session — see below. Zero today; non-zero the first time an address is confirmed |

Refusing the whole payload rather than the offending row is deliberate: a corpus
shown to produce fabricated positions is a corpus whose *other* placements have
not been shown to be sound.

### 2. Thousands of markers are not thousands of components — PASS

Employer count held fixed at 20, role count moved 100 → 5,000 — fifty times the
markers. The DOM under `#main` had to be **identical**, not merely small.

| Claim | Evidence |
|---|---|
| The DOM does not move | **364 elements at 100 roles, 364 at 5,000** |
| Every marker reaches the GPU | 5,000 of 5,000 in the instance buffer — `MAX_BEACONS`, which is also the API's `MAX_SIGNALS`, so this is the largest city this product can be asked to draw |
| They are one object | One `canvas`, one `custom` layer, no per-marker node anywhere |
| The test can fail | One `<span hidden />` per visible role in `CityRoster`: 364 → 5,264, red, naming the cause |

`docs/reviews/milestone-4c-scale.png` is that city, drawn at 200 employers.

### 3. The list and the map cannot disagree — PASS

Eight assertions existed before this session — selection by click, by roster and
by deep link; escape; empty sky; the reticle following a re-sort; the query
surviving a selection; the archive toggle moving the *buffer* rather than a
list. The edge Task 5 created was the one left: **a role that is selected and
not drawn**, reachable by a link to a role you have since been rejected from.

Three things could disagree about it and all three are one assertion, because
they are one piece of state: the panel says the role is hidden rather than
describing it as on-screen, the reticle is on nobody (`selectionAt` is null
rather than parked on whichever beacon now stands there), and checking the
toggle brings the beacon *and* the reticle back together. Mutation: parking the
reticle on `placements[0]` turns null into `[-620, 0, 700]` and the test red.

### Task 6, and the three defects the new instrument found

**The page counted roles it does not draw — FIXED.** `CitySignals` printed "On a
building: *n*" from the endpoint's counts while `arrangeUnresolved` draws the
unresolved field and nothing else. It is 0 today because
`data/company-locations.yaml` is empty; it stops being 0 the first time a human
confirms one address, and the failure would have been a quiet, permanent,
plausible undercount rather than a crash. **I7 in the form it actually arrives
in: not a mock presented as working, but a renderer presented as complete.** The
fix is a sentence.

**Two ceilings coupled by a comment — FIXED.** `MAX_BEACONS` (5,000, web) and
`MAX_SIGNALS` (5,000, API), with a `Math.min` between them and nothing checking.
Raising the API's is a one-line change with every test in both suites still
green, and the surplus roles are dropped on the floor: nothing throws, no count
disagrees with itself, and the `truncated` banner stays off because the *API*
did not truncate. The assertion went into `test_enum_parity.py`, which exists
for exactly this class of cross-language drift.

**A `WebGLRenderer`'s programs outliving the layer — FIXED.** `onRemove` disposed
every geometry, material and texture and then nulled the renderer. Bounded today
(nothing removes the layer without destroying the map) but undocumented, in the
one place §5.1 gave a second library a share of somebody else's context.
`renderer?.dispose()` — not `forceContextLoss()`, since the context is
MapLibre's and MapLibre is still drawing New York with it.

**And one fault in the instrument, before the product.** The DOM count first
read `document.querySelectorAll('*')` and flaked by a handful of elements
between two loads of the *same* corpus: `<head>` gains a `<style>` and a
`<script>` per route `next dev` has compiled, and the header's health indicators
move through loading → unreachable on their own schedule. Scoped to `#main`.

### Evidence, at Task 6

- **624 web unit tests green** (43 files), **187 of them in `lib/city`**.
- **27 offline browser tests green** (2.3 min) — 24 from M4b plus this session's
  three, in `e2e/city-acceptance.spec.ts`.
- **84 seeded browser tests green, 1 skipped** (5.6 min), 28 of them the city's.
- **1,940 Python tests green**, run alone, plus the new ceiling-parity assertion.
- `make lint` and `make typecheck` clean across both languages.
- **Six mutations, each shown to turn a named test red** — the table is in
  `docs/reviews/milestone-4c-review.md` §5.

**One limit recorded rather than fixed: the field is legible at 31 roles and not
at 5,000.** The layout wraps at six employers per row, so 200 employers recede
34 rows deep, the name plates at the back overlap into an unreadable strip, and
a column of 25 roles is ~1,125 m tall. The acceptance claim is unaffected — the
buffer takes all 5,000 and the DOM does not move — but §4.8's "legible" was
designed and measured at the size of the corpus that exists. The roster stays
usable at either size, so the information is never lost, only the view.
Deferred to M4d, beside the adaptive quality tiers it belongs with.

---

## M4b acceptance — the three criteria, walked

`city.md` §7: *"NYC renders dark, extruded and offline in `make demo`; every
gesture in §9.3 works on trackpad and touch; every animation is interruptible;
no job data is on screen yet."*

Walked on 2026-08-12 at the tip of `m4b-dark-city`. **All three pass. Two carry
a limit that is stated below rather than buried**, and both are the same limit
wearing different clothes: this walk had one machine, and that machine has no
touchscreen and no Safari.

**The instrument is new, and it had to be.** Every criterion here is a claim
about a renderer and a pointing device. `camera.test.ts` has 37 tests and
`CameraControls.test.tsx` 7, and all 44 drive a *fake* map in jsdom with no GPU:
they prove the controller calls `panBy` when an arrow key arrives. They cannot
prove that pressing an arrow key moves New York. So M4b's evidence is
`apps/web/e2e/city.spec.ts` — 19 tests, real Chromium, the real archives, no API
and no network — reading the camera through a debug handle that exists outside
production builds only (`apps/web/src/lib/map/debug.ts`, and the guard is the
whole design of that file).

**Every test in it was shown able to fail.** A gesture test that passes without
the gesture is not evidence, and one of them was not evidence until it was
fixed — see criterion 3.

### 1. NYC renders dark, extruded and offline — PASS

| Claim | Evidence |
|---|---|
| Offline | Every request the page makes is recorded and matched by scheme and host. **Zero off-machine requests**, and `blob:` is excluded by scheme rather than by pattern so a real host cannot hide behind one. Both archives were fetched from `/api/tiles/*` — a Next route reading a file from `~/.cache` |
| No API | The suite runs in `playwright.config.ts`, which starts the web server and nothing else. The city page draws while the same run's shell tests assert "api unreachable" is on screen |
| Extruded | The `buildings` layer is a `fill-extrusion` at runtime, not only in the style file, and **1,599 building features are rendered** in the frame at the opening pose |
| Dark | `docs/reviews/milestone-4b-opening-view.png`, 1600×900, captured from this suite twenty seconds after load. Read by eye. The measured tokens are unchanged: ground L\* 8.3, low-rise 26.1, tower faces 37.4, sky 34.1 |
| Drawing, not stalled | Two canvas screenshots either side of a camera move differ. A black rectangle is identical to a black rectangle; two different frames is weak evidence of beauty and strong evidence of drawing |
| In `make demo` | `make test-e2e` runs this suite and is green (23 tests, 2.3 min), and **`make acceptance` now runs it too** — before the API starts, which is not an ordering accident. `make demo` itself ends in a foreground server with no exit code, which is what `acceptance` exists to stand in for |

**The count is 1,599 rather than "all of them", and asking for the whole
viewport would have given zero.** That finding is at the top of this file,
because it is a trap set for M4c rather than a quirk of a test.

### 2. Every gesture in §9.3 works on trackpad and touch — PASS, with the hardware limit stated

Twelve tests, one per behaviour, each asserting the pose actually changed the
way the gesture means:

| §9.3 asks for | How it is driven | Shown able to fail by |
|---|---|---|
| Mouse pan | `mouse.down` → move → `up`; centre moves, bearing and zoom do not | `dragPan.disable()` → red |
| Mouse orbit | Right-drag; bearing changes | — |
| Wheel zoom | `mouse.wheel`; zoom rises | `scrollZoom.disable()` → red |
| Trackpad pinch zoom | **CDP `Input.dispatchMouseEvent` with ctrl held** — every browser reports a trackpad pinch as ctrl+wheel, and Playwright's `mouse.wheel` cannot set a modifier | `scrollZoom.disable()` → red |
| Touch pan | CDP `Input.dispatchTouchEvent`, one finger | `dragPan.disable()` → red |
| Touch pinch | Two fingers spreading | `touchZoomRotate.disable()` → red |
| Touch rotate | Two fingers swept around their midpoint at fixed separation | `touchZoomRotate.disable()` → red |
| Double-click focus | Pitch and bearing preserved to a degree, centre closer to the clicked coordinate than it started | — |
| Keyboard navigation | Arrow pans **up the screen** at bearing 202°, Shift+arrows rotate and tilt, `+`/`-` zoom, `0` returns to the opening pose | — |
| Bounds and pitch limits | A `flyTo` past both is clamped | — |
| Keyboard *reachability* | Tab from the top of the document, no click anywhere: the canvas takes focus in five stops, announces itself, shows a focus ring, and steers | Added by the review, which found the label was on a node nothing can focus |
| Reduced motion | Criterion 3 |

Touch goes through CDP rather than Playwright's `touchscreen`, which taps with
one finger and cannot express any gesture that matters here. `dispatchTouchEvent`
is the same entry point the browser uses for a real finger, so MapLibre receives
trusted events indistinguishable from hardware.

**The limit, stated: this is desktop Chromium with touch emulation, not a
phone.** What it therefore cannot catch is a mobile browser's own pan-and-zoom
handling fighting the map's, which is a named M4 risk and stays open. What it
does close is the weaker claim that stood before today — *"the touch handlers
are enabled"*, asserted by a unit test against a fake map — which is not the
same sentence as *"pinch and rotate work"*, and the distance between those two
sentences is exactly what I6 is about.

**Second limit: trackpad *rotation* is untested.** §9.3 says "where supported",
and it is supported only via `gesturestart`/`gesturechange`, which are Safari
events that do not exist in Chromium. The controller handles them and has jsdom
tests for the handlers; no browser has ever delivered one. Recorded here rather
than counted as covered.

### 3. Every animation is interruptible — PASS, and the first version of this test was not evidence

| Animation | Interrupted by | Result |
|---|---|---|
| `flyTo`, 8s | A mouse-down on the map | Stops where it is, `isMoving()` false, `camera.animating` false, position unchanged a second later, and nowhere near the target |
| `flyTo`, 8s | `Escape` | Same |
| Orbit | Any input | Bearing frozen, and the panel's button stops claiming the camera is turning |
| Everything | `prefers-reduced-motion` | No orbit button at all, and an 8-second `flyTo` lands in under 150 ms — a jump, not a journey |

**The finding that matters is what the first version of this test did not
catch.** Stubbing `#handleUserInput` to do nothing left the fly-to test *green*:
MapLibre's own drag handler stops an in-flight camera the moment you grab the
map, so the criterion was being met by the library while the test claimed to be
watching the controller. `camera.animating` is the controller's own record of a
move it started, nothing else clears it, and asserting it turns the test red
again. One line — and without it, this row of the walk would have been a
sentence about code that was not running.

**A second trap, in the tooling rather than the product.** Playwright's
documented `test.use({ reducedMotion: 'reduce' })` **does not reach the page** on
this version: `matchMedia('(prefers-reduced-motion: reduce)').matches` stays
false and the controller builds itself with the preference off.
`page.emulateMedia()` before navigation works. A reduced-motion test written the
documented way exercises the ordinary camera while claiming to exercise the
reduced one — it fails only because these assertions happen to be written the
way round that notices.

### 4. No job data is on screen yet — PASS

Asserted, not assumed: the page says *"There are no roles on it yet"* in the
browser. There is no jobs source, no beacon layer and no query for one — M4c.

### What the walk cost, and one thing it changed

`city.spec.ts` runs in 2.3 minutes with the shell suite, and **`workers` is now
capped at 2 in `playwright.config.ts`**. At Playwright's default of four, two
tests failed on this 8-core machine — a mouse-drag pan, and an unrelated
*navigation* test in `shell.spec.ts` — because four workers each rasterising a
million footprints with no GPU is four workers fighting over one CPU. Neither
failure had anything to do with the code under test. A suite that fails that way
teaches people to re-run it rather than read it, which is worse than a slow
suite.

**Capping workers was necessary and not sufficient**, which the first real
`make acceptance` run then demonstrated — see "The acceptance chain has now been
run" above. The durable fix was to stop measuring time at all: seven gesture
assertions poll for the pose they are waiting for, and both configs allow
fifteen seconds for a web assertion instead of five.

CI gets the same suite: the `e2e` job now restores the tile cache and fetches
the archives, because with the tile route answering 503 the page shows its
"cannot be drawn" card, which is correct behaviour and proves nothing about M4b.
Its budget went from 15 to 25 minutes.

### The machine ran out of disk, and Docker has not recovered

Recorded because it blocks a green `make acceptance` and because it will look
like a code failure to whoever hits it next.

Mid-session the volume reached 100% (234 MB free of 233 GB) — the tool harness
itself started failing to write. `npm cache clean --force` freed 2.3 GB and the
session continued, but **the Docker daemon was already wedged**: `docker ps`
hangs indefinitely, so `make up` never returns and `make acceptance` cannot get
past its first line. Nothing in this repo caused it and nothing in this repo can
fix it: it wants Docker Desktop restarted by a human, and probably a look at
where the other 200 GB went.

**What is wedged is the daemon's API, not the containers.** Worth knowing before
anyone reads a skipped test as a passing one: Postgres and Redis kept serving on
their published ports throughout, and the full Python suite run afterwards was
**1,906 passed, nothing skipped** — every database-backed test included. So the
loss is `docker compose`, which means `make up`, `make reset-db` and therefore
`make acceptance`; it is not the loss of a database.

Everything M4b claims was verified without any of it. The city needs no
database.

**Still true on 2026-08-12 after the disk recovered** (19 GB free): `docker ps`
still hangs. But the containers are still up, so the whole of `make acceptance`
except `make up` has now been run against them and is green — the table above
has each step. The daemon still wants restarting by a human; nothing else does.

---

### M4c Task 1 — the placement join, and the contradiction it walked into

**Built:** `services/api/nightshift/domain/placement.py`, `GET /city/signals`,
`placementSchema` and `fetchCitySignals` in the browser, ADR 0024. 24 Python
tests, 6 web tests.

`office_loading.py` deferred this join to M4c in as many words — "the
inheritance is a read-time join, and `COMPANY_OFFICE` is what that join reports
rather than something stored… **M4c builds it**, next to the renderer that needs
it." It is built the way that file promised: nothing is written back, so
`job_locations` still holds what the posting said and a corrected office strands
no stale coordinate.

**The contradiction.** I1 says a job whose location text is "New York, NY" does
not get placed on a building. §4.1 measured that every posting in this corpus
says exactly that — 0 of 247 name a street. §4.4 says jobs inherit their
employer's building. These are not two rules about different cases that happen
to overlap; they are two rules about the same case, and they disagree. Read
strictly, I1 means the skyline can never light no matter how many addresses a
human types.

ADR 0024 resolves it rather than choosing a side by feel: I1 prohibits
*fabrication*, and an inherited placement is not one — its coordinate traces to
a street address a human signed for by name, and the inference on top of it
("this role is at that office") is labelled in the data, in the payload and in
the interface at every point the coordinate appears. `location_confidence`
describes the coordinate; `inherited` describes the claim; they are two fields
because they are two sentences.

**What the code enforces beyond what the tests check.**
`Placement.__post_init__` refuses an impossible placement outright — unresolved
with coordinates, a building below `verified`, an approximate point carrying a
BIN. A test only covers the cases it thought of; this runs on every placement
the API serialises.

**Three rules worth knowing before Task 2 draws any of this:**

- **A verified office is a building; an approximate one is an area, never a
  point** (§6). A BIN on an approximate row is not a promotion and is dropped.
- **A fully-remote role is not placed at its employer's office.** This does not
  follow from I1 — the coordinate would be true. It follows from what the
  drawing *says*. Hybrid roles are placed, because hybrid means partly there.
- **What the posting said beats what its employer's office says**, even when the
  office is more precise. The other order would silently upgrade a posting's own
  approximate claim into a building by way of a different row.

**Today the endpoint returns every role unresolved**, and the test that asserts
so is the one that matters most in the file. `data/company-locations.yaml` is
still blank, which is a correct answer and not a blocker: §4.8 designs the
unresolved layer as the default view.

---

### M4b Task 5 — the camera, and the two handlers it had to switch off.

**The city can be driven.** `apps/web/src/lib/map/camera.ts` is the controller
`city.md` §5.4 asks for: no React in it, wrapping MapLibre's camera rather than
replacing it, and owning the whole of §9.3 in one place. 37 unit tests, plus 7
on the control panel, all in jsdom with no GPU.

**The split with MapLibre is the design, and two `disable()` calls are the
load-bearing lines.** MapLibre already has a good handler for every direct
manipulation gesture — drag-pan, right-drag orbit, wheel and trackpad-pinch
zoom, two-finger pinch, rotate and pitch — and rewriting those would be a worse
version of code that exists. So the controller enables all of those explicitly
(a default is a thing that changes in a minor release; this list is an
acceptance criterion) and takes over exactly two:

- **`keyboard`**, because the steps have to be ours. Arrows pan in _screen_
  space through `panBy`, so "up" is up the screen whatever the bearing is — the
  city opens at bearing 202°, and a keyboard that panned north would send the
  camera down and to the right when you press up. Shift+arrows rotate and tilt,
  `+`/`-` zoom, `0` goes home, `Esc` stops.
- **`doubleClickZoom`**, because a double-click here focuses: it flies to the
  point under the pointer and _keeps the pitch and bearing_, which is §9.3's
  "preserve spatial orientation". Zoom-around-centre throws the frame's subject
  off the edge.

Leaving either one enabled is a double-handling bug with no error attached: the
map pans twice per arrow key, or both zooms and flies on a double-click. A test
asserts the exact division rather than "the handlers are on".

**Reduced motion is one `if`, and every programmatic move is behind it.**
`flyTo` becomes `jumpTo`, keyboard steps get a duration of 0, and the orbit
simply does not run — there is no reduced version of "turn in a circle forever",
and slowing it down is still the motion the preference is about. The preference
is also watched: turning it on mid-orbit stops the orbit rather than waiting for
the next call. MapLibre's own camera happens to check the same media query, and
that is not a reason to skip this — nothing should depend on a library's private
courtesy for a guarantee we have written down as acceptance.

**Interruption is deliberately indiscriminate.** Any `pointerdown`, `wheel`,
`touchstart` or `keydown` on the container, in the capture phase, stops the
camera where it has reached. The alternative — cancelling only for inputs
MapLibre recognises as camera gestures — leaves the user watching a fly-to
finish a journey they already tried to stop, and "which inputs count" is a
question with no good answer at the moment it is being asked. The capture phase
matters: a keypress during a fly-to cancels the fly _before_ issuing its own
pan, and a test pins that call order.

**The orbit is a chain of 90° legs, not one 360° animation.** A single long
animation cannot be stopped and left where it got to without a snap, and cannot
change speed. A chain just stops scheduling. Each leg pivots `around` the point,
so the thing being orbited stays put on screen instead of swinging across it.

**`focusOn` returns whether it moved, and usually it should not.** §5.6 says
selection "moves the camera only if needed"; a camera that flies on every
selection makes a result list unusable, because reading the second result means
waiting out a journey from the first. On screen — with a margin, since a point
three pixels from the window edge behind a panel is not on screen in any sense a
user recognises — and close enough, and it does nothing. This is M4c's entry
point and it is built and tested now, before there is a selection to hand it.

**Trackpad rotation exists on exactly one engine.** Safari on macOS emits
`gesturestart`/`gesturechange` with a `rotation`; nothing else reports a
trackpad rotate at all, which is what §9.3's "where supported" is about. It
reads `rotation` and pointedly ignores `scale`, because Safari also emits a
ctrl+wheel for the same pinch and MapLibre's `scrollZoom` already answers that
one — applying both would zoom twice per pinch.

**The controller has one set of limits and the map constructor now reads them.**
`CAMERA_LIMITS` and `INITIAL_POSE` moved into `camera.ts` and `CityMap` imports
them, adding `minZoom: 9.5` (below it the NYC extract is a lit island in a void)
and `maxZoom: 18`. A camera with one set of limits in the constructor and
another in the controller is a camera with none, and the keyboard's reset key
needs a home position that cannot drift from the one the map opened at.

**The fake map is the reason any of this is tested.** `camera.ts` takes a
`CameraMap` — the exact subset of MapLibre it touches — so `camera.fixture.ts`
can supply a fake with no WebGL context, no tile archive and no frame budget. A
controller whose tests need a real map is a controller with no tests. jsdom also
implements no `matchMedia` at all, so the motion preference is faked in the same
file.

**`CameraControls` is not decoration.** Orbiting the city otherwise means
holding the right mouse button and dragging, and there are people for whom that
is not available; every button there is somebody's only route to the behaviour.
It also has no local copy of "orbiting" — it reads the controller through a
subscription, because the failure it exists to avoid is a button that still says
"Stop orbit" after a gesture ended the orbit, and then starts one while claiming
to stop it.

**Checked in a real browser, not only in jsdom:** the panel appears over the
city, the keyboard legend matches the keys the controller implements (it is
generated from the same table), Shift+→ rotates, double-click flies to street
level keeping the tilt, `0` returns exactly to the opening view, and a drag
during an orbit both stops the camera and flips the button back to "Orbit". No
console errors on load.

**Not verified: touch.** The touch handlers are enabled and the unit tests
assert they are enabled. Nobody has pinched this map on a phone. That is Task
6's problem and it should not be written up as a pass before then.

---

### M4b Task 4 — the skyline, and three silent failures on the way to it.

**New York has its own skyline.** 1,083,024 structures from NYC Open Data
`5zhs-2jue`, cut to `z13-z16` by `scripts/bake_buildings.py`, 104 MB, pinned by
digest exactly like the basemap — ADR 0022's shape, second artifact. `make
basemap` is now **`make tiles`** and fetches both; `/api/basemap` is now
`/api/tiles/[artifact]` and serves both from the one handler.

**Heights stay in feet all the way to the style.** The tiles carry the source's
own numbers and the conversion to metres happens once, in the paint expression.
A factor applied twice renders a city 3.3 times too tall and looks perfectly
fine doing it, so there is a test that counts the number of `0.3048`s in the
layer and requires exactly one.

**732 of 1,083,024 structures have no measured height** — 0.068%. They are drawn
at a stated 25 ft, and the count is in the manifest, in a Python test that fails
if the fraction passes 1%, in a TypeScript test, and on the page itself. §5.3
asks for a default that is *recorded as having been taken*; four places record
it.

**Colour carries height, because height is the one thing this layer knows.**
`ink-800` at ground level up to a new `ink-450` for the towers over 900 ft. That
token is above the old `ink-400` ceiling deliberately: ADR 0023 replaced the cap
with a headroom rule, and `ink-450` sits 41.3 L\* below `signal-400` against a
bound of 40. The ground still stops at `ink-400`, and a test now runs that rule
in **both** directions — the ground may not brighten, and the skyline may not
flatten back down, because a ramp quietly reduced to one shade would reverse
ADR 0023 by accident rather than by decision.

Measured on screen rather than asserted from the tokens: ground L\* 8.3,
low-rise L\* 26.1, tower faces L\* 37.4, sky L\* 34.1. Against `signal-400` at
L\* 85.6 the beacon headroom is real and not just declared. Worth recording that
a first look at the screenshot read the buildings as near-white and wrong; the
zoom tool auto-exposes, and the eye reads a dark surround as brightness. The
numbers came from sampling the actual frame.

**Three failures, all silent, all worth the record.**

**The bake had been hung for seventy minutes doing nothing.** `bake()` accepted a
`source` path and never put it in the command, so tippecanoe fell back to reading
GeoJSON from standard input — which was a socket nothing would ever write to. No
error, no output, 0.09 seconds of CPU across seventy minutes of wall clock, and
scratch files at zero bytes. It would have waited forever. The fix passes the
path *and* passes `stdin=DEVNULL`, so the same mistake becomes an immediate
error rather than a hang.

**The demolition filter was filtering nothing.** `--feature-filter` runs *after*
`--include` prunes attributes, so a filter naming `last_status_type` — which
`--include` had already deleted — matched nothing and kept every demolished
structure. It announced itself only as `Warning: attribute not found for
comparison`, printed into the middle of a progress bar. Proved both directions
on a three-feature fixture before re-baking: with the attribute included, a
`Demolition` feature drops and a feature genuinely *missing* the field is still
kept. That second half matters and is not incidental — absence of evidence is
not evidence the building is gone.

**An em dash 500'd every buildings tile.** HTTP header values are byte strings
and `new Response` throws on anything above 0xFF. The NYC licence contains an em
dash, so the `x-attribution` header threw on every *successful* tile — while
both failure paths, which carry no such header, passed their tests. Caught only
because the route test was parameterised over both archives rather than written
once for the basemap. The licence is percent-encoded now rather than stripped:
deleting characters from a licence to fit a transport constraint is the wrong
trade.

**And one that was not silent: the loading card sat over a drawn city for ten
seconds.** "Ready" was `once('styledata')` wrapping `once('render')`. The second
archive resolves its TileJSON seconds after the first, so `styledata` now
arrives long after New York is on screen, and the nested listener then waits for
the *next* frame on a map that may be idle. A style that has not been applied
cannot paint a frame anyway, so the outer wait was buying nothing. Keyed off the
first painted frame now.

**A missing skyline is not a broken map.** If the buildings archive is absent —
a clean clone, or a `make setup` that half ran — the style is built without the
source *and* without the layer, the city draws flat, and a panel in the corner
says so in the route's own words. Dropping only the layer would leave MapLibre
loading a source it cannot reach, raising `error`, and replacing a perfectly good
New York with a card about a file.

---

### M4b Task 2 — the dark style, and the black rectangle with 1,263 features on it.

`maplibre-gl` and `pmtiles` are in, `/explore/city` exists, and the city draws
from the local archive with no network at all.

**The style is hand-written over the archive's nine layers** rather than adapted
from a published dark theme, because the requirement is unusual: this map is a
*surface data is read against*, not a map. §2.2's rule — most of the city stays
dark so active data can breathe — becomes a hard cap: **the basemap tops out at
`ink-400`**, the dimmest shade cleared for a non-text indicator, and importance
is carried by line **weight** rather than brightness, because there is no
brighter shade to promote a motorway into that would not compete with a job.

**Every `kind` in every filter was measured**, by decoding tiles at z8, z10,
z12, z14 and z15 across Midtown, Lower Manhattan, Brooklyn, Staten Island and
JFK. The load-bearing ones are pinned in tests: a filter naming a kind the
schema dropped draws an empty layer in silence, and the harbour would simply
stop existing. `landcover` turned out to be absent from every NYC tile sampled —
it carries low-zoom natural land cover and New York is urban all the way down —
so styling it would have been styling nothing.

**Two absences are deliberate.** The archive's own OSM `buildings` layer is not
drawn, because §5.3 takes heights from NYC Open Data so the skyline is measured,
and drawing OSM footprints now would either double-draw against the real
extrusion or quietly become it. And there is no text at all: every symbol layer
needs a `glyphs` URL and every glyph URL is a network call.

**`dusk-*` landed with its assertion running the other way** from every other
token in this repository. Rather than proving the colour is readable it proves
each shade is too dark to be text at all, and that no component has reached for
one. §3's resolution to the magenta conflict is that the purple lives in the
air; a violet that can appear on a mark makes `alert-*` unreadable.

**Two failures, both silent, both worth the record.**

**MapLibre v6 hangs.** On v6.3.0 the map builds, resolves the pmtiles TileJSON
on the main thread, fires `sourcedataloading` — and then nothing, forever. No
tile request, no `load`, no `error`, no console output. Tile fetches happen in a
web worker, and v6's worker-side bridge for custom protocols does not reach
`pmtiles@4.5.0`. Pinned to `maplibre-gl@5.24.0`, with the finding written into
the component as the test to re-run before any upgrade.

**The first style was invisible.** Land sat one shade above the background and
the map rendered as an unbroken black rectangle — every layer drawing, 1,263
features on screen, and nothing a person could see. The fix arrived with a
metric rather than a nudge: **CIE L\*, not a WCAG contrast ratio.** The ratio's
`+0.05` flare term rates `ink-800` on `ink-950` at 1.09:1, which sounds like
"invisible" and describes a perfectly visible step between two large fills;
judging the map by it would have pushed the whole basemap several shades
brighter and spent the budget M4c needs. The thresholds are now stated as
multiples of a just-noticeable difference, and one test guards the other
direction — a style that passed them by simply getting brighter would ruin the
signal layer, so `signal-400` must stay 40 L\* clear of the brightest basemap
colour.

**Evidence.** 44 new web tests (31 style, 13 palette) plus 5 new `dusk-*`
assertions; `make check` and all five CI jobs green. Verified in Chrome against
the real 91 MB archive by sampling the rendered canvas: 506 distinct colours,
median pixel L\* 5.6, roads at L\* 40, and the brightest pixel exactly
`ink-400`.

---

### M4b Task 1 — the basemap artifact, and the week-long shelf life nobody planned for.

`city.md` §5.2 had already chosen self-hosted Protomaps over OpenFreeMap, and
the reason was `CLAUDE.md` §4 rather than anything about tiles: **`make demo`
works offline from a clean clone**, and a hosted tile service is a network call
on every pan. What §5.2 did not know is what happens when you try to implement
its one-sentence plan.

The obvious build is for `make setup` to cut the NYC box out of Protomaps' daily
planet build itself. No hosting, no artifact, always current. Measured on
2026-08-11:

| Build | Age | Result |
|---|---|---|
| `20260811`, `20260810`, `20260809` | 0–2 days | 206 |
| `20260804` | 7 days | **404** |
| `20260801`, `20260706` | 10 days, 5 weeks | **404** |

**Retention is about a week**, which kills setup-time extraction twice. It
expires — a pinned `--build` 404s at `make setup` on a clean clone, the exact
scenario §4 protects hardest. And before it expires it is not reproducible:
"whatever is current" hands two clones two different maps, with nothing to
checksum, so §5.2's *"the download is checksummed"* was unimplementable rather
than merely unimplemented.

So: **bake once, publish, pin by digest.** ADR 0022.
`scripts/bake_basemap.py` cuts the bbox over HTTP range requests — 100 MB
transferred against a planet file of several hundred gigabytes, in **eight
seconds** — and writes `data/basemap.manifest.json` from measurements of the
result rather than from its own arguments. The artifact is a GitHub release
asset on this repository: free, no key, stable URL, and independent of Q2.

**The artifact:** build `20260810`, basemap v4.15.1, OpenStreetMap as of
`2026-08-10T04:00:00Z`, the full five-borough bbox, zoom 0–15, **95,348,122
bytes**. Two size decisions have committed tests rather than comments — the bbox
is New York's own bounds (a test asserts each edge, because a tighter box
renders a city with part of New York simply absent) and z15 costs 91 MB against
z14's 28 MB and z13's 11 MB, which buys the street-level view §2.1 is built
around.

**The verification is most of the code, and the reason is that the dangerous
failure is a *plausible* file rather than a corrupt one.** An expired URL or a
captive portal returns an HTML error page with a 200; `curl` writes 400 bytes of
`<!doctype html>` under a `.pmtiles` name; every careless check passes and the
map goes blank with a decoding error from inside pmtiles.js. So the check is
layered and each layer is a named state carrying its own sentence:

| State | Caught by | Because the fix differs |
|---|---|---|
| `missing` | `exists()` | The expected state on a clean clone, not an error. Names `make basemap` |
| `not_pmtiles` | magic bytes | You downloaded an error page. The message quotes what it actually starts with |
| `wrong_spec_version` | the version byte | A real archive this build cannot read. Re-bake |
| `wrong_size` | `stat` | An interrupted download |
| `digest_mismatch` | sha256 | Right length, right format, wrong bytes |

That is invariant I3's distinction one subsystem over — "I could not check" and
"it is wrong" are different answers. Nothing is installed until it verifies: the
download lands on a `.partial` name and is moved into place only after, so a bad
fetch can never *become* the map.

**The route (`/api/basemap`) serves it over byte ranges**, from Next rather than
FastAPI so the degraded path (`make test-e2e`, no API behind it) still draws a
city — §5.6 requires that path to stay usable. A missing archive answers **503
naming `make setup`, not 404**, because pmtiles.js reads a 404's HTML body as an
archive header. A server that ignored `Range` would still "work" and send 91 MB
per tile, which is why the range parser is its own tested module: 27 cases, and
the distinction it exists to keep is malformed (ignore, serve the file) versus
unsatisfiable (416).

**Evidence.** 60 Python tests, 39 web tests (27 parser, 12 route). The route was
also driven against the real 91 MB archive through `next start`: HEAD reports
95,348,122; `bytes=0-6` returns 206 and the seven bytes `PMTiles`; a range past
the end returns 416. `make basemap` took 4.6 s cold and 0.55 s cached.

**CI caches the archive and runs `make basemap`.** Without it,
`test_the_downloaded_artifact_matches_the_manifest` skips and the one end-to-end
claim — that the pinned digest is what the release actually serves — is checked
nowhere. Same argument the embedding model's cache comment already makes.

**One thing found while writing it:** `urlopen` fails with
`CERTIFICATE_VERIFY_FAILED` on a Python built against macOS' system OpenSSL,
which reads like a network problem and is not one. The fetcher builds its
context from `certifi` and **never falls back to an unverified one** — an
unauthenticated 91 MB download is exactly the substitution the rest of the
module exists to prevent.

---

### M4a Task 5 — the coverage readout, and three descriptions that had gone stale.

The census belongs on `/analyze/coverage`, and `discovery/coverage.py` from M1
was already the right home — it exists to name what this system cannot see, its
`BlindSpot` carries `count: int | None`, and its docstring already forbids
denominators and zeros-as-stand-ins.

**No web work was needed.** The page renders `blind_spots` generically and
`coverage.spec.ts` reads the list from the API *at run time* rather than from a
snapshot, so the new disclosure was covered the moment it existed. One named
test was added on top, because this is the disclosure that explains the shape of
the whole map and removing it should go red rather than go quiet.

**One judgement inside it.** The first draft set `count=0`. `count` means "how
many things sit in this gap", and for the live database that is every posting at
an employer with no confirmed office — a number that moves as the worksheet is
filled. The 247 is the *recorded corpus*, so it is stated in the explanation
where it can be attributed rather than in a field the page renders as though it
described Postgres.

**Then acceptance surfaced three descriptions that had stopped being true while
still passing**, which is the dangerous kind:

| Where | Said | Now |
|---|---|---|
| `verify.py` | "0 mappable locations **in M0** — nothing is geocoded yet" | "no `job_locations` row carries coordinates — the loader writes offices, not job locations (§4.4)" |
| `verify.py` | "no location is verified or approximate **in M0**" | "no job location claims verified or approximate precision" |
| The Analyze page, **on screen** | "nothing geocoded yet" | "no posting states a street" |

The first got *stronger* rather than reworded: it used to assert "we have not
built geocoding" and now asserts the §4.4 decision holds. The third is the one
that matters, because it is the only one a person reads — "nothing geocoded yet"
describes a missing feature, and the number is zero because of a property of the
data instead.

**Sixth time in this project a description has outlived the thing it described,
and the first caught inside the slice that caused it** rather than a milestone
later.

---

### M4a Task 3 — the ladder, the worksheet, and the hospital.

**`domain/geocoding.py`,** behind a Protocol so nothing outside `adapters/`
imports an HTTP client and the offline path goes *through* the interface rather
than around it. Coordinates cannot be constructed with a confidence that has
none, or a method that never produces one — the same claims the DDL makes, one
layer up, so a violation reads instead of arriving as an `IntegrityError`. A
refusal is a value carrying *why*, which is I3's distinction one subsystem over.

**`data/company-locations.yaml`** is the promotion path (Q7 answered: "as many
as you'd like"). `read_worksheet` refuses four kinds of entry, each of which
would otherwise become a lit building nobody vouched for. The sharpest is an
address that names no street: ordinary input would be stored as `city_only` and
moved past, but somebody typing here is asserting *an office is at this address*,
and the honest answer to an assertion that cannot support itself is to say so.

**The NYC GeoSearch adapter, and the correction the recording forced.**

`city.md` §4.3 claimed Pelias would answer `"New York, NY"` with the city
centroid at a good score. That was reasoning. The measurement is worse:

```
"New York, NY"                     -> NEW YORK HOSPITAL   confidence 1.0  exact
"620 Eighth Avenue, New York, NY"  -> 620 EIGHTH AVENUE   confidence 0.8  fallback
```

A real building at First Avenue and 68th Street, at maximum confidence, because
Pelias matched the words against venue names — exactly. A centroid at least
reads as an approximation; **this reads as an answer**, and it outscores the
truth. So nothing in the adapter reads `confidence`. Acceptance is three facts
about what the response *is*: did the provider parse a house number, does the
feature carry that house number, is the BIN a real building rather than one of
the five per-borough placeholders. Each has a mutation test that breaks it
alone, and `test_the_garbage_outscores_the_truth_in_the_recorded_data` pins the
premise rather than the code — if a future release makes `confidence`
trustworthy, it fails and somebody reconsiders §4.3.1 deliberately.

**Migration `0021` — the BIN, which arrives free and was not planned for.** A4
reads as though the footprint join is PostGIS work: store the point, find the
containing polygon. GeoSearch returns `addendum.pad.bin` in the same response.
Better rather than merely cheaper — a BIN is an exact key, and point-in-polygon
is least reliable in exactly the case this product cares about, a tower whose
footprint abuts three others. Nullable and outside the `verified` constraint,
because a real address outside NYC is `verified` with no BIN and tying the two
would quietly redefine the invariant as "in New York".

**`test_fixture_provenance` widened, not exempted.** It required `board_token`
on every recording — true since M1, because every recording was an ATS board.
GeoSearch has no board. Now one of `board_token` **or** `provider`, for the
reason that file's own M2c comment gives: *an exemption is how a fixture with no
history gets in*.

Evidence: `make check` exit 0, **1815 Python** and 225 web; `0021` up/down/up
clean; `make drift` clean; mypy clean across 71 files.

---

### M4a Task 2 — the office table, and the first enum value this project has added.

`company_locations` exists (PRODUCT-SPEC §6.6, unbuilt for four milestones
because nothing needed it until Task 1 gave it a measured reason).

**Two constraints carry the design.**
`ck_company_locations_verified_requires_a_street_address` is new and has no
counterpart on `job_locations`: `verified` is the confidence that puts a beacon
on one specific building, and Task 1 measured that a city name can never earn
it. Without it, an office geocoded from "New York, NY" stores as `verified` and
the renderer places it on whichever building the centroid landed in — I1's exact
failure, arriving through the door `confidence_matches_coordinates` leaves open,
since that check only asks whether coordinates are *present*. And `confirmed_by`
/ `confirmed_at` are `NOT NULL`, which is what turns *"a lit building is a
verified fact"* from a habit into a property of the schema.

**The first enum value this project has ever added to an existing PG type**, so
there was no migration to copy. PostgreSQL has `ALTER TYPE ... ADD VALUE` and no
`DROP VALUE`, so the downgrade rebuilds the type and converts `job_locations`
across rather than leaving the value behind — the short version would have made
up/down/up pass while quietly not reversing, and the next person to add a value
would have copied it. The downgrade fails loudly if a surviving row uses
`company_office`, which is correct: you cannot downgrade past data that needs
the value.

`conftest._TRUNCATED` gained `company_locations` before `companies` — **the
fifth milestone running that this list has been kept correct by the database
rather than by somebody remembering**, and the fifth time the no-CASCADE choice
paid for itself.

Evidence: `alembic upgrade` → `downgrade -1` → `upgrade` all clean; `make drift`
reports no model/migration drift; `tests/test_company_location_models.py`, 11
tests, including two that attack the constraints with raw SQL because a
constraint only the ORM respects is one a raw INSERT gets past.

---

### M4a Task 1 — the census, and the zero it found.

M3 is closed and merged. M4 is open on `m4a-geo-spine`, and the design is written:
**`docs/architecture/city.md`. Read it before any MapLibre, any Three.js, and any
geocoding.** It is the required-read for M4 the way `matching.md` was for M3.

**M4 does not begin with the map, because it cannot.** No coordinate has ever been
written to this database. `job_locations.geom` is a column with an index and no
values; `mappable_locations` reads 0. Geocoding was labelled M1 in the table below
for four milestones and never built. A renderer on top of that would have 31 jobs
all reading "New York, NY" and, under I1, nothing it is allowed to place on a
building. So the milestone runs geo spine → basemap → signal layer → ship, and the
slice plan is `city.md` §7.

**The count ran and the answer is zero.** `scripts/census_location_text.py`, over
every committed fixture payload — 247 postings, 139 distinct location strings, 10
location-bearing fields, three providers:

```
  street_address        0    0.0%
  place_name          207   83.8%
  remote_only          25   10.1%
  nothing              15    6.1%

NYC postings: 58 of 247 (23.5%) — street_address 0, place_name 58 (100%)
```

**Nothing names a street.** Not in Greenhouse's `location.name`, not in its
`offices[].location`, not in Lever's `categories`, and not in Ashby's structured
`address.postalAddress` — the field this project had deliberately left unread since
M1 *because it was the good one*. Its key set across every Ashby fixture is only
ever some subset of `{addressCountry, addressLocality, addressRegion}`. Ashby's
schema has `streetAddress`. No employer in the corpus fills it.

Three consequences, in order of how much they cost:

1. **Rung 1 of A4's ladder is unreachable from a posting.** GeoSearch resolves
   addresses. There are none. A job's honest ceiling is `city_only`.
2. **Under I1, a job can never place itself on a building.** Never — not rarely.
3. **So buildings come from companies, and company addresses are not in ATS data
   either.** `city.md` §4.4 works the four candidate sources and lands on a curated
   `data/company-locations.yaml` with OSM proposing and a human confirming — the
   third instance of a pattern this project already runs twice. **Q7** asks the
   human how far to take the curation.

The zero is a measurement, not an artifact. **The detector's first draft reported
four street addresses and all four were false** — `ct\.?` matching Connecticut in
"Stamford, CT" and `fl\.?` matching Florida in "Miami, FL", which would have fired
on every posting in two states. The script now refuses to print a count until it
has proved on that run that it fires on "620 Eighth Avenue, New York, NY 10018" and
stays silent on "Miami, FL".

**What this validates about the ordering.** M4's design says the geo spine comes
before the renderer. Had it gone the other way, this would have been found in M4c,
after the beacons, the instancing and the selection wiring were built around an
assumption that jobs sit on buildings. It cost one script and one afternoon.

**Working-practice change M3d earned, in force from this task: open the PR as a
draft at task 1 of a slice, not at the end.** It costs nothing, gates nothing, and
it is the difference between a wrong sort key being caught in four minutes and
being caught in seven days. `make check` was run before every M3d commit and it was
not enough, because `make check` does not run the browser suite.

**Open question that does not block the first three slices but does block the
fourth:** Q2, the deployment target. A15 calls M4 a real ship. `city.md` §8 names
what changes under each answer.

---

## M3 acceptance — the six criteria, walked

`CLAUDE.md` §6: *"every score decomposes; every positive skill claim resolves to
an evidence row; hard blockers surface before soft gaps; `uncertain` never
collapses to a number; eval suite runs in CI; identical inputs + identical
`ruleset_version` → identical output."*

Walked on 2026-08-11 at the tip of `m3d-evaluation`. **Two of the six pass with a
stated limit rather than cleanly**, and those are §5 and §2 below.

### 1. Every score decomposes — PASS

A `match_results` row cannot exist without its parts. `MatchScore.__post_init__`
refuses a score that is not exactly six components, once each — five components
sum to a smaller total *and* a smaller denominator, so the fraction still looks
reasonable and nothing downstream notices. Beneath it, migration
`20260809_1607`'s `ck_match_results_the_total_is_its_parts` refuses the row at
the database.

The decomposition is stored, not derived on read (ADR 0019 §1): six component
scores, `match_component_assessments` with a sentence each,
`match_penalties` with its own `why`, `match_evidence`, `assessed_out_of`, and
`ruleset_version`.

Evidence: `test_the_response_carries_all_six_components_with_their_weights`,
`test_every_ranked_row_carries_its_whole_breakdown`,
`test_the_two_deferred_components_are_named_rather_than_scored` (the ten points
nobody scored are named on the list, not silently absent), and
`test_every_score_number_is_load_bearing.py` — every weight, ceiling and
threshold mutated, each one measured moving the golden corpus.

Read by eye at M3c Task 12, which is where three false sentences were found that
no unit test could see.

### 2. Every positive skill claim resolves to an evidence row — PASS, with the DDL asymmetry named

§7.2 is an equality, not a rate, and it has two halves with **different teeth**:

| | Enforced by | Runs in CI |
|---|---|---|
| A job span quotes the posting at the offsets it claims | A trigger, on INSERT **and** UPDATE — both probed by attacking the database | Yes, and `test_every_job_span_quotes_the_posting_at_the_offsets_it_claims` over 153 postings × 4 profiles |
| A user span quotes a **confirmed** record, never `resume_extractions` | `test_every_user_span_quotes_something_the_person_confirmed`, plus `verify.py` | Yes, since M3d Task 4. **No trigger** — `user_span_text` points into several tables and no single FK can see it |

Zero violations over the corpus. The embedding-proposed share of awarded points
is **0 of 9,417** (ADR 0018), published rather than only asserted.

**The limit, stated:** the second row has no DDL behind it. A row inserted by
hand that quotes an unconfirmed extraction would be accepted by the database and
caught only by a test. That is written into the docstring rather than implied,
and it is why M3d Task 4 mattered: before it, that half ran only under
`make acceptance`, against rows the script had rescored itself.

### 3. Hard blockers surface before soft gaps — PASS

Two mechanisms, at two altitudes.

**In the gate:** a hard blocker outranks a soft one and outranks an unknown, and
each carries a quoted span from the posting —
`test_a_hard_blocker_outranks_a_soft_one`,
`test_a_blocker_outranks_an_unknown`,
`test_a_blocker_quotes_the_posting_and_carries_its_span`.

**In the list:** `BAND_ORDER` groups by eligibility state before any score is
consulted, and the grouping is a visible section header rather than a number
(§5.3). A senior title is a *penalty* and can never become a blocker —
`test_a_senior_title_is_a_penalty_and_can_never_be_a_blocker` — which is the
direction A13 cares about.

Measured, not just asserted: `ineligible` precision is **1.000** over 240 pairs
(Task 3). The extractor never produced a hard block the labels do not support,
and `test_a_false_block_would_be_caught` proves the detector can see one, against
a constructed disagreement.

### 4. `uncertain` never collapses to a number — PASS

Three separate refusals:

- **Eligibility is never part of the score** (§5.2). The verdict sits beside the
  number, never inside it.
- **`uncertain` is its own band**, always rendered, above `likely_ineligible` —
  an open question is not a soft no, and
  `test_all_five_bands_are_present_even_when_empty` keeps the heading there when
  there is nothing under it.
- **A pair nothing could be assessed on has a `None` fraction, never `0.0`.**
  Zero sorts a posting last and one sorts it first, and both are claims about a
  pair nobody could score. `score_fraction` is the single rule, and
  `test_a_pair_nothing_could_be_assessed_on_sorts_last_in_its_band` holds the
  ordering: such a row keeps its band and leaves the ordering, marked
  `unassessed_sort_last` on the wire.

`A13`'s direction is measured too: the errors run safe. `eligible` precision
0.711 (shows somebody a posting they may not get) against `ineligible` precision
1.000 (never removes one from their world silently).

### 5. Eval suite runs in CI — PASS on the wording, and the wording is doing work

`matching.md` §7.1's table is the full inventory, brought level with what exists
at Task 8 and split by whether a metric can turn a merge red. Summarised:

| Metric | State |
|---|---|
| Skill-extraction precision / recall | **Gated** 0.84 / 0.86 |
| `required` vs `preferred` accuracy | **Gated** 0.91 |
| Four reading accuracies | **Gated** 0.86 / 0.98 / 0.88 / 0.91 |
| Hallucination equality, both halves | **Gated** — a violation is a failing test |
| Ranking stability | **Gated** — two full runs, byte-identical |
| Eligibility precision / recall per state | **Reported**, plus one hard gate: zero blocks the labels do not support |
| `enrollment_required` three-way accuracy | **Reported**, named in `REPORTED_NOT_GATED` with its reason |
| Ranking quality (NDCG, precision@k) | **Reported** |
| Embedding-proposed share | **Published**; a separate set assertion is gated |

**The distinction is the point and the criterion hides it.** *"Runs in CI"* is
satisfied by all nine. *"Gates in CI"* is satisfied by five. The three reported
ones are deliberate — §2.5 of the plan: report first, baseline second, gate third,
because a floor chosen before a number is measured is either unreachable or
vacuous and there is no way to tell which from outside.

**What that costs is not hypothetical.** A reported number reads exactly like a
gated one in a green run, and this milestone produced two findings of precisely
that shape: five accuracies sat ungated for a milestone after the condition they
were waiting on was met (Task 2), and the ranking-quality metric graded an
ordering the product had stopped serving for two tasks (review §2.1). Every
ungated number now carries its reason in code, and
`test_every_label_field_is_graded_or_named` fails if one appears without one.

### 6. Identical inputs + identical `ruleset_version` → identical output — PASS

`test_two_full_runs_are_byte_identical` rebuilds the corpus and **re-extracts**
rather than comparing a cached string to itself — 153 postings × 4 profiles,
twice, byte-identical.

The regeneration guard is the stronger half:
`test_a_score_that_moved_without_a_version_bump_is_refused` refuses a golden
regeneration while `ruleset_version` stays put, and
`test_the_refusal_names_what_moved` makes the refusal legible. It has fired
twice unprompted and been right both times — at M3c Task 12 (`RULESET_LOGIC_VERSION`
→ 2, for nice-to-have evidence rows that moved no total but changed the evidence
graph) and at M3d Task 1 (→ 3, for the ontology edges). **Nobody remembered to
bump it either time; the guard made it impossible not to.**

`test_growing_the_corpus_is_not_a_rule_change` keeps the guard from firing on
added postings, which is what would otherwise make people disable it.

---

## M3d — the evaluation suite. All eight tasks done.

Branch `m3d-evaluation`, merged as PR #14 (`7b480e9`) on 2026-08-11. The PR run
at `ade217b` and the post-merge run on `main` both passed — which is the evidence
criterion 5 below was arguing for from the workflow file rather than from a run.

### Task 8 — the ADRs, the review, and a metric that had been grading the wrong thing

**Shipped:** ADR 0020 (the ontology edge), ADR 0021 (the ordering key),
`docs/reviews/milestone-3d-review.md`, the M3 acceptance walk above,
`scoring.coverage_weighted_fraction`, two new tests, one repaired sort key, one
repaired `verify.py` check, and `matching.md` §5.3 / §7.1 / §7.3.

**The finding the task existed to find, and it was in Task 5's own file.**

`test_ranking_quality_against_the_ratings.py` sorts the rated corpus the way the
product sorts it, under a docstring reading *"the product's own ordering (§5.3),
not a second opinion about it."* Task 6 replaced that ordering one commit later
and did not touch the grader. So CI reported:

    NDCG@10      0.811   <- the ordering M3c shipped
    precision@5  0.600

for a product serving 0.817 / 0.800. Run the committed grader before the repair
and **the receptionist that Task 6 exists to demote is still printed at rank
five** — the milestone's own metric showing the defect the milestone had fixed.

Task 7 found the same drift in `verify.py` and `matching.spec.ts` and repaired
both, because both went red. This one did not go red **because it gates nothing**.
A reported metric cannot fail; it can only be wrong, and only to somebody who
runs it with `-s` and compares the number to a document.

Fixed by giving the arithmetic one Python definition that the grader and
`verify.py` both call, with `coverage_weighted_rank`'s SQL held against it by
`test_the_sql_ordering_is_the_documented_key` over rows chosen so the plain
fraction and the raw total each give a *different* permutation. The grader now
reproduces §5.3's chosen row from committed fixtures — **the first independent
confirmation Task 6's table ever had**, since it was measured by a harness that
never entered the repository.

**A second finding, one line long.** Task 7's repair of three vacuous checks
shipped a fourth: `check(scored >= 0, ...)` is true of every value
`recompute_pending` can return, including the zero that means the rescore did
nothing. Now `> 0`.

**A third, and it explains the other two.** `ci.yml` triggers on `push: [main]`
and `pull_request`. `m3d-evaluation` is pushed and has no PR, so
`gh run list --branch m3d-evaluation` returns `[]` — **no CI run at all across
eight tasks.** `matching.spec.ts` does run in CI and was red from Task 6 onward;
CI would have caught the drift in minutes. CI never ran. The practice change is
in "Next exact action": open the PR as a draft at task 1.

**One more, recorded because of when it happened.** The third assertion of
`test_the_sql_ordering_is_the_documented_key` — the non-vacuity one — passed
while proving nothing on its first draft: two rows tied at a raw total of 20 and
Python's stable sort reproduced the right permutation. Caught by making it fail
on purpose, which is the habit the whole review is about, in the test written to
close the class it is about.

### What ran, on this machine, at Task 8

| Check | Result |
|---|---|
| `make check` | **exit 0** — 1734 Python passed (445s), **225 web** passed (22 files); ruff, mypy, prettier, eslint clean |
| `make acceptance` | **exit 0** — up, migrate, drift, seed, **104 verify checks**, **55 seeded browser tests** passed, 1 skipped |
| The grader, before and after | 0.811 / 0.926 / 0.600 → **0.817 / 0.931 / 0.800**, reproducing `matching.md` §5.3's chosen row from committed fixtures |
| `check(scored > 0, ...)` | 31 pairs, under `make acceptance` |
| Mutation: `coverage_weighted_rank` reverted to the plain fraction | Killed by two tests, both named in the review |

**Not run:** the ARQ worker cron, unchanged from M3c — `recompute_pending` is
exercised four ways and the cron that calls it by nothing that asserts anything.
And CI, which is the next action rather than an omission.

### Task 1 — the ontology edge ADR 0018 asked for (`ff4feeb`)

`demonstrated_by:` in `data/skills.yaml`: PyTorch is evidence of Machine
Learning, Kafka of Distributed Systems. One-directional, one-hop, and **a claim a
human wrote into a versioned file rather than a cosine above a threshold** —
which is the whole of ADR 0018's argument, inverted into something constructive.

`RULESET_LOGIC_VERSION` 2 → 3, vocabulary `2026-08-10.1`, golden regenerated: 68
new evidence rows across 153 postings × 4 profiles. Measured: `experienced_ml`
matches 118 of 240 required rows where it matched 88, recovering 30. **The other
three profiles move by zero**, which is the shape a narrow edge should have.

`Data Structures` deliberately gets no edges — every language implements them, so
any list reads "you have written code", which is true of everybody and evidence
of nothing. Its three corpus occurrences stay unmatched.

**Two findings from the work rather than the plan.** The golden file was not
scoring what production scores: `demonstrates` began as an optional parameter
defaulting to no edges, and the golden test, the mutation harness and the
embedding measurement all call `score_match` directly — so all three pinned a
scorer that was not shipping, and the golden test passed with the feature
complete and wired. It is now a required keyword-only argument. And
`SCORING_VERSION = "m3c.1"` was dead while its comment claimed otherwise.

### Task 2 — floors on five reading accuracies, and one named as ungated (`c0dc8bf`)

Measured on the committed 60-posting key and gated just under, per M3a's rule:

    degree                0.867 -> floor 0.86
    graduation_window     1.000 -> floor 0.98
    min_years_experience  0.883 -> floor 0.88
    sponsorship           0.917 -> floor 0.91

`enrollment_required` is **deliberately not gated** on its three-way accuracy of
0.483: 30 of its 31 errors are `not_stated` where the key says `no`, and both
mean *you need not be a student* to the gate. The question that changes a verdict
already has a floor at 0.90 and measures 0.983. It is now an entry in
`REPORTED_NOT_GATED`, and a test partitions the graded fields so a future field
cannot be ungated by nobody noticing.

**The finding is the deferral itself.** The file said these stayed ungated "until
Task 5's remaining repairs are done"; M3b Task 5 shipped on 2026-08-05 and nobody
came back. A condition written into a docstring has no owner and no expiry, and a
reported number reads exactly like a gated one in a green run.

### Task 3 — eligibility precision and recall, per state (`b58124c`)

§7.1's first row, which had nothing behind it at all. 240 pairs: 60 labeled
postings × 4 fixture profiles. Agreement 202/240.

    state                 truth   pred     prec   recall
    eligible                 64     83    0.711    0.922
    uncertain                88     85    0.859    0.830
    likely_ineligible        48     38    0.947    0.750
    ineligible               40     34    1.000    0.850

**The errors run in the safe direction, and that is the finding.** `ineligible`
precision is 1.000 — the extractor never produced a hard block the labels do not
support. The weak figure is `eligible` precision at 0.711, which shows somebody a
posting they may not get; the converse would remove one from their world without
telling them, and A13 makes that the worst output this engine can produce.

Asserted rather than admired: the no-false-block test is a hard zero, not a floor
set under today's number. It passed on its first run, so a companion test
exercises the detection against a constructed disagreement — a hard-zero
assertion that has never been red is indistinguishable from one that cannot be.

### Task 4 — §7.2's second equality reaches CI (`8609bee`)

§7.2 has two assertions. The job-span one has had a trigger and a corpus test
since M3c. **The user-span one — that a span quotes a *confirmed* record and
never `resume_extractions` — ran nowhere in CI**, living only in `verify.py`,
which needs a live stack. It now runs over 153 postings × 4 profiles with no
database. The embedding-proposed share is published beside it.

### Task 5 — the ranking gets graded (`775b173`)

QUESTIONS Q5's thirty human judgements finally have a consumer. Every other
measurement in M3 grades the system against what a posting *says*; this one
grades it against what a person *wants*.

    NDCG@10      0.811
    NDCG@30      0.926
    precision@5  0.600
    precision@10 0.700

**Reported, not gated** — first sight of these numbers, over a corpus of nine
employers that are all quant firms or AI labs. Two anti-vacuity guards, and the
second is the one worth having: NDCG@30 must be **below** 1.000, because a
perfect score would mean the ordering had come from the ratings.

**The top ten was Task 6's input**: an Employee Experience Specialist
(Receptionist) rated `poor` ranked **fifth**, above four postings rated `good`.

### Task 6 — the ranked list weights its fraction by coverage (`27faac3`)

Review §2.10 closed with a measurement rather than an argument. The ordering key
is now `fraction × sqrt(assessed_out_of / 100)`.

    ordering                        NDCG@10  NDCG@30    P@5
    fraction (M3c)                    0.811    0.926  0.600
    raw overall_score                 0.777    0.902  0.800
    fraction x sqrt(assessed/100)     0.817    0.931  0.800

Not the +0.006. Three things decided it: leave-one-out across all 30 folds is
better in 28, tied in 2, worse in none; both endpoints of the exponent sweep lose
to the middle; and the mechanism is the one §2.10 describes, so it is not fitted
to the corpus. No `ruleset_version` bump — no score moved, this is a query
concern.

**The printed number is unchanged and that is a disclosed cost**: a reader can
see 17% ranked above 30%, which is why `MatchRankingOut.ordering` carries
`coverage_weighted_fraction` on the wire.

**Task 7 later found what this task left behind** — see below.

### Task 7 — three queue rows come off the deferred list (`cb0d41c`, `6686d83`, `70b9883`)

`command-center.md` **§7.4** is the design record; this is what happened.
PRODUCT-SPEC §10.4's four score-backed queue rows were named-but-deferred since
M2d. Three are now real and the fourth's reason changed.

| Row | Outcome |
|---|---|
| Best new internships | Built. Internships first seen within 14 days that the reader has no application for, ordered by the *imported* `band_rank` + `coverage_weighted_rank` |
| Resume mismatch warnings | Built as **Gaps on roles you are tracking**. `unmet_requirements` over live tracked roles, `required` only, differenced against the stored evidence graph |
| The one thing to do today | Built. One row repeated from a list below, chosen by `ONE_THING_ORDER`, composing nothing |
| High-match roles closing soon | Still deferred; `blocked_on` moved from `"milestone 3"` to `"the sources"` |

Three shapes are new and each is in §7.4: a row that is about a *posting* rather
than an application (`application_id` null, links to the job); a row that carries
an eligibility **state** and never the score it was ranked on (I4); and a section
that reports what it could not see (`BlindSpot` — a name, a count and a
*sentence*, emitted even at zero).

**The number worth remembering: `level_not_read` is 16 of 31 open postings.**
Over half the seeded corpus is `seniority = 'unclear'` and therefore invisible to
the internship row, which the row now says out loud and previously would have
hidden completely.

Nine mutations were run against the new tests; each killed exactly one test.

**Two failures this task found, both of which are review material:**

- **`make acceptance` had been red since Task 6.** `verify.py` and
  `matching.spec.ts` both asserted the ranked list descends by printed
  `fraction`; Task 6 replaced the key and updated neither. Both now recompute the
  documented key from the wire *and read `ordering` off the response first*, so
  the next change to the sort is a loud refusal rather than a wrong assertion
  about a right answer. **Nothing in CI covers `make acceptance`**, which is why
  a week passed.
- **Three brand-new `verify.py` checks were vacuous when written.**
  `check_daily_queue` runs after `check_profile_confirmation`, which invalidates
  every score on its way past — so all three score-backed rows were asserted
  against an empty table and passed. It rescores first now, and the gap row's
  assertions moved below the point where the script has a tracked role for them
  to be about. With that fixed the checks see 1 internship offered and 3 gap rows
  naming JavaScript, Kotlin and Swift.

`test_no_deferred_row_blames_something_that_now_exists` was added, mirroring
`test_search.py`'s guard of the same name. It went red immediately on the
reworded reason for the one surviving deferral, which is the guard working.


---

## M3c Task 12 — the milestone had no reader to be about

**Shipped:** `apps/web/e2e-seeded/matching.spec.ts` (7 tests),
`check_match_results` in `scripts/verify.py` (18 checks), `seed_demo_profile` and
`cmd_score` in `nightshift/cli.py`, `make score`,
`scoring.EVIDENCE_BEARING_REQUIREMENT_KINDS` and the zero-point nice-to-have
rows, `RULESET_LOGIC_VERSION = "2"` and a regenerated golden file, `workers: 1`
on the seeded Playwright config, four repaired assertions in three existing
specs, **ADR 0019**, and `docs/reviews/milestone-3c-review.md`.

### The finding the task existed to find, and it was about the fixtures

`make seed` created a dev user with an email and nothing else. Against that
profile the milestone could not demonstrate its own headline claim:

```
                              before   after
evidence rows                     13     102
  quoting a posting                0      27
  quoting the reader               0      27
components ever assessable    2 of 6   6 of 6
distinct fractions                 8      11
postings in a dimmed band          0       7
```

**Zero evidence rows quoted anything.** All thirteen came from freshness and
priority, the two components §2.1 exempts from quoting a person. So §7.2 — every
point traces to two literal spans — was true and unobservable, and the browser
walk had nothing to check it against.

`make seed` now writes the profile `tests/fixtures/resumes/nadia_okonkwo.txt`
describes, through `update_profile` / `add_skill` / `add_project` — the same
functions the form calls and the only writers I2 permits. It refuses to overwrite
a profile anybody has touched, and it leaves four of the resume's skills
unconfirmed on purpose, because `check_profile_confirmation` and
`profile.spec.ts` both need a proposal nobody has accepted.

`years_experience: 0` is what fills the dimmed bands, which is the "Not real yet"
entry above closing itself.

### Three false statements on the page, none of which a unit test could see

Every one was true of a database and false about a person:

| The page said | Why it was wrong |
|---|---|
| *What it asks for that you have nothing on file for:* **2** | A `years_experience` requirement. The profile states its years and the gate directly above reads them |
| *Nice-to-haves you have nothing on file for:* React, TypeScript, Python | All three confirmed, and quoted by name eight lines higher on the same screen |
| *0 · matched by a vocabulary rule* under a confirmed skill | True (§4.1) and reads as a judgement of the reader |

The first is `unmet_requirements` differencing against an evidence graph that can
only contain technologies. The second is `score_skill_overlap`'s **docstring
describing a feature nobody wrote** — it has promised a zero-point row for a
matched nice-to-have since Task 3, and the code iterated the required list only.

Both are fixed in the domain rather than in the page, and the rule they leave
behind is in `matching.md` §6: *a gap is only ever something an evidence row
could have answered.*

### The golden test refused to regenerate, unprompted, and was right

The nice-to-have rows moved no total — a preferred technology is still worth
nothing — but they changed the evidence graph, which is part of the score under
I4 and is what the gap list is differenced against. The regeneration guard
refused while `ruleset_version` stayed put, which is precisely the failure it was
written to catch. `RULESET_LOGIC_VERSION` went to `2`. **Nobody remembered to
bump it; the guard made it impossible not to.**

### A browser test of my own that could not fail

`matching.spec.ts`' load-bearing test — *every quoted word on the panel is text
printed on the same page* — **survived a mutation that lower-cased every quote
the panel printed.** It took the span from the API, asked whether some `<mark>`
matched it through Playwright's `hasText` (case-insensitive, substring), then
compared the API's span to the API's description: an assertion about something
the API guarantees and the page cannot break.

The two marks now carry their side and the comparison is rendered-to-rendered.
The same mutation kills it. The file's docstring says a paraphrasing panel would
pass every other assertion in it; it was describing itself.

### `git checkout --` ate two files of unstaged work

The first mutation script restored each mutated file with `git checkout --`,
which restores from the index — and two files had unstaged Task 12 work in them.
Reverted silently, mid-run; the three mutations after it ran against a tree
missing the change under test. Reconstructed, and the staged golden file then
matched byte-for-byte, which is a fair independent check that the reconstruction
was faithful. The script uses copies now.

### What ran, on this machine

| Check | Result |
|---|---|
| `make check` | **1656 Python passed**, 1 skipped, 382s; **214 web passed** (22 files); ruff, mypy, prettier, eslint clean |
| `make acceptance` | **exit 0** — up, migrate, drift, seed, **92 verify checks**, **55 seeded browser tests** passed, 1 skipped |
| `make seed` | 31 postings, 31 scored, demo profile written, 7.5s |
| Verify mutations | 3 written and measured red; a 4th killed by the database before `verify` saw it |
| Browser mutations | 4 written and measured red, one of them only after §2.5's fix |
| Screenshots | ranked list and two panels read by eye — where all three false statements were found |

### Not run

The ARQ worker path. `recompute_pending` is exercised by `make seed`,
`make score`, `verify.py` and the unit suite; the **cron that calls it** has been
run by `make dev` and by nothing that asserts anything.

---

## M3c Task 11 — the embedding gets measured, and says "you know Java, because you know Python"

**Shipped:** `services/api/tests/test_embedding_proposals.py` (6 tests),
`services/api/tests/matching_corpus.py` (the corpus loader, extracted from the
golden test so two files score the same rows), ADR 0018, amendments to
`matching.md` §2, §2.2, §2.3 and §9, and one comment in `MatchPanel.tsx`.

**Not shipped, deliberately: any embedding proposal path.** No new module, no
new column, no new dependency, and no change to a single score. `make check`
green — 1655 passed, 1 skipped.

### What the plan asked for and what came back

The M3c plan §1.1 held this task back behind ten tasks of rules-only work and
wrote down in advance that not shipping was allowed: *"If Task 11 measures a
small number, it is correct to not ship it and record the figure, and that
outcome has to be reachable from the plan rather than embarrassing."*

The number is not small. **It is inverted, which is worse.**

The rules-only baseline first, because §1.1 is right that nothing else means
anything without it. 153 recorded postings, of which **71 name at least one
`required` technology**, giving **240 requirement rows per profile**:

| Fixture profile | Matched, of 240 | Missed |
|---|---|---|
| `new_grad_backend` | 90 | 150 |
| `experienced_ml` | 88 | 152 |
| `early_career_no_experience` | 59 | 181 |
| `states_nothing` | 0 | 240 |

Then the question the plan actually posed: of what the vocabulary missed, what
would an embedding propose? Ranking every (missed requirement, confirmed skill)
pair by cosine similarity under the real `bge-small-en-v1.5`:

| Similarity | The claim it would put on the page |
|---|---|
| 0.797 | you meet a **Java** requirement, because you confirmed **Python** |
| 0.764 | **macOS**, because you confirmed **Linux** |
| 0.750 | **Azure**, because you confirmed **AWS** |
| 0.742 | **Excel**, because you confirmed **SQL** |
| 0.736 | **Windows**, because you confirmed **Linux** |
| 0.725 | **TensorFlow**, because you confirmed **PyTorch** |
| 0.705 | **Google Cloud**, because you confirmed **AWS** |
| 0.699 | **Kubernetes**, because your project used **Docker** |
| **0.624** | **Machine Learning**, because you confirmed **PyTorch** |

The last row is the only relation in this corpus a person would defend. It comes
ninth.

### Why there is nothing to tune

A threshold is worth having when the claims worth keeping sit above it. These
sit below. Cosine over technology names measures **topical relatedness**; a match
claim needs **substitutability**; and over exactly the pairs that matter the two
run opposite. Java and Python are maximally related and not interchangeable, and
it is *because* they are siblings that the model pairs them.

Two checks that were owed before concluding, both of which the layer failed:

- **Was the input impoverished?** Pair A embeds a bare token, and bare tokens
  embed badly. So the requirement was re-embedded *inside its own sentence from
  the posting* — the richest job-side text available. `Windows`←Linux,
  `macOS`←Linux, `Azure`←AWS, `Google Cloud`←AWS, `TensorFlow`←PyTorch and
  `Java`←Python are all still in the top twenty. The input was not the problem.
- **Was the yield simply negligible?** No, and this is why "we tried it and it
  did nothing" would be the wrong lesson. At a 0.70 cut the layer adds 44, 58
  and 43 rows on the three stating profiles — **+49%, +66% and +73% on top of
  what the rules matched**. At 0.50 it matches essentially everything the
  vocabulary missed, and above 0.80 it matches nothing at all, so the entire
  usable band sits inside the confusion zone. It was not rejected for being
  ineffective. It was rejected for being wrong.

### The correction to `matching.md` §2, which is the finding worth keeping

The span rule was carrying the safety argument, and it cannot.

A proposal of *"you meet the Java requirement"* quoting the posting's word
*Java* and the user's word *Python* **satisfies both spans literally and
completely**. Both strings were really written by the parties named. The rule
guarantees that no text was invented; it says nothing about whether one string
implies the other.

**Spans prove provenance, not entailment.** They are a real defence against
hallucinated text and no defence at all against unwarranted inference — and it
is the second that a similarity score produces. Worse, both spans render beside
the claim, so a fabricated qualification arrives *looking audited*. §2 now says
so, in a note under the rule it corrects.

### What the residue actually contains

The alias table in `data/skills.yaml` already owns every case where two strings
denote the *same* technology — `golang`/`Go`, `cpp`/`C++`. Those never miss, so
they never reach a proposal layer. What is left over for an embedding is, by
construction, pairs of strings denoting **different** technologies. There is no
honest match hiding in there for a better model to find.

One real gap did surface and it is a different shape: **33 occurrences of
concept terms** — `Machine Learning` (26), `Distributed Systems` (4),
`Data Structures` (3) — which a concrete tool can genuinely demonstrate. The
honest carrier is a `demonstrated_by:` edge in the vocabulary file: reviewable,
diffable, versioned, and a claim a human wrote down and can be argued with. It
is also strictly narrower than similarity — it says PyTorch demonstrates machine
learning and never that PyTorch demonstrates TensorFlow. Recorded in ADR 0018,
in "Not real yet", and not built, because it moves scores and so needs a
`ruleset_version` bump.

### How the decision is kept from reversing itself quietly

A decision not to build something is normally invisible. Three tests make this
one able to go red, and each was **proven able to fail** before being committed:

| Test | Broken by | Result |
|---|---|---|
| `test_the_rules_only_baseline_is_what_task_11_was_measured_against` | `90` → `91` in the pinned baseline | red |
| `test_no_threshold_admits_the_defensible_relation_without_fabrications_first` | `DEFENSIBLE` set to `("Java", "Python")` | red |
| `test_the_scorer_emits_no_evidence_row_an_embedding_proposed` | `Evidence.proposed_by` defaulted to `EMBEDDING` | red |

The second is the one that would reopen the ADR on evidence: if a future model
ranks the concept relation above the sibling confusions, it goes red and says so.

### One refactor, and why it was not optional

`_load_corpus` and `_load_profiles` moved out of `test_matching_golden.py` into
`tests/matching_corpus.py`, and `conftest.py`'s session fixture and
`test_every_score_number_is_load_bearing.py` now import from there. Copying them
was the alternative and it is the wrong one: a measurement taken against a corpus
that is *nearly* the golden file's is a measurement of nothing in particular. The
34 tests across the golden file and the mutation harness pass unchanged, which is
what makes it a move rather than a rewrite.

---

## M3c Task 10 — the score reaches a person, and the last bare number gets a reason

**Shipped:** `0019_match_penalties` (a table, a PG enum and one deferred trigger
asserting two things, both migration directions applied), `matching.BAND_ORDER`,
`matching.ranked_for` and `matching.unmet_requirements`, a new
`GET /matches` route, `MatchPenaltyOut` / `UnmetRequirementOut` /
`RankedJobOut` / `RankedBandOut` / `MatchRankingOut` in `api/schemas.py`,
`JobDetailOut.unmet_requirements`, and on the web side `MatchPanel`,
`RankedMatches`, `/explore/matches`, and eleven new schemas in `schemas.ts`.
11 tests added to `test_match_result_models.py`, 7 to `test_match_routes.py`,
12 in a new `test_match_ranking_routes.py`, 2 in `test_nothing_infers.py`, 5 in
`test_enum_parity.py`, 14 in `MatchPanel.test.tsx`, 9 in `RankedMatches.test.tsx`.

### The decision this task was handed, and why the answer was a table

PROGRESS assigned it in as many words: *"Task 10 decides whether that is
acceptable or whether §4.2's one-column decision needs revisiting."* It is not
acceptable and §4.2 did not need revisiting, which are two separate answers.

`match_results.penalty_score` stays one column. §4.2's reason holds — the
evidence trigger binds the six positive components and a second *score* column
would imply an evidence link that does not exist — and `the_total_is_its_parts`
still adds it exactly once. What §4.2 also said was *"what each penalty cost
belongs to the explanation"*, and nothing carried it: a reader saw `-18` and
could not be told that 12 of it was three unmet technologies and 6 a title
pitched above their stated years. I4 lists what a score stores as *"its
components, **its penalties**, its `ruleset_version`, and its evidence"*.

So `match_penalties` is §4.5's table one row down, with the same argument: the
rule's own sentence, produced by the same call as the points it explains, stored
rather than re-derived at render time. **Three consecutive tasks have now found
a missing column the moment somebody read the thing they had written** — Task 8's
denominator, Task 9's assessments, Task 10's penalties — and the pattern is worth
naming rather than treating each as a surprise.

### The guard is an equality, because a split invites exactly one failure

A decomposition that can disagree with the number it decomposes is worse than no
decomposition: it is a second account of the same claim, which is what §4.2
refused to store an `explanation` column for. So the trigger asserts
`sum(match_penalties.points) = match_results.penalty_score` at commit, plus
exactly two rows, one per name.

`PenaltyName` is a PG enum rather than free text and that is what makes the count
an assertion. With an open domain, a typo'd `seniority_missmatch` beside a
correct row is two rows, two names, and a guard that passes.

Both directions are tested. The equality was shown to fail with a row summing to
-4 beside a column of -10, and the count with one row and with none.

### The truncate list refused again, and this is the eighth time

`match_penalties` references `match_results`, so `TRUNCATE` without CASCADE
failed the moment the table existed — within a minute, exactly as it did for
`match_component_assessments` at Task 9. Sixth milestone running that
`_INGESTION_TABLES` has been kept correct by the database rather than by anybody
remembering to edit it.

### Two derivations of the missing technologies, and a test that they agree

§6's *why it may not fit* is a set difference over the stored evidence rows
(`matching.unmet_requirements`). The missing-requirement penalty independently
recorded what it charged for, in `compared["missing"]`. Different code, different
inputs, and the page prints one list beside the other's cost — so if they can
disagree, a person is told they are missing three things and charged for four.
`test_the_missing_technologies_are_the_ones_the_penalty_charged_for` asserts the
two sets are equal, and asserts the set is non-empty so it cannot pass vacuously.

The list is **null rather than empty when there is no score**. An empty list
beside a null score reads as *you meet everything*, which is a claim about a
person derived from no evidence rows at all — the same failure `eligibility`'s
own null exists to prevent one field up, and it would render as a clean page
rather than as a bug.

### `ORDER BY overall_score DESC` is the obvious clause and it is wrong

`assessed_out_of` is not always 100, so raw totals are not comparable: 40 of 50
is a better match than 45 of 100 and the obvious sort puts them the other way
round, with both numbers on the page staying true and only their comparison
lying. The list sorts on `overall_score / NULLIF(assessed_out_of, 0)`, and
`test_the_order_is_the_fraction_and_not_the_total` is the assertion, with the
fixture built so the two orderings disagree.

`NULLIF` also hands the unassessable pairs the null they are entitled to instead
of raising. **They sort last inside their band, deliberately** — Postgres'
default for `DESC` is `NULLS FIRST`, so without the explicit clause the pair
nobody could score leads the list. Last is a decision and not a default, so
`unassessed_sort_last` is on the wire; the row renders as *nothing to assess*,
never as `0%`.

### The band order is written out, not inherited from the enum

`BAND_ORDER` agrees with `EligibilityState`'s declaration order today, and taking
it from there would make a product decision a property of the order somebody
typed five members in. `uncertain` above `likely_ineligible` is the line worth
stating on its own: an open question is not a soft no, and the other way round
buries the postings a person could resolve by filling in one profile field under
the ones they cannot resolve at all. Two tests in `test_nothing_infers.py`, which
is where this repo's other hand-maintained lists are guarded.

The SQL needed a cast that was not obvious: a `CASE ... WHEN` over a PG enum
column binds its whens as `varchar`, and Postgres has no
`eligibility_state = character varying` operator. The query does not mis-sort, it
refuses to run — the better of the two failures, and it fired on the first run.

### The stale "not built yet" list finally has a test rather than a lucky catch

`JobDetail.tsx`'s `DEFERRED_FACTS` went from six entries to one. Five of the six
— match score, match breakdown, missing requirements, project evidence,
recommended resume — were about to sit on the same page as the sections that
answer them. A stale entry there has gone unnoticed for a whole milestone three
times in this project, and each time it was caught by accident; at M3b it was
caught only because the word "Eligibility" appeared twice and a test could no
longer tell the two apart.

`JobDetail.test.tsx` now asserts it structurally: **every name in the deferred
list must not appear anywhere else on the page.** It fired on this diff for five
of six entries, which is the first time this failure has been caught on purpose.
*Recommended resume* moved to `MatchPanel`'s own not-built list rather than being
deleted, because a score's missing parts belong beside the score.

### The recommended resume was declined, and the reason is I2 rather than time

§6 had it owed by "whichever of Tasks 10–12 takes it". Task 10 built the panel it
would render in and did not take it. *Which stored resume best covers the required
set* needs a per-resume set of skills, and there is none: `user_skills` is
confirmed and belongs to the **person**; `resume_extractions` is per-resume and
holds **proposals**, which §7.2 forbids any user-side span from quoting.
Recommending a resume from proposals is a claim about somebody's qualifications
built on text nobody confirmed.

Doing it honestly needs either a confirmation step that attributes a confirmed
skill to the resume it came from, or an explicit "this resume mentions" reading
that is never called evidence. Either is its own design. So the element count in
`matching.md` §6 moved from *seven computed, two not built* to **six computed,
three not built**, and the page names all three.

### The first end-to-end run on real postings

Everything before this had scored fixtures. `recompute_pending` against the
seeded database: **31 of 31 postings scored, 0 skipped**, then `ranked_for`
returned all 31 with `not_yet_scored = 0`.

What it produced is worth recording exactly, because it is thinner than the test
suite suggests:

| | |
|---|---|
| `eligible` | 13 |
| `uncertain` | 18 |
| `likely_eligible`, `likely_ineligible`, `ineligible` | 0 |
| Distinct denominators | 10, 20, 40, 50 — never 100 |
| Distinct fractions | 8 across 31 postings |

Two consequences are in "Not real yet" above and both are real: the dimmed bands
are exercised by no fixture a person can look at, and the seeded profile is empty
enough that most components are unassessable and most scores are zero. The
denominators are §5.1.1 working as designed on a corpus of mostly non-engineering
roles, not a fault — but nothing has yet shown the ordering doing useful work
against a realistic profile, and that is Task 12's browser walk to say.

### Not run this session

`make acceptance` and the browser walk. Both are Task 12's, and Task 12 also owes
`check_match_results` in `verify.py` and ADR 0018. `make check` is green.

---

## M3c Task 9 — the score reaches a reader, and a component learns to say why

**Shipped:** `0018_match_component_assessments` (a new table and one deferred
trigger asserting three things, both migration directions applied),
`matching.current_result_for` (the version filter),
`matching.COMPONENT_SCORE_COLUMNS` (one mapping, now read by two modules),
`scoring.score_fraction` and `scoring.DEFERRED_COMPONENTS`, a zero-weight
refusal in `matching_weights.parse_weights`, `MatchOut` / `MatchComponentOut` /
`MatchEvidenceOut` / `DeferredComponentOut` in `api/schemas.py`, and
`JobDetailOut.match`. 14 tests in a new `test_match_routes.py`, 9 added to
`test_match_result_models.py`, 1 to `test_matching_weights.py`, 1 to
`test_nothing_infers.py`, and 3 assertions added to existing recompute tests.

### The task owed a migration, and the reason is Task 8's reason one layer up

Task 8's note says its two columns were "found by implementing the thing that
fills them". Task 9 is the first task that *reads* a score, and it found the same
shape: **which components could not be assessed is not recoverable from
`match_results`.**

§5.1.1 requires the page to name them and say why. Neither half is there:

- A component that scored zero and one nobody could assess both store `0`. That
  indistinguishability is the entire content of §5.1.1.
- `assessed_out_of` does not resolve it. The six weights are 20, 30, 20, 10, 10,
  10 and several subsets sum to the same number, so the denominator names *how
  much* was assessed and can never name *which*.
- The `why` sentence exists nowhere else. The three exempt components quote
  nobody and put their values in `match_evidence.compared`; an assessable
  component that scored zero has no evidence row at all. Without the sentence
  those components reach the browser as bare numbers, which is I4 one level below
  the total.

`match_component_assessments` is six rows per score: `component`, `assessable`,
`why`. `matching.md` §4.5 is the decision.

### The alternative was re-running the scorer on read, and that is the worse one

The cheap version of this task computes the missing fields at render time —
`score_match` is pure, the stored row is guaranteed fresh (any input change
deletes it), so the two "should" agree. That is the second-derivation failure
`posting_for`'s own docstring is written about, and here it is worse than there:
a breakdown computed by a second path can disagree with the total printed above
it, and nothing on the page would look wrong. Every number in `MatchOut` is read
off the stored row.

### Storing a sentence is not the `explanation` column §4.2 refused

It looks like a reversal and it is not, and the line is worth stating because the
next person to read §4.2 will ask. An `explanation` is assembled **from** the
evidence rows, so it is a second version of a claim that can contradict its
source. A `why` is produced **alongside** the points, by the same call, from the
same inputs, and has no other source to contradict. Written into `matching.md`
§4.2 as well as §4.5, next to the refusal it qualifies.

### The trigger asserts three things, and the third one needed a change to the loader

1. **Exactly six rows, one per component** — the database's copy of
   `MatchScore.__post_init__`. Five means a component silently has no statement.
2. **An unassessable component scored nothing** — `ComponentScore.__post_init__`
   in SQL, for anything reaching the table another way.
3. **`assessed_out_of = 100` exactly when every component was assessable.**

The third is the one that matters on the page: without it the breakdown can name
three unassessable components beside a denominator of 100, and the ranked list
then sorts on a fraction that contradicts the rows printed under it.

It holds only while an unassessable component necessarily *narrows* the
denominator — which needs every weight ≥ 1, and the sum-to-100 assertion does not
give that. `role_relevance: 0` beside `skill_overlap: 50` totals 100 and passes,
while removing role relevance from every score in the corpus. That is the silent
removal `data/matching.yaml`'s own header claims is caught, in the one shape that
got past it, and `parse_weights` now refuses it. Left unfixed, a legal weights
file would have produced scores the database rejects, with the error naming a row
rather than the file that caused it.

### Three plausible wrong routes, each measured going red

The task's own criterion is a negative — *a stale row reads as not-yet-computed,
never as a score* — so the implementations that fail it were written and run:

| Mutation | What went red |
|---|---|
| `ORDER BY created_at DESC LIMIT 1`, no version filter | the stale-version test and the two-rows test |
| `ORDER BY overall_score DESC LIMIT 1`, no version filter | the same two |
| the `user_id` filter dropped | `test_another_person_s_score_is_not_served` |
| `score_fraction` returning `0.0` instead of `None` | one route test and one scoring test |
| assessments filtered to the assessable ones on write | 14 tests across three files |

**The two-rows test was measured failing to catch the first mutation** before it
was fixed, and the reason is worth keeping: `created_at` defaults to `now()`,
which is the *transaction* timestamp, so two rows written in one transaction are
indistinguishable in order and `ORDER BY created_at DESC` returned the right row
about half the time. Writing the stale row second is not enough; it now carries an
explicitly later timestamp and a higher score, so both shortcuts pick it every
time. A test that catches a bug half the time is a flake whichever way it lands.

### Two derivations of the eligibility state, shown to agree

`match_results.eligibility_status` is what the ranked list's bands will be built
from; the job page also computes the full verdict on read for its blockers and
unknowns. The page shows both at once, so two sources for one claim is a defect
unless something checks them —
`test_the_stored_eligibility_state_agrees_with_the_live_verdict` is the check.

### The truncate list refused again, on schedule

`_INGESTION_TABLES` in `conftest.py` had to gain `match_component_assessments`,
and the way that was discovered is 43 tests erroring with *cannot truncate a table
referenced in a foreign key constraint* within a minute of the table existing.
Seventh milestone running that this list has been kept correct by the database
rather than by somebody remembering to edit it.

### Verified, on this machine

| Check | Result |
|---|---|
| `make check` | **1616 Python passed**, 1 skipped, 395s; **182 web passed** (20 files); ruff format + lint clean; mypy clean on 67 source files; prettier + eslint clean |
| `make migrate` | `0017 → 0018` applied |
| `alembic downgrade 0017` then `upgrade head` | both directions applied, no error |
| `make drift` | no model/migration drift |
| Mutation runs | five wrong implementations written and each measured going red — the table above |

One thing this list does **not** include, and it is the honest gap: nothing was
looked at in a browser, because there is nothing to look at. The response carries
the score and no page reads it. `make demo` renders exactly what it did before
Task 8. The browser walk is Task 12's, and Task 10 is what makes one possible.

A note on how the `make check` figure was obtained, because the first two attempts
reported failures that were not real: three `make check` runs were started
concurrently against the one development Postgres, and they interfered — the two
runs produced *different* sets of 19 and 29 errors across ingestion, polling and
closure tests. `db_session` truncates inside its own transaction (conftest), which
is correct for one run and is contention for two. The green figure above is from a
single serial run with nothing else touching the database, confirmed by
`ps aux | grep pytest` returning nothing first. **Two piped `make check` runs also
reported exit 0 while failing**, because `cmd | tail` returns the exit status of
`tail`; the real status came from writing to a file and echoing `$?`.

---

## M3c Task 8 — the score reaches the database, and three triggers turn out to be one state

**Shipped:** `0017_match_score_denominator` (the two owed columns, both
directions applied), `nightshift/domain/matching.py` (assembly, persistence, and
the sweep), `workers.tasks.recompute_match_results` on a one-minute cron with
`run_at_startup=True`, `SCORING_RELEVANT_PROFILE_COLUMNS` and its three parity
guards, and the invalidation inside `update_profile` and `confirm_extractions`.
14 tests in `test_match_recompute.py`, 3 added to `test_nothing_infers.py`, 2 to
`test_enum_parity.py`.

### The three triggers are three routes into one state, not three mechanisms

§4.2 names a new or changed job, any profile change, and a ruleset version bump.
Implemented literally that is three code paths that can disagree about how a
score is computed, and two of them are events that can be missed.

They collapse because of what Task 2 already built. A changed job has its scores
*deleted* by the four triggers written then; a new job never had one; a version
bump changes `ruleset_version`, which is part of the uniqueness key. All three
arrive as the same fact — **no row at the current ruleset version** — which one
anti-join finds. So `recompute_match_results` takes no argument naming what
changed, and its work item is a row's absence rather than a queue message:
nothing is lost while the worker is down, and the next tick finds exactly what
the last one did not finish.

Only the profile change needed code, because no database trigger can see a
`users` column move.

### The plan said "enqueue"; this invalidates instead, and that is a departure

The M3c plan's Task 8 line is *"the task is enqueued from a named set of
scoring-relevant columns"*. The named set is exactly as planned. What is not is
the verb: `update_profile` **deletes** that person's scores inside the request's
own transaction, and the sweep rebuilds them.

The reason is that the two failure modes are not symmetric. A delete commits
with the change that caused it or neither happens. An enqueue after commit is
lost if Redis is unreachable at that instant — and what survives is a stored
score computed against a profile that no longer exists, with nothing anywhere
recording that it should not be trusted. It also keeps the API process free of
an ARQ pool it has no other reason to hold.

What it costs is latency: a score reads as not-yet-computed until the cron runs,
which is why that cron is every minute rather than hourly. This is the right
side to be wrong on — a missing score is a true statement and a stale one is
not — but it is a real difference from what the plan described, so it is
recorded here and in `matching.md` §4.2 rather than left in a diff.

### "Compared", not "provided", and that is the second half of the trap

The plan named "any profile change" as a trap and answered it with a named
column list. The list alone is not enough. M2c's `PATCH /profile` carries every
field the form holds, so somebody who opens the profile page and presses save
provides the entire scoring-relevant set and changes none of it — and a
`provided`-based implementation rescores the corpus on every click of a button
that did nothing.

`_clear_scores_if_inputs_moved` snapshots the named columns before the
assignments and compares after. `test_resubmitting_the_same_values_changes_nothing`
is the test for it, and it is the one a plausible implementation fails.

### `confirm_extractions` writes profile columns too, and was nearly missed

`update_profile` is the obvious writer. `confirm_extractions` also assigns
`graduation_year`, `graduation_month` and `degree` when somebody accepts a
proposal from their resume — and none of those are read by any *component*.
They are read by the eligibility gate, and `eligibility_status` is a column of
`match_results`. A score whose band no longer matches the person is exactly as
wrong as one whose number does not.

This is why the invalidation is a shared helper on a before/after snapshot
rather than a line at the end of the PATCH handler: the second writer would have
been found by nobody until a demo showed an `ineligible` badge on a person who
had just confirmed they graduate next spring.

### The third parity guard is the one that would actually catch the drift

`test_nothing_infers.py` gained three. Two are bookkeeping — the two tuples
partition `PROFILE_COLUMNS`, and every name is a real column. The third greps
`matching.py` and `eligibility.py` for `user.<column>` reads and asserts the
list names all of them.

That third one is the only one that can catch the expensive direction. A column
wrongly classified as *not* scoring-relevant is already accounted for by the
partition test, and produces a score that never updates, never errors, and never
looks wrong on the page. Shown able to fail: moving `remote_preference` to the
not-relevant tuple turns it red and leaves the other two green.

### The migration owed two columns and the second one was load-bearing

`assessed_out_of` was known about since Task 5. `match_evidence.job_span_field`
was not obviously urgent, and it is the one that would have silently cost
evidence.

Every span in this system points into `jobs.description_text` — so the quoting
trigger written at Task 2 checked that string. Role relevance is decided on the
**title**. The first real role evidence row would therefore have been refused
for not quoting a string it never claimed to come from, and the cheapest fix
under time pressure is to stop storing the span — which passes every test and
quietly removes the evidence for the component §2.1 cares most about.
`test_a_title_span_filed_as_a_description_span_is_refused` is the row that would
have been written, shown refused.

A second guard came with it: the enum's members and the trigger's `CASE`
branches are asserted equal. A `CASE` with no matching branch returns null in
Postgres rather than raising, so a missing branch does not fail loudly — it
fails as *"scores a job whose title is null"* on a job whose title is right
there.

### `overall_score <= assessed_out_of` was added because the fraction depends on it

Not in `matching.md` §5.1.2, and added while writing the migration. Each
component is capped at its weight and only assessable components widen the
denominator, so the inequality is already true of everything the rules can
produce. That is the argument for asserting it, not against: the ranked list
divides by this column, and a fraction above one is a posting sorting ahead of a
perfect match with nothing else on the row looking wrong.

### Existing rows are deleted rather than backfilled, in both directions

There were none, so it cost nothing. It is still a decision rather than a
shortcut: `100` is not a neutral default for an unknown denominator, it is the
assertion that every component was assessable — which is precisely the claim
§5.1.1 exists to stop anyone making by accident.

### A trap for Task 9, closed here

`profile_for` walks `user.skills` and `user.projects` and is synchronous, so a
`User` loaded without them raises `MissingGreenlet` rather than returning an
empty profile. That is the better of the two failures and still a trap, and the
caller who hits it is whoever loads a user for some other purpose and passes it
to `score_pair` — which is every route Task 9 adds. `score_pair` now refreshes
what is missing, which costs one query and only when something is missing.

---

## M3c Task 7 — nineteen kills, and the five dead ones that found a missing user

### What each number in `data/matching.yaml` is worth, measured

Scores that change when the number moves, out of 612 (153 postings × 4
profiles), on 2026-08-09:

```
components.role_relevance             → 0    354
components.skill_overlap              → 0    284
components.project_evidence           → 0    213
components.location_and_work_mode     → 0    333
components.listing_freshness          → 0    580
components.early_career_priority      → 0    392
penalties.missing_requirement         → 0    236
penalties.seniority_mismatch          → 0     80
thresholds.freshness_days.full        +1    296
thresholds.freshness_days.zero        −1    580
thresholds.missing_requirement.per_requirement  +1  194
thresholds.seniority_mismatch.per_year          +1   47
thresholds.seniority_years.internship  +1     19
thresholds.seniority_years.new_grad    +1     15
thresholds.seniority_years.junior      +1      5
thresholds.seniority_years.mid         +1     26
thresholds.seniority_years.senior      +1     17
thresholds.seniority_years.staff       +1     20
thresholds.seniority_years.director    +1     12
```

Reported, not gated — M3a's rule: a floor set before measuring is either
unreachable or vacuous and there is no way to tell which from outside.

### The plan asked for six kills. Nineteen numbers can move a score

Task 7 is written as "zero each weight". The six weights are not the only
numbers in the file that change what a person is shown: the two penalty
ceilings and the eleven thresholds do too, and **a decorative threshold is
exactly as invisible as a decorative weight**. All nineteen are mutated, and
`test_every_threshold_has_a_mutation` fails if one is added without one — the
same guard M3b's harness carries, because the failure mode is a check that looks
complete because nothing counts what it is missing.

A threshold is mutated by ±1 rather than by zeroing. "Zero it" is meaningless
for a rung that is already 0 and for a window whose lower bound is 7; ±1 is the
smallest change that could plausibly be a typo, which is the mutation worth
defending against.

### Five mutations were dead, and the fix was a user this product exists for

With the three Task 6 profiles, `seniority_years.internship` and `new_grad`
moved **zero** scores, and `junior` moved zero downwards. The reason is
arithmetic: `gap` is `max(0, implied - years)`, so a rung only ever bites
somebody *below* it, and the three profiles state 6 years, nothing and nothing.

The fix was a fourth fixture profile at **`years_experience: 0`** — and finding
it was worth more than the five kills. Somebody with no professional experience
yet is this product's user, and the fixture set had nobody in it. Zero is a
stated fact and not a silence, which is the exact distinction the seniority
penalty turns on and the one nothing was exercising.

One profile revived all seven rungs: internship 19, new_grad 15, junior 5.

### The named test is the golden file, and that is not a shortcut

No unit test in `test_scoring.py` reads `data/matching.yaml` — every component
takes its weight as a parameter, deliberately, because that is what keeps those
tests stable when the numbers are tuned. So the golden test is the only test a
weight change can turn red, and the harness asserts exactly that by rendering
the golden document under the mutated number.

That makes each kill stronger than a hand-picked case, not weaker: the assertion
is over 612 real scores, and the harness reports *which* scores moved rather
than a count, so a number moving one obscure posting shows up as one.

### The harness is proven able to fail, in both directions

Two guards on the harness itself, because a mutation harness that always says
"yes, load-bearing" certifies rules it never tested:

- `test_the_harness_reports_no_movement_when_nothing_is_mutated` — if rendering
  were non-deterministic, every kill above would be a false positive.
- `test_the_harness_can_tell_which_scores_moved` — a mutation known to move a
  handful of scores must report more than zero and fewer than all.

And the end-to-end check, run rather than asserted: `score_project_evidence`
made to return unassessable unconditionally — the shape of a rule somebody
disabled — turns exactly `[project_evidence]` red with the message naming it,
and leaves the other five green.

### The suite got slower, and it was the corpus rather than the mutations

The plan's §4 names this risk about Task 8's rescore, and it arrived two tasks
early. Tasks 6 and 7 took the Python suite from 435s to 753s, and the mutations
were not the cause: each one is ~0.5s. **Reading and classifying the 153
postings is ~26 seconds**, and it was happening three times — once for the
golden file's fixture, once for the determinism test, once for the mutation
harness — in two modules neither of which is *about* extraction.

It is now a session fixture in `conftest.py`, built once. The determinism test
still builds its own on purpose: a determinism test handed a cached corpus is
comparing one object against itself.

Measured: the two files together went 90s → 31s, and the full suite settled at
685s against 435s before M3c Task 6. The remaining ~250s is the two files' real
work — 612 scores rendered once for the golden file, once more for determinism,
and 19 more times for the mutations — and it is the price of checking the score
against a real corpus rather than against three hand-written postings.

### The mutation bypasses the loader, on purpose

`parse_weights` refuses a zeroed weight (the six must sum to 100) and a zeroed
per-unit threshold. Both refusals are correct and both are tested. The harness
constructs `MatchingWeights` directly, because that is the only way to ask what
a number's absence would look like about a number the loader exists to stop
reaching production.

---

## M3c Task 6 — the golden test, and the regeneration that refuses

### The corpus was measured before the format was chosen

Scoring all 153 recorded postings against three fixture profiles, on 2026-08-09,
before writing a line of the golden file:

```
459 scores          37 distinct overall scores      9 distinct denominators
1,098 evidence rows  5 pairs with assessed_out_of == 0
components earning points somewhere in the corpus: all six
```

That is what makes the file worth having. A scorer returning 50 for everything
would satisfy every other assertion in the test module — deterministic,
decomposing, real spans, byte-stable golden — so the anti-vacuity test is the
one that had to be written, and it is M3b's
`test_the_corpus_actually_exercises_the_gate` one milestone up.

The 5 pairs reaching `assessed_out_of == 0` matter separately: `fraction is
None` is a branch the corpus actually visits, not a defensive one. A test asserts
it stays non-empty, so if the branch ever becomes unreachable that is stated
rather than discovered.

### All 153 recorded postings, not the labeled 60

Nothing in this file is graded against a key — a golden file makes no claim that
a score is *right* — so the answer-key labels buy nothing here and the extra 93
postings buy coverage: more seniority levels, more cities, and postings with no
publication date at all (8 of 153).

### Every component prints its sentence, not only its points

`why` is what the explanation panel renders (§6). A rule that changes the
wording without changing the arithmetic has changed what a person is told, and a
golden file pinning only numbers would call that no change. Both are in the
file, one line each.

An unassessable component prints **`—` where its points would go, never `0`**.
That is §5.1.1 made visible: a component that scored zero and a component the
posting could not answer are different statements, and a file rendering both as
`0` cannot show a rule change that turns one into the other.

### Text rather than JSON, because the diff is the product

A JSON golden diffs one key per line and buries the number that moved among its
punctuation. The committed format reads as a breakdown, which is what somebody
staring at a red test needs:

```
akunacapital/7496397 · states_nothing
  0/50  role — · skill 0 · project — · location — · freshness 0 · priority 0 · penalty -25
  role        —  this profile states no preferred roles
  skill       0  none of the 5 required technologies is confirmed on this profile
  project     —  this profile records no projects
  ...
  penalty missing_requirement -25  5 of 5 required technologies have no evidence
  penalty seniority_mismatch —  this profile states no years of experience
```

### The failure a golden test invites, and the guard that blocks it

Change a rule, see red, regenerate, commit. `ruleset_version` then describes
rules that no longer exist, every stored `match_results` row claims a ruleset
that never produced it, and §4.2's "a stale result is never silently served"
quietly stops being true — because staleness is decided by comparing that
version.

So regeneration **refuses** when a score present in both the committed file and
the new one changed while the version stayed put, and it prints the diff rather
than only saying no. A guard that says only "no" is a guard people learn to
route around.

**Growing the corpus is deliberately allowed.** A new posting changes no
existing score. Refusing it would make the only way to add a fixture a version
bump that describes nothing, which is how a guard earns a reputation for crying
wolf.

The loop was run end to end rather than asserted: `skill_overlap: 30 → 25` in
`data/matching.yaml` with no version bump →

```
the score moved: -  8/30  ... freshness 8 ...   +  9/31  ... freshness 9 ...
GoldenRefused: N score(s) changed while ruleset_version stayed '1+2026-08-09.1'
```

→ restore → green again. Five unit tests cover the guard's own branches,
including the two it must *not* fire on.

### `as_of` is frozen, and that is not laziness

`listing_freshness` is arithmetic against today. A golden computed with
`date.today()` goes red every morning and teaches everyone to regenerate without
reading the diff — which makes the guard above pointless. The date is
2026-08-09 and it is a constant in the test module.

### One thing this file cannot do

It is nine employers, all quant trading firms or AI labs. 153 postings looks
broad and is the same narrow slice everything else in M3 measures on. A rule
that misfires only on an agency's posting moves nothing here. That is in the
test module's own docstring so it travels with the file.

---

## M3c Task 5 — the two penalties, and the total that carries its own denominator

### The missing-requirement penalty may only read `technology`, and that is §5.2

`matching.md` §5.1 describes it as *"required requirements with no evidence row
behind them"*, and the first thing implementation asked was: which required
requirements?

A posting's required rows can be `degree`, `graduation_window`,
`years_experience`, `enrollment`, `authorization`, `technology` or `role_level`.
The first five are **exactly the five dimensions M3b's eligibility gate owns** —
`eligibility.Dimension` lists those five and nothing else. Charging points for
an unmet degree requirement is the eligibility verdict converted into a number
by a side door, which §5.2 forbids in the plainest language that document has.
`role_level` belongs to the other penalty. So `technology`, alone.

That exclusion is one line of code and would rot silently, so
`test_every_requirement_kind_is_owned_by_the_gate_the_penalty_or_the_level`
asserts the three-way partition covers `RequirementKind` exactly. A seventh kind
turns it red and forces somebody to decide where it goes, rather than letting it
default into a penalty or out of one.

### The penalty counts instead of dividing, because the obvious curve is a weight change wearing a penalty's name

§5.1 gives the ceiling, -25, and nothing about the curve. The obvious one is the
fraction unmet times the ceiling. Written out beside skill overlap, it is:

```
skill overlap      +30 · matched
missing penalty    -25 · (1 - matched)
                   ─────────────────────
                    55 · matched - 25
```

That is one component of weight 55 with an offset. The penalty would move no
score that a weight change could not, and Task 7's mutation test — zero a weight
and watch a named test go red — could zero either one and see the other absorb
it, which is a mutation test that passes while measuring nothing.

The rule charges a flat 5 points per unmet required technology instead, capped
at the ceiling. That reads a fact the fraction cannot: five technologies you
cannot evidence are five things to learn whether the posting lists five of them
or fifty.

It reads the **evidence rows**, not the components' verdicts, so a technology
covered only by a project counts as met. Anything else would contradict a row
the same score is about to store.

### `None` years is not zero years, and reading it as zero is I2 pointed downwards

The seniority penalty needs both sides: what the posting's title band implies,
and what the person has confirmed. `users.years_experience` is null on most
profiles, and null is *not told*.

Reading it as zero charges every silent profile the full penalty against every
senior posting in the corpus — an invented qualification claim aimed at the
person rather than for them, which is the same invariant I2 governs and the
less-obvious direction of it. Both silences stop the rule instead:
`Seniority.UNCLEAR` is no rule having decided, and a null years figure is
nothing to compare against. Neither resolves to a number.

Mutating the rule to read `profile.years_experience or 0` turns exactly one
test red, and it is the one named for it.

### A senior title costs points and cannot block, and the type system is what says so

The task's acceptance line. The mechanical form of M3b's refusal is that
`eligibility.Dimension` has no seniority member at all, so this rule has no
route to `ineligible` even if somebody wanted one — A13's argument built into a
type rather than into a convention. The test asserts that absence rather than
asserting the penalty behaves, because the penalty behaving is a property of
today's code and the absence is a property of the design.

Scoring off the *title band* is also what makes the penalty additive rather than
a second copy of the gate's years rule: the gate reads a stated minimum in the
posting's text and can only answer when one is stated, so a "Lead Engineer"
title naming no number is invisible to it and obvious here.

### The ladder is in the data file and is shown able to run backwards

`data/matching.yaml` gained a rung per `Seniority` level, plus the two per-unit
costs. §4.2 puts every rule threshold in the file, and these are numbers that
move a score.

Two shapes load cleanly and break the rule silently, and both are now refused:

- **A falling rung.** Swap `junior: 8` and `staff: 1` and nothing crashes, every
  score stays in range, and a Lead posting costs an early-career profile *less*
  than a Junior one. The freshness window's failure, one rule over.
- **A flat ladder.** Every level implying the same years makes every gap zero,
  which is the seniority penalty deleted in data while every test that does not
  read this file stays green.

`per_requirement: 0` and `per_year: 0` are refused for the same reason: zero is
a valid whole number that switches a penalty off for the whole corpus, and the
result reads as "nothing was penalised" rather than as "this rule stopped
running".

`unclear` deliberately has **no** rung, and a test asserts it does not — it is
the one `Seniority` member that means no rule decided, and inventing years for
it is inventing the mismatch.

### The total carries its denominator, and that is a column Task 8 now owes

Q6's answer implemented: `assessed_out_of` is the sum of the weights of the
components that could be assessed, `overall` is the literal sum of the parts
floored at zero — the same arithmetic `match_results.the_total_is_its_parts`
asserts, re-asserted in Python so a unit test sees it — and the ranked list
sorts on the fraction.

`fraction` returns **`None`** when nothing at all could be assessed, not 0.0.
Zero sorts that pair last and 1.0 sorts it first, and both are claims nobody
made; a profile with no skills, no projects and no stated preferences against a
posting with no dates and no readable level reaches this.

Implementing it surfaced what the answer implied and nobody had written down:
**the denominator has to reach the database.** A component that scored zero and
a component that could not be assessed both store `0`, so the fraction cannot be
recomputed on read. `match_results` needs an `assessed_out_of` column; it lands
with Task 8's migration, and `matching.md` §5.1.2 records why the stored
`overall_score` stays the raw sum rather than being normalised to 100 — doing
that would break the check constraint *and* destroy the distinction the
constraint exists to preserve.

---

## M3c Task 4 — the three exempt components, and a date that was measured before it was trusted

### `last_seen_at` would have scored our own polling schedule

`matching.md` §2.1 said freshness is arithmetic on `last_seen_at`. Measured on
the seeded database before writing the rule:

```
31 jobs      1 distinct last_seen_at day      1 distinct first_seen_at day
             source_published_at spread: 10 to 347 days
```

`last_seen_at` records when *this system* last polled, so on an actively polled
board it is near-now for every open job and discriminates nothing. Worse, ADR
0007 gives boards different poll tiers — so an identical job would score higher
for sitting on the hot tier. That is §5.1's `application_urgency` argument
pointed at our own infrastructure instead of an employer's.

`source_published_at` is a genuine publication date on all three adapters
(Greenhouse `first_published`, Ashby `publishedAt`, Lever `createdAt` — checked
in the adapters rather than assumed from the column name, because A10 warns that
a `posted_at` is often a last-modified stamp). Present on **153 of 153** recorded
postings. A source giving none makes the component unassessable, not zero.

The architecture doc now says so; it is the second §2.1 sentence this milestone
has corrected by measuring it.

### Scored on the dimensions the person actually stated

Location has two comparable dimensions — where the job is, how it is worked —
and a profile may state either, both or neither. The weight splits across the
ones stated, so somebody who named cities and no work-mode preference is scored
entirely on cities. Scoring them on a preference they never expressed would mean
inventing one and then marking them down against it.

A dimension the *posting* cannot answer is dropped rather than failed: a
`remote_policy` of `unknown` is the source not saying, which A10 is explicit is
not the same as a mismatch. And `"remote"` typed into a locations field matches
a remote posting, because that is the word people actually type there.

Unmatched dimensions still produce evidence rows worth zero. "You asked for
hybrid and this is on-site" is the line the explanation panel needs, and a
component recording only its wins is not a breakdown.

### Priority reads the posting and never the person, and PRODUCT-SPEC §23 says otherwise

§23 asks for the opposite — *"boost only when eligibility appears plausible"*,
*"do not rank an internship highly if the graduation rules clearly exclude the
user"*. That is overridden, and the precedence is CLAUDE.md's: §5.2 forbids
eligibility from ever becoming points, and §23 is exactly that.

The concern behind §23 is real and is answered by §5.3 instead. An ineligible
posting sorts into a lower band whatever it scores, so a graduation rule that
excludes somebody moves the row without touching the number. Keeping the
component person-independent is also what keeps it *exempt* — the moment it read
a graduation year it would be a claim about somebody and would owe a user-side
span.

Both exempt-component signatures take no `profile` at all, and two tests assert
that by inspecting the signature. A rule cannot consult what it cannot reach.

### Thresholds moved into the data file, and the backwards window is shown able to fail

§4.2 puts "every rule threshold" in `data/matching.yaml`. Freshness is the first
rule with a tunable number, so the file gained a `thresholds` block and the
loader gained exhaustive validation of it — a threshold the code has never heard
of is a load error, same as a weight.

The assertion worth having is that the window cannot run backwards. Swap
`full: 7` and `zero: 90` and nothing crashes, every score stays between 0 and
100, and the ranked list is upside down on the one axis a person can check by
eye. Equal values are refused too: `zero - full` is a divisor, and a
ZeroDivisionError inside a worker is a worse failure than a load error.

---

## M3c Task 3 — the three components that claim something about a person

`domain/scoring.py`, 28 tests, no database. Pure and importing no ORM, the same
rule `eligibility.py` follows, so M3d can grade it over 60 postings and Task 7
can zero a weight and re-run.

### 43% of the corpus names no required technology, and it was measured before anything was designed around it

Counted over the committed answer key on 2026-08-09 — the **human's own
labels**, not the extractor's output, so this is not a recall problem:

```
labeled postings                                    60
naming no required technology                       26   (43.3%)
  ...of which no technology of any kind             16
```

Skill overlap is 30 points and project evidence is 20, and both read the same
required-technology list. So on 43% of the corpus **half the score cannot be
computed at all**. A component that answers zero there removes 50 points for a
reason having nothing to do with the person, which is exactly the argument §5.1
used to defer application urgency — an absent deadline scoring zero "measures an
employer's ATS configuration, not urgency" — with a bigger number behind it.

So a component returns `assessable` beside its points, and the two are different
statements: zero means *this person does not match*, unassessable means *the
posting does not say enough to ask*. What a total does with an unassessable
component changes what the number means and is **Q6**, for the human, before
Task 5. Nothing is blocked meanwhile — the flag is data either way.

**The tempting third option was already unavailable, and Task 2 is why.** Award
the points anyway and the database refuses the row: a positive component with no
evidence cannot be committed. The guard removed the dishonest fix before anyone
had to be disciplined about it, which is the argument for putting it in a
trigger, arriving one task later than the argument.

### The classifier was throwing away the only thing role relevance could quote

`family_reason` reads `title says 'engineer'`. That is fine for a human and
useless for §2.1, which requires the component to quote the posting — and
recovering a span by parsing that sentence back apart is the second derivation
that goes wrong quietly. The rule already had the match object; it now keeps it
as a `TextSpan`.

**The span carries the field it came from**, which nothing else in this system
has needed. Every other span points into `description_text`; a role family is
decided on the *title*, with the description able to veto it toward `not_tech`.
A span that could not say which string it indexes would be checked against the
wrong one — and the trigger that verifies spans would then reject correct rows.
`match_evidence` will need the same column when these rows are persisted at Task
8; it is carried on the dataclass now and is not yet in the schema.

### Three rules that cost recall on purpose, each with the reason in the module

- **Only `required` technologies score.** §4.1 calls necessity the column the
  product turns on, and Ramp's Android internship lists nine technologies under
  *nice to haves*. Scoring those rewards a posting for listing more things.
- **A project tag with no bullet behind it earns nothing.** `technologies` is a
  list of tags; `evidence` is what the person wrote. §2.1 does not let a
  project's *name* stand in for a user-side span, so a tag nobody wrote a
  sentence about produces no row at all.
- **A skill with a null `skill_id` matches nothing**, ever. That is the free-text
  path from `add_skill`, and resolving it to a vocabulary neighbour would
  fabricate a qualification.

Role relevance is a match or it is not — deliberately not a graded distance
between families. A number nobody can argue with is what §2.2 rejects
embedding-first ranking for, and inventing one between `security` and
`infrastructure` would be the same thing at a smaller scale.

### The remainder is shared out rather than rounded away

Three matched technologies and 20 points is 6.67 each. Integer division gives
three rows summing to 18 under a component claiming 20, and a breakdown that
does not add up to its own total is the small version of the defect I4 exists to
prevent. The remainder goes to the earliest rows one point at a time.

`ComponentScore.__post_init__` refuses two things the database also refuses:
points on an unassessable component, and points with no evidence row. Both are
asserted in tests that need no Postgres, so the guard is visible at the unit
level and enforced at the storage level.

---

## M3c Task 2 — the tables, and the two guards that make a score refusable

Migration `0016_match_results`. Ran up, down and up against the dev database;
`make drift` reports no model/migration drift; `make check` passed with **1453
python tests, 182 web across 20 files**, ruff, mypy, eslint, tsc and prettier
clean. `make seed` and `make verify` both re-run clean afterwards — verify's
requirement walk rewrites a job description (9 spans → 0 → 1), which is exactly
the path the new triggers sit on.

### A check constraint covered one direction of two, and a test is what said so

The constraint enforcing `matching.md` §4.3's second tier was written first as
the doc phrases it — one biconditional:

```
(component IN ('role','skill','project')) = (job_span_text IS NOT NULL
                                             AND user_span_text IS NOT NULL)
```

It reads like it covers both directions. It does not. For a `freshness` row
carrying `user_span_text = 'Python'` and no job span, the left side is false and
the right side is false, the equality holds, and **the row is accepted** — a
quotation of somebody's own words filed under a component that makes no claim
about them, which is the exact fabrication §2.1 is arranged to prevent, wearing
an exempt label.

The test asserting it was refused was written before the constraint was
re-read, and it failed. There are now two constraints: a person-claim quotes
both sides, and *only* a person-claim quotes a person. A job-side span on an
exempt component stays legal on purpose — the priority component reads a
posting's own seniority and quoting the sentence it read is more auditable, not
less.

This is the second time in two milestones that stating a rule as an equality
produced a hole in one quadrant of it. The general shape is worth naming: an
`A = B` constraint over nullable columns is four cases, and reviewing it as one
sentence checks two of them.

### Ingestion would not have committed, and the reason is three triggers deep

`_apply_normalized_fields()` rewrites `jobs.description_text` on every re-poll of
a changed job. That fires M3a's `jobs_description_change_clears_requirements`,
which deletes the job's `job_requirements`, which cascades to `match_evidence`
— leaving a `match_results` row with a positive component and no evidence, and
**failing the deferred guard at commit**. Ingestion, not the scorer, would have
been what broke, on the first poll after the first score was written.

The fix is that a score is deleted whenever anything it was computed from moves:
four triggers, on `jobs.description_text`, on `job_requirements` (insert, update
and delete — re-extraction changes what was scored against even when the text
did not), and on `user_skills` and `user_projects` (update and delete). An
absent score reads as not-yet-computed, which is true; Task 8's ARQ task
recomputes.

**Deletion rather than update, and version-checking is not enough on its own.**
§4.2 says a stale row is never served and the API refuses one whose
`ruleset_version` is not current. A rewritten description does not change the
ruleset version, so that check cannot see this class at all — the row would read
as current while its evidence quoted characters that had moved.

`test_ingestion_rewriting_a_description_does_not_fail_at_commit` walks the whole
chain: requirement, score, evidence, description rewrite, commit check, and
asserts the score is gone rather than that an error was raised.

The insert half of the `user_skills` trigger is deliberately absent. An *added*
skill cannot invalidate a stored evidence row — it can only mean a score is now
too low — and a trigger firing on insert would throw away the whole corpus one
row at a time while a resume's confirmed skills are being written.

### `SET CONSTRAINTS ALL IMMEDIATE` is sticky, and it silently changed what two tests measured

The deferred guard cannot fire in this suite, which rolls back and never
commits, so the tests force it. The first version of the helper ran `SET
CONSTRAINTS ALL IMMEDIATE` and stopped there — and that setting holds for the
**rest of the transaction**. The two tests that check, then delete an evidence
row, then check again were measured raising on the `DELETE` statement itself
rather than at the second check: passing tests, asserting immediate-mode
behaviour, while the deferred behaviour every real commit depends on was never
observed. The helper now restores `SET CONSTRAINTS ALL DEFERRED` after each
check, and the reason is in its docstring rather than here alone.

### Autogenerate, run rather than predicted

Three defects, all previously recorded in this repository:

* `nightshift.db.types.UTCDateTime(timezone=True)` emitted for
  `match_evidence.created_at` with no `nightshift` import — a `NameError` on
  import. M2c's finding 2, fourth appearance.
* No `DROP TYPE` on downgrade for any of the three new enums, so the next
  upgrade would fail with "type already exists". M2c's finding 3.
* A random hex revision id (`47e471205cf4`) rather than `NNNN_name`.

Everything else came through, including all nine check constraints, both
composite indexes and every `ondelete`. Worth recording in that direction too:
the tool is not uniformly untrustworthy and the previous three notes read as if
it were.

### Three departures from the shapes the specs name, each recorded where it was taken

* **`match_results.explanation` does not exist**, though §6.13 lists it. §6 of
  `matching.md` says no explanation text is generated and every line is
  assembled from evidence rows — a stored copy is a second version of the same
  claim that can disagree with the rows, which is why `resumes` dropped §6.4's
  `structured_profile` at M2c, and it is what §2.2 forbids outright.
* **`user_skills.skill_id` is not a foreign key**, though `command-center.md`
  §2.3 called it one. There is no `skills` table to point at: the taxonomy is
  `data/skills.yaml`, its identifier for a skill *is* the canonical name, and
  that is the same string `job_requirements.value` stores — which is what makes
  a requirement and a confirmed skill joinable at all. Null means confirmed and
  outside the taxonomy, which `add_skill`'s free-text form makes reachable and
  which no other column can express.
* **`match_evidence` gained `job_char_start` / `job_char_end` and `compared`.**
  §7.2's hallucination check is stated *at the offsets recorded*, and Task 11's
  embedding proposals point at spans that are no requirement row, so the offsets
  cannot be read through `job_requirement_id`. `compared` is where the three
  exempt components record what they weighed — §2.1 exempts them from quoting a
  span, not from being inspectable.

All three are now written into `docs/architecture/matching.md` §4.2, §4.3 and
§4.4, so the design document describes what exists rather than what was planned.

### A third guard the plan filed under "test"

The M3c plan's grading table puts "every stored span is a literal substring at
its offsets" in a test and in `verify.py`. The job side is a trigger here
instead — `match_evidence_span_must_quote`, the same pattern `job_requirements`
and `resume_extractions` already carry — because it is the strictly stronger
version of the same assertion and the pattern was written twice already. It is
shown able to fail by shifting an offset one character: the row still claims
`job_span_text = "Python"`, the offsets are still inside the description, and
nothing about it looks wrong in a debugger.

The user side stays a test. `user_span_text` points into several different
tables and a trigger there would need per-kind logic; M3d's equality covers
both.

### One rename, to stop a fifty-fifty guess

`profile.remove_skill(skill_id=...)` meant the row's primary key. `user_skills`
now has a column called `skill_id` holding a taxonomy name. The parameter is
`user_skill_id` as of this task; the route's path parameter is unchanged.

---

## M3b — merged to `main` as PR #11 (`d2273e7`)

**CI green on all five jobs, first attempt** — run
[31310986928](https://github.com/Tahmudun/Nightshift/actions/runs/31310986928).
Counts read from the job logs rather than inferred:

```
python       1383 passed; 72 distributions, all pinned
e2e          5 degraded + 48 seeded passed, 1 skipped
web          20 files, 182 tests
migrations   up, down, up, and no drift
secret scan
```

**The e2e arithmetic is the assertion that matters here.** The previous run at
`b403a8e` was 43 seeded and 1 skipped; this one is 48 seeded and **still 1
skipped**. 43 + 5 = 48, and the skip count did not rise — so all five eligibility
tests ran rather than skipping, **including the one that skipped itself green
locally against the stale server.** The remaining skip is `operate-boards`',
which predates M3b.

Locally, before the push:

```
make check         1383 python; 182 web across 20 files; ruff, mypy, eslint,
                   tsc, prettier all clean
make acceptance    73 verify.py assertions + 48 seeded browser tests, 1 skipped,
                   exit 0
make drift         no model/migration drift
migrations         0015 down and up again against a real database, drift clean
```

**Everything above ran against a verified-fresh API**, which is a sentence this
project has today earned the right to have to say. See "the three-day-old
server" below.

`make acceptance` and `verify.py` are still the two things CI does not run, so
the 73 assertions remain local-only evidence — unchanged from every previous
milestone, and the reason `make acceptance` is in the merge checklist by hand.

The PRODUCT-SPEC rename to "CitySignal" that sat in the working tree was a VS
Code artefact — the human confirmed it on 2026-08-09 and it is reverted. The
product is Nightshift.

---

## M3b Task 12 — the walk, the verify check, ADR 0017, and a promise made twice

Full review: `docs/reviews/milestone-3b-review.md`. Four findings, three fixed
this session, and the pattern across them is worth the sentence:

> **A check that measures the right thing can still measure it at the wrong
> altitude.** M3a's lesson was that a guard could be blind to what it was named
> for. M3b's is subtler — the metric worked perfectly and could not see the
> difference between a false positive costing precision and one costing somebody
> a job.

### The finding the browser walk existed to find, and did

The degree rule demotes `bachelors+equivalent` to uncertain (A13), and the hatch
is checked **before `profile.degree` is read** — that ordering is what makes it
always win. Filed as `cannot_tell`, `evaluate` attached `profile_field="degree"`
and the page rendered:

```
the posting accepts equivalent experience in place of the degree,
which is not something this system can assess.   [Add your degree]
```

beside a profile that already had a degree in it. **The gate refuses to invent a
blocker and the page invented an action** — the same class of claim, one layer
up, and harder to notice because it looks helpful.

`Outcome` gained `cannot_assess`; `Unknown.profile_field` is nullable to carry
it; the page has two headings and only one of them has a link. Every unit and
component test passed the whole time, because "not something this system can
assess" reads perfectly in a fixture and reads as a broken promise underneath a
link.

### The same promise, two paragraphs higher, still standing after the fix

Found reviewing the fix rather than the bug. `uncertain`'s headline and caveat
describe only the `cannot_tell` cause:

```
Not enough in your profile to tell
Nothing here is a no. Fill in what is missing and this can answer.
```

Both false when every open question came from the posting's wording — and the
promise is the part a reader acts on, because it is the part they read first.
Now conditional on whether any unknown is askable. **Shown able to fail in both
directions**: neutered, the first test goes red; over-applied to "any
unassessable unknown", the second does. "Nothing here is a no" stays in both
branches — correcting a false promise is not a reason to withdraw a true comfort.

### A hand-transcribed map nobody was comparing

`ASKS` in `JobEligibility.tsx` is a copy of the gate's `_ASKS_FOR` values, and it
is not a `z.enum`, so `test_enum_parity.py`'s parametrised test could not reach
it. `ASKS[field] ?? field` falls back to the raw column name, so a rule added
without its phrase does not throw and does not blank the page — it prints
**"Add years_experience"** at a person, inside a sentence otherwise asking them
politely for help. Two of the last four milestones found a transcription defect
at this boundary. Shown able to fail by deleting `is_enrolled`.

`ASKS[row.profile_field!]` also went: `Array.filter` does not narrow, so the `!`
compiled by asserting something the compiler had not checked — and what it
asserted was exactly the distinction the fix above had just introduced.

### The git guard fired for the second time in two tasks

`test_every_source_file_is_tracked_by_git` failed on `eligibility.spec.ts`:
written, passing, never added. Task 11 hit it on `SearchCaveats.tsx`. Twice in
two tasks is a pattern, and the pattern is that a *new file* is what this
workflow loses — an edit shows up in `git status` as a modification and a new
file sits under `??` where it reads as noise.

### The three-day-old server, and the 73 checks it answered

**The single most important thing found this session, and it was found by
disbelieving a skip.**

The first full `make verify` printed `all checks passed` — 73 of them, sixteen
written that morning. It was answered by a `uvicorn` **started by hand on
2026-08-05 and still holding port 8000 three days and eight hours later.**
`verify.py` starts its own API; that one died instantly with "address already in
use" into `DEVNULL`; `wait_for_api` got a healthy `/health` from the squatter.

`CLAUDE.md` §4 has said the rule since the M0 review — *verify from a clean
shell; a server you started an hour ago will make a broken target look like a
passing one*. **A habit written down is not a guard.** Two now exist:

```
port_is_taken()               refuses to run at all when the port is not ours
wait_for_api(process)         polls process.poll(), so our own server dying
                              while something else answers is caught too
```

The port guard was **run against the live stale process and seen to refuse**,
with its `lsof` line, before that process was killed.

**The frightening part is that the output was identical.** The stale run and the
honest run print the same 73 lines and the same counts. Nothing in the transcript
tells them apart. What surfaced it was a sixth signal: a Playwright test skipping
with *"no seeded posting is unassessable on any dimension"* — a claim about a
committed, deterministic fixture corpus, and therefore one that cannot be true.

Two artefacts made that survivable and both asserted something false:

- The skip itself. The corpus deterministically holds Datadog's *AI Research
  Scientist*, whose degree extracts as `phd` with `has_equivalence`. **The test
  covering this milestone's headline fix reported itself as inapplicable.** It
  now throws, naming both possible causes and the `lsof` command. The other four
  tests in the file keep their skips — a corpus with no `ineligible` case is a
  real possible state; this was not. That is M3a review §2.8 recurring one
  milestone on, on a different test.
- `playwright.seeded.config.ts` reused the API under a comment reading *"an API
  already running for `make dev` is the same API"*. It is not, and the comment is
  why nobody questioned the reuse. Still reused — refusing breaks the ordinary
  `make dev` loop — but the comment now says what it cannot guarantee.

**The remaining hole, stated at its real size:** Playwright still cannot tell a
fresh API from a stale one. A general check needs the API to report its build and
`/health` reports database and Redis. Worth an ADR at M3c, not a rushed field now.

### `check_eligibility_gate` failed on its first execution

`KeyError: 'posting_span'`. The domain object carries a `posting_span` tuple;
`EligibilityBlockerOut` flattens it to `char_start`/`char_end` on the wire, the
shape `job_requirements` already uses. The check was written against the
dataclass and run against the API.

Recorded rather than quietly fixed: **1383 Python tests knew the correct shape
and not one of them was looking at this script.** The crash also proved the
`finally` block does what it claims — "the profile is left as it was found" ran
and passed while the function was unwinding.

### What `check_eligibility_gate` asserts, now that it runs

```
an empty profile is blocked from nothing        zero `ineligible`, as an equality,
                                                over every seeded posting
the corpus reaches more than one state          the opposite failure: a gate
                                                answering `uncertain` to
                                                everything satisfies the line above
no verdict without its breakdown (I4)
every unknown names a field /profile has, or names none
every blocker's quote is the text its span points at
the same URL twice gives the same verdict
clearing a column changes it, restoring the column restores it exactly
```

The last two are ADR 0017 made checkable: no worker runs and no cache is cleared
between them. It snapshots the six gate columns and restores them in a `finally`,
and the limit is stated in the docstring rather than implied — killed mid-run,
the profile keeps this function's values and nothing on disk remembers what
preceded them.

Against the live seeded corpus, printed rather than assumed:

```
22 of 31 postings judged, 9 unread (nothing extracted, verdict null)

empty profile      eligible 13   uncertain 9                        ineligible 0
blocked profile    eligible 13   uncertain 1   likely_ineligible 7  ineligible 1
```

**`ineligible 0` on the empty profile is M3b's headline assertion, now measured
on live data rather than only on the answer key.** The second row is what stops
the first being vacuous: the same corpus does reach `ineligible` when a profile
genuinely contradicts a stated bar.

### ADR 0017, and the plan branch that could not exist

`docs/adr/0017-the-eligibility-verdict-is-computed-on-read.md`. The plan's §3
composition had five branches; the gate has four. `likely_eligible` would mean
"every rule passed, but one leaned on something uncertain", and no rule here
passes on an uncertain input — each returns `cannot_tell`, which is the safer
answer, so the branch is not merely unreachable but would be wrong if reached.
The enum keeps the member for PRODUCT-SPEC §8.3 and M3c. **Recorded in the ADR
rather than silently not implemented**, which is the difference between a
decision and an omission.

### What ran on 2026-08-09, after Docker came back

```
make check         1383 python; 182 web across 20 files
                   ruff (138 files), mypy (64), eslint, tsc, prettier — clean
make acceptance    73 verify.py assertions + 48 seeded browser tests, 1 skipped
                   exit 0
make verify        73 checks, run separately three times
make drift         no model/migration drift
migrations         0015 down, up, drift clean
```

All five eligibility browser tests run and pass. The fifth — "no unknown offers
an action that could not resolve it" — **skipped on its first attempt and passes
now**, which is the stale-server section above in one line.

The one remaining skip in the seeded suite is `operate-boards.spec.ts`'s
"an unchanged board is not presented as a problem", which predates M3b.

---

### Not real yet — M3b

- **`verify.py`'s 73 assertions are local-only evidence.** CI does not run
  `make acceptance`, and that is unchanged from every previous milestone. Listed
  first because it is the largest body of checks in this repository that no push
  will ever exercise.
- **Playwright still cannot tell a fresh API from a stale one.** `verify.py` now
  refuses a port it does not own; the browser suite cannot, because
  `reuseExistingServer: true` is load-bearing for the `make dev` loop. What
  covers it is one throwing assertion in `eligibility.spec.ts`, which catches
  only the case that actually happened. A general check needs the API to report
  its build and `/health` reports database and Redis. ADR-worthy at M3c.
- **No score, no weights, no `match_results`, no project evidence graph.** M3c.
  Nothing is stubbed for them — no empty table, no placeholder column.
- **Nothing is stored about a verdict.** No row anywhere records what any
  posting concluded about anybody. That is ADR 0017's decision, not an omission,
  and it is revisited when M3c stores a score beside it.
- **No eligibility precision or recall, in CI or anywhere.** `matching.md` §7
  puts them at M3d. The 60-posting answer key has no eligibility ground truth in
  it, so what M3b publishes is reading accuracy, classifier accuracy, and the
  wrong-ineligible equality.
- **`likely_eligible` is an enum member no rule can reach.** Kept because
  PRODUCT-SPEC §8.3 names it and M3c's score components may earn it. The page
  has words for it and will never show them.
- **Every number in M3b is an upper bound.** The classifier's thresholds and
  precedence were chosen with the same 60 titles the grade is computed on. The
  93 recorded-but-unlabeled postings are the held-out check this wants and they
  are not labeled.
- **`role_family: unclear` is labeled on zero postings**, so the corpus cannot
  grade the case the classifier most needs to get right. A test asserts the gap
  and goes red the day a posting is labeled `unclear`.
- **`fall`, `winter` and `spring` are reachable by the internship-season rule
  and stated by no posting in the corpus.** A gap in the corpus, not in the rule.
- **Three of five reading accuracies are below 0.95** — `degree` 0.867,
  `min_years` 0.883, `sponsorship` 0.917. Two of `sponsorship`'s five errors are
  the deliberate `offered` tie-break and are kept on purpose.

---

## Superseded: what Tasks 9 and 10 could not verify, closed on 2026-08-05

**Docker came back on 2026-08-05, and everything Tasks 9 and 10 could not verify
was run locally then.** It went down again on 2026-08-09; see the block at the
top for what that leaves unrun now. The gaps this section records are closed:

```
make check         1380 python passed, 178 web tests, ruff, mypy, eslint, tsc, prettier
make acceptance    57 verify.py assertions, 43 seeded browser tests, 1 skipped
migrations         0015 up, down, up against a real database; make drift clean
```

**CI is green on all five jobs at `b403a8e`, first attempt** — run
[31062755692](https://github.com/Tahmudun/Nightshift/actions/runs/31062755692).
Counts read from the job logs rather than inferred:

```
python       1380 passed; 72 distributions, all pinned
e2e          5 degraded + 43 seeded passed, 1 skipped
migrations   up, down, up, and no drift — 0015 included
web          20 files, 178 tests
secret scan
```

The migrations job's log carries the line that matters, after a full
down-to-base and back up:

```
Running upgrade 0014_profile_experience -> 0015_internship_season,
    jobs.internship_season and jobs.internship_year
```

**Migration 0015 has now run on a machine that is not this one**, which is the
assertion this project has twice had to learn to make. This is the sixth
first-try CI pass here, recorded because seven runs across this project have
failed and every one found something no local command had executed.

`make acceptance` had not run since Task 8 and `verify.py` had not run at all
since then. Both have now. **What `verify.py` still does not check is the
eligibility gate** — that is Task 12's `check_eligibility_gate`, and it is the
one thing on the Task 9/10 "NOT run" list that a working Docker did not close,
because it is unwritten rather than unrun.

---

## M3b Task 10.5 — the classifier runs on every poll (`cbcd5dc`), unrecorded until now

**This landed on the branch and nothing in this file said so**, which is why the
"Not real yet" table went on calling `jobs.role_family` and `jobs.seniority`
always-NULL for a day after they stopped being. Recorded here rather than
folded into Task 11, because a commit nobody wrote down is the same failure the
table itself keeps having.

`sync_classification` is **unconditional, unlike `sync_requirements`, and the
contrast is the point.** Re-extracting requirements on every poll churns
invisibly, which is why that call is gated on the description hash. This one has
to be ungated for two reasons: a retitled posting is a re-levelled one with no
character of the description changing, and — duller but more important — these
columns were null on every existing row the day they were added, so a poll of an
*unchanged* posting is precisely the event that would otherwise never fill them.

A comment claiming this cost nothing because SQLAlchemy emits no UPDATE for
unchanged values was **wrong, and the measurement is what said so**. Reseeding
twice moved `max(updated_at)`; stashing the call and reseeding twice moved it
identically. The churn is the poll's own — `last_seen_at` is written on every
observation — so these columns ride along in a statement already being emitted.
**The conclusion survived and the reasoning did not**, and the comment now says
the measured thing. A comment that is right for the wrong reason is the kind
that gets cited later.

Against a freshly seeded database, checked rather than inferred:

```
seniority   unclear 16   director 5   senior 4   mid 3   staff 2   internship 1
```

---

## M3b Task 11 — two filters come on, and the corpus decides a column's shape

Both had been deferred since M2a. Both now exist, and neither ships without
saying what it hides.

### The plan's premise for this task was wrong, and measuring is what said so

The plan deferred `internship_season` out of Task 3 with its shape undecided —
"one `summer_2027` string, or a term enum plus a year" — and predicted the
corpus would settle it, noting **"4 of 5 internships state a season in the
title"**. That was read off the five internships in the *answer key*. Across all
153 recorded postings:

```
internships by title       19
a season in the title       8 / 19     every one of them "Summer"
a year in the title        10 / 19
both                        8 / 19
neither                     7 / 19
```

**Two postings state a year and no season** — Old Mission's *"Software Engineer
– 2027 Internship Program (June Start)"* and Point72's *"2026 Warsaw MI Data –
Web Scraping Internship"*. A single `summer_2027` value can hold those only by
inventing the season or by discarding the year. So: two nullable columns, and
the shape question came out the other way from what the plan expected.

### Two restrictions, both measured, both removing real errors

**The description is never read.** Its years are 2011 (Akuna's founding), 2015,
2025, 2028 and 2029 — a founding date, a fund launch and a graduation horizon.
Harvesting one puts a confident season on a posting whose title honestly says
nothing.

**Only internships get a season.** Six non-internship titles in the corpus carry
a season or a year:

```
Akuna Capital's 2026 Virtual Quant Trading Challenge          a competition
Expression of Interest: 2027 Trading Sneak Peek Weeks         a programme
Associate Product Manager, New Grad (2027 Start)              a full-time start
2027 EU Campus Programme Talent Community                     a talent pool
Campus AI/ML Researcher (Fall 2026)                           a cohort start
Point72 Academy ... for Upcoming Graduates (2027 – HK)        full-time
```

The fifth is the one the gate costs something on: it states a term and a year
plainly. **The answer key labels it `is_internship: no`**, with the labeler's
reason written beside it — *"campus role, so is_internship is no"*. Following
the label over the title is the ordering in `matching.md` §1.1 doing its job a
milestone after it was set up.

### A rule was written and deleted, and the deletion is the finding

The first version refused a year outside a plausible hiring window, so *"Summer
Intern, Class of 2011 Reunion"* could not claim a 2011 season. Two things killed
it. It guards nothing observed — every year stated in a corpus internship title
is 2026 or 2027, and the implausible ones are all in descriptions the rule
already refuses to read. And **"plausible" can only mean "near now"**, which
makes the same posting classify differently next year and breaks M3's
determinism criterion, for a case nobody has seen. A test pins the decision so
the next person does not rediscover the idea and keep it.

`fall`, `winter` and `spring` are reachable by the rule and stated by no posting
in the corpus. That is a different situation from `EligibilityState`'s
`likely_eligible`, which no *rule* could reach; here only the corpus is missing.
`test_the_rule_is_not_fitted_to_summer` is what keeps it a measured gap rather
than three enum values nobody can account for.

### The docstring was wrong about autogenerate, and running it is what said so

The migration's first draft claimed autogenerate handled this correctly —
that an `add_column` introducing a *new* `sa.Enum` emits its `CREATE TYPE`,
unlike 0013's `alter_column`. That was a guess, so it was checked:

```
sqlalchemy.exc.ProgrammingError: type "internship_season" does not exist
[SQL: ALTER TABLE jobs ADD COLUMN internship_season internship_season]
```

**M2c's finding 2 for the third time in this project, and 0013's for the
second.** The downgrade emitted no `DROP TYPE` either — M2c's finding 3. The
pattern was known, written down, and cited in the migration file directly above
this one, and knowing it still did not prevent writing the wrong sentence. Only
running it did.

### `skill` outlived two deferral reasons, and the second one was caught in time

```
M2a  "requires the skill taxonomy and its aliases"   went stale at M2c, unnoticed for a milestone
M3a  "recall is 0.459 — it would hide more than half" went stale at M3a.1, caught the same session
```

At 0.861 it hides roughly one matching role in seven. That is on the panel in
words, next to the control, not in a tooltip and not behind a disclosure — a
caveat nobody sees is a caveat that is not being made.

`_canonical` moved out of the answer-key grader into `SkillVocabulary.canonical`
because the filter needs the same resolution in production. Two copies is how
the filter and the grader come to disagree about whether `GCP` and `Google
Cloud` are one technology — **M3a.1's opening defect, one layer down**, and the
one place a user would feel it: an unresolved alias returns zero rows, which is
indistinguishable from an honest "no such job".

The filter matches **any necessity**, deliberately. Restricting to `required`
would hide a posting listing Python under "nice to have" — a posting that does
ask for Python and that a person can apply to. Which list it sits in is shown on
the job page, where it can be read rather than silently applied.

### The defect this task shipped and then caught, in the browser

Both caveat counts rendered **only in the branch of the list that has rows**.
Filtering the seeded corpus by Summer returns nothing — its one internship,
*"Software Engineer Internship, Android"*, states no season — so the screen read:

```
No roles match these filters.
```

and nothing else. **The product asserting there are no summer internships**,
when the truth is that its one internship never says when it runs. That is the
exact failure the count exists to prevent, in the one state where it matters
most, and the component test could not see it because it cannot see which branch
the real page takes.

`SearchCaveats` is now its own component so it renders in both, caveat first.
**The Playwright test was shown to fail against the pre-fix shape before being
trusted** — the caveat was removed from the empty branch, the suite went red on
that one test and green on the other 42, and it was put back.

### What the two counts mean, kept apart on purpose

```
excluded_no_requirements   postings the skill filter could not have matched
                           however well it works — nothing was extracted from
                           them. NOT postings that ask for nothing.
excluded_no_season         internships stating no season (11 of 19 in the
                           corpus) or no year (9 of 19)
```

The season count **takes the query**, because the answer differs by dimension:
asking for `summer` hides the internships with no season, asking for `2027`
hides the ones with no year. One number ignoring which was asked is wrong on
both.

**Exercised against a running stack, not only in tests**, and the first number
is larger than expected:

```
/jobs                             total 31   no_req  0   no_season 0
/jobs?skill=Python                total  7   no_req 12
/jobs?skill=GCP                   total  2   == /jobs?skill=Google+Cloud
/jobs?skill=golang                total  3   == /jobs?skill=Go
/jobs?internship_season=summer    total  0   no_season 1
deferred_filters                  match_score, eligibility, borough
```

**12 of the 31 seeded jobs have no technology extracted from them at all** —
39%, on a corpus that is mostly customer-success and account-executive postings
from the recorded Alloy board, which genuinely name few technologies. Whatever
the cause, it is the number that decides whether `excluded_no_requirements`
earns its place, and at 12 it plainly does: a person filtering for Python sees
7 results and a line saying 12 more could not be read either way. Without it
that reads as a corpus of 7 Python jobs.

### The guard that caught the untracked files

`test_every_source_file_is_tracked_by_git` failed on `SearchCaveats.tsx` and its
test — both written, both passing, neither added to git. A component that exists
on one machine and in no commit is a component CI has never seen.

`InternshipSeason` was added to `test_enum_parity.py` and **shown able to fail**
by typoing `winter` in the TypeScript. It crosses the boundary as a *filter
value* rather than as a rendered field, which is the more brittle direction: a
typo there produces an empty result that looks like an honest answer.

---

## Superseded: the first Docker outage, as it was recorded during Tasks 9 and 10

**Docker Desktop went down on this machine part-way through Task 9**, so nothing
database-backed could be run locally after that point. **It came back on
2026-08-05, and the "closed on 2026-08-05" section above records what was then
run.** Kept because the record of what was and was not verified at the time is
the point of keeping it — and because it went down again on 2026-08-09, which
makes the shape of this section current news rather than history.

**CI closed most of that gap and the record says so rather than leaving the
scarier version standing.** Green on all five jobs at `38e22ac`, run
[31057503553](https://github.com/Tahmudun/Nightshift/actions/runs/31057503553):

```
python       1345 passed; 72 distributions, all pinned
e2e          5 degraded + 41 seeded passed, 1 skipped
migrations   up, down, up, and no drift — including 0014
web          19 files, 169 tests
secret scan
```

**1345 against 1047 locally** — roughly 300 database-backed tests ran there and
could not run here, including every API route test. The `e2e` job migrates,
seeds and drives a browser against a real stack, so the job detail page rendered
the new `eligibility` field and Zod parsed it; had the schema and the response
disagreed, that suite would have thrown. The seed step passing also exercises
Task 3's new exit-code guard against a real database.

`38e22ac` is the last commit containing anything CI executes, so the usual
pre-merge invariant applies:

```
git diff 38e22ac..HEAD --stat    # must list nothing outside docs/
```

**What is still not verified, and CI does not cover it:** `scripts/verify.py` —
the 57 assertions `make acceptance` runs and CI does not — has not run since
Task 8. Neither has the eligibility browser walk, which is unwritten and is
Task 12's.

**[PR #11](https://github.com/Tahmudun/Nightshift/pull/11) is open as a draft,
and that is deliberate.** Seven CI runs in this project have failed and every
one found something no local command had executed; waiting until the end of a
twelve-task milestone to learn that is the expensive version. CI now runs on
every push, and it has been **green on all five jobs twice** —
[31052329000](https://github.com/Tahmudun/Nightshift/actions/runs/31052329000)
at `bcf5f58` (Tasks 1–4), and
[31053249925](https://github.com/Tahmudun/Nightshift/actions/runs/31053249925)
at `1da91ce` (through Task 5). Counts read from the job logs:

```
python       1308 passed; 72 distributions, all pinned
e2e          5 degraded + 41 seeded passed, 1 skipped
migrations   up, down, up, and no drift — including 0013
web          18 files, 159 tests
secret scan
```

`1da91ce` is the branch head, so the recorded result covers every line on the
branch by inspection rather than by a diff. **Migration `0013` has now run
up, down and up on a machine that is not this one**, which is the assertion
this project has twice had to learn to make.

The plan is `docs/plans/2026-08-05-m3b-eligibility-gate.md`. Two decisions the
human took on 2026-08-05 before planning: role families are the eight tech
families plus an explicit `not_tech` and `unclear`, and the `skill` filter comes
on with what it is based on stated beside it.

**Task 1 is done and its result is a baseline, not an achievement.**

---

## M3b Task 1 — the five answer-key fields nobody had ever graded

**M3a graded one of the answer key's nine label fields.** The extractor has been
emitting `degree`, `graduation_window`, `years_experience`, `enrollment` and
`authorization` proposals since commit `3722026`, against a key committed before
any of those rules existed, and **no test had ever compared one of them to a
label.** It read as finished because nothing counted.

Measured 2026-08-05, over the 60 labeled postings, before any rule was changed:

```
degree                 0.567     34 right, 26 wrong
graduation_window      0.917     55 right,  5 wrong
min_years_experience   0.883     53 right,  7 wrong
enrollment_required    0.317     19 right, 41 wrong
sponsorship            0.917     55 right,  5 wrong
```

**No floors are in CI yet, deliberately.** They go in after Task 5 repairs what
this found, set just under what the rules then achieve — M3a's rule, for M3a's
reason: a floor picked before measuring is either unreachable or vacuous and
there is no way to tell which from outside.

### The confusions say what is wrong, which is why the report prints them

```
degree               read 'none' for 'bachelors+equivalent' x14, for 'bachelors' x5,
                     'phd' for 'bachelors' x2, 'none' for 'masters+equivalent' x2
enrollment_required  read 'not_stated' for 'no' x30, for 'yes' x11
graduation_window    read '2027-2027' for 'through-2027' x2, and 3 more of that shape
min_years_experience read None for 10, 14, 1; and read 5 where 3 was labeled
sponsorship          read 'offered' for 'not_offered' x2, 'not_stated' for 'not_offered' x2
```

**`enrollment_required` at 0.317 is mostly a vocabulary gap, not 41 defects.**
30 of the 41 are `not_stated` where the human wrote `no` — the reading has no
rule that can ever output `no`, which is stated in the function's own docstring
rather than discovered from the grade. Producing `no` needs to know the posting
is not an internship, and **`is_internship` is the classifier's, so this one is
blocked on Task 4.** The other 11 are real misses: the rule matches only
"currently pursuing / enrolled / studying" and postings say "rising senior",
"returning to school", "must be enrolled in".

**`degree` at 0.567 is the one to chase.** 21 of the 26 errors read `none` where
a degree was labeled, which means the degree was found and filed under a heading
the extractor does not read as required — the same class of defect M3a.1 fixed
for technologies, in a dimension nobody had looked at. The 2 postings read `phd`
against a labeled `bachelors` are the opposite error and the more dangerous one:
that is a wrong blocker waiting for the gate to exist.

### A rule that could not fire, found by measuring within the hour

`_resolve_graduation_window` shipped a branch producing the answer key's
`through-YYYY` form when the words `through|by|before` appeared in a proposal's
`raw_text`. **`raw_text` for these proposals is the matched year and nothing
else** — `"2027"`, or `"2027-2028"`. The branch could never fire.

Deleted rather than left in, and **the numbers were identical before and
after**, which is what makes "it was dead" a measurement rather than a claim.
Producing that distinction needs the words around the year, which only the
extractor has; it is Task 5's. Until then those 5 postings read as a narrower
window than the posting states — the direction that invents blockers.

### One tie-break is deliberately wrong on this corpus

`_resolve_sponsorship` prefers `offered` when a posting somehow says both, and
that costs 2 of its 5 errors. Kept: "we do not sponsor H-1B for this role, but
we do sponsor OPT extensions" is one real sentence containing both, and reading
it as `not_offered` tells a person they cannot apply for a role that says it
will help them. The other error sends them into a conversation. A13 ranks those
two, and this is the ranking applied rather than accuracy maximised.

### The grader is guarded against being the thing that is broken

Two of its four tests are about the machinery rather than the corpus, because
M3a shipped a violation count stuck at zero for a whole milestone:

- `test_the_grader_can_fail` runs a constructed disagreement through the tally
  and asserts it is recorded — a tally that cannot count a miss reads 1.000.
- `test_every_label_field_is_graded_or_named` fails if a label field is in
  neither the graded list nor the named-and-excluded list. **That is the guard
  that would have caught M3a's gap a milestone earlier**: five fields were
  unmeasured and nothing anywhere said so.
- `test_none_years_never_compares_equal_to_zero` — `not_stated` and "no
  experience required" are different postings, and the gate treats them
  differently, so the grader must not merge them.

---

## M3b Task 2 — `role_family` and `seniority` labeled, before a classifier exists

60 postings × 2 fields, added to `labels.yaml`. **120 insertions, zero
deletions** — checked with `git diff --stat`, and the patch script refuses to
write at all if the rewrite removes a line, because the one thing it may not do
is reformat a committed label.

The ordering is the whole point (`matching.md` §1.1). Rules written first make
the corpus get chosen — in good faith — to hold the cases the rules already
handle, and the grade then measures nothing. Both fields are **required with no
default**: a posting arriving unlabeled must fail to parse rather than quietly
acquire an answer nobody chose. `test_neither_new_field_has_a_default` is that
guard, and `unclear` and `not_tech` are both real answers a human picked, so
neither may become what happens when nobody picks.

### The taxonomy gained a value the human's list did not have

`hardware`. Akuna's *Hardware Engineer Intern* and IMC's *Graduate Hardware
Engineer* are both FPGA and low-latency hardware design — read, not guessed
from the titles. `not_tech` would be false and `infrastructure` would make that
family mean two unrelated things. Two of sixty. **Recorded as a departure from
the decision rather than absorbed into it**, and it is one line to revert.

The rule applied consistently for the harder calls, written down because a
labeler's rule that lives only in their head is a rule the next pass will
contradict: **`role_family` describes the work's primary output.** Software,
systems or models earn a tech family; a deal, a hire, a policy, a report or a
financing is `not_tech`. That is what puts Anthropic's *Applied AI Architect*
in `not_tech` — its own first sentence says "you will be a Pre-Sales
architect" — and OpenAI's TPM roles in `product`.

`seniority` was harvested from the 60 titles rather than invented, the lesson
M3a's Task 7 paid for. `staff` covers the Lead / Staff / Principal band because
the corpus writes "Lead" and never "Staff".

### What the distributions say, including the part that is a gap

```
role_family   not_tech 19   quant_trading 13   ml_ai 9   software_engineering 4
              security 4    product 4          infrastructure 3
              hardware 2    design 1           data_engineering 1   unclear 0

seniority     unclear 14    mid 13   new_grad 8   director 6
              internship 5  senior 5  staff 5     junior 4
```

**`role_family: unclear` is labeled on zero postings, and that is a coverage
gap rather than a success.** All sixty could be classified, so the corpus holds
no example of the case the classifier most needs to get right: a posting it
should refuse to guess at. A classifier that never answers `unclear` scores
perfectly here and is wrong the first time it meets a genuinely ambiguous
posting.

`test_the_corpus_cannot_grade_an_unclear_family_and_says_so` **asserts the
gap** — it fails the day a posting is labeled `unclear`, and its message says to
delete it. That is deliberate: this project has now four times shipped a blind
spot recorded in a comment that nobody re-read once the thing it waited on
landed. A comment goes stale silently; a test goes red.

`design` and `data_engineering` carry one posting each and `hardware` two, so
per-family accuracy on those is not a measurement. Asserted by name in
`test_two_families_are_too_thin_to_grade_on_their_own`, so a future table
printing `design 1.000` cannot be read as a result.

**14 of 60 seniority labels are `unclear`**, which means roughly a quarter of
the classifier's job is knowing when not to answer. That is the right shape for
this milestone and it also means a classifier that always says `unclear` scores
0.23 — visible, rather than hidden behind an average.

### The guard that worked on its first day

Adding two label fields turned `test_every_label_field_is_graded_or_named` red
immediately: both were in neither the graded list nor the named-and-excluded
one. That test was written four hours earlier, in Task 1, precisely because M3a
had five unmeasured fields and nothing anywhere said so. **This is the first
time in this project a new label field has been unable to arrive unmeasured.**

---

## M3b Task 3 — two `String` placeholders become real types, and a seed that lied

Migration `0013_role_family_and_seniority`. `RoleFamily` (11 values),
`Seniority` (8), and `EligibilityState` (5).

**`EligibilityState` is deliberately not a PostgreSQL enum**, unlike everything
else in `db/base.py`. M3b computes a verdict on read and stores none, so there
is no column to attach a type to until `match_results` arrives at M3c. Creating
a database type with no column is shape with no use — the same reasoning that
left `user_skills.confidence` out at M2c.

**Both columns were empty, and that was checked rather than assumed**: no writer
anywhere in `nightshift/`, `scripts/` or the web app, and `count(role_family),
count(seniority)` returned `0, 0` against a freshly seeded database holding 31
jobs. So the conversion could not lose a value.

`null` still means "not yet classified" and stays distinct from `unclear`, which
is the classifier having read a posting and declined to guess. Merged, an unrun
classifier and a corpus of ambiguous titles would look identical.

### Autogenerate got three things wrong, and this project had recorded all three

```
alter_column does not create the enum type   -> `type "role_family" does not exist`
VARCHAR to enum needs an explicit USING       -> postgres will not cast implicitly
the downgrade emitted no DROP TYPE            -> next upgrade: "type already exists"
```

The first and third are M2c's review findings 2 and 3, about `add_column` rather
than `alter_column`. **Knowing the pattern did not prevent it** — autogenerate
produced the same shape again and it was caught by running the migration, not by
remembering.

A fourth, new: `alembic_version.version_num` is `varchar(32)` and the generated
revision id was 36 characters. The migration applied and then failed writing
down that it had.

Verified: up, down one, up; and a full down-to-base and back. `make drift`
reports no drift. `make acceptance` passes with the drift step in it.

### The vocabulary now exists in three places, so it is asserted equal in all three

The enums in `db/base.py`, `ROLE_FAMILY_VALUES` / `SENIORITY_VALUES` beside the
labels, and the migration's own tuples. **The migration's copy is unavoidable**
— a migration that imports a model stops describing the schema as of its own
revision and starts describing today's — so an assertion is the only defence
available. Shown able to fail by misspelling `hardware` in the migration.

### The seed reported success over an empty database

The eighth time in this project something that reported success was wrong, and
the first where the reporter was `make seed` itself.

The model change landed before its migration. Every INSERT failed with `type
"role_family" does not exist`. `ingest_boards` counted all 31 postings into
`stats.failed` — **which is correct**, I3 says one bad posting may not kill a
board — and the command printed `seed complete` and exited `0`.

```
  greenhouse fixture ingest: 0 created, 0 updated, 0 unchanged, 10 failed (succeeded)
  lever fixture ingest:      0 created, 0 updated, 0 unchanged,  9 failed (succeeded)
  ashby fixture ingest:      0 created, 0 updated, 0 unchanged, 12 failed (succeeded)
    canonical jobs      0 (0 open)
seed complete. `make dev` then open http://localhost:3000     <- exit 0
```

**The counts were on screen the whole time, and that is not enough.** CI's "Seed
loads" step reads the exit code and nothing else, so a completely broken seed
was a green check. `make demo` would have handed a developer an empty city under
a success message. `make acceptance` *would* have caught it — `verify.py`
indexes `jobs["items"][0]` and would have raised — but the CI seed step has no
such backstop and it is the one that runs on every push.

The guard is "ended with zero jobs", not "any posting failed". The fixtures are
committed and deterministic so any failure is a defect, but failing the whole
seed over one bad posting would make the command brittle in exactly the way
`ingest_boards` refuses to be.

**Demonstrated failing twice, from two unrelated causes** — the missing enum
type, and orphaned `source_job_records` left by a careless `truncate`, which the
seed refuses on the M1 acceptance criterion. Both now exit 1; a healthy seed
still exits 0 with 31 jobs.

### Two plan corrections, recorded rather than absorbed

1. **`internship_season` moved from Task 3 to Task 11.** The plan put the column
   here. It does not belong here: nothing in the answer key labels a season, so
   populating it in Task 3 would add a field graded by nothing — the exact
   condition Task 1 built a guard against, four hours earlier. It lands with the
   filter that uses it, where the two can be checked together. Its shape is also
   undecided: one `summer_2027` string, or a term enum plus a year, and the
   corpus (4 of 5 internships state a season in the title) should decide.
2. **Enum parity moved from Task 3 to Task 9.** The parity test compares Python
   enums against `z.enum` copies in `schemas.ts`, and nothing serves these
   values to a browser yet. Writing the TypeScript now would be shape with no
   use, and the drift it guards happens at the moment of transcription — which
   is Task 9.

---

## M3b Task 4 — the classifier, and the number that matters more than accuracy

```
role_family      0.950     57 right,  3 wrong
seniority        0.967     58 right,  2 wrong
is_internship    0.933     56 right,  4 wrong
```

Floors in CI at **0.94 / 0.96 / 0.93**, set after measuring.

### One rule changed after the first measurement, and it is recorded on its own

```
role_family   0.933 -> 0.950   the role type beats the domain in a title
```

OpenAI's *Senior Technical Program Manager - Security* names a job and a subject
area. The job is program management; security is what it is *about*. Graded with
the domain families first it came out `security`, which describes the team
rather than the work — and it was **the only family error in the corpus that was
not a safe `unclear`**. Explicit management phrases now sit above every domain
rule.

### Three orderings are load-bearing and every one comes from a real posting

- **`not_tech` is tested first.** *AI Compliance Officer* contains AI, *Capital
  Markets - Infrastructure Financing* contains Infrastructure, *Cloud Partner
  Enablement Lead* contains Cloud, *People Research Scientist, Recruiting*
  contains Research Scientist. Four business roles wearing a technical word; a
  tech-first order files all four wrongly.
- **New-grad beats junior.** *Associate Product Manager, New Grad (2027 Start)*.
- **A years figure ≥ 6 beats an early-career title word.** Jane Street's *Campus
  Recruiter, Early Careers Partnerships & Initiatives* says early career three
  times and asks for six years. A title-only classifier ranks it into a new
  graduate's list.

**The description may only veto towards `not_tech`, never promote into a tech
family.** Every description in this corpus talks about technology, most at
length, so a promoting rule would promote nearly all of them. The one phrase
that decides on its own is Anthropic's own first sentence about the Applied AI
Architect role: *"you will be a Pre-Sales architect"*.

### The assertion that matters more than the floor

`test_every_role_family_error_is_a_refusal_rather_than_a_wrong_answer`. All
three remaining family errors say `unclear` — the classifier declining to make a
claim, which is the same instinct A13 demands of the gate.

**A floor cannot tell a confident error from a refusal, and those are not the
same mistake.** A future rule that buys accuracy by guessing fails this test
before it fails the floor.

### Two misses are inherited, and that was checked rather than assumed

*Data Center Architect, CSA* is labeled `senior` on 10 years and the classifier
says `unclear`, because the reading returns `None`. The posting writes:

```
Required 10+ years delivering mission-critical facility infrastructure
```

`_years_of_experience` needs the word "experience" within 40 characters of the
figure, and it is not there. **The classifier's error is the extractor's**, and
it is one of the two `read None for 10` confusions Task 1 already printed. Task
5's to fix.

### The methodological caveat, in the module rather than in a review

The seniority precedence and its two thresholds (3 and 6 years) were chosen with
these 60 titles visible. That is **weaker independence than M3a had** — there
the key was labeled by reading descriptions and the rules were about headings
and vocabulary, a different surface. Here labels and rules came off the same
titles, hours apart.

Some rules are not fitted in any meaningful sense: "Director in the title means
director" is what anybody would write. The thresholds and the ordering are.
**So these numbers are an upper bound, not an estimate of behaviour on an unseen
posting.** The corpus carries 93 recorded-but-unlabeled postings and they are
exactly the held-out check this wants. **Not done, and named here rather than
left to be noticed.**

---

## M3b Task 5 — four repairs, each measured on its own

```
Task 1 baseline                          degree 0.567   enrollment 0.317
+ curly apostrophe in the degree words   degree 0.700
+ "or an equivalent" broadened           degree 0.733
+ "minimum education" heading harvested  degree 0.850
+ enrollment stops requiring "currently"                enrollment 0.483
```

**The technology numbers are unchanged at 0.847 / 0.861 / 0.915**, checked
rather than assumed — adding a required heading is exactly the kind of change
that could have moved M3a.1's figures.

### The apostrophe: M3a.1's en-dash finding, in a different rule

Akuna, Anthropic and IMC type the **curly** apostrophe in "Bachelor's degree",
because that is what a rich-text editor produces. The pattern accepted only
ASCII `'` and matched none of it. **21 of the 26 degree errors were postings
whose degree sentence the extractor could not see at all.**

Two of those came out `phd` against a labeled `bachelors`:

```
Requirements for this role: Pursuing a bachelor's, master's, or Ph.D.
```

`Ph.D` is the one spelling in that list with no apostrophe in it, so it was the
only proposal and won by default. **A posting explicitly open to a bachelor's
graduate read as a doctorate requirement** — the direction A13 ranks worst, and
it was one migration away from being a wrong `ineligible`.

Normalising the text to ASCII first would also have worked and was rejected:
every proposal carries character offsets into `jobs.description_text`, and
rewriting the string those offsets point at is how a span comes to quote
something the posting never said. U+2019 happens to be one character wide so the
offsets would have survived — but the rule is not "when the replacement is the
same width", and the next such fix would not be.

### Both new phrasings were harvested, not invented

- **`minimum education`** occurs in exactly **15** postings — every Anthropic
  posting in the corpus, which appends a `Logistics / Minimum education: ... /
  Required field of study: ...` block to all of them. It is the last heading
  before the degree sentence, so without it a posting whose own words are
  *"Minimum education: Bachelor's degree"* was read as requiring **no degree**.
- **`or an equivalent`** — A13's escape hatch. `or\s+(?:an?\s+)?equivalent`
  matches 23 of 60 against the narrow form's 8. Missing one is the dangerous
  direction: it turns "or an equivalent combination of education, training,
  and/or experience" into a hard degree requirement.
- **The enrollment rule required the word "currently"**, and 10 of the 11
  postings labeled `enrollment_required: yes` do not use it. They write
  *"Pursuing a bachelor's, master's, or Ph.D."* and *"Current university
  student graduating between..."*. The replacement is anchored to a degree word,
  because "pursuing excellence" is ordinary prose — the same prove-itself
  discipline `_looks_like_a_heading` already applies to headings.

### One metric was redefined rather than one rule tuned, and no label was edited

**`enrollment_required`'s `no` and `not_stated` are not separable from the
postings.** Among the 47 non-internship postings, 30 are labeled `no` and 17
`not_stated`, and reading the descriptions the split is not driven by anything
they say — a few `no` labels carry a note pointing at real text, most do not. To
a person both mean the same thing: you do not have to be a student to apply.

So the three-way figure measures a distinction that does not exist, and it would
keep looking broken however good the rules got.

```
enrollment, as the gate asks it   0.983    59 right, 1 wrong
enrollment, three-way             0.483    still printed, not gated
```

**No label was edited.** Rewriting 30 labels to lift a metric is exactly the
move `matching.md` §1.1 forbids, and "with a recorded reason" would not make it
a different move. The metric is redefined on the distinction that changes a
verdict — the gate asks "must this person be enrolled", and a posting that is
silent and a posting that says no produce the identical answer — and the
three-way figure stays printed beside it so the change is visible rather than a
quiet improvement.

**This is the only floor in that file so far**, at 0.90. The other five stay
reported and ungated until the repair pass is finished, because a floor set
mid-repair is a floor that has to be edited again next week.

### What is still wrong, and what it is waiting on

```
degree 0.850            9 left: 2 read `none` for `bachelors+equivalent`,
                        2 read `bachelors+equivalent` for `none`
graduation_window 0.917 all 5 are the `through-YYYY` form, which needs the
                        words around the year and so needs the extractor
min_years 0.883         "Required 10+ years delivering ..." — the rule needs
                        the word "experience" within 40 characters and it is
                        not there
sponsorship 0.917       2 of the 5 are the deliberate `offered` tie-break
```

---

## M3b Tasks 6 and 7 — the gate, and the two blockers it was caught inventing

`domain/eligibility.py`. Pure, no ORM, reads no description. It takes a
`PostingReading` and a `SeekerProfile` and returns a state, its blockers, its
unknowns and its version. **Nothing is stored** — `match_results` is M3c's, and
a stored verdict goes stale the moment somebody edits their graduation year.

```
any blocks       -> ineligible
else any soft    -> likely_ineligible
else any cannot  -> uncertain
else                eligible
```

`blocks` needs **two explicit halves at once**: the posting states it under a
required heading, *and* the person's confirmed profile contradicts it. Either
half missing is `cannot_tell`. That is I2 doing the work — an inferred fact
never blocks anybody, because an inferred fact is not a fact.

**There is no branch producing `likely_eligible`, and that is stated rather than
left to be noticed.** It would mean "every rule passed, but one leaned on
something uncertain", and no rule here passes on an uncertain input — each
returns `cannot_tell` instead. A fifth state no rule can reach would be shape
with no use. The enum keeps the member because PRODUCT-SPEC §8.3 names it and
M3c's score components may earn it.

### Three rules whose reasons matter more than their code

- **A years shortfall may never hard-block.** "5+ years" is a wish far more
  often than a rule, and A13's first hard case is an employer writing "Intern"
  and "3+ years required" in the same document. It reaches `likely_ineligible`
  and stops. The person sees the role, sees the gap, and decides.
- **Enrollment may hard-block**, because it is categorical and checkable rather
  than a matter of degree.
- **Authorization blocks in exactly one configuration** — the posting says in
  writing that it does not sponsor **and** the person has said they need it.
  `unspecified` is the column default and most users' day-one value; reading it
  as "needs sponsorship" would silently block them out of every such posting
  before they had typed anything. `f1_student` is likewise not `needs_sponsorship`
  — an F-1 on OPT does not need sponsorship today, and inferring one from the
  other is the fabrication I2 forbids in the field where being wrong costs most.

**Blockers and unknowns are separate types** because they mean opposite things
to a person. A blocker says "this is probably not for you". An unknown says
"tell us one more thing and we can answer" — and names the profile field that
would settle it, because "complete your profile" is not an action and "tell us
your graduation year" is.

### The wrong-ineligible check found two real blockers on its first run

Zero, as an equality, over **60 postings × 5 profiles**. The checker is written
from the answer key and **never calls the gate** — a checker that called the
gate would agree with it by construction and assert nothing, which is precisely
how M3a's `test_no_nice_to_have_is_ever_reported_as_required` sat at zero for a
whole milestone.

**1. "Must be graduating August 2027 or prior"** was read as the single year
2027, so the gate blocked a 2024 graduate from a role whose own words say they
qualify. **Task 5 had recorded this exact form as a 5-label accuracy gap and
deferred it.** It was not an accuracy gap. The gate is what turned five labels
into a person being told they cannot apply. `_is_open_ended` now reads the words
on either side of the year; `graduation_window` went **0.917 → 1.000**.

**2. "MS Office" was read as a master's degree** on IMC's *Administrative
Assistant* posting, which the answer key labels `degree: none` — hard-blocking a
bachelor's graduate. Bare two-letter abbreviations now need two things at once:

- **case-sensitivity**, because `\bms\b` under `re.I` matches the milliseconds
  in "5 ms in latency" and these boards are trading firms. The same call
  `skills.yaml` already makes for `Go`, `Rust`, `React` and `Outlook`.
- **a following degree context** — a slash, "in", "or", "degree", or a comma
  *only when another abbreviation follows*. "BS, MS preferably in business" is
  IMC's; "MS, Word, Excel" is what the constraint keeps out.

**That second fix left accuracy at 0.850, then 0.867 — and that is the finding.**
It removed no error on paper and removed a hard block on a real person.
**Accuracy could not tell the difference between a false positive that costs
precision and one that costs somebody a job.** It is the clearest argument in
this milestone for why the wrong-ineligible equality exists beside the floors
rather than instead of them.

### The mutation test was wrong on its first write, and is recorded as such

It strips A13's equivalence hatch and re-runs. The first version used a
bachelor's holder — who clears a `bachelors+equivalent` bar whether the hatch is
honoured or not — so the break produced **zero** violations and the test failed
for its own reason rather than the gate's. The profile the hatch is addressed to
is the one with **no degree at all**, and that person is now in the profile set.

### The distribution, printed rather than assumed

```
a 2027 undergraduate, enrolled, needing sponsorship   eligible 27  ineligible 2   likely_inel 20  uncertain 11
a 2024 graduate with two years and a green card       eligible 22  ineligible 11  likely_inel 15  uncertain 12
a PhD with eight years, a citizen                     eligible 29  ineligible 11  likely_inel 5   uncertain 15
a self-taught engineer with no degree and four years  eligible 16  ineligible 21  likely_inel 9   uncertain 14
somebody who has filled in nothing                    eligible 13  ineligible 0                   uncertain 47
```

**The last row is the one to read.** A person who has filled in nothing gets
**zero** ineligibles and 47 uncertains — the state every user is in on day one.
`test_the_corpus_actually_exercises_the_gate` guards the opposite failure: a
gate answering `uncertain` to everything would satisfy every other assertion in
that file, has perfect precision, and is worthless (`matching.md` §3.3).

---

## M3b Task 8 — every gate rule shown able to fail, in the suite

**All five rules are load-bearing.** Replacing any one with an unconditional
`passes` changes the verdict of a case taken from `test_eligibility_gate.py`.

`matching.md` §8 asked for this on the gate specifically, and gave the reason:
three tests in this project have turned out unable to fail, and the gate is
where that would cost most.

**It runs as a test rather than as an exercise a human did once and wrote down.**
A mutation result in a review is true on the day it was written. A mutation
result in the suite is true every time the suite runs.

Two guards on the harness itself, because a mutation harness that mutates
nothing is the most confident kind of vacuous test:

- `test_every_rule_in_the_gate_has_a_case_here` fails when a rule is added
  without a mutation case — the same shape as
  `test_every_label_field_is_graded_or_named` one layer down, and the same
  failure mode it prevents: a check that looks complete because nothing counts
  what it is missing.
- `test_the_harness_itself_is_not_vacuous` neuters all five at once and asserts
  the all-passing outcome.

**That second risk is real and was measured rather than supposed.** `_RULES`
holds function references captured at import, so `monkeypatch.setattr(
eligibility, "_degree_rule", ...)` leaves the tuple pointing at the original.
Run directly: the verdict stayed `ineligible` under that patch. The harness
rebuilds the tuple instead, and the comment saying so was written after
checking rather than before.

---

## M3b Tasks 9 and 10 — the verdict reaches the browser

`GET /jobs/{id}` returns the state, every blocker with the posting's own words
and offsets, and every unknown with the profile field that would resolve it.
**Computed on read, stored nowhere.** Null when the posting has no extracted
requirements at all — a verdict from an unread posting would say `eligible` to
everyone and be indistinguishable on the page from a posting that genuinely
asks for nothing.

### The gate asked five questions and `users` could answer three

`years_experience` and `is_enrolled` did not exist. Without them two of the five
rules return `cannot_tell` for every real person forever, **and the page would
have printed "tell us your years of experience" beside a profile with nowhere to
say it** — a dead end, which is M2c's finding about a provenance link that 404s,
one milestone on.

Both nullable: "has not told us" must stay distinct from `0` and from `false`.
Neither is ever inferred — `graduation_year` is already stored and one
subtraction would produce a plausible number for both, which is the I2 violation
easiest to write and hardest to spot in review.

### The I2 guard had silently stopped covering what it guards

`PROFILE_COLUMNS` in `test_nothing_infers.py` is the list of columns only
`domain/profile.py` may write. **It is hand-maintained, and neither new column
was in it.** The guard would have gone on passing.

**That is the fourth time in this project a list has quietly stopped describing
the thing it names**, and always in the same direction — things get added and the
list does not. The other three were "not built yet" lists, where the cost was a
stale sentence on a page. This one was an invariant.

The list is now checked against `User.__table__`: every column must be
classified deliberately as a profile fact or as not one, and neither choice can
be made by forgetting. Shown able to fail by removing `is_enrolled` and watching
it name the column.

### `_degree_of` reads free text, whole words only

`users.degree` is what a person typed. A substring test for `bs` matches
**jobs** and `ba` matches **database** — the defect that made `react` a required
technology on eight postings at M3a.1. Anything unrecognised returns `None`,
which reaches `cannot_tell` and asks the person, rather than inventing a level
low enough to block them or high enough to pass them.

### Three enums crossed the boundary and all three were right

`RoleFamily`, `Seniority`, `EligibilityState`, added to `test_enum_parity.py`.
Two of the last four milestones found a hand-transcription defect there, so this
is recorded as the outcome rather than assumed. **The guard was shown able to
fail** by typoing `quant_trading` in the TypeScript and watching exactly that
parameter go red — a guard that passes is otherwise indistinguishable from a
guard that is not looking.

`EligibilityState` is not a database enum and is guarded anyway: that test is
about a vocabulary crossing the boundary, not about where it is persisted.

### The page, and the sentence that matters most on it

Never hidden, and it never hides a job. A blocker is a wall; an unknown is a
question with somewhere to go and links to `/operate/profile`, which was checked
to exist. `blocks` and `soft_blocks` get different headings, because the gate
never lets a years shortfall produce an `ineligible` and the page must not imply
otherwise.

Under `ineligible` the page says: the rules misread postings, the quote is right
there, and **if it does not say what we claim then we are wrong and you should
apply anyway.** A verdict that sounds like a decision somebody made is a verdict
nobody argues with. It has its own test.

No state is rendered as its enum value — `likely_ineligible` is jargon on the
one verdict a person least wants to read. Checked for all five.

### A stale claim removed, and a test is what found it

**"Eligibility" was still in the job page's "Not yet computed" list**, about to
sit directly beside a section computing it. It surfaced only because the new
section put that word on the page twice and an existing test could no longer
tell the two apart. Three times before this, the same kind of list went stale
for a whole milestone with nothing catching it.

### What has not been verified, stated rather than implied

Docker Desktop hung during Task 9 and has not recovered. So:

```
verified   1047 non-database Python tests, 169 web tests, ruff, mypy,
           eslint, tsc, prettier; migration 0014 up/down/up + clean drift
           probe, run before the daemon died
NOT run    every database-backed Python test since Task 8
NOT run    make acceptance, make verify, the seeded browser suite
NOT written the eligibility browser walk — Task 12's, and it needs a stack
```

CI provisions its own postgres and is the standing check for the first gap.
It cannot stand in for the browser walk.

---

### After M3b Task 10: the rest of the M3b plan.

**PR #9 is merged.** `main` is at `452ec90`, checked against the PR rather than
assumed. CI was green on all five jobs at `3fbffd6`, run
[31039059510](https://github.com/Tahmudun/Nightshift/actions/runs/31039059510) —
counts read from the job logs rather than inferred:

```
python       5m11s   1282 passed
e2e          2m50s   41 seeded passed, 1 skipped
migrations   1m17s   up, down, up, and no drift
web            59s   159 tests
secret scan      7s
```

The pre-merge invariant held: `git diff 3fbffd6..HEAD --stat` listed docs only.
**That branch took three CI runs, and only the first found anything** — the
check-constraint defect below. The second and third were green first time.

**All four stale merged branches are deleted, locally and on the remote.**
`m1a-provider-breadth`, `m2c-profile-and-resume`, `m2d-daily-queue` and
`m3a-answer-key` are gone, and `ci-pin-and-canary` followed once PR #10 merged;
`git branch -a` now lists only `main` and `m3b-eligibility-gate`, checked after
a `--prune` rather than assumed. This had been carried as an open item since M2c, in four
consecutive PROGRESS entries, because the permission was not available.

**[PR #10](https://github.com/Tahmudun/Nightshift/pull/10) is MERGED** —
`0c5bcbd` on `main`, 2026-08-05T22:37Z, checked against the PR rather than
assumed. CI was green on all five jobs, first attempt, run
[31045860049](https://github.com/Tahmudun/Nightshift/actions/runs/31045860049).
Counts read from the job logs rather than inferred:

```
python       299s   1282 passed; 72 distributions, all pinned
e2e          189s   5 degraded + 41 seeded passed, 1 skipped
migrations    74s   up, down, up, and no drift
web           69s   18 files, 159 tests
secret scan    5s
```

**The step that matters is `The pin covers everything that got installed`, and
it passed in the real runner** — the constraints file resolved to exactly the 72
lines it names, on a machine that is not this one. Seven CI runs across this
project have failed and every one found something no local command had executed;
this is the fifth first-try pass, recorded because it is not the usual outcome.

`headSha` is `cef574a`, which is also the branch head, so the pre-merge
invariant is satisfied by inspection rather than by a diff.

---

## Q4 answered: CI pins what gates a merge, and a canary watches what does not

**The human's decision on 2026-08-05, on the recommendation in the question:
both.** Full reasoning, and the four alternatives rejected, in **ADR 0016**.

Reproducibility and early warning only conflict if there is one place to
install. There are now two:

| | Installs | Runs on | Can block a merge |
|---|---|---|---|
| `ci.yml` | pinned, from `services/api/constraints-ci.txt` | `pull_request`, `push` to main | yes |
| `dependency-canary.yml` | unpinned | `schedule` weekly, `workflow_dispatch` | **no** |

72 distributions are pinned, wired in as **one** workflow-level `PIP_CONSTRAINT`
rather than a flag on three install steps that could drift apart.

**The pin is checked rather than assumed.** `-c` constrains only the
distributions the file names, so a dependency added to `pyproject.toml` and never
regenerated would install unpinned with nothing anywhere saying so — the pin
becomes partial while everything keeps calling it a pin, which is this project's
recurring failure class exactly. The `python` job diffs `pip freeze` against the
file and fails on a difference in either direction.

**The constraints file cannot be generated on this machine, and that was
measured rather than assumed.** `make constraints` resolves inside a
`linux/amd64` container. The two platforms disagree about eleven distributions
and one irreconcilably:

```
onnxruntime   1.28.0   resolved on linux/amd64, what CI installs
              1.23.2   the newest release with a macOS x86_64 wheel
```

So **the pin covers CI and does not cover a developer's machine**. That is a
smaller copy of the original problem, left standing on purpose and written into
the file's own header rather than discovered later.

**What this gives up:** the alembic finding arrived free, the day it shipped.
The same finding would now arrive up to seven days later, from the canary. That
is the price of an unrelated pull request never going red at a moment nobody
chose, and it is paid deliberately. The canary writes a diff of unpinned-versus-
pinned to its job summary on every run, green or red; notification is GitHub's
own email to the repo owner on a failed scheduled run.

### `make drift` — the gap this episode exposed, now closed

The drift probe existed only in CI, so "it passes locally" and "it passes in CI"
were never the same claim about the schema. That is how a defect eleven
migrations old sat unseen. `make drift` runs the probe against the developer's
own stack and is part of `make acceptance` — **not** of `make check`, which must
keep working without a database.

**Shown able to fail rather than assumed to work.** Adding a `mutation_probe`
column to the `Company` model makes it print both operations and exit 1:

```
==> the models have drifted from the migrations:
    op.add_column("companies", sa.Column("mutation_probe", sa.String(length=10), nullable=True))
    op.drop_column("companies", "mutation_probe")
```

The temporary revision file is cleaned up on the failure path too, checked with
`git status` after — a probe that leaves a migration behind when it fails is a
probe that gets committed by accident.

**What is still floating, named so nobody reads the pin as broader than it is:**
pip itself, the `ubuntu-latest` runner image, `setup-python`'s 3.12.x patch, and
the Postgres service tag. Node was already locked by `package-lock.json`, which
is why the canary is Python-only.

---

## CI's first run on this branch, and the defect it found

**The migrations job failed on the first run — the seventh CI failure in this
project, and the seventh to find something no local command had executed.**

The drift probe emitted forty operations. The cause was older than the branch:
`NAMING_CONVENTION` in `nightshift/db/base.py` renders
`ck_%(table_name)s_%(constraint_name)s`, five migrations wrote the *rendered*
name into `name=` rather than the bare one, and `op.create_table` applies the
convention to whatever it is given. **The database has carried
`ck_jobs_ck_jobs_closed_at_matches_status` since 2026-07-29** while the models
called it `ck_jobs_closed_at_matches_status`. Ten constraints, across `users`,
`jobs`, `job_locations`, `job_source_links` and `ingestion_runs`.

**The constraints were never wrong, only misnamed**, which is exactly why no
behavioural test noticed — each enforces what it was written to enforce. Two of
the ten were long enough that the doubled prefix pushed them past PostgreSQL's
63-character limit and SQLAlchemy truncated them with a hash suffix
(`ck_job_locations_ck_job_locations_confidence_matches_co_b8be`), so nobody
could predict those names at all.

**Why it surfaced on 2026-08-05 and not before, measured in both directions:**

```
alembic 1.18.5   0 autogenerate operations     <- the developer venv
alembic 1.19.0   40 autogenerate operations    <- what CI installed that day
```

Alembic did not compare check constraints during autogenerate until 1.19.0. CI
runs `pip install -e "services/api[dev]"` unpinned and picked the release up the
day it shipped. **No local command could have found this**, and that is the
finding worth keeping: `make check` never ran a drift probe at all, so local
evidence and CI evidence were never the same claim.

Fixed by migration `0012_check_constraint_names`, which renames all ten and
reverses cleanly. `tests/test_check_constraint_names.py` is the guard that does
**not** depend on an alembic version — it reads `pg_constraint` and
`Base.metadata` directly. Both its assertions fail before the migration and pass
after. The local venv is now on 1.19.0 so `make check` means what CI means.

**A third assertion was written and deleted rather than kept green.** It flagged
constraint names at the 63-character limit; the truncated names are 60, so it
could not have caught this defect and guarded nothing the first test does not.

### Both of the things this section left open are now done

It read: *"`pip install -e` stays unpinned"* and *"a `make` target that runs the
drift probe locally does not exist and should"*. Both were closed on
`ci-pin-and-canary` — see the Q4 section above and ADR 0016. Left here rather
than deleted, because the entry above is the reason the decision came out the
way it did: pinning is only defensible alongside something still unpinned.

---

## M3a.1 — COMPLETE. What moved, and what was measurement rather than progress

**Recall 0.459 → 0.861. Precision 0.659 → 0.847. Necessity 0.668 → 0.915.
Nice-to-haves reported as required: still 0, and now a stronger claim than it
was.**

Floors in CI are now **0.84 / 0.86 / 0.91**, set after measuring and just under
what the extractor achieves.

### The first change was not an improvement, and is recorded as such

**The grader compared raw strings.** A posting the human labeled `GCP` scored as
a miss *and* a false positive against an extractor that had correctly found it
and emitted the vocabulary's canonical `Google Cloud`. Same technology,
penalised twice. The same defect covered `python`/`Python`, `Pytorch`/`PyTorch`,
`Golang`/`Go`, `Microsoft Azure`/`Azure`.

That this was a defect rather than a decision is visible inside the one file:
the necessity-accuracy loop already casefolded both sides while `score_sets` did
not, so two metrics over the same labels disagreed about whether `python` and
`Python` are the same word.

Both sides now resolve through the same vocabulary, and **only a match spanning
the whole term counts**. A substring rule would have resolved the label
`Entra ID/Azure AD` to `Azure` — it contains the word — merging Microsoft's
identity product into its cloud platform. Measured: the substring rule collapses
two distinct labels into one on `akunacapital/8047104`; the whole-term rule
collapses none.

```
before, raw strings         precision 0.659  recall 0.459  necessity 0.668
after, both canonicalised   precision 0.706  recall 0.492  necessity 0.683
```

**No extraction rule changed between those two lines.** The human's decision on
2026-08-05 was to fix it, re-baseline, and keep the old numbers on record so
nobody reads the jump as the extractor improving.

### It also un-hid a real violation that had never been at zero

`test_no_nice_to_have_is_ever_reported_as_required` reported **0 violations**
before this change and **1** immediately after: Databricks 8290810002, where the
human labeled `Apache Spark` a nice-to-have and the extractor called canonical
`Spark` required. The raw-string comparison could not see it because the strings
differ. **The assertion with no floor had never actually been at zero** — it was
at zero the way a test that cannot fail is at zero.

Chasing it found the deeper defect. The "heading" governing that sentence was
the bare word *requirements* occurring in prose — "requirements, when we ingest
terabytes per second across 100…" — because `_REQUIRED_HEADINGS` matched
anywhere in the text.

### The rule that fixed it already existed, one directory away

`scripts/make_label_worksheet.py` has demanded since its first real run that an
ambiguous heading **prove itself** — a colon follows, it is capitalised, or it
opens a sentence — after *30 of 60* worksheet excerpts anchored inside ordinary
prose. **The extractor was graded against an answer key built with that rule
while using a looser one itself.** Now ported, with the same ambiguous list.

One correction the port needed, found by measuring rather than supposing:
Databricks writes `[Preferred] Experience using ... Apache Spark`, and with
brackets absent from the sentence-opener set that heading failed its own proof,
the preferred block never opened, and Apache Spark was reported required on two
*more* postings. `[` and `(` were added to both files, which stay identical on
purpose.

### Each step measured on its own, so the movement is attributable

```
canonicalised comparison (measurement)   0.706 / 0.492 / 0.683
+ headings must prove themselves         0.700 / 0.516 / 0.693
+ a bracketed heading is a heading       0.716 / 0.516 / 0.704
+ skills.yaml gains 33 terms             0.800 / 0.820 / 0.889
+ VPNs, firewalls, Entra ID aliases      0.805 / 0.844 / 0.905
+ "candidates must be" heading           0.784 / 0.861 / 0.915
+ React and Outlook case-sensitive       0.847 / 0.861 / 0.915
```

**The sixth line cost precision** and was kept anyway, because the two postings
behind it say "Candidates must be: Fluent in Python programming" — the extractor
was getting a plain statement wrong. The seventh line then returned the
precision and more, from a defect the sixth made visible.

### Two ordinary English words were required technologies

Found by grading, not by reading:

- **`react`** — "the ability to react quickly and accurately to rapidly changing
  market conditions" is a line in four Akuna trading postings, and bare `react`
  made the JavaScript library a **required** technology on eight postings that
  never mention it.
- **`outlook`** — "eager to solve challenging problems with a pragmatic outlook"
  made the mail client required on two Jump research postings. This one was
  self-inflicted, added earlier in the same session.

Both are now `case_sensitive: true`, which is the rule `skills.yaml` already
documented for `Go` and `Rust` and which nobody had applied to these.

### The heading was harvested, not invented

Per the lesson Task 7 paid for. A harvest of heading-shaped phrases across the
60 labeled postings found `candidates must be` in exactly the 2 postings whose
`Python` was missing. The same harvest is what kept the other candidates out —
`the impact you will have`, `your core responsibilities` and `visa sponsorship`
are heading-shaped and are not requirements headings.

### What is still missed, and why it is a decision rather than a gap

17 of 122 labeled required technologies. Every one is a term `data/skills.yaml`
deliberately does not carry:

```
ACI 318, ASCE 7, IBC, IFC, AISC, FM Global     structural engineering codes
Kyriba, GTreasury, Trovata, TMS, Quantum       treasury management systems
US GAAP, IFRS                                  accounting standards
MS Office, Word                                too ambiguous to match safely
Excel, Google Sheets (1 posting)               a necessity call, not a miss
```

**The vocabulary is what the product knows, and it is a NYC *tech* product.**
Building codes and accounting standards are real requirements of real postings
in the corpus and they are not software skills; adding them would raise recall
by teaching the product a domain it does not serve. `Word` and `MS Office` are
left out for the reason `skills.yaml` already leaves out bare `node` and bare
`rest` — the word is too ordinary to match without inventing requirements.

This is a cap on recall and it is stated rather than papered over.

### `skills.yaml` is shared with resume extraction, and that was checked

34 entries were added, so a resume can now propose `SIEM` or `CUDA` too — that is
intended. What was verified rather than assumed: the fixture resume produces
**16 proposals before and 16 after, identical but for the vocabulary version**.
The additions introduce zero spurious resume proposals.

### `EXTRACTOR_VERSION` moved to `m3a.2`, and stored rows lag

The rules changed, so the stamp changed. **Rows written by `m3a.1` keep that
value until their posting is re-seeded or its description moves** — the
description-change trigger cannot help, because the text is identical and only
the rules changed. `make seed` refreshes them, and `make acceptance` confirms
`m3a.2` on the seeded corpus.

`sync_requirements`'s docstring claimed "the backfill script calls it". **There
is no backfill script** — the ninth instance in this project of a claim that
went stale in the direction nobody re-reads. Corrected to say what is true.

### What must not happen

**Do not tune against the answer key by editing the answer key.** It was
committed before any extraction rule existed, and that ordering is the only
reason these numbers mean anything. If a label looks wrong, it is fixed with a
recorded reason in the review, never quietly. **No label was edited in M3a.1.**

**All twelve M3a tasks are done and committed.** The three commands were run
locally at the branch head and their counts are read from the output, not
inferred:

```
make check        1280 Python, 159 web, ruff/mypy/eslint/tsc clean
make acceptance   57 verify checks + 41 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests        <- the third command, run separately
alembic           down, up, no drift; both triggers present after the cycle
```

**`make acceptance` was run three times back to back and passed all three**,
which is the idempotency evidence rather than a hope about it. The single e2e
skip is the pre-existing honest one: `an unchanged board is not presented as a
problem` needs a board that has answered `304`.

**CI has not run on this branch.** Every previous milestone's PROGRESS entry at
this point carried a CI result; this one cannot. Six CI runs across this project
have failed and every one found something no local command had executed, so the
three green commands above are evidence about this machine and not yet evidence
about the branch. Pushing alone does not change that — see the top of this
section.

Once CI has run, the invariant this project learned twice applies before
merging — name the last commit CI executed, and check nothing outside `docs/`
follows it:

```
git diff <that-sha>..HEAD --stat    # must list nothing outside docs/
```

### What M3a is

The reading half of matching, and nothing else. A posting's requirements are
extracted by rules, stored with the characters they came from, and shown on the
job page quoting the posting's own words. **Nothing is compared against a person
yet** — no eligibility gate, no score, no `uncertain`.

| Task | Commit | What it did |
|---|---|---|
| 1 | `c577d56` | Fixture selectors by eligibility shape, not location |
| 2 | `6a9b7cf` | Nine boards recorded, 153 postings |
| 3 | `b297c36`¹ | The labeling worksheet — six fix rounds, each measured |
| 4 | `9929aa0` | The answer key's schema, loader, and the two gate tests |
| 4b | `0f10284` | The key filled: 60 postings × 9 fields, audited |
| 5 | `44a70e7`² | `job_requirements`, migration `0011`, both triggers |
| 6 | `3722026` | The extractor — every proposal carrying its span |
| 6b | `7eb3750` | `match_all`, which keeps repeated occurrences |
| 7 | `7134094` | Grading against the answer key, and the rules it demanded |
| 8 | `7c950d5` | `sync_requirements` — extraction follows the description |
| 9 | `7f52a8f` | `GET /jobs/{id}` returns requirements with their spans |
| 10 | `38d5e69` | The job page, the Zod refinement, the parity guard |
| 11 | `7cff577` | The fifth coverage blind spot |
| 12 | this | The browser walk, `verify.py`, ADR 0015, the review |

¹ Task 3 landed across five commits of fix rounds; `b297c36` is the last.
² Task 5's trigger fix landed separately in `aa0235b`.

### The measured numbers

**Extraction, graded against the 60-posting answer key.** The key was committed
*before* any extraction rule existed, so this measures the rules rather than the
choice of examples:

**These are M3a's numbers, kept as they were when M3a closed. M3a.1 superseded
them — see the section above for the current figures and for why part of the
movement was the meter being fixed rather than the extractor improving.**

```
required technology   precision 0.659   recall 0.459   (tp 56, fp 29, fn 66)
necessity accuracy    0.668             over 199 labeled technologies
nice-to-haves reported as required      0            <- see below; this was wrong
```

Floors in CI at M3a: 0.65 / 0.45 / 0.66. Set *after* measuring, just under what
the extractor achieves — a floor picked before measuring is either unreachable
or vacuous and there is no way to tell which from the outside.

**The last line of that block was not true**, and M3a.1 is what proved it. The
comparison was raw-string, so a nice-to-have labeled `Apache Spark` reported as
canonical `Spark` did not register as a violation. The honest M3a figure is 1,
not 0.

**The first measurement was 0.432 / 0.156 / 0.447**, with an imagined heading
list. Setting a floor under that would have enshrined a broken extractor. The
103 misses were split by cause first: 60 are terms `data/skills.yaml` does not
carry and no rule can reach; 43 the extractor found and filed under the wrong
necessity. Only the second kind is an extraction defect.

**The answer key holds 60 postings across seven boards:**

```
akunacapital 15   anthropic 15   databricks 10   imc 7
openai 8          jumptrading 3  janestreet 2
```

**What the corpus could not demonstrate**, from the union of the nine boards'
`coverage_not_available_on_this_board` lists — the number is how many of the
nine boards lack that shape:

```
multi-level posting spanning an eligibility boundary      8 of 9
sponsorship stated in writing                             4 of 9
new grad / university programme in the title              3 of 9
internship in the title                                   2 of 9
a preferred section whose contents are not gaps           2 of 9
senior or above in the title — the seniority mismatch     1 of 9
a graduation year stated numerically                      1 of 9
internship employmentType                                 1 of 9
```

The first line is the important one. **A posting spanning an eligibility
boundary is absent from eight of nine boards**, so the case A13 calls hardest —
a role open to both a new grad and a senior — is the one the answer key can say
least about. M3b must not read its grading as evidence there.

### The queue's own acceptance, measured

`check_job_requirements` in `make acceptance`, compared **before and after**
rather than against an absolute state:

```
✓ the job detail answers                          HTTP 200, 4 required, 5 preferred
✓ requirements carry an extractor version         m3a.1
✓ every span quotes the description it points at  9 spans
✓ no single span is both required and preferred   4 required, 5 preferred
✓ changing the description clears the old rows    9 -> 0
✓ a description change replaces the requirements  9 -> 1
✓ the job is left as it was found                 nothing is left behind
```

**Its first version passed with nothing on either side.** It picked the first
posting with any requirements; that posting's three rows were all `mentioned`,
so the necessity line read "0 required, 0 preferred" and ticked green. It now
prefers a posting that can fail the check and prints the mix either way, so a
vacuous case is visible in the output rather than hidden behind a passing line.

### What M3a found that the plan did not predict

Eleven in Tasks 8–12 and **eight were in code or tests that reported success** —
the ninth milestone running. Tasks 1–7's are in their commit messages. Full
detail in `docs/reviews/milestone-3a-review.md`; the four worth reading here:

1. **The plan credited the wrong guard, and measuring said so.** The plan said
   delete-then-insert is what keeps a span honest when a description changes.
   It is not — Task 5's `jobs_description_change_clears_requirements` trigger
   already does, and **removing the delete leaves every description-change test
   green**. The delete's real job is idempotency: a second sync over unchanged
   text re-emits the same `(kind, value, char_start)` tuples and the unique
   constraint rejects them. This matters beyond a docstring — a reader who
   believes the delete is the integrity guarantee will delete the trigger,
   because the trigger looks redundant. It is the other way round.
2. **An unconditional re-extract on the update path churns invisibly.**
   Identical row counts, every row replaced, `created_at` reset across the
   corpus each time any board answers. A salary edit changes fields and moves
   no character. Gated on the description hash; the guard compares row **ids**
   rather than counts, because counts are exactly what this failure preserves.
3. **A "not built" reason had gone stale, for the third milestone running.**
   The `skill` filter still blamed the absence of the skill taxonomy, which
   shipped at M2c. It is always the same direction: nobody re-reads that list
   when the thing it waits on lands. The filter stays deferred for a reason
   that is now measured — at 0.459 recall it would hide more than half the
   postings that ask for a skill and return them as an empty result, which
   reads as "no such job".

   **That reason is itself now stale, one milestone later, in the same
   direction.** M3a.1 took recall to 0.861, so "it would hide more than half"
   is no longer true. The `skill` filter's deferral needs re-deciding on the
   current number rather than inheriting this one — which is the fourth
   milestone running that this exact pattern has appeared, and the first time
   it has been caught in the same session that invalidated it.
4. **A component-test fixture was a cast, not a check.**
   `const BASE: JobDetail = {...}` asserts a shape without verifying one, so it
   went stale the instant this milestone added two fields and said nothing —
   the render crashed instead. Now parsed through `jobDetailSchema`. Second
   time this project has shipped that exact mistake.

### The mutation that should have failed and did not

Moving the delete after the empty-text guard in `sync_requirements` fails
**zero** tests. Chasing why is what produced finding 1 above. It is recorded
because a mutation that survives is the more useful result and the one easiest
to write off as "the mutation was not meaningful".

### Not real yet — M3a

- **Recall was 0.459 at M3a and is 0.861 after M3a.1.** The remaining 17 misses
  are all terms `data/skills.yaml` deliberately does not carry — building codes,
  treasury systems, accounting standards — and that cap is a decision recorded
  in the M3a.1 section above, not a gap waiting to be closed.
- **Necessity accuracy was 0.668 at M3a and is 0.915 after M3a.1.** It is not
  1.0, so some technologies are still filed under the wrong heading. **The job
  page makes this visible rather than hiding it**: measured on the seeded
  corpus at M3a, 2 of 32 rows shown as `required` sat beside a quoted sentence
  that itself says "preferred" or "a plus". A reader can see the disagreement
  because the sentence is printed next to the claim. That is the argument for
  showing the quote. **That 2-of-32 count was measured before M3a.1 and has not
  been re-measured since** — the numbers behind it moved and this line has not.
- **The answer key is model-labeled, not human-verified.** Two `+equivalent`
  calls read an escape hatch worded without the word "equivalent" — Akuna
  8035515's *"or evidence of mathematical and quantitative skill"* and OpenAI
  8fb1615c's *"or have a demonstrated track record"*. Both are kept, because
  `+equivalent` resolves to `uncertain` and the alternative tells a qualified
  person they are blocked. They are the two entries most likely to be wrong.
- **93 of the 153 recorded postings are committed and unlabeled.** Deliberate:
  the payloads are real and cheap to keep, and re-recording later costs a
  network round against nine live boards.
- ~~**`has_equivalence` is stored and read by nothing** but the tests and a badge
  on the job page.~~ **Stale as of M3b Task 6.** `_degree_rule` reads it, and it
  is the only thing in the gate that produces `cannot_assess`. Struck rather
  than deleted: this project has four times shipped a blind spot recorded in a
  line nobody re-read once the thing it waited on landed.
- **The `jobs_description_change_clears_requirements` trigger is guarded by
  exactly one test.** Dropping it turns exactly that one red. Thin for a
  structural guarantee, and recorded rather than padded — its whole purpose is
  the writer that does *not* call `sync_requirements`.
- ~~**Everything in `matching.md` §9 is M3b or later**: the eligibility gate, the
  score and its components, role-family and seniority classification, the
  project evidence graph, and the `uncertain` resolution. None is stubbed.~~
  **Partly stale as of M3b.** The gate, the classifier and the `+equivalent`
  resolution are built. The score and its components, the versioned weights and
  the project evidence graph are M3c, and are still not stubbed. See "Not real
  yet — M3b" below.

### The M3a plan

`docs/plans/2026-08-04-m3a-answer-key.md`. Two merged remote branches are still
there — `origin/m2c-profile-and-resume` and `origin/m1a-provider-breadth` — both
fully merged into `main` with nothing ahead. Deleting them needs a permission
this session did not have; it is one `git push origin --delete`.

---

### The M2d record, kept below

All seven tasks are done, committed, pushed, and CI-green. The three commands
were run locally at the branch head and their counts are read from the output,
not inferred:

```
make check        1136 Python, 144 web, ruff/mypy/eslint/tsc clean
make acceptance   50 verify checks + 37 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests        <- the third command, run separately
alembic check     no drift; 0010 up, down, up clean
```

**`make acceptance` was run three times back to back and passed all three**,
which is the idempotency evidence rather than a hope about it. The single e2e
skip is the pre-existing honest one: `an unchanged board is not presented as a
problem` needs a board that has answered `304`.

**CI is green, on the first attempt.** [PR #8](https://github.com/Tahmudun/Nightshift/pull/8),
run [30884388243](https://github.com/Tahmudun/Nightshift/actions/runs/30884388243)
— **all five jobs**, counts read from the job logs rather than inferred:

```
python       257s   1136 passed, zero skipped
e2e          187s   5 degraded + 37 seeded passed, 1 skipped
migrations    80s   up, down, up, and no drift
web           63s   17 files, 144 tests
secret scan   10s
```

`headSha` on the run is `c6e5a977225884c84cd69ea47adbbc24cf43108f`, checked
against the branch head rather than assumed. **1136 in CI matches 1136
locally**, so the database-backed tests really ran there too. No retries and no
flakes are recorded in the logs — worth checking explicitly, because the review
below marks a test `test.slow()` for parallel-load reasons and a silent retry
would have hidden whether that worked.

Six CI runs across this project have failed and every one found something no
local command had executed. This is the fourth first-try pass; it is recorded
precisely because it is not the usual outcome.

**`a6c4ead` is the last commit containing anything CI executes** — everything
after it touches `docs/` only, which is one command:

```
git diff a6c4ead..HEAD --stat    # must list nothing outside docs/
```

If that shows a file under `apps/`, `services/`, `infra/`, `data/` or the
Makefile, the recorded results do not cover the branch and the three commands
must run again.

**M2d earns none of M2's four acceptance criteria, and that is not a gap.** All
four were verified at M2a, M2b and M2c and are recorded below, unchanged. What
M2d completes is M2's *deliverable* list in `CLAUDE.md` §6, of which the daily
queue was the last item.

Seven tasks, branch `m2d-daily-queue`.

| Task | Commit | What it did |
|---|---|---|
| 1 | `9bef08a` | `domain/queue.py` — four queries, three thresholds, the `actor = 'user'` filter |
| 2 | `4ed6390` | Migration `0010`, two partial indexes, the first query-plan assertion |
| 3 | `02eeb39`¹ | `GET /queue`, the schemas, the four named absences |
| 4 | `a3d6b11` | Zod schemas, `fetchQueue`, and five enums added to the parity guard |
| 5 | `1f39435` | `QueuePanel`, `/operate/queue`, the Operate link |
| 6 | `02eeb39` | The browser walk and `check_daily_queue` |
| 7 | `a6c4ead` | ADR 0014, the review, the reworked plan assertion |

¹ Task 3's route landed in its own commit; `02eeb39` is Task 6's.

### The queue's own acceptance, measured

`check_daily_queue` in `make acceptance`, compared **before and after** rather
than against an absolute state — asserting "the queue is empty" would pass
vacuously on a fresh database and fail on a developer's own:

```
✓ the queue answers                              HTTP 200
✓ four sections, always                          follow_up, interviews_approaching, stale_saved, closed_while_saved
✓ four deferred rows, each with a reason         4
✓ no deferred row carries a number
✓ the thresholds are coherent                    7 / 21 / 14
✓ a past next action adds exactly one follow-up  0 -> 1
✓ every row says why it is there                 1 rows
✓ the row names the reason it was added          you set a next action for 1 Jan
✓ clearing the next action removes the row again 1 -> 0
✓ the application is left as it was found        nothing is left behind
```

### What M2d found that the plan did not predict

Six, and **three were in code or tests that reported success** — the eighth
milestone running to record that pattern. Full detail in
`docs/reviews/milestone-2d-review.md`; the three worth reading here:

1. **The query-plan assertion was wrong twice, in opposite directions.** The
   plan's version could not fail: every queue statement joins `jobs` and
   `companies`, so `pk_jobs` and `pk_companies` appear in all four plans
   whatever the filter does — measured by dropping both new indexes and watching
   all four still report index nodes. The fix then over-corrected by naming the
   expected index, and **that broke within the hour**: `interviews_approaching`
   used one index against one corpus and another against a corpus a few
   applications larger, which is the planner switching from a time scan to a
   nested loop and doing its job. The property that holds is *no fall back to
   reading a whole table*; with `enable_seqscan = off` a sequential scan means no
   usable index exists. Dropping all three `application_events` indexes turns
   three of four red. **Between a vacuous assertion and a brittle one there was a
   correct one, and finding it took measuring the planner twice.**
2. **The plan's test helper could not insert a closed job.**
   `ck_jobs_closed_at_matches_status` is a biconditional, so setting `status`
   alone fails — six tests, every one about "closed while saved". The schema was
   right and the plan was wrong.
3. **Operate claimed tracking was not built, directly below a link to it.** The
   "Not built yet" list still said *"Saving, applying, and stage tracking —
   milestone 2"*, false since M2b. M2c's review made the same finding about a
   different list, which makes this the pattern rather than the incident: **a
   "not built" list goes stale in the one direction nobody checks**, because
   nobody re-reads it when a feature lands.

Also: the plan's browser walk would not have run twice — it gave both tests the
same job, and an `interview_scheduled` event cannot be deleted, so the
follow-up test's "the row is gone" assertion would fail on the second run of the
day. That is the exact bug M2b's pipeline test shipped.

### A prediction the plan made that did not come true

The plan added M2b's four enums to `test_enum_parity.py` and predicted **at
least one would disagree** with Python, reasoning that hand-transcribed and
never machine-checked is what produced M2c's defect. **All four were correct.**
Recorded rather than deleted — the prediction was sound and the outcome was
better than it. The guard now covers thirteen enums instead of nine, and
`QueueSectionKey` is the first entry in it that is not a database enum.

### Not real yet — M2d

The four rows PRODUCT-SPEC §10.4 asks for that need M3. **None are stubbed**;
each is named on the page with its reason, rendered from the API's own
`deferred_rows`:

- **Best new internships** — 'best' is a ranking and there is no match score.
- **High-match roles closing soon** — needs a score *and* a deadline most
  sources never publish (A10).
- **Resume mismatch warnings** — needs requirement extraction and the evidence
  graph.
- **The one thing to do today** — ranking across four heterogeneous row types.

Also deliberately absent: **dismiss and snooze** (§7.3 — new state, a new table,
and a decision about whether a dismissed row returns tomorrow), and
**`assessment_due_at`** (§7.1 — `next_action_at` already carries the date).

**`offer` is excluded from every queue section.** An offer is a decision rather
than a chase and the pipeline shows it prominently. That is a judgement a real
user might overturn, and it is one tuple — `TERMINAL_STAGES` — in one file.

**The browser walk leaves one archived application**, for the same reason
`check_application_tracking` does: an `interview_scheduled` event is append-only,
so archiving is the only way to take a role back out of the queue. Stated in the
test. `check_daily_queue` itself leaves nothing.

### The M2d plan, and the two branches still on the remote

`docs/plans/2026-08-04-m2d-daily-queue.md`. Two merged remote branches are still
there — `origin/m2c-profile-and-resume` and `origin/m1a-provider-breadth` — both
fully merged into `main` with nothing ahead. Deleting them needs a permission
this session did not have; it is one `git push origin --delete`.

**Next after M2d: merge, then M3 — explainable matching.**

---

### The M2c record, kept below

**PR #7 is merged.** `main` is at `e42d612`, merged 2026-08-04 by the human,
checked against the PR rather than assumed. The pre-merge invariant held: `git
diff 1fe34ef..HEAD --stat` listed one file, `docs/PROGRESS.md`, so the recorded
CI result covered every line of code on the branch. `m2c-profile-and-resume` is
deleted locally.

**Two remote branches are still there and both are fully merged into `main`
with nothing ahead** — `origin/m2c-profile-and-resume` and, from much longer
ago, `origin/m1a-provider-breadth`. The M1 record below claims every milestone
branch was deleted "both locally and on the remote", and for `m1a` that was
never true. Deleting them needs a permission this session did not have; it is a
human's `git push origin --delete` and costs nothing to defer.

**Branch `m2d-daily-queue` is open at `0465e63`** with two docs commits on it
and no code yet.

### What M2d is, and what it earns

Four rows the system can compute honestly — follow up, interviews approaching,
stale saved, closed while saved — plus the four PRODUCT-SPEC §10.4 asks for
that need M3, named on the page with their reason rather than rendered as
empty sections. An empty section claims "you have none of these"; a named
absence says "this does not exist yet". Only one of those is true.

**M2d earns none of M2's four acceptance criteria, and that is not a gap.** All
four were verified at M2a, M2b and M2c and are recorded below. What M2d
completes is M2's *deliverable* list in `CLAUDE.md` §6, of which the daily
queue is the last item.

### Three decisions taken on 2026-08-04, before planning

All three are recorded in `docs/architecture/command-center.md` §7, which was
amended rather than left to the plan:

| Decision | Where |
|---|---|
| Thresholds: 7 days of silence, 21 days stale, a 14-day interview horizon | §7 |
| "Assessments due" folds into Follow up rather than getting its own row | §7.1 |
| The queue writes nothing — no dismiss, no snooze, every row a link | §7.3 |

**The second one was a discrepancy, not a preference.** PRODUCT-SPEC §10.4
lists nine queue rows. `command-center.md` §7 named eight and had lost
"Assessments due" without saying so — the exact failure mode that document
exists to prevent. `applications` carries `next_action_at` and nothing else
date-shaped, so an assessment with a date already surfaces under Follow up;
the fold is now written down with its reason instead of being a silent drop.

### What the plan checked against the code rather than assuming

Three things, and all three would have been wrong in the executor's hands:

1. **The query-plan helper is `_plan`, not a new `EXPLAIN` call.** It compiles
   with `paramstyle="named"` and sets `enable_seqscan = off` inside the
   transaction; a second copy would not have matched how the existing
   assertions run.
2. **There is no shared `client` fixture.** Each route-test file defines its
   own, because it overrides `current_user_id` as well as the session so the
   suite does not depend on `make seed` having run. Reproduced in the task.
3. **M2b's four enums cross the Python/TypeScript boundary unguarded.**
   `test_enum_parity.py` covers nine, all of them M2c's. The queue's row schema
   parses `current_stage` through `applicationStageSchema`, so M2d depends on
   one of them being right. The plan adds all five — the four plus its own
   `QueueSectionKey` — and predicts at least one will fail on its first run,
   because hand-transcribed and never machine-checked is the exact condition
   that produced M2c's defect.

**M2b built for this milestone deliberately** and it shows: `next_action_at` is
already indexed with a comment naming M2d, and `ApplicationEvent`'s docstring
already records that `occurred_at` may be in the future because an
`interview_scheduled` event carries the interview's own time. Neither needed
changing.

### The M2c record, kept below

**All eleven tasks are done, committed, pushed, and CI-green.** The three
commands were run locally and their counts are read from the output, not
inferred:

```
make check        1093 Python, 129 web, ruff/mypy/eslint/tsc clean
make acceptance   73 verify checks + 34 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests        <- the third command, run separately
```

**`make acceptance` was run three times back to back and passed all three**,
which is the idempotency evidence rather than a hope about it. The single e2e
skip is the pre-existing honest one: `an unchanged board is not presented as a
problem` needs a board that has answered `304`.

**CI is green, on the first attempt.** [PR #7](https://github.com/Tahmudun/Nightshift/pull/7),
run [30877140583](https://github.com/Tahmudun/Nightshift/actions/runs/30877140583)
— **all five jobs**, counts read from the job logs rather than inferred:

```
python       4m09s   1093 passed, zero skipped
e2e          2m39s   5 degraded + 34 seeded passed, 1 skipped
migrations   1m20s   up, down, up, and no drift
web            55s   16 files, 129 tests
secret scan     8s
```

`headSha` on the run is `e63ec2fe525738db7eb8791971a68a59566912fb`, checked
against the branch head rather than assumed. **1093 in CI matches 1093
locally**, so the database-backed tests really ran there too. The single e2e
skip is the pre-existing honest one.

Six CI runs across this project have failed and every one found something no
local command had executed. This is the third first-try pass; it is recorded
precisely because it is not the usual outcome.

**`1fe34ef` is the last commit containing anything CI executes** — and it is the
docs commit, because the review found two defects and fixing them is code
(§2.1's provenance link, §3.3's new guard). The three commands above were run
*after* those fixes and before that commit, so their counts cover it. Every
commit after `1fe34ef` must touch `docs/` only, which is one command:

```
git diff 1fe34ef..HEAD --stat    # must list nothing outside docs/
```

If that shows a file under `apps/`, `services/`, `infra/`, `data/` or the
Makefile, the recorded results do not cover the branch and the three commands
must run again. This is the invariant M1d wrote down after PROGRESS twice
carried a green claim beside a SHA that was no longer the head.

Eleven tasks, eleven commits, branch `m2c-profile-and-resume`.

| Task | Commit | What it did |
|---|---|---|
| 1 | `09a4724` | Paste, `.txt` and PDF, failing whole; `pypdf` + `python-multipart` |
| 2 | `b82b652` | `data/skills.yaml` and the matcher |
| 3 | `72814c9` | The extractor — 16 proposals, every one carrying its span |
| 4 | `a87b280` | Migration `0009`, four tables, the span-quoting trigger |
| 5 | `74f1076` | `domain/profile.py` — the only writer of a confirmed fact |
| 6 | `e99e085` | Thirteen routes; a resume can be selected on an application |
| 7 | `61ff9c3` | Zod schemas and the client, and the enum-parity guard |
| 8 | `8390704` | The profile page, the skill list, the upload control |
| 9 | `e5f7fdc` | The confirmation screen and the overlapping-span highlighter |
| 10 | `f2d01f0` | The browser walk, and `check_profile_confirmation` |
| 11 | this | ADR 0013, the review, this entry |

### Criterion 4, earned: no parsed resume fact is stored as confirmed without a user action

Four independent guards, each shown able to fail:

| Guard | Where | Shown able to fail by |
|---|---|---|
| Two tables, one writer | `domain/profile.py` is the only module that may write `users` / `user_skills` / `user_projects` | `test_nothing_infers.py` — three greps: assignment, constructor, `setattr` |
| The extractor cannot reach the confirmed tables | It does not import the ORM | `test_the_extractor_does_not_call_back_into_the_writer` |
| Every proposal quotes its span | Trigger `resume_extractions_span_must_quote`, re-asserted in the API response and again in Zod | Task 4's tests; and a one-character shift in the response turns the API test red |
| The browser confirms nothing on its own | `ExtractionReview` opens with every row undecided | `confirms nothing until somebody says so` |

**The browser test is the criterion, not a proxy for it.**
`apps/web/e2e-seeded/profile.spec.ts` pastes the fixture resume, asserts sixteen
proposals with the characters each came from, then **navigates to the profile and
finds it unchanged** — that step is the criterion. Only then does it confirm two
and reject one, and assert exactly those outcomes, that the rejected skill is
absent, that it survives a reload, and that it survives deleting the resume.

`check_profile_confirmation` asserts the same over HTTP and compares the profile
**before and after** rather than asserting "no skills", which would pass
vacuously on a fresh database and fail on a developer's own. Measured:

```
✓ pasting a resume succeeds                              HTTP 201
✓ the resume produced proposals                          16
✓ every proposal quotes the text it points at
✓ invariant I2: every proposal is still pending
✓ invariant I2: reading a resume confirmed nothing
✓ exactly the confirmed skill was added, and nothing else   Python
✓ the confirmed skill points back at the words it came from resume:e445e1e0…#238-244
✓ a confirmed skill survives deleting the resume it came from
✓ the skill this check added is removed again            nothing is left behind
```

### What M2c found that the plan did not predict

**Eleven, and eight were in code or tests that reported success** — the seventh
milestone running to record that pattern. Full detail in
`docs/reviews/milestone-2c-review.md`; the seven worth reading here are below,
starting with the four from Tasks 1–5:

1. **A vocabulary test could not fail.** `test_the_longest_term_wins_when_two_
   overlap` used "Machine Learning", which contains no shorter vocabulary term,
   so the longest-first ordering it claimed to guard was never exercised. Found
   by mutating the sort and watching nothing go red. Rewritten over "Tailwind
   CSS", where three terms genuinely overlap.
2. **`op.add_column` does not create an enum type**, unlike `create_table`. The
   autogenerated migration failed with "type does not exist" on its first run.
   Restructured to the house pattern from `0001` and `0004`.
3. **Autogenerate emitted `nightshift.db.types.UTCDateTime` with no import** —
   the fourth migration in this project to do it — **and** omitted both `users`
   check constraints, because it does not emit table constraints for a table it
   is only adding columns to, **and** emitted no `DROP TYPE`, which would have
   left nine enums behind on downgrade.
4. **`parents[3]` is `services/`, not the repo root.** The vocabulary loader
   pointed at a path that does not exist. This is the same off-by-one M1c's
   plan made, and the reason `domain/registry.py` uses `parents[4]`.

And the three from Tasks 6–11:

5. **Two enum vocabularies were transcribed into TypeScript wrong, and nothing
   local could see it.** `WorkAuthorization` gained a `requires_sponsorship` that
   does not exist — the real member is `needs_sponsorship` — and
   `SkillSourceType` lost `assessment` and `github`. The Python suite never reads
   TypeScript; the web suite parses fixtures written to match the schema. **The
   failure would have been a real response reaching a real browser and Zod
   refusing to parse the page.** Found by printing the enums rather than reading
   them. `tests/test_enum_parity.py` is the guard and it is the only test in the
   repo that reads both sides of that boundary at once. This is the fifth time a
   defect has lived somewhere no local command looks.
6. **A skill's provenance linked to a resume that may have been deleted.**
   Deleting a resume deliberately keeps the skills it produced, so the pointer
   outlives its target and the link 404s. A 404 dressed up as evidence is worse
   than no link. The provenance is still stated; only the link is withheld, and
   the row says "in a resume you have since deleted".
7. **A component test was fed data the API cannot produce.** `ExtractionReview`'s
   fixture put `Python` at characters 34–40, which is `"\nPytho"` — the right
   length, the wrong words, and exactly the row `resumeDetailSchema` exists to
   refuse, sitting inside the test for it. The fixture is now parsed through that
   schema in its own test.

Also corrected against measurement rather than assumption: the fixture
generator's docstring claimed `encrypted.pdf` could not be byte-reproducible.
Two consecutive runs produce identical bytes on pypdf 6.14, so it now records
what was measured. And `pypdf` is BSD-3-Clause, not the plan's "MIT" —
`costs.md` had it right.

### Mutation testing: ten more, and nine killed their intended test

The tenth found a test that could not fail rather than a rule that was wrong,
which is the same outcome Task 2 recorded. `HighlightedText` drops a span whose
bounds fall outside the text rather than clamping it; the test asserted the
rendered text was unchanged, **and it is unchanged either way** — an
out-of-range slice is the empty string whichever branch runs. The assertion is
on the marks now, and the same mutation kills it.

The most valuable of the ten: inserting `return []` at the top of
`extract_proposals` fails **19 tests** across three files, so the extraction path
is decorative in none of them.

### Three things the review checked rather than assumed

- **Nothing logs the resume text.** No logging statement in
  `services/api/nightshift/` carries `parsed_text` or a resume body, and
  `logging.py` has no request-body middleware. This is the most personal data
  the project holds (§13).
- **No proposal can come to quote different words.** Nothing assigns
  `resumes.parsed_text` after creation. **The trigger cannot catch this** — it
  fires on `resume_extractions`, so an UPDATE to the parent passes unexamined
  while every child row silently starts lying.
  `test_nothing_rewrites_the_text_a_proposal_quotes` is the new guard.
- **`make acceptance` leaves nothing behind from M2c.** Both the verify check and
  the browser walk clean up after themselves, and the browser walk normalises on
  *entry* as well — M2b's pipeline test could not run twice for the opposite
  reason. `check_application_tracking` still leaves one archived application, by
  design and stated in its docstring.

### The plan being executed: `docs/plans/2026-08-03-m2c-profile-and-resume.md`

**M2b is merged and its branch is gone.** PR #6 merged at `2f984f3` with head
`40d7dd8`, checked against the PR rather than assumed; `m2b-the-loop` is deleted
locally and on the remote. The pre-merge invariant held — `git diff
6a10bb6..HEAD --stat` listed one file, `docs/PROGRESS.md`, so the recorded CI
result covered every line of code on the branch.

**M2c is the slice with the most invariant risk in M2**, which is why
`command-center.md` §1 put it third. Everything a resume says is a claim about a
person, and I2 forbids storing any of it as fact without an explicit click. The
enforcement is structural: proposals live in `resume_extractions`, confirmed
facts live in `users` / `user_skills` / `user_projects`, and one module may
write the second set.

**One decision the human made on 2026-08-03, before planning:** resume input is
**paste, PDF, and `.txt`**. PDF costs one dependency (`pypdf` — pure Python,
MIT, no native libraries, no key, so `make demo` stays offline). `.docx` is not
supported and the upload control says so by name. The confirmation screen shows
the text the extractor actually read, which is what makes PDF safe to accept: a
scrambled two-column extraction is visible rather than hidden behind a tidy
form.

### The M2b record, kept below

**M2b is complete and M2's headline criterion is earned.** All three commands
were run at the branch head and their counts are read from the output, not
inferred:

```
make check        992 Python, 84 web, ruff/mypy/eslint/tsc clean
make acceptance   28 verify checks + 31 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests        <- the third command, run separately
alembic check     no drift, up/down/up clean on migration 0008
```

**`make acceptance` was run three times back to back and passed all three**,
which is the evidence for the idempotency claim rather than a hope about it.
The single e2e skip is the pre-existing honest one: `an unchanged board is not
presented as a problem` needs a board that has answered `304`.

**CI is green, on the first attempt.** Run
[30797523109](https://github.com/Tahmudun/Nightshift/actions/runs/30797523109)
at `6a10bb6` — **all five jobs**, counts read from the job logs rather than
inferred:

```
python       241s   992 passed, zero skipped
e2e          164s   5 degraded + 31 seeded passed, 1 skipped
migrations    79s   up, down, up, and no drift
web           63s   11 files, 84 tests
secret scan   47s
```

`headSha` on the run is `6a10bb67d5172ef615816d9e75a16f3f33bcfa6a`, checked
against the branch head rather than assumed. **992 in CI matches 992 locally**,
so the database-backed tests really ran there too. The single e2e skip is the
pre-existing honest one.

Five CI runs across this project have failed and every one found something no
local command had executed. This is the second first-try pass; it is recorded
precisely because it is not the usual outcome.

The invariant this project has learned twice still applies before merging —
`6a10bb6` is the last commit CI has seen:

```
git diff 6a10bb6..HEAD --stat    # must list nothing outside docs/
```

Eight tasks, eight commits, branch `m2b-the-loop`.

| Task | Commit | What it did |
|---|---|---|
| 1 | `2c51a16` | The stage machine — 90 ordered pairs, classify never block |
| 2 | `d02cb08` | `applications`, `application_events`, migration `0008`, the trigger |
| 3 | `765b792` | The write layer — no change without an event |
| 4 | `bb09b53` | Nine routes, and the guard that nothing applies |
| 5 | `aca7957` | A closing listing writes an event, never a stage change |
| 6 | `00c5ee1` | Zod schemas and the eight client mutations |
| 7 | `f0a3eaf` | The save control, on the list and the job page |
| 8 | `e711a45` | The pipeline board and the application page |
| 9 | this | The browser loop test, `verify.py`, ADR 0012, the review, this entry |

### Acceptance criteria — M2

`CLAUDE.md` §6 gives M2 four. **All four are now earned and verified below** —
three by M2b, the fourth by M2c. The <200ms filter criterion was earned at M2a
and is unchanged.

**M2 is not closed.** M2d — the daily queue — is still to build, and CI has not
run on M2c.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Full discover→save→apply→track loop works with zero 3D | **VERIFIED** (M2b) | `apps/web/e2e-seeded/pipeline.spec.ts`, `discover, save, apply, track — the whole loop`. Walks a real browser: open a role, save it, assert the control reports a stage, open the application, assert **no control that applies**, record "I applied", write a note, move to `interview`, read the history back with its transition class, archive, restore, and correct the stage back. 15.2 s against the seeded stack. **That test is the criterion, not a proxy for it.** |
| 2 | Events are append-only, enforced at the DB level, not by convention | **VERIFIED** (M2b) | Trigger `application_events_append_only`, reusing `nightshift_refuse_mutation()` from `0002`. Three tests attempt the violation and catch the error: UPDATE, DELETE, and **deleting the parent application**, which cascades into the trigger. Mutation-checked: dropping the trigger turns exactly those 3 red. An application therefore cannot be deleted at all — archive is the only removal, and that is a property of the schema rather than a UI choice |
| 3 | No stage moves without a user (invariant I5) | **VERIFIED** (M2b) | Enforced in three places and each proven able to fail. Python: `SystemMayNotSetStageError`. Database: `ck_application_events_only_a_user_moves_a_stage` — neutering it to `true` fails 1 test, and a `system` actor carrying a stage fails 3. Client: `applicationEventSchema`'s `superRefine`. Plus `tests/test_nothing_applies.py`, which asserts `PoliteClient` exposes no write method and that `domain/applications.py` is the only module assigning `current_stage`. A closing listing writes a `listing_closed` event and the stage does not move — asserted end to end through `apply_freshness`, not through the helper |
| 4 | No parsed resume fact is stored as confirmed without a user action | **VERIFIED** (M2c) | `apps/web/e2e-seeded/profile.spec.ts`, `a resume proposes, and confirms nothing until it is told to`. Pastes the fixture resume, asserts 16 proposals each showing the characters it came from, then **navigates to the profile and finds it unchanged** — that step is the criterion. Then confirms two, rejects one, and asserts exactly those outcomes, that the rejected skill is absent, that it survives a reload, and that it survives deleting the resume. Four guards behind it, each shown able to fail — see the table above. Also asserted over HTTP by `check_profile_confirmation` in `make acceptance` |

The <200ms filter criterion was earned at M2a and is unchanged.

### What M2b found that the plan did not predict

Ten findings. **Six were in code or tests that reported success** — the sixth
milestone running to record that pattern. Full detail in
`docs/reviews/milestone-2b-review.md`; the four worth reading here:

1. **The event timeline could not be ordered, and every row looked present.**
   `created_at` defaulted to `now()`, copied from every other table. Postgres's
   `now()` is the *transaction* timestamp — measured: three inserts in one
   transaction give **1 distinct `now()` and 3 distinct `clock_timestamp()`**.
   With one value the sort falls through to a random UUID, so the history
   renders complete, plausible, and in the wrong order. Two of the plan's own
   tests failed on this before anything was changed. Fixed at the column;
   every other table keeps `now()`, which is right for them.
2. **A concurrent save returned HTTP 500, reproduced before being fixed.** Four
   simultaneous POSTs for one job: `[500, 500, 201, 500]`, one row. Data
   integrity never broke — that is the unique constraint working — but the
   loser of the race got a server error for a save that succeeded. Fixed with a
   savepoint and a re-read; re-measured across six rounds, **zero 500s**.
3. **A tracked job flashed an actionable Save button, and a browser test landed
   a click in that window.** `SaveJobButton` rendered the button whenever the
   query had not answered yet. The flake was the product telling the truth
   about itself: a person can click that. Fixed with a pending state — which
   then broke the test in a second way, because the test asked `isVisible()`
   before the control had settled. Both fixed.
4. **An archived application looked unsaved, and saving it did nothing.** The
   control queried without `archived`, so the route filtered the row out, the
   button said "Save", and the save returned 200 having changed nothing.

Three more, all in tests: a stage-change test asserted on the returned
in-memory object and could not detect a missing `session.add`; three Zod tests
passed before the schema existed, because `undefined.parse()` throws; and the
I5 source guard excluded the stage machine by basename, hiding a substring bug
where `.current_stage =` also matches `Application.current_stage == stage`.

### Three corrections M2b made to its own plan

- **The plan's browser test could not run twice.** It archived on the way out,
  and an archived application is excluded from the pipeline and refuses every
  mutation. Each test now normalises what it finds on entry rather than
  trusting its own tidy exit.
- **The posting link could not be built as specified.** The plan said
  `application_url ?? job.sources[0].canonical_url`; the application's `job` is
  a `JobSummaryOut` and carries no `sources`. An application with no recorded
  URL now says so, rather than a fabricated board link (I1).
- **The plan predicted the wrong test would catch a mutation.** It said that if
  `test_a_closing_listing_does_not_move_the_stage` did not fail, the test was
  wrong. It did not fail, and the test is right: the mutation writes a false
  *event* without touching `current_stage`. Recorded rather than "fixed".

### What M2b deliberately did not build

Profile and resume, with the confirmation step (M2c); the daily queue (M2d);
match score, eligibility, skill and internship-season filters (M3); boroughs
and any coordinate (M4). **Contacts** are unscheduled — a contact is a person
and needs its own table.

**None of these are stubbed.** The application page renders them by name with
the reason and the milestone, from the API's own `deferred_fields`.

### Not real yet

- **`make acceptance` leaves one archived application behind**, by design and
  stated in `check_application_tracking`'s docstring. `make reset-db` clears
  it. Deleting it is impossible — see acceptance criterion 2.
- **The seeded browser suite leaves two saved applications** in the developer's
  corpus, for the same reason: it tests the loop against a real stack.
- **`discovered` is an unreachable stage.** The enum value exists because M3
  will use it; nothing writes it today.


**M2a is complete. The first CI run failed and it caught a real defect no local
command had run** — see item 4 below. Fixed, and the second run is what the
merge decision should rest on.

```
make check        856 Python, 63 web, ruff/mypy/eslint/tsc clean   (read, not inferred)
make acceptance   18 verify checks + 27 seeded browser tests, 1 skip
make test-e2e     5 degraded-path tests          <- the suite CI caught, run separately
alembic check     no drift, all three migrations applied
```

**CI is green.** Run
[30788730379](https://github.com/Tahmudun/Nightshift/actions/runs/30788730379)
at `76190c8` — **all five jobs**, counts read from the job logs rather than
inferred:

```
python       232s   856 passed, zero skipped
e2e          164s   5 degraded + 27 seeded passed, 1 skipped
migrations    77s   up, down, up, and no drift
web           55s
secret scan    8s
```

`headSha` on the run is `76190c88657f8a6a1d4883ef3a469a0501a41bac`, checked
against the branch head rather than assumed. **856 in CI matches 856 locally**,
so the database-backed tests really ran there too. The single e2e skip is the
pre-existing honest one: `an unchanged board is not presented as a problem`
needs a board that has answered `304`, and the seeded stack has polled nothing.

**The first run failed, and it earned its keep.** Run
[30788290888](https://github.com/Tahmudun/Nightshift/actions/runs/30788290888)
at `1aabc58`: four of five green, `e2e` red — item 4 below. Four CI runs across
this project have now failed, and every one found something no local command
had executed.

The M1d invariant still applies and is still cheap to check before merging:

```
git diff 76190c8..HEAD --stat    # must list nothing outside docs/
```

Ten tasks, ten commits, branch `m2a-search-and-detail`.

| Task | Commit | What it did |
|---|---|---|
| 1–2 | `4120415` | `search_vector`, the filter indexes, `domain/search.py` |
| 3 | `0eed338` | `/jobs` filters on text, city, type, source, date, salary |
| 4 | `0c30d2c` | The query-plan guard — and the defect it immediately found |
| 5 | `69fdd89` | `/companies` and `/companies/{id}` |
| 6 | `3920b9d` | Zod schemas and the API client |
| 7 | `7d42ceb` | The filter panel, state in the URL |
| 8–9 | `1df5156` | Job and company detail pages |
| 10 | this | Seeded browser tests, review, this entry |

### Criterion: filters return in <200ms on seeded data

Measured against the 31-job seeded corpus, worst of five requests each:

```
q=engineer&status=open                        9 hits    31.6 ms
q=engineer&include_description=true          21 hits    40.1 ms
city=New York&employment_type=full_time      15 hits    36.1 ms
salary_at_least=90000                        27 hits    42.7 ms
(no filter)                                  31 hits    53.4 ms
```

**The first attempt at this measurement was wrong and looked right.** Run
straight after `make check`, it produced five plausible figures of 12–23 ms —
against a corpus of **zero jobs**, because the Python test fixtures truncate
the dev database. It was caught only because the corpus size was printed
beside the timings. Any future measurement must print what it measured against.

The number is not the guard. `tests/test_query_plans.py` is: it asserts every
filter is servable by an index, which is what stays true as the corpus grows.

### What M2a found that the plan did not predict

Nine defects, **seven in code that reported success** — the same pattern M1a,
M1b, M1c and M1d each recorded, now five milestones running. Full detail in
`docs/reviews/milestone-2a-review.md`; the four worth reading here:

1. **Searching descriptions by default made the search box useless.**
   `q=developer` matched all nine recorded Alloy postings, because it stems to
   `develop` and every description says "business development" somewhere. Not
   an index bug — it is what full-text search over long documents does with no
   relevance ranking to sort the noise down, and ranking is M3. The tempting
   fix was to change the test, which would have shipped a search box where
   typing a job title returns the corpus. Fixed with a title-only vector
   (migration `0006`) and `include_description` as an opt-in.
2. **The salary floor could not be served by an index**, found by the
   query-plan test on its first run. The floor is an `OR` across both bounds
   and Postgres needs an index on each side to build a BitmapOr; only
   `salary_max` had one. **The wrong plan returns exactly the right rows**, so
   this is invisible in the code, in the response, and in every correctness
   test. Migration `0007`.
3. **Two defaults governed one behaviour and only one was guarded.** Flipping
   `JobSearchQuery.include_description` failed nothing, because the FastAPI
   route re-declares its own default and that is what governs. Found by
   mutation testing — the guard looked present and was not.
4. **`make check` and `make acceptance` both miss the degraded e2e suite, and
   CI caught what they missed.** The new remote-policy filter added a second
   "Remote" to `/explore`, breaking a page-wide text assertion in
   `make test-e2e`. Neither aggregate target runs that suite and neither can —
   it needs the API *down*, which is the opposite stack state from acceptance.
   **`make test-e2e` is a third command and must be run before pushing.** This
   is the fifth time in this project that a defect lived somewhere no local
   command looks.

### Two corrections M2a made to its own plan

- **`ix_job_locations_city_lower` must be declared on the model.** The plan
  said the opposite. Measured: with the index in the database and absent from
  the model, `alembic check` reports `remove_index` and fails.
- **Two Playwright failures were harness, not product.** `.check()` on a
  URL-controlled checkbox catches the input mid-revert, and the first
  navigation into a dynamic route pays `next dev`'s on-demand compile. Both
  diagnosed by probing the browser rather than by assuming the link was broken.

### What M2a deliberately did not build

Save, apply, tracking, notes, stage history (M2b); profile and resume (M2c);
the daily queue (M2d); match score, eligibility, skill and internship-season
filters (M3); boroughs and any coordinate (M4).

**None of these are stubbed.** Where the spec asks for them, the UI names them
and says what they are waiting for — the filter panel renders five disabled
filters with their reasons, and the job page lists seven uncomputed fields.

---

### The M1 record, kept below

**M1 is closed. All four PRs are merged, `main` is at `044189e`, and every
milestone branch is deleted both locally and on the remote.** The `git diff
75d9ab7..HEAD` check below was performed before merging and listed nothing
outside `docs/`, so the recorded CI result covered the branch.

**M2 is scoped and its design is written: `docs/architecture/command-center.md`.**
Read it before any M2 work; `CLAUDE.md`'s read-order table now requires it.

Three decisions the human made on 2026-08-03, all recorded in that document:

| Decision | Where |
|---|---|
| Slice order: search → track → resume → queue, so the loop criterion is earned at M2b | §1 |
| Resume extraction is rules-based with a character span per proposal — not an LLM, not a bare form | §6.1 |
| The daily queue ships its four honest rows and names the four that need M3 | §7 |

**Two things the design corrected against the code rather than the spec**, both
found by reading the schema instead of trusting the plan:

1. **A borough or neighborhood filter cannot be built in M2, and it is an I1
   problem rather than a scheduling one.** `job_locations` has `city`, `state`
   and `country` and no borough column, because a posting saying `"New York,
   NY"` does not say which borough it is in. Deriving one is interpolation. A
   **city** filter is honest today because it matches what the source wrote;
   boroughs arrive with the geocoder at M4.
2. **A stage machine must not block a stage change.** §10.2 requires the user
   can always correct a stage, and `saved → offer` is real — referrals happen.
   The machine classifies each transition (`advance` / `correction` / `reopen`)
   and records it, instead of refusing it. What it *does* enforce is I5: a
   stage change requires an actor of `user`, so a closing listing writes a
   `listing_closed` event and a prompt, and never moves the stage itself.

M2's acceptance criteria are not yet claimed. Nothing below this line describes
M2 work — the tables in this file are still M1's and M0's.

**M1d is complete, M1 with it, and CI was green.**
[PR #4](https://github.com/Tahmudun/Nightshift/pull/4), run
[30783504694](https://github.com/Tahmudun/Nightshift/actions/runs/30783504694)
at `75d9ab7` — **all five jobs green**:

```
python       3m18s   804 passed, zero skipped   (read from the log, not inferred)
e2e          2m33s   20 passed, 1 skipped
migrations   1m17s   up, down, up, and no drift
web            54s
secret scan    11s
```

`headSha` on the run is `75d9ab798a46b1a49602adacffe3575fbe862b87`, checked
against the PR head rather than assumed.

**That check found something worth keeping, and then a regress worth naming.**
The first green run was at `4106072`; two docs commits landed after it, so this
file briefly claimed "CI-green" beside a SHA that was no longer the branch head.
Re-running fixed that — and the commit recording the re-run moved the head past
the SHA *it* recorded. Chasing this converges on nothing: **any commit that
writes down a CI result invalidates its own claim.**

So the invariant is stated rather than chased. `75d9ab7` is **the last commit
containing anything CI executes.** Every commit after it on this branch touches
`docs/` only, which is verifiable in one command:

```
git diff --stat 75d9ab7..HEAD    # must list nothing outside docs/
```

If that shows a file under `apps/`, `services/`, `infra/`, `data/` or the
Makefile, the recorded result does not cover the branch and CI must run again.
That is the check to perform before merging, and it is cheap.

The stronger form of this mistake has bitten this project before: PROGRESS once
carried a CI-green line that predated twenty-one commits of real work. The rule
that prevents it is **name the commit, and say what may follow it.**

**804 in CI matches 804 locally**, so the database-backed tests really ran there
too. The single e2e skip is honest: `an unchanged board is not presented as a
problem` needs a board that has answered `304`, and the seeded stack has polled
nothing.

M0's acceptance row 2 was the reason to insist on this. Three CI runs were
needed at M0 and the two failures found five defects that every local command
had passed over. This time the first attempt was green — which is worth
recording precisely because it is not the usual outcome.

| Task | Commit | What it did |
|---|---|---|
| 1 | `6e516cf` | `PoliteClient.get_json_conditional`; `304` returned as data |
| 2 | `8d5f5c5` | `FetchOutcome` separates *listed* from *fetched* |
| 3 | `4106ed0` | All three adapters revalidate |
| 4 | `6a5757b` | Greenhouse two-phase, plus `fetch_full_board` for first ingestion |
| 5 | `dd9e62a` | **Freshness ages against the listed set** — the central guard |
| 6 | `f356a0e` | `board_poll_state`, `board_tier`, migration `0004` |
| 7 | `6230bd8` | Poll cycle and `next_poll_at` scheduler |
| 8 | `51c7627` | Hot/warm tiers derived from postings |
| 9 | `408c768` | Row lock in `merge_jobs`, in primary-key order |
| 10 | `d3738b6` | `promote` appends; **the 19 boards are in the registry** |
| 11 | this | `GET /boards`, the Operate table, ADR 0011, review |

### Criterion 13, verified against a live provider

Two consecutive polls of `datadog` through `nightshift poll`, 2026-08-03:

```
poll 1   HTTP 200   created=429   ~16 min   (first ingestion, one request)
poll 2   HTTP 304   created=0     0.009 s
```

Job state either side of the `304`, byte-identical:

```
before   460 records | 446 jobs | 676 locations | 460 links | 0 events | 446 embeddings | 0 misses | 0 closed
after    460 records | 446 jobs | 676 locations | 460 links | 0 events | 446 embeddings | 0 misses | 0 closed
```

The ETag stored on poll 1 is the one sent on poll 2, and the same one Greenhouse
served when the design was being measured. The dev database was reset to its
documented 31-job corpus afterwards.

**"Zero writes" is claimed precisely.** A `304` *does* write one row — the
board's own `board_poll_state` bookkeeping, which is the point of polling and
not a claim about any job. What is asserted is zero writes to **job state**: no
insert or update against `source_job_records`, `jobs`, `job_locations`,
`job_source_links`, `job_status_events` or `job_embeddings`; no miss-counter
movement; no closure. `_job_state_snapshot` is that assertion, and it includes
the miss sum and the closed count because a regression that increments every
miss counter changes no row count at all.

### The 19 boards are in the registry

`make registry-approve-write` with the fixed `promote`: **4 boards → 23**, git
reports **171 insertions and 0 deletions**, no existing board lost or modified,
and `after.startswith(before)` is true — the old file is a strict byte prefix of
the new one. The note on the `Stripe` entry reading *"enable once the freshness
and closure state machine lands"* survived; under the old `promote` it would
have been deleted by the act of approving nineteen unrelated boards.

Two `Abridge` candidates stay withheld — one employer, two live Ashby tokens —
and the two `empty` boards stay held. Both are a human's call under ADR 0005.

**Stripe is still `disabled`.** M1d is the milestone its note was waiting for,
and enabling it is a decision for the human rather than a side effect of the
work finishing. A test now asserts it by name.

### What Tasks 1–5 found that the plan did not predict

Nine defects. **Seven were in code that reported success**, which is the same
pattern M1a, M1b and M1c each recorded — now four milestones running.

1. **A `304` currently reads as an authoritative empty board.** `FetchOutcome.
   is_authoritative_empty` was `ok and not jobs`, and a `304` satisfies it. That
   is "every posting on this board is gone" for a provider behaving perfectly.
   Fixed in Task 2, mutation-checked.
2. **httpx counts only 2xx as success and `304` is not retryable**, so a naive
   conditional client falls through to the terminal-failure branch and records
   an outage. The `304` check has to precede both branches.
3. **The same "jobs without listed" footgun appeared three times** — the fixture
   adapters, and two pipeline test stubs. Each instance silently means "the
   board listed nothing", which ages every record. Fixed at the type: a
   `FetchOutcome` carrying jobs with no listing now derives one.
4. **`isinstance` against a runtime-checkable Protocol matches method names
   only.** A single-phase Lever stub that implemented `fetch_postings` for
   convenience got pulled into a phase Lever has no endpoint for. The pipeline
   gates on the `is_two_phase` flag and *then* narrows.
5. **`make seed` would have crashed.** `FixtureGreenhouseAdapter` subclasses the
   real adapter and inherited `is_two_phase = True`, along with a
   `fetch_full_board` that needs the HTTP client the fixture adapter
   deliberately lacks. **The fixture adapters had no tests at all** — the
   offline demo path, untested. 24 now, plus a real two-seed run.
6. **Eleven route tests were *errors*, not failures**, on a fourth
   `_StubAdapter` copy. Errors read as noise; failures read as signal.
7. **Migration autogenerate emitted `nightshift.db.types.UTCDateTime` with no
   import** — a `NameError` at upgrade time. Second migration running that the
   note at the head of `0002` has caught.
8. **`jobs.source_updated_at` already existed and reusing it would have been
   wrong.** After a merge one job carries records from several boards and its
   timestamp reflects whichever wrote last, so the phase-2 diff would refetch
   what had not changed and skip what had. The new column is on
   `source_job_records`, because it answers a per-board question.
9. **The pipeline had never been tested against Greenhouse at all.** Every
   ingestion, closure, merge and route test drove a stub wrapping *Lever*.
   After Task 4, live Greenhouse ingestion produced zero jobs and **nothing
   went red** — a green suite over a provider that had stopped working.

### Two things Tasks 1–5 changed about what is written down

- **ADR 0007's phase 2 is Greenhouse-only, and its "no `updated_at`" problem
  dissolved.** Lever and Ashby return every posting in full from one request,
  so there is no second fetch for a timestamp to gate. Recorded in the design;
  the carried finding below is struck through.
- **Criterion 13's "zero writes" is claimed precisely.** A `304` does write one
  row — the board's own poll bookkeeping, which is the point of polling. What is
  asserted is zero writes to *job state*: no insert or update to
  `source_job_records`, `jobs`, `job_locations`, `job_source_links`,
  `job_status_events` or `job_embeddings`, no miss-counter movement, no closure.
  `_job_state_snapshot` in `tests/test_ingestion.py` is that assertion.

### What was measured before planning, and what it changed

All three providers were probed live on 2026-08-02, because ADR 0007 asked for
exactly this and never got it.

1. **All three honour `If-None-Match` and return `304`.** Greenhouse, Lever and
   Ashby, each sent its own ETag back, each answering `304` with an empty body.
   ADR 0007 verified only Greenhouse and provided a fallback for a provider that
   could not revalidate. No fallback is needed.
2. **"Neither Lever nor Ashby publishes an `updated_at`" is no longer M1d's
   biggest problem — it mostly dissolves.** This file recorded it three times,
   most recently as *"the most consequential"* finding carried into M1d. The
   worry was that ADR 0007's phase-2 diff has no timestamp to compare on two of
   three providers. True, and close to irrelevant: **Lever and Ashby return the
   complete posting, description included, in the single board request** (Lever
   `alloy`, 6,373 characters of `description` on the first posting; Ashby
   `ramp`, 7,332 of `descriptionHtml`). There is no second fetch for a timestamp
   to gate. Two-phase polling is a **Greenhouse-only** mechanism, and Greenhouse
   publishes `updated_at` on its listing.
3. **Greenhouse's per-posting payload is byte-identical to its `content=true`
   list item** — compared key-by-key and value-by-value, zero differences. So
   phase 2 reuses `GreenhouseAdapter.normalize` unchanged and there is no second
   normalization path for the location parser to drift in.
4. **Lever does not compress.** 232,855 bytes with no `Content-Encoding` despite
   being offered gzip. A Lever `200` is the most expensive response this system
   takes, which makes its `304`s the most valuable.

### The defect the design exists to prevent

`apply_freshness` ages a record by `last_seen_at < now`. Phase 2 deliberately
does not refetch an unchanged posting, so that posting is never written, so it
looks absent — **every unchanged posting on every Greenhouse board would take a
miss per poll and close on the third.** Nothing errors; the damage lands three
polls after the change. `FetchOutcome` therefore separates *listed* (phase 1,
complete, drives freshness) from *fetched* (phase 2, partial, drives
persistence). Plan Task 5, with the mutation check that proves it.

Related, and already true in committed code: `FetchOutcome.is_authoritative_empty`
is `ok and not jobs`, which a `304` satisfies — so a `304` currently reads as
"this board authoritatively has no postings". Plan Task 2 fixes it and adds a
validator making the confusion unrepresentable.

### `promote` destroys the registry's comments — found by running it

The human approved promoting M1c's 19 discovered boards. Running
`make registry-approve-write` for the first time in the project's history
exposed a defect M1c structurally could not see, because M1c deliberately never
wrote to the registry and cited byte-identity as evidence of restraint.

`promote`'s docstring says *"Additive, never destructive."* In the data sense it
is — verified semantically: all four existing boards came through identical,
nothing re-enabled, nothing lost. But it rebuilds the file with
`yaml.safe_dump`, preserving only the leading comment block, and it **deleted
ten lines of human-written rationale from between the entries** — including the
note on `Stripe` reading *"enable once the freshness and closure state machine
lands"*, which is a message to M1d, deleted by approving unrelated boards. It
also writes `added: '2026-08-02'` where hand-written entries use bare dates,
leaving one file with two conventions.

**The write was reverted; `data/board-registry.yaml` is unchanged at 4 boards.**
Plan Task 10 fixes `promote` to append rather than re-serialize, then promotes
the 19 for real, with a diff that must be additions only.

Also in Task 10: `test_the_pollable_set_is_exactly_these_three_boards` fired
correctly on all 19 and needs reshaping — enumerating every pollable board does
not survive a registry meant to grow into the thousands, and deleting the guard
would remove the only thing stopping a hand-disabled board going live. Replaced
by an exact set over the four hand-curated boards plus a provenance requirement
on every other pollable one.

### Scope decided by the human this session

- Merge PR #3 — done, `f377303`.
- Approve the 19 discovered boards — deferred into Task 10 behind the `promote`
  fix, so their arrival does not destroy the file they arrive in.
- Of the three carried weaknesses, M1d fixes **the `merge_jobs` row lock only**.
  The discovery mass-failure signal and `cmd_validate`'s per-board file rewrite
  stay recorded as debt and are explicitly out of scope.
- Scheduling shape: `next_poll_at` per board drained by a small cron, over a
  cron per tier. ADR 0011 records it during Task 11.

**The M1c record, kept for the history below:** six tasks, three acceptance
criteria evidenced, review written. Branch head `19236f5`, run
[30764366853](https://github.com/Tahmudun/Nightshift/actions/runs/30764366853):
all five jobs green — `python` **607 passed, zero skipped** (read from the log,
not inferred), `e2e` 2m22s, `migrations`, `web`, `secret scan`.

**The first CI run failed, and it caught something no local command could
have.** Recorded here rather than only in the review, because the lesson is
about how this repo verifies itself: `.gitignore` carried an unanchored
`coverage/` — meant for vitest output — and an unanchored pattern matches a
directory of that name at *any* depth. It silently swallowed
`apps/web/src/app/analyze/coverage/page.tsx`, the whole coverage route, for the
entire milestone. `git add -A` said nothing. `make check`, `make acceptance`
and all 16 seeded browser tests passed, **because every one of them reads the
working tree, where the file existed.** CI built from a clean checkout and got
a 404 — its accessibility snapshot literally reads "This page could not be
found".

A local suite cannot see a file missing from the repository, because it is not
missing locally. `services/api/tests/test_repo_integrity.py` now closes that
gap: it is the one test that asks `git ls-files` rather than the filesystem. It
sweeps the source trees, names the lost file specifically so a future
over-broad ignore rule cannot absorb the regression, and asserts the unanchored
pattern itself never comes back. This is the fourth time in this project that a
defect lived somewhere no local command looks.

After the merge, M1d is the last piece of M1: two-phase
conditional polling (ADR 0007), hot/warm tiers, queue-driven ARQ. No plan file
exists for it yet. **Read the four items below before writing that plan** —
they are M1c's output and they change what M1d has to do.

### What M1d inherited, and what it did about it

1. **No mass-failure signal in a discovery sweep.** A provider that changes its
   payload envelope classifies *every* board `unreachable`, and nothing says so
   louder than a per-candidate note. **Still open** — explicitly out of M1d's
   scope by the human's decision, not by oversight.
2. **`cmd_validate` rewrites the whole candidate file after every board.**
   Correct at 23 candidates; O(n²) at 2,605. **Still open**, same reason.
3. ~~**`merge_jobs` has no row lock**~~ — **fixed in M1d** (`408c768`), and the
   deadlock was reproduced from Postgres before being fixed rather than argued
   about. See the review §3.4.
4. ~~**ADR 0007's phase-2 diff has no timestamp on two of three providers**~~ —
   **resolved by measurement.** Lever and Ashby return every posting in full
   from the board endpoint, so there is no phase 2 on those providers and
   nothing for a timestamp to gate. Greenhouse, the only two-phase provider,
   publishes `updated_at` on its listing. This file had recorded it three times
   as the most consequential item here and it had never been re-checked against
   a live board since M1a.

### What M1 leaves for M2 and beyond

Ranked, from `docs/reviews/milestone-1d-review.md` §4:

1. **`max_jobs` is still 1, and raising it is not free.** `PoliteClient`'s rate
   limiter is per process, so two concurrent jobs against one provider halve the
   spacing it enforces. Queue-driven polling makes raising it a config change
   rather than a rewrite — but the limiter must become per-host and shared
   first. Recorded as a comment on the line somebody would change.
2. **The ARQ *worker* has never consumed a queued job.** The scheduler half is
   now verified against live Redis (2026-08-03): `enqueue_due_boards` synced 22
   boards and queued 22 `poll_board` jobs with correct arguments, and a second
   tick enqueued zero — the double-enqueue guard holding, because `next_poll_at`
   moves forward before the jobs run. What is untested is a worker process
   dequeuing them; the poll cycle they invoke has run live twice through the CLI.
   The queue was drained and the schedules reset afterwards.
3. **Only `datadog` has been polled conditionally against a live provider.**
   Lever and Ashby were measured serving `304` during design; their adapters'
   conditional path has been exercised only against fixtures.
4. **`nyc_presence` is now decorative.** Nothing in the polling path reads it —
   asserted by a test that inspects code with docstrings stripped — so deleting
   it is a cleanup rather than a behaviour change.

### The M1c pipeline, run end to end on 2026-08-02

Real network, real providers, `SOURCE_REQUESTS_PER_SECOND=0.8`:

```
make discover          400 crawl rows -> 23 distinct tokens; 23 new candidates
registry-validate      validated 23: live_named 21, empty 2      (0 failures)
make registry-approve  21 eligible -> 19 offered, 2 withheld (name collision)
                       Dry run. Nothing was written.
```

**`data/board-registry.yaml` is byte-identical to its state at branch start.**
Verified: `git diff cf48719..HEAD -- data/board-registry.yaml` is empty.
Promoting 19 employers is a product decision for the human; the plan's job was
to prove the pipeline works. `make registry-approve-write` is the command that
would do it.

Six of the 21 live boards produce NYC postings: a16z New Media (13 of 25), 9fin
(12 of 40), 3i Members (5 of 8), Abacum (5 of 18), Aaron School (2 of 2),
1Password (1 of 68).

### Plan defects found and fixed rather than copied

Four, all in the plan's own code or tests:

1. **Repo-root arithmetic off by one** in Tasks 2 and 4 (`parents[3]` is
   `services/`, not the root). Would have written
   `services/data/board-candidates.yaml` while approval read an empty file from
   the correct path — a silent split, not a crash.
2. **`test_validation_never_raises` was vacuous.** Its stub route key matched no
   URL, so the stub raised "no route" and the test passed without ever reaching
   the unexpected-exception branch it exists to cover.
3. **Task 4's test violated Task 2's own model rule** (`nyc_posting_count=7`
   against the default `posting_count=3`). The invariant catching the plan that
   specified it is the system working.
4. **`approval_report` promised an ordering it did not apply** — it rendered in
   the order given while its header said "NYC-producing first".

### M1c findings — measured 2026-08-02, all against live sources

These are the reason Task 3 took the shape it did. All four change something
already written down.

1. **`a3c41b8b71eff8c4` is dead.** The design (`board-discovery.md` §6) names it
   as *the* live-but-unnameable board — 200 with ten well-formed postings under
   a machine-generated token — and the plan says deleting its fixture "would
   hollow out the whole design". Its API now returns **404**, and it is absent
   from the July 2026 crawl index in a range the committed slice covers
   (`a-place-for-mom` … `abridge` brackets it), so it is gone rather than
   transiently missing.
2. **What replaced it is stronger evidence, not weaker.** Ashby serves
   **HTTP 200 with `<title>Jobs</title>`** for *any* token that does not exist —
   verified against both the dead token and a made-up one, byte-identical 7,128-
   byte pages. So "a live page that names no employer" is now a recording
   (`ashby_unnameable_page.html`), where the plan had specified a hand-written
   stub. Acceptance criterion 11 is still evidenced, by a real recording of the
   real mechanism.
3. **The token is not the name, about half the time.** Of the 23 Ashby tokens in
   the committed crawl slice, 21 boards are live and **10 have a name that
   differs from the token**: `0g`→"0g Labs", `a-place-for-mom`→"A Place for Mom",
   `a-team`→"A.Team", `10xteam`→"10x Team", `8fleet-inc`→"8Fleet Inc.". This is
   the measured basis for I2's rule here, and it is a stronger number than the
   design's single `0g` anecdote.
4. **Case-variant duplicate tokens are real.** The same slice holds both
   `Abridge` and `abridge` — two Ashby tokens, one employer, both live with 42
   postings. **M1d and the approval step must expect this**: `(ats, token)` is
   the candidate key and these are two distinct keys, so they will both reach
   approval as separate boards and then produce a full set of duplicate jobs
   for dedupe to merge. Cheaper to catch at approval as a `name_collision`.

Also recorded, lower urgency:

- **`scripts/record_crawl_fixture.py` (Task 1) uses `urllib`, which cannot
  verify TLS on this host** — `CERTIFICATE_VERIFY_FAILED`, no certifi bundle
  wired in. `PoliteClient` uses httpx and works. Task 3's recorder
  (`scripts/record_discovery_fixture.py`) goes through `PoliteClient`
  accordingly. The crawl recorder should be moved onto it too.
- **Common Crawl's index 504s** at `limit=6000` and above for
  `jobs.ashbyhq.com/*`; `limit=400` succeeds. Any bulk harvest has to page.
- `0x` and `abe` are live Ashby boards with **zero** postings — real `empty`
  verdicts, now recorded (`ashby_0x_empty_board.json`) so that branch is
  asserted on Ashby's `{"jobs": []}` shape and not only on Lever's `[]`.

**M1b is merged.** `main` is at `cf48719` and contains it; PR #2 was merged by
the human and both the branch and its worktree are gone.

The M1c plan was written last session: six tasks, TDD, real code in every step.
The design it implements already existed in full at
`docs/architecture/board-discovery.md` — this plan does not re-decide anything,
it sequences it.

**Re-verified before planning, per §3's own instruction** (2026-08-02):

- Common Crawl is reachable. `collinfo.json` → HTTP 200, **126 collections**,
  newest `CC-MAIN-2026-30` — the same crawl §3's 2,605-token count was measured
  against, so the design's numbers are not stale.
- The CDX query shape works and returns what the design assumes: newline-
  delimited JSON, one object per captured URL, token as the **first** path
  segment. Most captured URLs are job pages *beneath* a board, which is why
  Task 1's parser takes segment 1 — a last-segment parser would harvest UUIDs.
- **`0g` is in the live index**, which is the case ADR 0005's approval gate
  turns on: the token is not the name, and the board page says "0g Labs".
- `PoliteClient` has only `get_json` (`adapters/http.py:95`), so Task 3 adds
  `get_text` to that class rather than opening a second HTTP path.

**Two things the plan deliberately does not build**, recorded here so the gap
is visible rather than discovered later:

1. **The careers-page probe for Lever.** It needs a list of employer domains to
   start from and nothing in the repo has one. Building a domain-guessing
   heuristic would be exactly the fabrication this milestone exists to prevent.
   Lever therefore stays undiscovered, and the coverage page is required to say
   so by name.
2. **The community-snapshot source**, for the same reason.

### The M1b decisions, kept because M1c and M1d inherit them

M1b is done, but two of its rules govern everything downstream and are easier
to find here than in an ADR:

- **Closure is cautious** — three consecutive misses *and* seven elapsed days,
  both required (ADR 0009). M1d's tiers change the poll rate, and the elapsed
  condition is what stops that changing what closure *means*.
- **Similarity may never merge on its own** (ADR 0010). It is reachable only
  after company, employment type, title and location already agree. M1c's
  validator reuses `normalize_company_name` for the `name_collision` verdict
  and must not quietly widen that.

### Findings from writing the plan — read these before M1d

Live boards were probed while planning, so these are measured, not assumed. All
three change work that is already designed.

1. **Neither Lever nor Ashby publishes an updated-at field.** Lever has
   `createdAt` only; Ashby has `publishedAt` only. **ADR 0007's phase-2 diff is
   specified as "new or changed `updated_at`" and has no timestamp to compare on
   two of the three providers.** M1d must fall back to the description hash
   there. This is the most consequential of the three.
2. **Parser bugs fabricating a city, present in real payloads.**
   `"Vancouver, BC"` parsed to a city called `"BC"` and `"New York, NY (HQ)"` to
   one called `"NY (HQ)"` — I1 failures in the module whose docstring claims to
   enforce I1. The first appears 3× on the recorded Lever board, the second 95×
   on the Ashby board. M1a Tasks 3–4 fix them. **Two more of the same class were
   found later and are recorded below** — a latent `;`-splitting gap found by the
   pre-merge review, and one introduced during M1a itself and caught in task
   review. Four in total; the count is the point, because every one of them
   turned a string the source really wrote into a place that does not exist.
3. **Ten Lever tokens guessed, two live** (`alloy` populated, `plaid` empty,
   the rest 404). Direct support for ADR 0006: Lever boards genuinely have to be
   found by careers-page probing, not guessed and not harvested.

Also recorded, less urgent: Ashby's `address.postalAddress` is structured
(`{addressLocality, addressRegion, addressCountry}`) and is better input for
geocoding than its location string; Ashby's `isRemote` is `true` on 33 postings
sitting at the New York office, so it does **not** mean the job is remote.

### What was decided this session, in one place

The product goal was restated by the human: *if any tech job or internship opens
in NYC, the system knows the day of, from any employer.* That changed M1's
registry from a curated file into a discovery pipeline.

| Decision | Where it lives |
|---|---|
| Registry filled by discovery, not curation; 2,605 tokens measured available | `board-discovery.md` §3 |
| Batch approval, exceptions held individually | ADR 0005 |
| Common Crawl as primary source; Lever needs careers-page probing | ADR 0006 |
| Two-phase conditional polling, hot/warm tiers, queue-driven | ADR 0007 |
| Employer scope: tech roles at *any* employer | `board-discovery.md` §2 |
| Workday/iCIMS/Taleo deferred to the next milestone | `board-discovery.md` §2 |
| LinkedIn and Indeed rejected, with reasons | `board-discovery.md` §9 |
| Scaling to other cities, states, and job types | `board-discovery.md` §10 |
| Discovery runs on command, not on a schedule | ADR 0006, `board-discovery.md` §4 |

Two open questions remain in `docs/QUESTIONS.md` (Q1 Gmail, Q2 deployment cost),
neither blocking. Q3 is answered there in full.

`make acceptance` is the single-command acceptance run. Most recently run at
`bb80680` (M1a's closing commit) on 2026-07-30, against the containers already
running from earlier in the session (not a clean/empty volume — see the
"Verified locally" table below for that caveat):

```
18 verify checks + 6 seeded browser tests, all green, corpus 31 jobs / 3
companies / 3 sources / 62 locations (greenhouse + lever + ashby)
```

The earlier run this line used to cite, `19dc760` (the rename, against an
empty volume), still stands as the last *clean-volume* run — it predates
M1a and is superseded here only for "what does `make acceptance` currently
report," not for "was it ever run from empty."

CI: **M1a is green.** Run #9 at `430347a` — the branch head — passed all five
jobs on the first attempt: https://github.com/Tahmudun/Nightshift/actions/runs/30592177638
(`python` 74s, `e2e` 122s, inside A14's five-minute target). The `python` job's
new `postgres` service worked: `Initialize containers`, `Create extensions`,
`Migrate` and `Unit tests` all succeeded in order, so the database-backed tests
were reachable rather than skipped. See "Next exact action" for the one caveat —
the `350 passed` line itself was not read, only inferred.

The previous green run was `6f88d9a`, which **predated all of M1a.** Twenty-one commits landed between `6f88d9a` and the
M1a-closing commit — the Lever and Ashby adapters, the widened location
parser, the upserts, the ingestion and route test suites, everything in this
plan — and CI has not run against any of them this session. Do not read this
line as M1a being CI-verified; it is not. Check the Actions tab for the
current head before trusting anything past `6f88d9a`.

**Pre-merge review finding, fixed 2026-07-30: the `python` CI job had no
`postgres` service.** Only `migrations` and `e2e` did. `tests/conftest.py`
skips every database-backed test when it cannot reach a database, so on CI
the `python` job was running 323 tests and silently skipping the other 13 —
including the only tests of the ingestion pipeline and the API routes
against a real database — while still reporting green. Fixed by giving the
`python` job the same `postgres` service, env, and migration steps the
`migrations` job already uses (copied verbatim rather than retyped, per the
image-tag history in that job's comment). Verified locally: with the
database unreachable, `323 passed, 13 skipped`; with a freshly-migrated
CI-equivalent Postgres (same image, same recipe, no seed step) reachable,
`336 passed, 0 skipped`. **The workflow change is now verified in
production**: run #9 at `430347a` shows the `python` job initialising the
postgres container, creating extensions, migrating, and running the suite, all
green. The fix did what it was written to do.

---

## Blockers

### B4 — Host disk full; Docker would not start — RESOLVED 2026-08-01

Both halves are now clear, and they were two problems rather than one.

**Disk.** `/System/Volumes/Data` was at **100% — 180 MB free** of 233 GB. Now
**11 GB free**. Freed by the human; nothing in this project was deleted by an
agent.

**Docker.** Freeing the disk was *not* sufficient. With 12 GB free,
`open -a Docker` started `com.docker.backend` (two processes, confirmed by
`pgrep`) but no socket was ever created — `~/.docker/run/` stayed empty and
`docker info` failed with `connect: no such file or directory` after 180 s of
polling. Fixed by the human at the GUI. Engine now reports **29.6.2**.

**What that unblocked, verified the same session at `c52315e`:**

```
make up       postgres + redis healthy (postgres recreated from the compose file)
make migrate  alembic upgrade head, clean
make test-py  350 passed          <- 0 skipped
```

**`350 passed` with zero skips closes the open question this file had been
carrying.** The 13 database-backed tests in `test_ingestion.py` and
`test_routes.py` skip when Postgres is unreachable, so every previous local run
reported `337 passed, 13 skipped` and CI's `350` was established by inference
rather than by a read count. It is now a direct local observation: the same 13
tests run, against a real PostGIS cluster, and pass. No inference left in the
chain.

### B1 — No container runtime — RESOLVED 2026-07-30

Docker Desktop was installed by the human after `brew install --cask
docker-desktop` had rolled itself back on an interactive-sudo step
(`mkdir -p /usr/local/cli-plugins`; `/usr/local` is `root:wheel`).

Everything B1 had been blocking is now verified with recorded output. Kept here
because the acceptance table's history refers to it.

### B3 — Acceptance re-run outstanding — RESOLVED 2026-07-30

Caused by B2. The Docker daemon died mid-session with `no space left on device`,
came back showing an Electron error dialog, and then recovered once disk pressure
was relieved. The re-run it was blocking has now happened.

`make acceptance` ran to completion at commit `14abb68` from a clean shell with
nothing pre-started: **18 verify checks and 6 seeded browser tests, all green.**
That closes the one gap this entry described — the 6 seeded browser tests had
last run one commit earlier, at `bb46732`. Every acceptance row is now verified at
current HEAD.

### B2 — Host disk was full — RESOLVED 2026-07-30

`/System/Volumes/Data` was down to **1.2 GB free** of 233 GB, which is why the
final clean-clone re-run was skipped rather than risk destabilising the host.
Recovered to 14 GB, and **5.8 GB free** as of the end of the CI session, which
pulled a 4 GB Postgres image to replicate CI locally and then deleted it again.
Still tight: this host has no room for a spare clone. The earlier clean-clone run
at `0830589` stands and row 1 says
precisely what it covers; a fresh clean-clone run is no longer blocked, but it is
also no longer load-bearing, since `make acceptance` passes at HEAD.

Docker's own reclaimable space was pruned (build cache and dangling images,
~477 MB). The remaining large image, `hg-engine:latest` (2.06 GB), is not part of
this project and was left alone.

---

## Acceptance criteria — M1

Per invariant I6, "the code exists" is not evidence. M1 has fifteen criteria in
`CLAUDE.md` §6 across four plans. **Nine are earned and verified below. Six
belong to M1c and M1d and are explicitly unclaimed** — listing them as pending
rather than omitting them is the point of this table.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Same fixture input → byte-identical normalized output, twice | **VERIFIED** (M1a) | `test_normalization_is_deterministic` per adapter. Unaffected by M1b; `test_decision_is_deterministic` extends the same guarantee to the closure verdict |
| 2 | Re-ingestion is idempotent: no dupes, no spurious updates | **VERIFIED** | `test_reingestion_is_idempotent` (M1a) plus `test_re_ingesting_a_merged_board_is_idempotent` — the second poll of a merged pair reports `created == 0`, leaves 1 job, and writes no second merge event. `test_an_unchanged_repoll_does_not_re_embed` asserts the model does no work either |
| 3 | Simulated source outage closes zero jobs | **VERIFIED** | `test_a_failed_board_does_not_increment_a_miss`: five consecutive failed polls, well past every ADR 0009 threshold, leave all 9 jobs open **and every miss counter at 0**. The counter is the assertion, not the status — a failed fetch that bumps the counter closes jobs three polls later, and the pre-existing status-only test does not catch that. Confirmed by mutation: making a failed board count as answered fails this test and not the older one |
| 4 | Dedupe fixture suite: true dupes merge, near-dupes and same-title-different-role stay separate | **VERIFIED** | `tests/fixtures/dedupe_pairs.yaml`, all seven §7.5 categories, both verdicts, 55 assertions in `test_dedupe.py`. Zero skips locally — the similarity cases require the real model and it is present. Non-vacuity: removing the title guard collapses the 9 real postings on the recorded Alloy board |
| 5 | Every canonical job traces to at least one raw source record | **VERIFIED** | `test_every_job_still_traces_to_a_raw_record` and `test_a_merge_keeps_every_source_link` — after a merge the surviving job carries **both** links, with distinguishable reasons (`sole_source_record`, `identical_content`). Also asserted at the API boundary: `test_admin_rows_carry_provenance` |
| 6 | Multi-location postings produce multiple `job_locations` rows | **VERIFIED** | `test_multi_location_posting_yields_multiple_rows` (M1a), plus the browser test on real seeded data. **And a merge no longer destroys them** — `test_a_merge_absorbs_locations_the_winner_did_not_have`, which is the review's headline bug |
| 7 | Ingestion failures are visible in the UI, not just logs | **VERIFIED** | `/operate` shows per-source last success, last failure, last run error and a job breakdown by closure state; `/operate/jobs` shows every job's state with a permanent legend. 5 seeded browser tests, including one asserting the status is readable as a word rather than only a colour (§12.4) |
| 8 | Freshness + closure state machine | **VERIFIED** | 22 pure decision tests + 11 pipeline tests against a real database. Both ADR 0009 thresholds asserted, and `test_unverified_never_becomes_closed_however_long_it_lasts` runs the outage out to ten years |
| 9 | Admin job table, source health page | **VERIFIED** | `/operate/jobs` and the grown `/operate`. `job_status_counts` was added to the source route because `job_count` cannot move when a job closes — asserted directly: three empty-but-live polls take a source from 9 open to 9 stale while its total stays 9 |
| 10 | Discovery yields candidates from a committed crawl fixture, deterministically | **VERIFIED** (M1c) | `tokens_from_cdx` over the committed 400-row Ashby crawl slice → 23 distinct tokens. `test_is_deterministic_and_sorted` asserts same input → same sorted output twice; `make discover` run twice leaves the candidate file byte-identical (`test_is_idempotent`). Ran for real: `400 crawl rows -> 23 distinct tokens` |
| 11 | A live-but-unnameable board cannot reach bulk approval | **VERIFIED** (M1c) | Asserted at both layers — `test_a_live_but_unnameable_board_cannot_be_bulk_approved` on the verdict, and `test_an_unnameable_board_is_not_promoted_even_with_write` through the command a human types. **Mutation-checked twice**: making the Ashby name fall back to the token classifies the board `live_named` with `company_name='0g'` (the I2 fabrication) and fails exactly that test; dropping the verdict filter in `approvable` fails 8 tests |
| 12 | The coverage page names what is *not* covered | **VERIFIED** (M1c) | `/analyze/coverage`, four structural blind spots by id (`lever_undiscovered`, `workday_icims_taleo`, `no_public_board`, `aggregator_only`), each with its reason in plain language. 5 seeded browser tests, including one asserting the section holds no `<details>` and its text is visible unexpanded, and one asserting **no percent sign appears anywhere on the page** — there is no denominator, so a coverage percentage would be invented. `count=null` renders "unknown", mutation-checked by typing the field `int = 0`, which fails the route test |
| 13 | A `304 Not Modified` produces zero writes and closes zero jobs | **VERIFIED** (M1d) | Two consecutive live polls of `datadog`: `200`/429 created, then `304`/0 created in 0.009s, with job state byte-identical across all eight measures. Plus `test_a_304_writes_no_job_state` at pipeline and poll-cycle level. Claimed as *zero writes to job state* — the board's own bookkeeping row does move, which is the point of polling. Mutation-checked: ageing `304` boards fails exactly that test |
| 14 | Greenhouse + Lever + Ashby behind one interface | **VERIFIED** (M1a) | Three adapters on the unchanged `JobSourceAdapter` Protocol |
| 15 | `source_job_records` preserving raw payloads | **VERIFIED** (M0/M1a) | Asserted again in M1b: a merge collapses the canonical view and leaves both raw records untouched |

**M1 is complete.** All fifteen criteria are verified with recorded evidence.

Criterion 13 was the last, and it is the one worth reading the evidence for
rather than the claim: a `304` from a real provider, with eight independent
measures of job state identical either side of it.

Two criteria were re-earned rather than merely inherited. Criterion 3 (a source
outage closes zero jobs) now also holds for a board that answers `304`, which is
a new way to learn nothing and would have closed every posting on every
unchanged board. Criterion 2 (re-ingestion is idempotent) now covers a
two-phase poll, where "unchanged" means a posting is deliberately never
refetched — the case that made the freshness fix necessary.

---

## Acceptance criteria — M0

Per invariant I6, "the code exists" is not evidence. Each row is either verified
with recorded output or explicitly marked blocked.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Clean clone → `make setup && make demo` works, documented, no hidden steps | **VERIFIED** | Genuine `git clone` into a scratch directory at commit `0830589`, no `.env`, no Docker volumes: `make setup` built the venv and installed JS deps in **47.8s**, then `make setup && make acceptance` passed **18/18** checks. Postgres initialised from an empty volume, so the extension init script ran for real. `make acceptance` was re-run to completion at `bb46732` from a wiped volume with nothing pre-started, which is the same chain minus the `git clone`. Commits after that (`f0cb5a6` palette, `14abb68` docs) were verified in place rather than by re-cloning, because the host disk filled (B2). Of everything post-clone, only the Makefile `browsers` target touches the setup path, and it was exercised including its ~100 MB first-run download |
| 2 | CI green | **VERIFIED** | Run **#3** at commit `4c1643f` on `github.com/Tahmudun/Nightshift`: all five jobs green — `python`, `web`, `migrations`, `e2e`, `secrets`. https://github.com/Tahmudun/Nightshift/actions/runs/30528565491 · Longest job 129s, inside A14's five-minute target. Runs 1 and 2 failed and were worth more than a first-try pass: between them they exposed a secret scan that had never executed, a Postgres image that did not exist, a formatter hook that could never resolve, a drift probe comparing our models against the whole server, and a migration path that rolled back every upgrade while exiting 0. Every one of those lived in configuration no local command runs, which is precisely the gap this row exists to close |
| 3 | Migrations apply and roll back | **VERIFIED** | Against live PostGIS 16 + pgvector. Before: 12 tables, 8 enum types. `make migrate-down` → the 8 project tables and **all 8 enum types** dropped, leaving only `alembic_version` and PostGIS's own `geography_columns` / `geometry_columns` / `spatial_ref_sys`. A downgrade that forgets `DROP TYPE` leaves enums behind and this is how you see it. `make migrate` → 12 tables and 8 enums restored; re-seeding produced a byte-identical corpus (10 jobs, 21 locations, same confidence split) |
| 4 | `/health` reports DB + Redis honestly, including when they are down | **VERIFIED** | Real containers stopped, not mocked. Both up → `200 {"status":"ok",…"database":{"ok":true,"detail":"postgis + pgvector present","latency_ms":4.27},"redis":{"ok":true,"detail":"PONG","latency_ms":3.2}}`. Postgres stopped → `503 "degraded"`, `database.ok:false`, `detail:"ConnectionRefusedError: [Errno 61] Connection refused"`, **redis still `ok:true`** — the two are reported independently. Redis stopped too → both false, with distinguishable details. `/health/live` stayed `204` throughout, as a liveness probe should. Both restarted → `200`, and `/stats` still reported all 10 jobs open: an outage closed nothing (I3) |
| 5 | One real Greenhouse board's jobs appear in the browser | **VERIFIED** | Board fetched live 2026-07-29: `boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true` → HTTP 200, 5,309,493 bytes, 426 postings, 134 naming New York. 10 recorded verbatim into a committed fixture. Now rendered in a real Chromium via `apps/web/e2e-seeded/` — **6 tests, all passing** — which reads the expected titles from the API at run time and finds them in the DOM. Also asserts the A2 multi-location rows, the I7 "committed fixture" badge, and that no job ladder claims verified/approximate placement |
| 6 | No secrets committed | **VERIFIED** | No key-shaped strings anywhere in the tree (scanned for `sk-*`, `AKIA*`, `ghp_*`, PEM private keys). `.env` is gitignored (`.gitignore:2`), confirmed via `git check-ignore`. Only credential-shaped value in the repo is `nightshift_dev_only`, the local compose password, confined to the files entitled to contain it. `tests/test_env_example.py` asserts this rather than trusting it. **gitleaks itself had never executed until 2026-07-30** — its config used a negative lookahead, which Go's RE2 cannot compile, so it panicked at config load on every invocation (see the session log). Now: `gitleaks detect` over full history exits 0 on gitleaks **8.24.3**, the version the action pins, and a planted `nightshift_dev_only` in a non-allowlisted file exits 2 — so the rule is proven able to fail |

**M0 is complete.** All six rows are verified with recorded output above.

Row 2 was not a formality, and the record shows it: three CI runs were needed,
and the two failures found five defects that every local command had passed
straight over. CI is the only thing that runs the `migrations` up → down → up
sequence, the drift probe, and the secret scan on every change, and it is where
the `e2e` job guards acceptance row 5 from regressing.

---

## Before M1 starts

Carried from `docs/reviews/milestone-0-review.md` so a new session does not have to
open it. Do these in order; items 1 and 2 are the ones that get expensive later.

**Items 1, 2 and 3 were Tasks 3–5, 8 and 9 of the M1a plan — all three are now
done**, marked below with the commits that closed them. They stayed listed
here as well because this file is what a cold session reads first; the plan
was where the ordered steps lived. Items 4 and 5 were not in M1a and remain
open — 4 waits for geocoding, and 5 is a one-line cleanup with no milestone
attached.

The board-discovery design (`docs/architecture/board-discovery.md` §14) depends on
the first three and does not replace them. Item 1 is a hard prerequisite: NYC-ness
is derived from parsed locations, so a first-provider parser caps the accuracy of
everything downstream. Item 2 stops being theoretical the moment polling becomes
queue-driven (ADR 0007) — concurrency above 1 is the point of that design.

1. **DONE — Write Lever and Ashby location fixtures before touching the parser.**
   Fixtures added at `43dd80a`; the parser was then widened and two real
   fabricated-city bugs fixed at `96a4e16`, `12da0ce`, `d81b03c` (ADR 0008
   accepted at `031a6b9`). `tests/test_locations.py` now has 145 assertions
   (measured 2026-07-30; 98 at M0) across three providers' shapes rather than
   one. (W1)
2. **DONE — Make `get_or_create_source` / `get_or_create_company` upserts.**
   Fixed at `1b37ed9` (`ON CONFLICT DO NOTHING` + read, not check-then-insert).
   No longer a landmine for the moment worker concurrency goes above 1.
3. **DONE — `domain/ingestion.py` and the API routes now have tests.**
   `domain/ingestion.py` covered against a real database at `5573231`
   (vacuous-assertion fixes at `c677822`); the API routes covered in this
   session's commit (`services/api/tests/test_routes.py`, M1a Task 10) —
   `/health`, `/health/live`, `/jobs`, `/jobs/{id}` against the app's own
   dependency-injected session, not a mock.
4. **Re-read `_replace_locations` when geocoding lands.** It deletes and reinserts
   location rows; once coordinates are resolved it must not discard them. Today
   there is nothing to lose, which is the only reason it is safe.
5. **Delete the redundant ordering in `_existing_location_signature`** — the caller
   wraps it in `set()`. (W4)

Not blocking M1, deferred deliberately to M4's accessibility pass: no test asserts
focus-visible styling, and the confidence ladder has never been checked with a real
screen reader.

---

## Verified locally (recorded output)

These ran on this machine and passed:

| Check | Command | Result |
|---|---|---|
| Python format | `ruff format --check services/api` | 45 files already formatted |
| Python lint | `ruff check services/api` | All checks passed |
| Python types | `mypy nightshift` | Success: no issues found in 31 source files (strict) |
| Python tests | `pytest -q` | **856 passed**, zero skipped (local, 2026-08-03; 804 at M1 close, 607 at M1c). Read from the output rather than computed — an earlier draft of this line said 797, a real measurement taken before the `/boards` tests existed |
| Web types | `tsc --noEmit` | clean, `strict` + `noUncheckedIndexedAccess` + `exactOptionalPropertyTypes` |
| Web lint | `eslint . --max-warnings 0` | clean |
| Web tests | `vitest run` | **63 passed** (8 files; 42 at M1 close) |
| Colour contrast | `vitest run colour-contrast` | 16 assertions on measured WCAG 2.1 ratios |
| Web build | `next build` | compiled, 7 static routes, 102 kB shared JS |
| E2E — degraded (no API) | `make test-e2e` | **5 passed** in 15.0s |
| E2E — seeded corpus | `make test-e2e-seeded` | **27 passed, 1 skipped**, 53.3s — 7 new on search and the detail pages (20 at M1 close). The skip is honest: `an unchanged board is not presented as a problem` needs a board that has answered `304`, and the seeded stack has polled nothing |
| Migration renders | `alembic upgrade head --sql` | full DDL emitted, 8 tables, 8 enums |
| Migration round trip | `make migrate-down && make migrate` | 8 tables + 8 enum types dropped and restored, live cluster |
| Whole-stack acceptance | `make acceptance` | **18 checks + 20 browser tests**, re-run 2026-08-03 at `d3738b6`; seeded corpus 31 jobs / 3 companies / 62 locations, plus **22 board poll schedules, none polled** |
| Migration round trip (M1d) | `make migrate-down && make migrate` | `0003` and `0004` both reversible against the live cluster. `board_tier` confirmed absent from `pg_type` after the downgrade and present after the upgrade — checked directly rather than inferred from a clean exit |
| Model/migration drift | `alembic check` | No new upgrade operations detected |
| Conditional poll, live | `nightshift poll --ats greenhouse --token datadog` ×2 | `200` then **`304` in 0.009s**, job state byte-identical across eight measures |
| Live source reachable | `GET /v1/boards/datadog/jobs` | HTTP 200, 426 postings |

**Total: 951 automated tests passing** (856 Python, 63 web unit, 5 degraded e2e,
27 seeded e2e), plus the 18 assertions in `scripts/verify.py`, which are not
pytest tests but do gate `make acceptance` with an exit code. Was 871 at the
close of M1.

M1d added 197 Python tests. The ones that carry the milestone are small in
number: `test_an_unchanged_posting_takes_no_miss_when_it_is_not_refetched`,
`test_a_304_writes_no_job_state`, and
`test_two_workers_merging_the_same_pair_leave_one_survivor`. Each was
mutation-checked, and the last was run eight times because one green run proves
nothing about a race.

**`tests/test_merge_concurrency.py` deliberately does not use the `db_session`
fixture.** That fixture holds one transaction and rolls it back, which is
correct isolation for every other test in the suite and precisely wrong for a
race: two sessions inside one transaction cannot contend, so the defect under
test could not occur. Those three tests commit, contend for real against
Postgres, and truncate after themselves.

**That gap is now closed, and it was closed by reading rather than by
inferring.** At M1a those tests skipped in CI (no `postgres` service) and the
fix had never been proven. `gh` was installed this session, so CI run #10's
`python` job log was read directly: `467 passed, 2 warnings` with no skip
line. The `Fetch the embedding model` step ran too, which matters for the same
reason — the real-model tests and the similarity half of the dedupe suite skip
themselves when the weights are missing, so without that step CI would have
been green while never testing the component the threshold depends on.

Re-run in the M1a session on 2026-07-30 (Task 10, closing M1a): Python format,
lint, types, tests (via `make check`); web types, lint, unit tests (also
`make check`, unchanged at 35 — no web code changed this plan); and the whole
stack via `make acceptance`, including the seeded e2e suite. Python went from
204 to 336 tests (Lever, Ashby, the widened location parser,
ingestion-against-a-real-database, and the new API route tests all landed in
this plan), and `make acceptance`'s seeded corpus grew from 10 jobs/1 source
to 31 jobs/3 sources because `make seed` now loads all three fixture boards
(M1a Task 10 step 3) — a deliberate, permanent change to the dev database, not
drift. Migration round-trip, colour contrast as a standalone command, web
build, and the live-source-reachable check were not re-run this session; their
last verified values stand at `f0cb5a6` / `14abb68`.

### What those tests actually cover

The counts are only meaningful if the tests can fail. The invariant-bearing ones:

- **I1 (no fabricated locations)** — 159 location-parser assertions (measured
  2026-07-30: `pytest tests/test_locations.py --collect-only -q`, up from 145
  earlier the same day), up from 98 at M0, driven by
  `tests/fixtures/locations.yaml`, whose cases are real unedited
  `location.name` strings from the three recorded boards
  (Greenhouse/Datadog, Lever/Alloy, Ashby/Ramp) plus labelled synthetic edge
  cases. Includes the ten-location posting that mixes one physical office with
  nine remote states. Plus: `test_never_produces_coordinates` asserts
  structurally that `ParsedLocation` has no latitude/longitude field at all;
  `test_country_only_does_not_round_up_to_city_only`;
  `test_unrecognised_country_is_unknown_not_guessed`. On the web side, six Zod
  tests reject a point whose confidence does not justify it, in both directions.
  **Pre-merge review, fixed 2026-07-30: two latent fabricated-city/on-site
  bugs, same class as the Vancouver/BC and NY(HQ) fixes above, neither yet
  seen in a recorded payload.** `parse_location_list` — the entry point
  Lever's `categories.allLocations` and Ashby's `secondaryLocations` actually
  call — never applied the `;`/`|` segment split its own module docstring
  says both providers use; `"New York, NY; Boston, MA"` as one array element
  parsed as a single segment with city `"NY; Boston"`. Separately, a
  trailing parenthetical Remote (`"Austin, TX (Remote)"`) was lifted out
  before Remote detection ran and then never re-checked, resolving
  `city_only`/`on_site` instead of `remote`. Both fixed in
  `nightshift/domain/locations.py`; both pinned with `synthetic: true`
  fixture cases, the first also exercised through `parse_location_list`
  directly (`test_list_entry_point_matches_field_entry_point`) rather than
  only through `parse_location_field`, since that was the entry point the
  bug actually lived in.
- **I3 (no silent closure)** — `TestInvariantI3`, six cases: 404, connect
  timeout, 503, malformed JSON, and a 200 with the wrong shape all produce
  `ok=False`; a genuine empty board produces `ok=True` and
  `is_authoritative_empty=True`. That last one matters — without it the
  invariant could be satisfied by never trusting anything.
- **A10 (fields that are usually null)** — `test_absent_deadline_stays_none`,
  `test_last_modified_is_never_stored_as_a_publication_date`,
  `test_pay_transparency_range_is_extracted` (asserts `salary_period is None`,
  because Greenhouse states no period and inferring one from magnitude would be
  a guess presented as data).
- **A2 (many locations per job)** —
  `test_multi_location_posting_yields_one_row_per_place`, on real data.
- **Determinism** — `test_normalization_is_deterministic` and
  `test_parse_is_deterministic`, both asserted from M0 so M1's "byte-identical
  output twice" criterion cannot quietly become false first.
- **Company identity** — 27 assertions (measured 2026-07-30) organised around
  the two ways `normalize_company_name` can fail: splitting one employer in
  two, or merging two real ones. Includes the false merges a fuzzy matcher
  would make (Meta/Metabase, Ramp/Rampart) and the suffixes that must *not*
  be stripped (Palantir vs Palantir Technologies). **This suite found a real
  bug** — see the session log.
- **Board registry** — 35 assertions (measured 2026-07-30, up from 29 at M0)
  on the file that decides which boards get polled, where a typo means
  silently never seeing a company's jobs. Includes path-traversal rejection
  on the token, since it is interpolated into a URL, and the closed-set test
  pinning the pollable set to exactly `{greenhouse:datadog, lever:alloy,
  ashby:ramp}`.

---

## What exists

### `services/api` — FastAPI + ARQ (one deployable, A11)

```
nightshift/
  config.py              pydantic-settings; refuses to start on a bad value
  logging.py             structlog, console locally / JSON in production
  cli.py                 seed | ingest | enqueue | stats
  adapters/
    base.py              JobSourceAdapter Protocol, FetchOutcome, RawJob
    http.py              PoliteClient — the ONLY module importing httpx
    greenhouse.py        real adapter, field shapes read off a live response
    lever.py             real adapter; no updated_at, no company name (M1a)
    ashby.py             real adapter; no updated_at, no company name (M1a)
  domain/
    locations.py         location parsing; I1 lives here
    companies.py         conservative company-name normalization
    registry.py          board-registry.yaml loading + validation
    ingestion.py         fetch → preserve → normalize → persist
  db/
    base.py              declarative base, 8 PG enums as StrEnum
    types.py             UTCDateTime — rejects naive datetimes at the boundary
    models.py            8 tables
    session.py           one async engine per process
  api/
    main.py              app factory
    routes/health.py     /health, /health/live
    routes/jobs.py       GET /jobs, GET /jobs/{id}
    routes/sources.py    /sources, /ingestion-runs, /stats, /registry
  workers/
    main.py              ARQ WorkerSettings, hourly cron at :17
    tasks.py             ingest_greenhouse — one real task, not a no-op
migrations/              alembic, async env, one reversible migration
tests/                   336 tests (pytest -q, measured 2026-07-30); fixtures/ committed
```

**Schema (8 tables):** `users`, `companies`, `sources`, `source_job_records`,
`jobs`, `job_locations`, `job_source_links`, `ingestion_runs`.

Deliberately narrower than PRODUCT-SPEC §6 — applications, match results,
snapshots, and user skills arrive at the milestone that reads them. What is here
is shaped for what comes later: `users` exists so every user-owned table can
carry a real FK from its first migration (A3); raw payloads are preserved and
canonical jobs are reachable only through `job_source_links`, so M1's dedupe adds
a merge step rather than restructuring anything.

### `apps/web` — Next.js App Router

```
src/
  app/layout.tsx         shell: wordmark, ModeNav, HealthTelemetry, skip link
  app/explore/           jobs list + confidence legend + corpus readout
  app/operate/           source health table
  app/analyze/           corpus readout + why nothing is geocoded
  components/
    ConfidenceLadder     the signature element (below)
    CorpusReadout        counts incl. "placeable on a map: 0"
    HealthTelemetry      polls /health every 10s; can say "down"
    JobRow / JobList     one confidence ladder per location
    SourceHealthTable    labels fixture sources in gold
  lib/
    schemas.ts           Zod at every network boundary; I1 re-checked here
    api.ts               single API client
    confidence.ts        the five-value scale + user-facing meanings
  app/colour-contrast.test.ts   WCAG ratios computed from the real tokens

  --- the city (M4), which the tree above predates ---
  app/explore/city/      the map route; CityMap owns lifecycle and nothing else
  components/
    CityMap              builds the map, adds the layer, subscribes outside React
    CityRail             owns placement for the whole right-hand side
    CameraControls       the gesture surface, in buttons
    CityRoster           who is hiring; the field's non-3D equivalent (§5.6)
    CityDetail           the selected role, and the only writer of the URL
    CityLegend           §6's thirteen rows, live counts, the archive toggle
    CitySignals          the census, and what is not on the city
  lib/map/
    darkStyle.ts         every layer, testable with no GPU
    camera.ts            poses, limits, interruption, reduced motion
    debug.ts             the handle the browser suite reads the scene through
  lib/city/
    scene.ts             zustand; the one place the map and the list agree
    unresolvedField.ts   where a role goes when nobody said where it is (§4.8)
    treatments.ts        `city.md` §6 as one table and one pure function
    beacon.ts            the bodies: per-instance colour, strength, pulse, size
    markMesh.ts          the four shapes §6 puts *on* a body
    labelAtlas/labelMesh one texture, N employer name plates
    selectionMesh.ts     the reticle — interface state, not a §6 row (ADR 0027)
    signalLayer.ts       the custom layer: Three.js in MapLibre's context
    pick.ts              raycast against the matrix the last frame drew with
    mercator.ts, focus.ts, selection.ts
e2e/                     Playwright with NO API — the degraded path
e2e-seeded/              Playwright against a seeded stack — acceptance row 5
playwright.config.ts     starts the web server only
playwright.seeded.config.ts    starts web + API, gated on /health
```

Two Playwright configs on purpose. `e2e/` proves the app says "api unreachable"
rather than rendering an empty list, so it must run with the API *absent* —
starting one would make it pass for the wrong reason. `e2e-seeded/` proves real
rows reach a browser. Neither substitutes for the other, and CI runs both in that
order.

**The confidence ladder** is the product's signature UI element: five ticks of
increasing height, lit to the precision actually achieved, with a text label and
an accessible name. It appears on every location of every job. In M0 no ladder
anywhere in the app rises above three ticks — which is the truth, rendered.
§4.3 requires the interface to document its own visual language, so the legend
ships as a permanent panel rather than a tooltip (§12.4: no essential
information available only through hover).

### Infrastructure

- `infra/docker-compose.yml` — postgres + redis, real healthchecks. The Postgres
  healthcheck asserts PostGIS **and** pgvector exist, so "healthy" means
  "usable" rather than "accepting connections during initdb".
- `infra/postgres/Dockerfile` — see ADR 0001.
- `Makefile` — 20 targets; every command runs from the repo root.
- `scripts/dev.py` — runs api + worker + web with correct group shutdown.
- `scripts/doctor.py` — names a missing prerequisite instead of failing deep in a
  pip build. It reports B1 correctly.
- `scripts/record_fixture.py` — regenerates a committed fixture from a live board.

### Documentation

- 8 ADRs: 0001 Postgres image, 0002 I1 in the schema, 0003 `FetchOutcome` and I3,
  0004 fixture seeding labelled in the data, 0005 batch approval of discovered
  boards, 0006 Common Crawl as a discovery source, 0007 two-phase conditional
  polling, 0008 decided bare place names (M1a).
- `docs/architecture/costs.md` — required from M0 by A9. **$0/month, 0 API keys.**
- `docs/QUESTIONS.md` — **2** open questions (Q1 Gmail, Q2 deployment cost),
  none blocking. Q3 (registry scope) was answered 2026-07-30 — see the M1
  design session log entry below.

---

## Not real yet

Everything half-built or standing in for something real. Nothing in this list is
presented to a user as working.

| Thing | What it actually is | Real at |
|---|---|---|
| Four rows of `city.md` §6 | **Not drawn, named as not drawn in the interface's own legend** (ADR 0028). *Approximate location*: no role in this corpus resolves to an area — it takes a confirmed office at approximate confidence and there are none. *Closed / fading afterimage*: an afterimage belongs to the session that watched a role close, and closed listings are absent from a cold load by design. *Applied as a "solid illuminated **building**"*: nothing here stands on a building, so the beacon's own body fills instead. *Urgent deadline*: drawn, but no posting in the corpus carries `application_deadline`, so the legend counts it rather than implying it is live | The first two at **M5**; the third when a confirmed office exists; the fourth if any provider ever publishes a deadline |
| Roles at a confirmed office, or in an area | **Counted, named, and not drawn.** `arrangeUnresolved` lays out the unresolved field and ignores every other placement kind, so a `building` or `area` role appears in the census panel's counts and nowhere on the city. It is **0 today** — `data/company-locations.yaml` is blank and no posting names a street — and the panel now says *"n of these are not drawn on this map yet… missing from the sky, not from the corpus"* the moment it stops being 0. Found by the M4c acceptance walk, which is the only thing that has ever executed that branch | The renderer's building and area treatments are **M4d/M5**, and arrive with the first confirmed address |
| The unresolved field's legibility past a few hundred roles | **Real, and measured at the wrong size until now.** The layout wraps at six employers per row, so 200 employers recede 34 rows deep: the name plates at the back overlap into an unreadable strip and a column of 25 roles is ~1,125 m tall. Legible at the 31 roles this corpus has, and `docs/reviews/milestone-4c-scale.png` shows what 5,000 looks like. The roster stays usable at either size, so the *information* is never lost — only the view | **M4d**, beside the adaptive quality tiers: level-of-detail on the plates, a camera that frames the field, clustering |
| The city's five demo applications | Real `Application` rows with real append-only event trails, written by `make seed` through `save_job` and `change_stage` — the same functions the UI calls, no shortcut. They are **seeded data, not a user's**: one at each stage §6 draws, so the encoding has something to encode in `make demo` and something to assert in the seeded browser suite | Permanent. This is the demo path, not a stopgap |
| `data/skills.yaml` coverage against real postings | **Largely addressed at M3a.1, and the remainder is now a decision rather than a gap.** The vocabulary went from **73 entries to 107** — 34 added, counted from the file
rather than from memory, because the commit message for this work says 36 and is
wrong: ML frameworks (JAX, LangChain, HuggingFace, DSPy), accelerators (CUDA, ROCm, Triton, SYCL), HDLs (Verilog, VHDL, SystemVerilog), Windows/network/security administration (Active Directory, SIEM, EDR, SSO, MFA, VPN, DNS, TCP/IP, PowerShell, Windows, macOS, firewalls), and business systems (Salesforce, Google Sheets, Microsoft 365). Recall moved 0.459 → 0.861. **What is deliberately still absent**: structural engineering codes (ACI 318, ASCE 7, IBC, IFC, AISC, FM Global), treasury systems (Kyriba, GTreasury, Trovata, TMS), accounting standards (US GAAP, IFRS), and words too ordinary to match safely (`Word`, `MS Office`). Those are real requirements of real postings in the corpus and are not software skills — adding them would raise recall by teaching the product a domain it does not serve | Closed as vocabulary work. The residual absences are a scope decision, revisited only if the product's scope changes |
| Eligibility answer key (`tests/fixtures/eligibility/labels.yaml`) | **Filled in, and model-labeled rather than human-verified.** All 60 postings × 9 fields were labeled 2026-08-04 by a browser-side Claude reading the recorded excerpts, with the web explicitly off — the grader compares against text the extractor also sees, so a label sourced from outside that text marks a correct extractor wrong. Audited on install: 0 of 199 named technologies absent from the posting text, and no sponsorship, graduation-window, internship or years claim unsupported by the text. Two `+equivalent` calls read an escape hatch worded without the word "equivalent" (`akunacapital/8035515`, `openai/8fb1615c…`) and are the entries most likely to be wrong. Not spot-checked by a human | Human spot-check of ~10 entries, unscheduled |
| `FixtureGreenhouseAdapter` (`cli.py`) | Subclasses the real adapter, overrides only `fetch_board` to read a committed JSON file. Constructed with no HTTP client, so it cannot make a request. Attributed to source `greenhouse_fixture` with `source_type='fixture'`, badged **"committed fixture"** in the Operate UI. ADR 0004 | Permanent — this is the offline demo path, not a stopgap |
| Geocoding | **Built in M4a and correct to say so.** `domain/geocoding.py` behind a Protocol, the NYC GeoSearch adapter with committed fixtures, the permanent cache that refuses to store an outage, and the office loader. **What is still true: no coordinate has been written**, because the worksheet below is blank — not because the geocoder is missing. `mappable_locations` reads 0 and the page now says *"no posting states a street"* rather than *"nothing geocoded yet"*, which is the difference between a property of the data and a missing feature. Rungs 2–3 (Nominatim, neighbourhood centroids) are still unbuilt and stay deferred: they produce `approximate` points the office loader refuses by design | Done at **M4a**. Coordinates appear when the worksheet has a row |
| `company_locations` table and `data/company-locations.yaml` | **Table, worksheet and loader all exist and are now connected.** The table, its migration and its constraints landed at M4a; `read_worksheet` and `load_offices` at M4a/M4b; **`make offices`, the thing that calls them, at M4e Task 1 on 2026-08-16** — until then the worksheet led nowhere and no number of typed addresses could have changed a pixel. The file now covers all **23** registry boards with every `street_address` **blank**, which is a correct answer rather than a gap (Q7 answered: "as many as you'd like"). `read_worksheet` refuses four kinds of entry, the sharpest being an address that names no street — somebody typing here is asserting *an office is at this address*, and a weaker version of that assertion is not what they meant. Until a row is filled, the honest render is every job in the unresolved layer | Table and promotion path **done**; end to end, verified live (Datadog → BIN 1087186). **The renderer still cannot draw a `building` placement — that is M4e Task 6.** The row count is the human's |
| Street-level placement of any job | **Impossible from this data, and now measured rather than assumed.** 0 of 247 postings, 139 distinct location strings, 10 fields, 3 providers. Reproduce with `./.venv/bin/python scripts/census_location_text.py`, which refuses to print a count until it has proved on that run that it can see a real address | Not a gap — a property of ATS data. Named on `/analyze/coverage` at **M4a** |
| Dedupe similarity threshold | **Real, thinly calibrated, and now with one real-world data point.** `SIMILARITY_THRESHOLD = 0.85` was derived from three labelled pairs. M1d's live Datadog poll merged two genuine postings on `similar_description` at **0.864** — the first evidence from outside the labelled set, and it landed close to the line. One observation is not a calibration and nothing was changed on the strength of it, but it is the first sign the number is doing real work at a real boundary. Re-derive as the fixture set grows | Unscheduled; revisit when more live boards are polled |
| ~~Merge concurrency~~ | **Fixed in M1d** (`408c768`). The defect was reproduced before being fixed — Postgres reported a real `DeadlockDetectedError` between two workers merging the same pair in opposite directions. Both rows are now locked in primary-key order, as two statements rather than one `IN` clause, because a single statement's lock acquisition follows the query plan rather than the sort. Mutation-checked: the caller's order deadlocks on 3 of 3 runs; the fix passed 8 consecutive | Done |
| Later-arising duplicates | Dedupe runs only on creation, deliberately: re-running the matcher every poll is how a settled merge starts oscillating. The consequence is that two jobs which become duplicates *later* — a title corrected on one board to match the other — never merge, and nothing reconciles them | No milestone. Revisit if visible duplicates are reported |
| `job_locations.geom` | Column and GiST index exist; always NULL | **M4a** |
| `normalize_title` | Whitespace and dash folding only. Deliberately does **not** attempt role-family normalization — asserted by `test_does_not_attempt_role_family_normalisation` | M3 |
| ~~`jobs.role_family`, `jobs.seniority`~~ | **Filled in as of M3b (`cbcd5dc`), and this row said otherwise for a day.** `sync_classification` runs on every poll, ungated, and a freshly seeded database reads 16 `unclear`, 5 `director`, 4 `senior`, 3 `mid`, 2 `staff`, 1 `internship` — checked against Postgres rather than inferred. NULL still means "never classified" and stays distinct from `unclear`. **This is the fifth time a list in this project has quietly stopped describing the thing it names, and the fifth in the same direction**: the code moved and the row did not | Done |
| `jobs.internship_season`, `jobs.internship_year` | **Real, and null on all 31 seeded jobs — which is the correct answer, not a gap.** The seed holds one internship, "Software Engineer Internship, Android", whose title states no season and no year. Across the wider recorded corpus 8 of 19 internships state a season and 10 of 19 a year. The filter reports what it hid rather than returning an empty list | Done |
| Stripe board registry entry | Verified live (HTTP 200) but `status: disabled`. Polling more boards before the closure machine exists would mean ingesting jobs the system cannot honestly age out | M1 |
| `/registry` route | Still read-only. The *crawl-index* half of the resolution pipeline now exists (M1c) and fills `data/board-candidates.yaml`; the careers-page probe does not | M1c partly, careers probe unscheduled |
| Lever board discovery | **Does not exist and cannot, from the crawl archive.** `jobs.lever.co/robots.txt` disallows CCBot, so no Lever page is in Common Crawl (ADR 0006). `sources/careers_probe.py` is designed but not built: it needs a list of employer domains and nothing in the repo has one, and guessing domains would be the fabrication this milestone exists to prevent. Named as the first blind spot on `/analyze/coverage`, with the structural reason, and a browser test asserts it reaches the screen. **Lever boards enter the registry only by hand** | No milestone. Needs a domain source first |
| Community-snapshot discovery source | Designed in `board-discovery.md` §4, not built, same reason as the careers probe | No milestone |
| Discovery beyond Ashby | `PROVIDER_PATTERNS` includes both Greenhouse board domains and the code paths work, but **no Greenhouse crawl fixture is recorded**, so `make discover --provider greenhouse` has never run against real data. Greenhouse *validation* is tested, on the recorded `6sense` board | M1d |
| The 2,605-token figure | Not re-measured by M1c and never claimed by it. The committed slice is **400 rows → 23 tokens**, the alphabetical head of one provider (`0g`…`abridge`). Common Crawl's index 504s at `limit=6000`, so a full harvest needs paging that does not exist | M1d |
| ~~Discovered boards in the registry~~ | **19 promoted in M1d** (`d3738b6`), on the human's decision. 4 boards → 23, 171 insertions and 0 deletions, nothing lost or modified. Two `Abridge` candidates and two `empty` boards remain withheld for individual review under ADR 0005 | Done |
| Ashby's `address.postalAddress` | Still deliberately unread by `AshbyAdapter.normalize`, and **M4a closed the question in the opposite direction to the one this row expected**. It was waiting for geocoding to exist; the census then showed the field carries `addressLocality`/`addressRegion`/`addressCountry` and **never `streetAddress`**, on any posting, from any employer. So reading it would upgrade nothing — it resolves to the same city name the free-text string already gives | Not a gap. Closed by measurement at **M4a** |
| 3D city, map, MapLibre, Three.js | **The city renders, can be driven, and has roles on it.** `/explore/city` draws New York offline from two local archives on `maplibre-gl@5.24.0` — streets, water, and 1,083,024 extruded structures at measured heights — with the full §9.3 gesture surface, a keyboard, and a control panel, all proved in a browser by `e2e/city.spec.ts`. **Three.js and the job data arrived at M4c Tasks 1-2**: every open role is a floating beacon above the skyline and none is on a building, which the page states in those words — a map that looks finished and is empty is indistinguishable from one that is broken. **This row said "no camera controller" for two days after the controller shipped** — the sixth time a list here has quietly stopped describing the thing it names, and again in the same direction | Buildings **done, M4b Task 4**; camera **done, M4b Task 5**; signal layer drawing at **M4c Task 2**; labels, sorting and the roster at **Task 3**; picking, the reticle and the shared selection at **Task 4**; §6's treatments and the in-interface legend at **Task 5**; the acceptance walk at **Task 6**. **M4c is complete.** What remains for M4d: frame-time numbers, adaptive quality tiers and automated accessibility tests |
| The signal layer's renderer | **Built and drawing (M4c Task 2).** Three.js in MapLibre's context, one instanced mesh, one draw call, N transforms — every unresolved role is a floating beacon above the skyline, grouped into a column per employer. What is **not** built: labels (a column is an anonymous stack until you know what it is), picking, selection, the §6 treatments and the legend. Nothing is on a building, and nothing may be until an office is confirmed | Tasks 3-5 |
| Window speckle on buildings | Not built. §2.1's treatment is edge light *plus* lit windows; the extrusion delivers the first via `fill-extrusion-vertical-gradient` and a height-driven colour ramp. The speckle needs a texture, a texture needs a sprite, and a sprite is a network call this style has spent three tasks refusing | The Three.js layer — **M5**, not scheduled sooner |
| ~~The published buildings artifact~~ | **Published 2026-08-12** as release `buildings-20260812`, 109,555,308 bytes — the size the manifest pins. Proved by deleting the local copy and re-fetching from the public URL, which is the clean-clone path, digest and all. The optional/required split built while it was unpublished stays: a re-bake reopens the same window every time, and `make tiles-strict` in CI is what closes it | Done |
| Map labels — neighbourhood and street names | **Not drawn, and not an oversight.** Every symbol layer needs a `glyphs` URL and every glyph URL is a network call, which `make demo` may not make. Self-hosting the font stack is a second baked artifact on the ADR 0022 pattern; it buys neighbourhood names, which are not in M4b's acceptance. The style declares no `glyphs` and a test asserts it stays that way | Unscheduled. Needs a second baked artifact or a decision to accept a network call |
| Basemap tiles | **Real, pinned, verified and drawn.** 95,348,122 bytes of NYC vector tiles, Protomaps build `20260810`, downloaded once by `make setup` and checked against a committed sha256 before it is installed. Served over byte ranges by `/api/tiles/basemap`, and on screen since Task 2 — this row's "the one thing it is not yet is *drawn*" was three tasks out of date. **Not a mock and not a stopgap**: the permanent offline tile source (ADR 0022) | Done at **M4b Task 1**, drawn at **Task 2** |
| NYC building footprints | **Loaded, baked and drawn.** NYC Open Data `5zhs-2jue` → 1,083,024 structures at measured `height_roof`, baked into `nyc-buildings-20260812.pmtiles` and published as a release asset on the ADR 0022 pattern. 732 have no recorded height, take a documented 25 ft default, and **are counted on screen**. Never queried per frame; never in PostGIS, which A4's approach does not need. The Protomaps archive's own OSM `buildings` layer still **must not be extruded** — those are guessed heights — and the test that guards it matches on the *source*, not the layer name, because both archives call their layer `buildings` | Done at **M4b Task 4** |
| Auth | None. Single seeded `dev_user`, id in config (A3). Every user-owned table will still carry a real `user_id` FK from its first migration | M5 |
| Live polling of Lever/Ashby | **Fixed in M1d.** `ADAPTERS` in `domain/polling.py` covers all three providers, `sync_board_poll_state` gives every pollable registry board a schedule, and `nightshift poll --ats lever --token alloy` works. `active` in the registry now means what an operator would assume. **Caveat:** only `greenhouse:datadog` has actually been polled live end to end. Lever and Ashby were measured serving `304` during design, but their conditional path has been exercised only against fixtures | Polled path proven on one provider; the other two are wired and fixture-tested |

---

## Session log

### 2026-08-03 — M1d: conditional polling, and the close of M1

Eleven tasks, eleven commits. A `304` now costs one request and writes nothing,
which closes the last M1 criterion.

**Fourteen defects. Ten were in code that reported success** — the same pattern
M1a, M1b and M1c each recorded, four milestones running. This time the sharpest
was self-inflicted and worth stating plainly.

**The pipeline had never been tested against Greenhouse.** After Task 4 made it
two-phase, live Greenhouse ingestion produced **zero jobs** and the suite stayed
green. Every ingestion, closure, merge and route test drove a stub wrapping
*Lever*, handed a `FetchOutcome` the test built itself — so the pipeline had
never seen a Greenhouse-shaped response, and outcomes constructed by tests
cannot disagree with what adapters actually return. I predicted the suite would
fail; it did not; the green run was the finding.

**ADR 0007's own optimisation creates a silent mass-closure bug.**
`apply_freshness` ages a record whose `last_seen_at` predates the run. Phase 2
deliberately never refetches an unchanged posting. Wire those together literally
and every unchanged posting on every Greenhouse board takes a miss per poll and
closes on the third — no error, damage landing three polls after the cause.
`FetchOutcome` now separates *listed* from *fetched*, and both halves of the
guard are mutation-checked.

**The same footgun appeared three times, so the type changed rather than the
call sites.** A `FetchOutcome` with postings but no `listed` set reads as a
board that listed nothing. It now derives one — a posting we hold the content
of was self-evidently on the board.

**`make seed` would have crashed.** `FixtureGreenhouseAdapter` inherited
`is_two_phase = True` from the real adapter, along with a `fetch_full_board`
that needs an HTTP client the fixture adapter deliberately lacks. The fixture
adapters — the thing that makes `make demo` work offline — **had no tests at
all**. There are now 24, and two consecutive `make seed` runs were verified to
leave 31 jobs open with zero misses.

**A real deadlock, reproduced before fixing.** The M1b review named the missing
`merge_jobs` row lock as the one thing M1d must not inherit. Postgres reported
it directly. Locking both rows in primary-key order fixes it, as two statements
rather than one `IN` clause, because a single statement's lock acquisition
follows the query plan rather than the sort. The mutation deadlocks on 3 of 3
runs; the fix passed 8 consecutive.

**`promote` was destructive in everything a human had written.** Found by
running `--write` for the first time in the project's history — it deleted ten
lines of rationale between entries, including the `Stripe` note addressed to
this very milestone. Now literally appended, asserted as
`after.startswith(before)`.

**Structural typing did the wrong thing quietly.** `isinstance` against a
runtime-checkable Protocol matches method *names*, so a single-phase Lever stub
that implemented them for convenience got pulled into a phase Lever has no
endpoint for. The pipeline gates on the flag and *then* narrows.

**Existing guards that earned their keep:** `test_repo_integrity` (added in M1c
after `.gitignore` swallowed a route) caught two new modules before they were
staged; `conftest`'s no-CASCADE truncate refused `board_poll_state` until it was
listed; the `job_merge_events` append-only trigger refused a test's cleanup
`DELETE`; the `jobs` check constraint refused a `closed` job with no
`closed_at`; and the registry closed-set test refused all 19 new boards until
deliberately reshaped.

**Two of my own tests were badly written and got stronger.** They grepped module
source for `nyc_presence` and borough names, and failed on the docstrings
explaining why neither belongs in the code. A test that greps prose punishes
documenting the rule. They now parse the module and strip docstrings.

**Two things written down turned out to be wrong**, corrected in place: phase 2
is Greenhouse-only, and the "no `updated_at` on Lever and Ashby" problem this
file recorded three times as M1d's most consequential inheritance dissolved once
someone measured the payloads.

### 2026-08-02 — M1c: board discovery

Six tasks, seven commits. The registry stops being a hand-written list and
becomes the reviewed output of a pipeline — and the pipeline's own output is
what found most of what was wrong.

**The design's central example board is dead.** `a3c41b8b71eff8c4` is the
live-but-unnameable board the entire approval gate is built around; the plan
says deleting its fixture "would hollow out the whole design". Probing it
before recording returned **404**, and it is absent from the July 2026 crawl
index in a range the committed slice covers (`a-place-for-mom` … `abridge`
brackets it), so it is gone rather than transiently missing.

What replaced it is stronger, and finding it was the useful part: **Ashby
serves HTTP 200 with `<title>Jobs</title>` for any token that does not
exist** — verified against both the dead token and a made-up one, byte-identical
7,128-byte pages. So "a live page that names no employer" is now a committed
recording rather than the hand-written stub the plan specified. The plan's own
test synthesised that HTML; a recording is strictly better evidence.

**Four defects, three of them found by running something rather than reading
it.** That is the same pattern M1a and M1b recorded — three milestones running.

1. **Two candidates naming one employer both reached the approval report.**
   `Abridge` and `abridge`: two live Ashby tokens, one employer, 42 postings
   each. Found by `make registry-approve` on real validated data. The
   `name_collision` verdict compares against names already in the *registry*,
   so it is structurally unable to see a collision inside a single batch.
   Approving would have written two rows for one company, polled the same board
   twice, and handed dedupe 42 duplicate jobs. Fixed: both held, neither wins,
   and the report names what it withheld — an operator reading a report these
   were merely absent from would conclude the boards were never discovered.
2. **Harvested tokens were recorded as `unreachable`.** Found by reading the
   first real `make discover` output. That claims we tried and failed, about
   boards nobody had contacted, and the coverage page would have reported 23
   failures that never happened. Fixed by adding a sixth verdict,
   `unvalidated`, with `last_validated = date.min` so nothing downstream reads
   a never-contacted board as freshly checked.
3. **`test_validation_never_raises` was vacuous** — the one caught by reading.
   Its stub route key matched no URL, so the stub raised "no route" and the
   test passed without ever entering the branch it exists to cover.
4. **The plan's repo-root arithmetic was off by one** in two tasks.

**The token is not the name, about half the time.** Measured across the 23
Ashby tokens in the committed slice: 21 boards live, and **10 have a name that
differs from the token** — `0g`→"0g Labs", `a-place-for-mom`→"A Place for Mom",
`a-team`→"A.Team", `8fleet-inc`→"8Fleet Inc.". Deriving an employer name from a
token would be wrong roughly half the time, always in the direction of
inventing an employer. That is a far stronger basis for I2's rule here than the
design's single `0g` anecdote.

**Two gates, both mutation-checked rather than merely tested.** Making the
Ashby name fall back to the token classifies the junk board `live_named` with
`company_name='0g'` — the exact I2 fabrication — and exactly one test fails.
Dropping the verdict filter in `approvable` fails eight, including one that
drives the command a human actually types. Typing the coverage `count` field as
`int = 0` instead of `int | None` fails the route test, which is what keeps
"we cannot know" from silently becoming "there is no gap".

**The coverage page reports no percentage anywhere, and says why.** There is no
denominator — nobody knows how many tech roles open in New York — so a figure
like "we cover 73%" would be arithmetic on a number nobody has. Asserted three
ways: in the summary, in the text report, and in a browser test that fails if
any percent sign reaches the page.

**Deliberately not built: the careers-page probe, so Lever stays
undiscoverable.** It needs a list of employer domains and nothing in the repo
has one; guessing them would be the fabrication this milestone exists to
prevent. Carried honestly instead — `lever_undiscovered` is the first blind
spot on `/analyze/coverage`, it states the structural reason (Lever's own
robots.txt disallows CCBot), and a browser test asserts it reaches the screen.

**Also recorded:** `scripts/record_crawl_fixture.py` (Task 1) cannot run on
this host — it uses `urllib`, which has no certifi bundle here and fails TLS
verification. Task 3's recorder goes through `PoliteClient` and works. Common
Crawl's index 504s at `limit=6000` for `jobs.ashbyhq.com/*` while `limit=400`
succeeds, so any bulk harvest needs paging that does not exist yet.

### 2026-08-01/02 — M1b: the canonical spine

Ten tasks, ten separate commits, each mutation-checked. The engine — closure,
dedupe, embeddings — and the operational surface that makes both observable.

**The session opened by finding the repo ahead of its own notes.** PROGRESS
said M1a was "written, not started". It was finished, CI-green and already
merged as PR #1; the file was simply stale. Synced, removed the leftover
worktree, and — with Docker back — ran the database tests locally for the first
time ever: `350 passed`, zero skipped. Until that moment every local
`make check` on this host had reported `337 passed, 13 skipped` and nobody had
seen the other 13 run anywhere except by inference.

**Two decisions were the human's, and one of them was against my
recommendation.** ADR 0009 fixes closure at three misses *and* seven days, the
cautious end of three options offered. ADR 0010 admits embedding similarity
into dedupe; I recommended deterministic rules only. Both ADRs record who
decided what. The constraint that makes the second safe is that similarity is
unreachable until company, employment type, title and location already agree —
so it breaks ties and never matches on its own, asserted by
`TestSimilarityIsConfined` with a control case so its negative tests cannot
pass by the layer merely being broken.

**Three bugs, none of them found by reading code.**

1. **A merge silently dropped locations only the losing posting named.** The
   worst of the three. Board A says "Washington, DC"; board B says
   "Washington, DC" and "Austin, TX"; they share a location so they merge, and
   Austin cascaded away with the deleted row. A user filtering for Austin would
   never have seen the role, at the exact moment two sources agreed it exists
   there. Found by writing a throwaway probe with a deliberately asymmetric
   pair — every existing merge test used pairs whose location sets were
   identical, so the suite was green and blind. *A fixture that varies only in
   the dimension under test will not catch a bug in a dimension held constant.*
2. **Two descriptionless postings merged on their emptiness.**
   `content_hash(None)` returns the sha256 of the empty string — a genuine
   64-character digest, equal on both sides — so layer 2 found them identical
   and merged them on "identical content". The same failure shape as two null
   URLs matching each other, which `normalize_url` had already guarded. One
   guard existed and its twin did not.
3. **Alembic autogenerate produced three defects at once**, all of which would
   have failed at runtime rather than at review: it referenced `pgvector` and
   `nightshift.db.types` without importing either, and emitted a `CREATE TYPE`
   for `job_status`, which already exists and is in use by `jobs`. The M0
   migration leaves a note at its head about exactly this; that note is now
   load-bearing rather than historical.

**The similarity threshold was derived, not chosen.**
`scripts/derive_dedupe_threshold.py` scores the labelled set under the real
model: merges at 0.9693 and 0.9370, the distinct pair at 0.7640. Any value in
(0.7640, 0.9370] separates the set; 0.85 is the midpoint. The script refuses to
suggest a number when no separating window exists, which is the branch that
matters. **Three labelled pairs carry descriptions, so three points define this
number** — recorded in "Not real yet" as the thing most likely to be wrong in
a way no current test can see.

**The mutation that mattered most.** Making a failed board count as answered
fails two closure tests — and *not* the pre-existing
`test_a_failed_board_closes_nothing`, because one failed poll never reaches a
threshold. The damage only becomes visible three polls later. That is why the
new assertion is on the miss counter rather than on the status, and it is the
clearest example in this project so far of an invariant test that was true and
insufficient.

**`gh` was installed, and it had been failing for a reason unrelated to `gh`.**
The dead tap `homebrew/cask-versions` — a repository Homebrew itself deleted —
made `brew update` error, and since every `brew install` auto-updates first,
*any* package would have failed the same way. Untapped. That likely explains
part of the earlier Docker Desktop trouble too. With `gh` working, CI run #10's
log was read directly rather than inferred, closing the last inference in the
evidence chain.

**Deliberately not done:** a row lock in `merge_jobs`. Two workers merging
concurrently is unreachable at `max_jobs=1` and becomes routine the day ADR
0007's queue-driven polling lands. It is named in the M1b review as the single
thing M1d must not inherit unnoticed, and it should be designed against M1d's
real concurrency model rather than guessed at now.


### 2026-07-31 — Review session: state verified; host disk full again (B4)

A review pass requested by the human, run deliberately lean on a metered
budget. What was checked, and what it found:

- **Repo state matches this file.** Clean tree, 24 commits on
  `m1a-provider-breadth`, head `2c2594c` (docs-only commits past the
  CI-verified `430347a`), branch up to date with origin, PR still open.
- **`make check` green at head**: 337 Python + 35 web tests passed. The 13
  database-backed tests skipped — investigated rather than waved through, and
  the cause is environmental, not code: Docker cannot start because the disk
  is at 100% (180 MB free). Recorded as blocker **B4**; Docker Desktop was
  launched to run them, failed with `Docker Desktop is unable to start`, and
  was quit again. Nothing was deleted; the space measurements are in B4.
- **No code was changed.** The two known open cleanups ("Before M1 starts"
  items 4–5) are deliberately deferred with reasons, and the branch head is
  CI-verified green — pushing cosmetic changes would invalidate that evidence
  for no functional gain. This was a judgement call, on the record.
- Scope caveat, per I6: this session verified the branch's *claims* (state,
  checks, CI record) and relied on M1a's existing review layers — per-task
  review, mutation testing, the pre-merge fix wave, CI run #9 — rather than
  re-reading all 24 commits line by line. A full independent re-review of an
  already-multiply-reviewed green branch was judged not worth its cost.

### 2026-07-31 — M1a CI-green on the first run

PR opened; run #9 at `430347a` passed all five jobs — `python` 74s,
`e2e` 122s, `migrations` 55s, `web` 52s, `secret scan` 5s.
https://github.com/Tahmudun/Nightshift/actions/runs/30592177638

Notable against M0, which took three runs and whose two failures found five
defects — every one in a file no local command executes. The difference is
probably that the pre-merge fix wave verified the new `postgres` service
against a container matching CI's exact pinned image rather than trusting the
YAML, which is the same lesson M0's `manifest unknown` failure taught.

**The CI fix is confirmed working.** The `python` job ran
`Initialize containers` → `Create extensions` → `Migrate` → `Unit tests`, in
order, all green. Before this branch that job had no database at all and would
have skipped 13 tests while reporting success.

One honest gap: nobody read the `350 passed` line. Downloading Actions logs
needs admin rights on the repository, which the agent does not have, so the
claim "the database tests ran" rests on inference — the skip fires only when
the database is unreachable, and two earlier steps connected to it. Sound, but
it is inference. Expanding the "Unit tests" step in that run would settle it
outright, and doing so costs one click.

### 2026-07-30 — M1a pushed, PR pending

Branch `m1a-provider-breadth` pushed to origin: 23 commits from merge base
`3e3dee1`. **Not merged, and CI has never seen it.**

> Superseded 2026-07-31: the PR was opened and CI run #9 passed at `430347a`.
> Left as written — this entry records what was true when the branch was
> pushed, and editing a dated record to match later events makes it tidier and
> untrue.

The PR was not opened by the agent — `gh` is not installed on this machine, so
there is no way to create one from the CLI. The push output printed the
creation URL and it is recorded in "Next exact action" above. `brew install gh`
and `gh auth login` would let a future session open PRs directly; that is the
only thing standing between this repo and a fully automated finish.

Worth being precise about what "done" means here, because the file says
COMPLETE in several places: **every M1a acceptance claim in this file was
verified on a laptop.** `make check` (350 Python, 35 web), `make acceptance`
(18 checks + 6 browser tests), mypy strict, ruff, and a live-Postgres run of
the 13 database tests. None of it has been verified by CI, and the branch
changes CI configuration — including adding the `postgres` service without
which those 13 tests silently skip. Per I6 that gap is named rather than
glossed: laptop-green is evidence, but it is not the evidence M0 learned to
demand, and M0's own record is that every defect CI found lived in a file no
local command executes.

One process note for whoever runs the next plan. A subagent doing mutation
testing was killed mid-run by a usage limit, between "confirmed the test
fails" and "restore the code" — leaving the deliberate bug (`company_name =
board.token.title()`, the exact I2 fabrication) live in the working tree and
uncommitted. It was caught by checking `git status` before trusting the
agent's report. Mutation testing is worth doing and found three tests that
could not fail, but it writes real bugs to disk on purpose, so an interrupted
run is a hazard: check the tree, not the summary.

### 2026-07-30 — M1a final pre-merge review: fix wave

A final pre-merge review of the M1a branch flagged five findings, all fixed
in this session, no second wave planned.

1. **CI silently skipped every database test.** The `python` CI job had no
   `postgres` service — only `migrations` and `e2e` did — so `tests/conftest.py`'s
   database-unreachable skip fired on every CI run, and the 13 tests covering
   the ingestion pipeline and the API routes against a real database never
   executed there, while the job still reported green. Fixed by adding the
   `migrations` job's `postgres` service, env, and migration steps to the
   `python` job verbatim (same image, same pinned tag — see that job's own
   comment for why retyping it from memory has cost CI runs before). Verified
   locally the way the reviewer did: `POSTGRES_PORT=5999 pytest -q` →
   `323 passed, 13 skipped`; a freshly-migrated CI-equivalent Postgres
   (`imresamu/postgis:16-3.4-bundle0`, same recipe, no seed step) reachable →
   `336 passed, 0 skipped`. **The workflow file change itself is unverified —
   CI has never run against this branch.** *(Superseded 2026-07-31: run #9
   confirmed it works in production. Left as written, per the note above.)*
2. **Latent fabricated-city bug in `parse_location_list`.** The function
   Lever's `categories.allLocations` and Ashby's `secondaryLocations` arrays
   actually call never applied the `;`/`|` segment split that
   `parse_location_field` does and that the module's own docstring says both
   providers need. `["New York, NY; Boston, MA"]` (one array element) parsed
   as a single segment with city `"NY; Boston"` — a fabricated place at
   `city_only` confidence, same failure class as the Vancouver/BC and
   NY(HQ) bugs M1a already fixed twice. Not yet seen in a recorded fixture,
   which is exactly how the first two got in. Fixed: every element passed to
   `parse_location_list` is now run through the same split before parsing.
   De-duplication and primary-first ordering preserved. Pinned with two
   `synthetic: true` fixture cases, one exercised directly through
   `parse_location_list` via a new `raw_list` field and a new
   `test_list_entry_point_matches_field_entry_point` test.
3. **Latent remote-misclassification bug, same defect class.** Parenthetical
   annotations are lifted out of a segment before Remote detection runs, and
   Remote detection never looked at the lifted annotations — only at comma
   parts. `"Austin, TX (Remote)"` therefore resolved `city_only`/`on_site`
   instead of `remote`. Leading Remote (`"Remote (US)"`) already worked,
   which is what made the trailing case easy to miss. Fixed in the same pass
   as item 2; pinned with a `synthetic: true` fixture case.
4. **Two false docstrings.** `lever.py`'s `fetch_board` said "Never raises"
   directly above a `raise RuntimeError` for a null client — reworded to say
   the no-raise guarantee covers source failures, not caller bugs. (`ashby.py`
   has the identical phrasing and the identical null-client raise, but was
   not named in the review; left untouched rather than guessing it should be
   in scope.) `locations.py`'s module docstring said `"Global, Remote"` stays
   `unknown` "same as a lone `Global`" — true for `city` (`None` both ways),
   false for `confidence` (`remote` vs. `unknown`); corrected.
5. **Registry/poller mismatch undocumented.** `data/board-registry.yaml`
   marks `lever:alloy` and `ashby:ramp` `status: active`, and the registry
   test pins them into the pollable set, but `workers/tasks.py` and `cli.py`
   both hard-filter `pollable(ats="greenhouse")` — nothing polls Lever or
   Ashby boards; their jobs enter the corpus only via `make seed`'s
   fixtures. Recorded in "Not real yet" so an operator reading the registry
   does not conclude otherwise.

Net effect on the numbers elsewhere in this file: Python tests 336 → 350 (14
new: 2 new fixture cases × the field-entry-point checks, plus a
list-entry-point check on 2 cases); location-parser assertions 145 → 159;
total automated tests 382 → 396. Row counts on the seeded dev database
(`jobs=31, companies=3, sources=3, source_job_records=31, job_locations=62,
job_source_links=31, ingestion_runs=4, users=1`) were checked before and
after this session and are unchanged — the new database-backed test
coverage referenced above is exercised entirely inside rolled-back
transactions (see `tests/conftest.py`).

### 2026-07-30 — M1a closed: provider breadth (Lever + Ashby)

All 10 tasks of `docs/plans/2026-07-30-m1a-provider-breadth.md` executed this
session. Greenhouse, Lever, and Ashby now sit behind one `JobSourceAdapter`
Protocol; the location parser handles all three providers' shapes; the two
upserts that would have raced under concurrency are fixed;
`domain/ingestion.py` and the API routes are both tested against a real
database for the first time; and `make seed` / `make demo` load all three
fixture boards.

**The most consequential finding: neither Lever nor Ashby publishes an
updated-at field.** Lever has `createdAt` only (a creation timestamp, not a
freshness signal); Ashby has `publishedAt` only. ADR 0007 specifies M1d's
phase-2 conditional polling as a diff on "new or changed `updated_at`" — and
on two of the three providers there is no such field to diff. Both adapters
set `source_updated_at=None` and the test suite asserts this as a recorded
fact (`test_lever_publishes_no_updated_at`-shaped assertions), not an
oversight. **M1d must fall back to the description content hash on these two
providers** — the hash already exists (`content_hash`, reused from the
Greenhouse adapter) and `persist_source_job` already compares it
(`content_changed`), so the fallback is not new machinery, but ADR 0007's text
describes a diff that two-thirds of the registry cannot perform as written.

**Ten Lever board tokens were guessed from company names; two were live**
(`alloy` populated, `plaid` empty with `200 []`, the other eight 404). Direct,
measured support for the existing ADR 0006 conclusion: Lever boards must be
found by probing a company's own careers page, not guessed and not harvested
from Common Crawl (`jobs.lever.co/robots.txt` disallows `CCBot`). Recorded as
fixtures — `alloy_board.json`, `plaid_empty_board.json`,
`ramp_unknown_board.json` (Lever's 404 shape) — so I3's empty-vs-unavailable
distinction has real Lever payloads behind it, not just Greenhouse's.

**Two fabricated-city bugs, both found by running the parser against real
recorded payloads rather than by reading it.** `"Vancouver, BC"` (3× on the
Alloy board) parsed to a city literally named `"BC"` — the subdivision code
was being read as if it were the city. `"New York, NY (HQ)"` (95 of 123
postings on the recorded Ashby/Ramp board) parsed to a city named
`"NY (HQ)"` — the parenthetical annotation was never stripped before the tail
token became the city. Both are I1 failures in the module whose own docstring
claims to enforce I1, on the two provider fixtures this plan added. Fixed
(`96a4e16`, `12da0ce`); both are now regression fixtures, not just a bug
report.

**ADR 0008, and what it deliberately does not fix.** Fixing the two bugs
above surfaced a separate, older gap: `"New York"` alone (no state, no
country, no corroboration) resolved to `unknown` — the parser's
corroboration rule is right for junk like `"Global"` but wrong for the one
city this whole product exists to find. ADR 0008 adds a short, enumerated,
committed list of NYC place names (the five boroughs and their common
spellings) that resolve to `city_only` without corroboration, and nothing
else. The cost is stated in the ADR and repeated here on purpose: **`"London"`
stays `unknown`**, and so does every other bare city name not on the list —
the enumeration is deliberately narrow rather than a general gazetteer, which
would be the guessing I1 forbids. A second, smaller residual gap is marked
`TODO(M1)` in `locations.py:481`: a corroborated-but-unresolved second part
still lets junk corroborate junk — `"Global, XX"` comes out with city
`"Global"`. Not a new failure mode (the pre-ADR-0008 parser did the same, just
naming the city `"XX"` instead) and not fixable without a real gazetteer.

**Also found and recorded, less urgent:** `ParsedLocation.is_nyc` tests
`city` only (`locations.py:331`). A location parsed as `state="New York"`,
`city=None` — the real shape of `"New York, USA, Remote"`, a recorded
Greenhouse string — is therefore `is_nyc == False`. ADR 0007 assigns a board
to the hourly `hot` tier on producing an NYC posting, so a board whose
postings only ever say statewide-remote New York would poll daily instead of
hourly: the product's stated goal (same-day knowledge of an NYC opening)
failing in the direction that loses coverage, not the direction that
fabricates one. Not fixed this session — flagged for whoever builds M1d's
tiering, since fixing it means deciding whether a state-level "New York" claim
is strong enough evidence of NYC-ness to actually place, which is a product
call, not a parser bug.

**Task 10 (this task, closing the plan): API route tests.** The database
fixture from Task 9 (`db_session`) truncates and rolls back inside its own
transaction; letting the FastAPI app open its *own* session in a route test
would make the app blind to that transaction's uncommitted rows, block on the
`TRUNCATE`'s lock, and commit for real against this developer's database.
Avoided by overriding `get_db_session` via
`app.dependency_overrides` with a stand-in that yields the fixture's own
session — every route in `tests/test_routes.py` now reads and writes inside
the same transaction the test controls, and nothing it does survives the
test's rollback. Confirmed empirically, not just by reasoning about it: dev
database row counts were queried before writing any route test and again
after the full 336-test suite ran — `jobs=10, companies=1,
source_job_records=10, job_locations=21, job_source_links=10,
ingestion_runs=1, sources=1, users=1` both times, identical.

The route response shapes in the task's own draft test code were wrong in one
place, caught by reading the real schemas before writing assertions (per this
task's own instruction that the route is the contract): `HealthResponse` has
no `checks` wrapper — `database` and `redis` are top-level keys — so the
draft's `body["checks"]` assertion was rewritten to match
`nightshift/api/schemas.py` rather than the other way around.

`make seed` was extended to load all three fixture boards (Task 10 step 3),
attributed to `greenhouse_fixture` / `lever_fixture` / `ashby_fixture`
respectively, following `FixtureGreenhouseAdapter`'s exact shape (client-less
subclass, overrides only `fetch_board`). Verified safely before running it
for real: a throwaway, uncommitted pytest file exercised
`FixtureLeverAdapter` / `FixtureAshbyAdapter` through the same
truncate-then-rollback `db_session` fixture, confirming 9 and 12 jobs created
respectively with zero failures, then deleted. Only after that did `make seed`
run for real via `make acceptance` — a deliberate, permanent change to the
dev database (not the hazard above): the corpus grew from 10 jobs / 1 source
to **31 jobs / 3 companies / 3 sources / 62 locations**, and `make acceptance`
passed in full — 18 verify checks plus 6 seeded browser tests, all green,
against the new three-provider corpus.

### 2026-07-30 — M1 design: board discovery

Design only. No implementation code was written; the deliverable is
`docs/architecture/board-discovery.md` plus ADRs 0005–0007.

**The milestone changed shape because the goal was restated.** M1's registry was
specified as a curated file. Asked how many companies belonged in it, the human
answered that the goal is same-day knowledge of *any* NYC tech opening from *any*
employer. No list length reaches that, so the registry becomes the output of a
pipeline. Q3 in `docs/QUESTIONS.md` records the original question and why it was
the wrong one.

**Everything in §3 of the design was measured, not estimated.** Common Crawl's
July 2026 index yields 2,605 board tokens in about two minutes at no cost.
Greenhouse serves two board domains and the newer one contributed 433 tokens the
older one did not. Listing a board costs 27 KB against 841 KB for full
descriptions — a 31× gap that decided the polling design — and the listing
endpoint carries an `ETag`, so unchanged boards revalidate for nothing.

**Lever is structurally invisible to the archive.** `jobs.lever.co/robots.txt`
names `CCBot` — Common Crawl's crawler — and disallows it, so Lever job pages are
absent and always will be. Its API remains sanctioned. Lever must be discovered by
careers-page probing, which is now a test assertion rather than a footnote.

**Two errors in my own first draft, both found by checking rather than reading.**
I wrote that Ashby returns the employer name. It does not — not at board level,
not on any job object — which would have routed all 383 Ashby boards to manual
review and quietly broken the approval design. The name is on the board page,
which Ashby's robots.txt permits. Second, I had treated the token as a usable
name; Ashby's `0g` is "0g Labs" and `10xteam` is "10x Team". Deriving an employer
from its slug is exactly the fabrication I2 forbids, and it is now a fixture.

Also established: Lever returns `404` with `{"ok":false}` for an unknown token and
`200` with `[]` for a live board with no openings. I3 depends on those being
distinguishable and they are.

**A rule of the human's was relaxed, deliberately and on the record.** A1 requires
per-entry human review of discovered boards. At 2,605 that is a control nobody
performs, and an unperformed control is worse than a weaker one that runs, because
the documentation still claims the strong one. ADR 0005 moves it to batch approval
with typed exceptions. Asked whether I would have invented that rule unprompted,
the honest answer was mostly no — the tell being that my first instinct on seeing
the number was to ask for it to be relaxed. The junk board `a3c41b8b71eff8c4`,
which returns ten well-formed postings under a machine-generated name, is why the
rule earns its place and why deleting its fixture would hollow out the gate.

**Scope answered for the long term** (§10): geography is nearly free because the
unit of polling is a company, not a city — whole boards are already fetched and
`job_locations` already stores every location, so NYC is a query filter. What
costs money is the geocoder, which A4 chose as an NYC-government service that
knows nothing else. Job-type breadth is free to collect and expensive to be useful
about, since M3's matching is tech-shaped. And the small end of the labour market
— local restaurants, contractors — publishes nothing machine-readable, so it is
unreachable by any polling strategy. The honest ceiling is every job posted to a
machine-readable board in the US.

**LinkedIn and Indeed were asked about directly and refused** (§9), with the
robots.txt evidence recorded so it is not re-litigated.

### 2026-07-30 — renamed CitySignal → Nightshift

Product decision by the human. Done before M1 rather than after, because the
discovery subsystem would have roughly doubled the number of references.

193 occurrences across 47 files, in three case forms (`citysignal`,
`CitySignal`, `CITYSIGNAL`) — which collapse to three substitutions, since the
lowercase form is a prefix of `citysignal_dev_only`, `citysignal_ci` and
`citysignal_env`. The Python package directory was moved with `git mv` so history
follows it. Recorded ATS fixtures were checked first and contain the string
nowhere, so no committed payload was edited.

Three things the text substitution could not reach, all found by running it:

1. **The Docker Compose project name changed too.** `docker compose down -v`
   addressed the *new* project and left `citysignal-postgres-1` running on port
   5433, so the new stack could not bind. Removed the orphaned containers,
   volume and network by name.
2. **A container created during that failed attempt was reused.** It reported
   `running (healthy)` with no host port mapping at all, because it had been
   created while the port was taken. `up -d` left it alone since the config hash
   matched. Fixed with `--force-recreate`; worth remembering that "healthy" and
   "reachable" are different claims.
3. **The database role, database name and password are all in the name.** The
   existing cluster was initialised as `citysignal`, and initdb only runs on an
   empty volume, so the volume had to be destroyed rather than migrated. Fine
   here — the corpus is fixture data — but it is the reason the rename is cheap
   now and would not have been later.

Two judgement calls in the diff. The self-identifying `HTTP_USER_AGENT` URL was
corrected to the real repository casing, `Tahmudun/Nightshift`, since its purpose
is to let a site owner look us up. And the quoted `.env` syntax error in the
2026-07-30 acceptance entry below was **restored to `CitySignal`**: it is
presented as recorded output, and rewriting a product name inside a verbatim
error message would make the record tidier and untrue.

Verified: `make check` (204 Python, 35 web), `gitleaks` clean, and
`make acceptance` — 18 checks and 6 browser tests — against a cluster
initialised from empty under the new name.

### 2026-07-30 — first CI run on real infrastructure

Remote created (`github.com/Tahmudun/Nightshift`, public) and `main` pushed. The
push was made over HTTPS, not SSH: there are no SSH keys on this machine, so
`git@github.com:` was refused, and there was already a working GitHub credential
in the macOS keychain.

Run 1: `python` and `web` green, `migrations`, `e2e` and `secrets` red. Both
failures were in CI configuration that had never been executed, which is the
entire argument for acceptance row 2 not being a formality.

**1. The secret scan had never run — not once.** It did not fail to find
anything; it crashed before scanning a single file:

```
panic: regexp: Compile(`^(?!\.env\.example$|...).*`):
       error parsing regexp: bad perl operator: `(?!`
```

`.gitleaks.toml` expressed "flag this password anywhere except these four files"
as a negative lookahead in `path`. gitleaks compiles rule patterns with Go's
`regexp`, which is RE2: no backtracking, therefore no lookahead, and
`MustCompile` panics. Reproduced locally, byte-identical.

The failure mode is worth naming. A crash and a strict scan both leave CI red,
so nothing about the job's colour distinguishes "this scanned everything and
objected" from "this has never scanned anything." The evidence for acceptance
row 6 had been written as though the tool ran.

Rewritten as a rule-level `[rules.allowlist]`, which is the supported way to say
"except these paths". Scanning then surfaced two files that legitimately name the
password and were never in the original list — `tests/test_env_example.py`, which
asserts the confinement, and `docs/PROGRESS.md`, which quotes it as evidence —
plus `.gitleaks.toml` itself, whose regex is a literal copy of the string. All
three added.

Verified against gitleaks **8.24.3**, the version `gitleaks-action@v2` pins,
rather than the newer build Homebrew installs: full history exits 0, and a
planted `nightshift_dev_only` in a non-allowlisted file exits 2. Per CLAUDE.md
§7, an allowlist that silences everything is not a scan.

**2. The CI Postgres image does not exist.** `Initialize containers` failed in
both `migrations` and `e2e`, before checkout:

```
docker pull ghcr.io/imresamu/postgis:16-3.4-bundle
Error response from daemon: manifest unknown
```

Two independent errors in one reference. The tag is `16-3.4-bundle0`, with a
trailing zero, and ghcr.io denies anonymous pulls of that package at all — the
runner authenticated to ghcr as the repo owner and still could not fetch it.
Docker Hub serves it unauthenticated.

Confirmed by running the image and executing the committed
`infra/postgres/init/001-extensions.sql` against it rather than trusting the tag
name: postgis 3.4.3, vector 0.7.4, pg_trgm 1.6, pgcrypto 1.3 on PostgreSQL 16.4,
all four `CREATE EXTENSION` statements succeeding.

**Worth carrying forward:** CI runs a third-party prebuilt image while local dev
and `make demo` build `infra/postgres/Dockerfile`. That divergence is why a
non-existent tag sat in the repo unnoticed — no local command ever pulls it.
Acceptable now that CI actually exercises it every push; revisit if the two
builds drift in a way that matters.

Run 2: `python`, `web`, `secrets` and `e2e` green. `migrations` still red, now
on the drift probe, which had also never run anywhere.

**3. The post-write hook could never have worked.** `alembic revision` died with
`Could not find entrypoint console_scripts.ruff`, on CI and on this machine
alike. `alembic.ini` declared the hook as `type = console_scripts`, and the ruff
distribution publishes **no console_scripts entry points at all** — it ships a
compiled binary as a plain script. Changed to `type = module`, which runs
`sys.executable -m ruff`: the interpreter already running alembic, so it needs
ruff on neither PATH nor an entry point.

**4. The drift probe compared our models against the whole server.** With the
hook fixed, autogenerate proposed dropping about forty tables — `addrfeat`,
`faces`, `featnames`, `topology`, `layer` and the rest of postgis_tiger_geocoder
and postgis_topology, which CI's bundle image installs and puts on the search
path. `include_object` excluded exactly three PostGIS names by hand, so
everything else looked like drift.

Now filtered by ownership read from `pg_depend`, which follows whatever is
installed instead of a hand-kept list. The filter refuses to exclude any table
present in the models, whatever pg_depend says: an extension shipping a table
named like one of ours would otherwise switch off drift detection for that
table — the filter hiding the change it exists to surface. Moved to
`nightshift/db/autogenerate.py`, because `migrations/env.py` runs migrations as
an import side effect and cannot be imported by a test. Eight tests, checked
non-vacuous by mutation: removing the models guard fails one, disabling the
table filter fails two.

**5. And then I introduced silent data loss, and nearly shipped it.** Reading
`pg_depend` inside `do_run_migrations` autobegins a SQLAlchemy transaction.
Alembic only commits a transaction it opened itself; finding one already open,
it treated it as externally managed, and the enclosing `connect()` block rolled
the whole migration back on close. Every `CREATE TABLE` ran, the
`alembic_version` row was inserted, then `ROLLBACK` — and `alembic upgrade head`
printed "Running upgrade" and **exited 0** with an empty database.

Found only by checking the database after a run that claimed success, against a
local container built to match CI's image. Reproduced, then isolated by removing
the one added line: `COMMIT` and the tables came back. Fixed by ending the read
before configuring alembic, so alembic owns its transaction again.

The exit code cannot see this, so a CI step now asks the database instead:
**Upgrade actually persisted** fails if `alembic current` is not at head after a
successful upgrade. Verified in both directions — it passes at head and fails
after a downgrade.

Worth stating plainly: the mistake was mine, made while fixing something else,
and the only reason it did not land is that verification looked at the database
rather than at the exit code. A green `alembic upgrade head` was, for one commit,
completely compatible with an empty schema.

**Verified after the fix** — `make check` (204 Python, 35 web), `make reset-db`
(version row present, 10 tables), `make acceptance` (18 checks + 6 browser
tests), and CI's full migrations sequence replayed against a local replica of
the CI image: up, down, up, drift probe clean, seed loads.

Run 3 at `4c1643f`: **all five jobs green**, longest 129s.
https://github.com/Tahmudun/Nightshift/actions/runs/30528565491 — acceptance
row 2 satisfied, and M0 closed.

The pattern across all three runs is worth keeping. Every defect CI found lived
in a file no local command executes: a scanner config, a service image tag, a
formatter hook, an autogenerate filter. The application code was green on run 1
and never broke. "The same commands pass on my laptop" was true the whole time
and would have shipped five bugs.

### 2026-07-30 — M0 acceptance

Docker Desktop installed by the human, clearing B1. Ran the acceptance criteria
against live infrastructure for the first time. Four bugs, every one of them found
by running the thing rather than by reading it.

**1. `make demo` failed on a clean clone.** The reported symptom:

```
.env: line 53: syntax error near unexpected token `('
.env: line 53: `HTTP_USER_AGENT=CitySignal/0.1 (+https://github.com/tahmudun/citysignal)'
make[1]: *** [migrate] Error 1
```

(Recorded before the project was renamed to Nightshift, and left as it was
actually emitted. Rewriting the product name inside a quoted error message would
make the record tidier and untrue.)

The Makefile loads config with `set -a && source .env`, because Alembic and the
seed CLI read the process environment rather than pydantic-settings. An unquoted
`(` is a bash syntax error. Three parsers read this file — bash, `docker compose
--env-file`, python-dotenv — with three different quoting rules, and only
python-dotenv had ever been exercised. `tests/test_env_example.py` now sources the
file exactly as the Makefile does and requires bash and python-dotenv to agree on
every value.

This is the M0 acceptance criterion that matters most and it was broken by one
missing pair of quotes. Worth remembering that the failure had nothing to do with
the interesting parts of the system.

**2. Acceptance row 5 had no automated coverage at all.** The existing Playwright
suite runs with *no API* on purpose — it proves the app reports "api unreachable"
instead of rendering an empty list, which is the right thing to test. But it meant
nothing asserted that real rows from Postgres ever reach a screen. Added
`apps/web/e2e-seeded/`, and an `e2e` job to CI so the criterion cannot regress
silently.

While writing it: the first version of the I1 test failed, and the app was right
and the test was wrong. `ConfidenceLegend` renders the same ladder component for
all five levels to document the visual language, so an unscoped
`getByRole('img')` was asserting against the legend rather than against job data.
Scoped to `role="article"`. Then added the assertion that the rejected label *does*
appear in the legend — otherwise over-narrow scoping would make the test pass by
matching nothing, which is the failure mode CLAUDE.md §7 means by "a test that
cannot fail is not a test."

**3. `make setup` never installed Playwright's browser.** It ships separately from
the npm package and the required build changes on minor upgrades, so
`make test-e2e` could not work from a clean clone. The e2e targets provision it
now; keeping it out of `make setup` avoids putting a 100 MB download in front of
every first run.

**4. `make acceptance` had a hidden step — mine.** I added the seeded suite to the
target, but `verify.py` starts its own uvicorn and tears it down on exit, so the
suite that ran after it had nothing to talk to. Six tests failed on
`ECONNREFUSED`. It had passed when I first ran it only because I had started
uvicorn by hand — precisely the class of thing acceptance criterion 1 exists to
forbid, committed by me while verifying that criterion. `playwright.seeded.config.ts`
now declares both servers, gated on `/health`, and the duplicate CI step is gone.

**5. The palette failed WCAG AA, and worse than the review guessed.** Review action
6 was "measure contrast on `paper-faint`/`ink-500`; lighten if below 4.5:1".
Measured: `paper-faint` 3.89:1, a genuine fail for the 9-11px labels it carries.
But `ink-500` — a *surface* shade — was being used as a text colour in fourteen
places at **1.69:1**, which is close to invisible. The palette had three named
text weights and a fourth unnamed one that nobody had decided on. Fixed by
lightening `paper-faint` to 5.43:1 and moving every `text-ink-500` onto it, so
there are now exactly three text steps and all three are readable.

`colour-contrast.test.ts` computes the ratios from the real tokens rather than
trusting a comment. Confirmed non-vacuous by restoring the old value: three tests
fail. It also pins `ink-500` *below* 3:1, so lightening it to reuse as text trips
a failure that points at the explanation.

**Verified against live infrastructure:** migration down/up dropping and restoring
all 8 enum types; `/health` degrading per-dependency with real containers stopped;
all four `job_locations` check constraints refusing their violations. The review's
line — *"a constraint nobody has seen reject anything is a comment with extra
syntax"* — is now settled: each one raised `IntegrityError`.

**Not verified at the time:** CI (no remote exists — it needs an account
decision), the final clean-clone re-run (host disk, B2), and the 6 seeded browser
tests after the last commit (Docker died, B3). B2 and B3 were both cleared later
the same day — `make acceptance` passed at `14abb68`, 18 checks plus 6 browser
tests. CI remains the one open item, and it is the one that needs a human.

The disk filling up was self-inflicted in part: I made two full clones of the repo
to test the clean-clone path, ~730 MB each in `node_modules` and venvs, on a
machine that had ~2 GB free to begin with. Both are deleted. Testing the
clean-clone path is right; doing it twice without checking `df` first was not.

### 2026-07-29 — M0 build

Read CLAUDE.md, AMENDMENTS (all 15), and the relevant PRODUCT-SPEC sections.

Verified the Greenhouse endpoint against a live board before writing the adapter,
per A1's instruction to re-verify field shapes. That paid for itself immediately —
five things the spec did not say, now encoded in the code and its comments:

1. `content` arrives **HTML-escaped** (`&lt;p&gt;`), so unescaping must precede
   any tag handling.
2. `location.name` is one `;`-delimited string that routinely names ten places.
   Concrete proof of A2 — the messiest real value found was
   `"Boston, Massachusetts, USA; Connecticut, USA, Remote; … ; Rhode Island, USA, Remote"`.
3. `application_deadline` was **null on all 426 postings**. A10, confirmed on
   real data.
4. Compensation is not a top-level field; it hides in `metadata` as
   `value_type == "currency_range"`, and it is present on NYC postings
   (pay-transparency law) while absent on most others.
5. `updated_at` is a last-modified stamp and `first_published` is the real
   publication date. They are carried in separately-named columns and there is no
   `posted_at` anywhere in the codebase to be misread.

Wrote `tests/fixtures/locations.yaml` **before** the parser, as A2 directs.

**Two real bugs found by tooling rather than by reading:**

1. mypy strict caught `IngestionRun.source` being used by `GET /sources` but never
   defined as a relationship on the model — a runtime `AttributeError` on a route
   that had no test yet.
2. The company-normalization suite, written during the milestone review, caught
   `normalize_company_name("Moody's")` returning `"moody s"`. The apostrophe was
   being replaced with a space, leaving a dangling token, so `Moody's Analytics`
   and `Moodys Analytics` would have become two separate companies in a table
   whose `normalized_name` is unique. Real NYC employers affected: Moody's,
   Macy's, Lowe's, McDonald's. Fixed by deleting apostrophes rather than spacing
   them, and both the typewriter and typographic forms are now covered.

The second one is the argument for writing those tests earlier: it was a pure
function with no database dependency, so nothing was stopping me.

Deviations from spec, all deliberate and documented above: no
`discover_companies()` (A1), location on its own table (A2), ARQ (A11), no
Turborepo (A12), schema narrower than §6.

Did not start the 3D city. It is at M4 for a reason.
