# Milestone 4c review — the city with the jobs in it, and the corpus that could not test it

**Date:** 2026-08-12
**Branch:** `m4b-dark-city`
**Scope:** six tasks — the placement join and `GET /city/signals` (ADR 0024), Three.js in
MapLibre's own context (ADR 0025), the unresolved field made legible, navigable and sortable
(ADR 0026), selection shared by the list and the map (ADR 0027), §6's treatments and the
in-interface legend (ADR 0028), and this session: the acceptance walk, and the three defects
it found.

---

## 1. The shape of what went wrong this time

M4b's finding was about the *instrument*: every defect it produced was invisible to a passing
suite because the suite and the product were not looking at the same thing. M4c's is one
floor along, and it is about the *corpus*:

> **Every claim this milestone makes was being tested against the only corpus that cannot
> falsify it.**

Thirty-one seeded roles, all `unresolved`, none carrying a coordinate, none at a confirmed
office. Against that corpus:

| The claim | What the seeded suite could actually see |
|---|---|
| No placement is fabricated at any confidence | Nothing lied, so nothing was drawn as though it had |
| Thousands of markers are not thousands of components | Thirty markers did not produce thirty components |
| A role the renderer cannot place is not silently lost | `counts.building` was 0, so the branch never ran |

Every row is a true sentence and none of them is the claim. The first tests what happens when
nothing claims precision, not what happens when something does. The second would pass against
an implementation that renders one `<div>` per marker. The third is a branch that has never
executed in a browser and will execute the first time a human confirms an address.

The fix is not more assertions against the seed. It is a second corpus, chosen rather than
found: `apps/web/e2e/city-acceptance.spec.ts` stubs `/city/signals` and serves the payloads
this corpus cannot produce — a lie, five thousand roles, and a role at a building. It runs in
the **offline** config, beside M4b's rendering tests, because it needs no API at all: the map,
the archives, MapLibre, Three.js and the instance buffers are all real, and only the corpus is
chosen.

Three defects fell out of it on the first run.

---

## 2. The three acceptance claims, walked

`city.md` §7: *"Done when: no placement is fabricated at any confidence, thousands of markers
are not thousands of components, and the list and the map cannot disagree."*

### 2.1 No placement is fabricated at any confidence — **met**

| Evidence | Where |
|---|---|
| Every role in the real corpus is `unresolved`, and the sum of the three kinds equals the total | `e2e-seeded/city.spec.ts` — "nothing on the city claims a precision the corpus does not have (I1)" |
| A payload that claims a position it has no right to takes the **whole corpus** off the city, in three shapes: an unresolved role carrying coordinates, a building placement below `verified`, an area placement naming a BIN | `e2e/city-acceptance.spec.ts` — "a placement claiming more than it can prove…" |
| The same twelve roles with nothing fabricated draw twelve beacons — the control, so the refusal is about the lie and not about the stub | same test |
| The detail panel says a beacon's position means its employer and *"nothing whatsoever about where in New York"* | `e2e-seeded/city.spec.ts` — "the selected role opens the panel that describes it" |
| A role the renderer cannot place yet is counted **and named**, not dropped | `e2e/city-acceptance.spec.ts` — see finding 3.1 |

The refusal is deliberately of the whole payload rather than of the offending row. A corpus
that has been shown to produce fabricated positions is a corpus whose remaining placements
have not been shown to be sound, and drawing them anyway is the city asserting something it
cannot know. It says "the roles could not be loaded" instead — I3's habit of mind, applied to
a renderer.

### 2.2 Thousands of markers are not thousands of components — **met**

Held the employer count fixed at 20 and moved only the role count: 100 → 5,000, fifty times
the markers. The DOM under `#main` must be **identical**, not merely small.

- 364 elements at 100 roles. 364 elements at 5,000 roles.
- 5,000 of 5,000 reached the instance buffer (`MAX_BEACONS`, which is also the API's
  `MAX_SIGNALS` — the largest city this product can be asked to draw).
- One `canvas`, one custom layer, no per-marker node anywhere.
- Mutation: one `<span hidden />` per visible role in `CityRoster` → 364 became 5,264 and the
  test went red naming the cause.

`docs/reviews/milestone-4c-scale.png` is the 5,000-role city, drawn at 200 employers. It is
also the evidence for §4.1 below, which is the part of this that is *not* met.

### 2.3 The list and the map cannot disagree — **met**

Eight assertions existed before this session (selection by click, by roster, by deep link;
escape; empty sky; the reticle following a re-sort; the query surviving a selection; the
archive toggle moving the buffer rather than a list). The edge Task 5 created was the one
left: **a role that is selected and not drawn**.

That state is reachable two honest ways — a link somebody sent you to a role you have since
been rejected from, and rejecting a role while its panel is open — and three things could
disagree about it. The panel could describe it as though it were on screen. The reticle could
be left ringing whichever beacon now stands where it used to. The toggle could put the beacon
back without the reticle following.

`a selected role that §6 is hiding says so, and the reticle is not on somebody else` walks all
three, and they are one assertion because they are one piece of state. Mutation: parking the
reticle on `placements[0]` when the selected role is absent — the classic wrong-beacon bug —
turned `selectionAt` from `null` into `[-620, 0, 700]` and the test red.

---

## 3. Findings, fixed this session

### 3.1 The page counted roles it does not draw — FIXED

`CitySignals` printed "On a building: *n*" and "In an area: *n*" from the endpoint's own
counts. The renderer draws the unresolved field and nothing else — `arrangeUnresolved` takes
the unresolved signals and ignores the rest — so any non-zero value there is a role counted on
the page and absent from the city, with no notice.

It is 0 today, because `data/company-locations.yaml` is empty and no posting names a street.
It stops being 0 the first time a human confirms one address, which is the next planned piece
of work in this area. **That is I7 in the form it actually arrives in**: not a mock presented
as working, but a renderer presented as complete — and the failure would not have been a
crash, it would have been a quiet, permanent, plausible undercount.

The fix is a sentence, not a feature: *"2 of these are not drawn on this map yet… they are
missing from the sky, not from the corpus."* Pinned by a component test and a browser test,
both shown red when `undrawn` is forced to zero.

### 3.2 The two ceilings were coupled by a comment — FIXED

`MAX_BEACONS` in `beacon.ts` is 5,000; `MAX_SIGNALS` in `api/routes/city.py` is 5,000;
`setSignals` clamps to the first with a `Math.min`. `beacon.ts` claimed the two match. Nothing
checked it.

Raising the API's ceiling is a one-line change with a good reason behind it and every test in
both suites still green — and the surplus roles would be dropped on the floor. Nothing throws.
No count on the page disagrees with itself. The `truncated` banner stays off, because the
*API* did not truncate. The city simply stops drawing part of the corpus, silently, forever.

`test_enum_parity.py` already exists for exactly this class of cross-language drift, so the
assertion went there: `MAX_BEACONS >= MAX_SIGNALS`, read out of both files. Shown red by
lowering `MAX_BEACONS` to 2,000.

### 3.3 The renderer's compiled programs outlived the layer — FIXED

`onRemove` disposed every geometry, material and texture the layer owns and then set
`renderer = null`. The programs and render lists behind them belong to the `WebGLRenderer`,
and nulling a reference does not free them.

Bounded today: nothing removes this layer without destroying the map, and a destroyed map
takes its context with it. But "the only caller happens to make this harmless" is not a
property to leave undocumented in the one place §5.1 gave a second library a share of somebody
else's context. It is `renderer?.dispose()` now — and not `forceContextLoss()`, because the
context belongs to MapLibre, which is still drawing New York with it.

Covered by inspection and by the full browser suites passing across map teardown, not by a
test of its own: the layer's unit tests run in jsdom where there is no renderer to dispose.
Stated here rather than implied.

### 3.4 The instrument was wrong before the product was

The first version of the DOM-count assertion counted `document.querySelectorAll('*')` and
failed by a handful of elements between two loads of the *same* corpus. Nothing was rendering
per marker. `<head>` gains a `<style>` and a `<script>` for each route `next dev` has compiled
so far, and the shell's health indicators move through loading → unreachable on their own
schedule with no API behind them. Scoped to `#main`, which holds every beacon, roster row and
legend row and no clock.

M4b's lesson, one milestone on: the first thing a new instrument measures is itself.

---

## 4. Limits recorded, not fixed

### 4.1 The field is legible at 31 roles and not at 5,000

`docs/reviews/milestone-4c-scale.png`. The layout wraps at `COMPANIES_PER_ROW = 6`, so 200
employers is 34 rows receding north; the name plates at the back overlap into an unreadable
strip along the horizon, and a column of 25 roles is ~1,125 m tall and leaves the frame at the
opening pitch.

Nothing about the acceptance claim is affected — the buffer takes all 5,000 and the DOM does
not move — but §4.8 asks for *"a legible, navigable, sortable field"*, and that was designed
and measured at the size of the corpus that exists. It is legible at 31. The roster stays
usable at either size, which is the non-3D equivalent §5.6 requires, so the information is
never lost — only the view.

**Deferred to M4d/M5, deliberately.** The remedies are level-of-detail on the plates, a camera
that frames the whole field, and clustering — and adaptive quality tiers are already an M4d
deliverable, which is where this belongs rather than as a rushed sixth task here.

### 4.2 A treatment change writes the instance buffer twice

`CityMap`'s store subscription calls `setSignals` (which rewrites bodies and marks) and then
`setTreatments` (which rewrites them again) whenever the treatment map changes. Both are
needed and the order is load-bearing: the visible set is filtered by the new treatments, but
the layer's *colours* come from its own closure, which `setTreatments` has not updated yet.
Reordering the two would leave the field one write stale instead.

Both happen synchronously inside one subscriber call, so no frame is ever drawn from the
intermediate state. It is two full buffer writes per application stage change at up to 5,000
instances, which is a cost nobody has measured. Recorded rather than restructured: M4d
measures frame time, and that is the right moment to find out whether this matters.

### 4.3 Neither test suite is isolated from the other's database

Recorded in `PROGRESS.md` during Task 5 and still true. Running the Python suite while the
seeded browser suite is running against the same Postgres produces failures that name real
tests and look exactly like a regression. Run them one at a time. Nothing warns you.

---

## 5. The hunt CLAUDE.md §5 asks for

| Hazard | Verdict |
|---|---|
| Hallucinated certainty | The one instance was §3.1, and it was structural rather than textual: a count with no statement of what happens to it. Fixed. The panel, the legend and the roster otherwise name what they cannot draw — including the four rows of §6 nothing in this corpus can produce (ADR 0028) |
| Silent data loss | Two found. §3.2 (the ceiling) is fixed. §3.1 (roles counted and not drawn) is fixed. The layer's own `Math.min` clamp remains, and is now the only thing standing behind an assertion rather than a comment |
| Wrong merges | Not applicable to this slice — no merge path was added. The placement join is a left join by design (ADR 0024) and produces `unresolved` rather than a guess when nothing matches |
| Race conditions | Two fetches land in either order and both write to the same closure (`setSignals` / `setTreatments`), by construction. The URL↔store ping-pong was found and fixed during Task 4. The `styledata`-vs-`load` attach race was found and fixed during Task 2 |
| Retry storms | `Providers` sets `retry: 1`, `refetchOnWindowFocus: false`, `staleTime: 30s` globally, and `/city/signals` disables focus refetching a second time. A dead API produces two requests per query and a sentence on the page |
| GPU leaks | §3.3, fixed. Every mesh, material, geometry and the label atlas texture are disposed on `onRemove`, and the `move` listener is removed **first**, since a listener left on the map keeps the whole closure reachable and none of the disposal would ever be collected |
| Unbounded render work | `render` asks for the next frame only while something is animating, and under `prefers-reduced-motion` nothing ever is — asserted from the instance data, not from a flag. The honest caveat: one new role means the city repaints continuously, which is §6's encoding working as specified and is a cost M4d measures |
| Mobile gesture conflicts | M4b's ground, unchanged here. The one M4c addition is the click-to-select path, and a drag does not clear the selection — MapLibre suppresses `click` past `clickTolerance`, verified in its source rather than assumed |
| Accessibility gaps | Every role is reachable without the canvas: the roster is a keyboard-navigable list of employers and roles, the sort is a radio group, the legend documents every mark in words, and the detail panel says in prose what the beacon says in colour. Asserted by "a role can be selected without touching the canvas at all". **Automated accessibility tests are an M4d deliverable (A14) and do not exist yet** |
| Privacy overreach | Nothing new leaves the machine. The city makes three requests, all to the local API, and the tile archives are files on disk |
| Tests that assert nothing | Five mutations were run against this session's new assertions and every one turned a *named* test red (table below). Two tautologies were caught during Task 5 and are recorded in `PROGRESS.md`; a third instrument fault is §3.4 above |

### Mutations run this session

| Mutation | Test that went red |
|---|---|
| The unresolved-carries-a-position check deleted from `placementSchema` | a placement claiming more than it can prove takes the whole corpus off the city |
| The buffer clamped to 1,000 instead of `MAX_BEACONS` | fifty times the markers… ("the buffer never reached the full corpus": expected 5000, received 1000) |
| One `<span hidden />` per visible role in `CityRoster` | fifty times the markers… ("the DOM grew when the corpus did": expected 364, received 5,264) |
| `undrawn` forced to 0 | names the roles it counts but cannot place *(unit)*; a role the renderer cannot place yet is counted and named *(browser)* |
| The reticle parked on `placements[0]` when the selected role is absent | a selected role that §6 is hiding says so, and the reticle is not on somebody else |
| `MAX_BEACONS` lowered to 2,000 | the browser allocates room for every signal the API can send *(Python)* |

---

## 6. Not real yet

Carried forward into `PROGRESS.md`'s own list, and repeated here because a review that only
lists what works is the failure mode this section exists for:

- **Nothing stands on a building.** Not a shortfall — `city.md` §4.4 and ADR 0024 make a
  confirmed office the only honest source of one, and `data/company-locations.yaml` is empty.
  The renderer has no building or area treatment at all, which §3.1 now says on the page.
- **Four of §6's thirteen rows are not drawn**, each named as undrawn in the legend with its
  reason (ADR 0028).
- **The field's legibility past a few hundred roles** — §4.1.
- **Frame-time instrumentation, adaptive quality tiers and automated accessibility tests** —
  all M4d, all absent.

---

## 7. No ADR was written for this task, and that is a decision

Five ADRs came out of M4c's first five tasks — 0024 through 0028 — because each
resolved something a later session could reasonably want to reverse. Task 6
resolved nothing of that kind. The refusal of a lying payload is ADR 0024's rule
enforced a second time (`schemas.ts` keeps a deliberate copy of the API's
`Placement.__post_init__`); "the field draws the unresolved layer and nothing
else" is `city.md` §7's scope, now stated on the page as well as in the
architecture; and the ceiling parity check is a test, not a choice.

`docs/architecture/city.md` §6.1 and §7 were amended instead, since both had gone
slightly stale: §6.1 listed what is drawn without saying that two placement
*kinds* are not, and §7 had no record that M4c had been walked.

---

## 8. Verdict

**M4c's three acceptance claims are met, and two of them are met by evidence that did not
exist at the start of this session.** The claim that was closest to being untestable — no
fabricated placement — is now walked from the only side that can falsify it, and the walk
found that the honest handling of a placement this renderer *cannot* draw was missing
entirely.

The milestone's own lesson is worth carrying into M4d: **a corpus that cannot produce a
failure cannot test the guard against it.** M4d's claims are numbers — 60fps desktop, 30fps
mobile — and the machine that will measure them is a headless browser with no GPU, which is
the same trap wearing different clothes.
