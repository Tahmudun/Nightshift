# Milestone 4b review — the dark city, and the tests that could not see it

**Date:** 2026-08-12
**Branch:** `m4b-dark-city`
**Scope:** six tasks — the baked pmtiles artifact and its route (ADR 0022), MapLibre and
the hand-written dark style, the full-window canvas and the lit city (ADR 0023), New York's
own measured skyline, the camera controller and its gesture surface, and this session: the
acceptance walk in a browser, `apps/web/e2e/city.spec.ts`, and the four defects it found.

---

## 1. The shape of what went wrong this time

M3a's finding was that a check could be blind to the thing it was named for. M3b's was that
a check can measure the right thing at the wrong altitude. M3c's was that every false
statement was true of a database and false about a person. M4b's is the first one that is
about the *instrument* rather than the claim:

> **Every defect this milestone produced was invisible to a passing test suite, because the
> suite and the product were not looking at the same thing.**

Six defects across the slice, and not one of them could fail a test that existed at the
time:

| What broke | What the tests were looking at |
|---|---|
| The canvas rendered 300 px tall inside a box that hid it (Task 2) | The style object, which was correct |
| The tile route threw on every successful buildings request — an em dash in a licence header (Task 4) | The two *failure* paths, which carry no such header |
| Two style filters filtered nothing (Task 4) | That the filters existed |
| A manifest committed before its release existed broke `make setup` everywhere but this machine (between Tasks 4 and 5) | A cached archive that was already on this machine |
| The map's accessible name was "Map" (found today) | JSX that named a wrapper nobody can focus |
| A fly-to interruption test passed with the interruption handler removed (found today) | A behaviour MapLibre also provides |

The generalisation, and it is the one M4c has to inherit: **this milestone's output is a
frame and a gesture, and neither is in the DOM.** jsdom cannot see a frame; a unit test
that asserts `touchZoomRotate.enable()` was called has asserted something about a call, not
about a finger. The instrument that closes the gap is a real browser driving the real
archives, which is what Task 6 built, and the first thing it did was find two things wrong.

---

## 2. Findings from Task 6, in full

Tasks 1–5's findings are recorded in `docs/PROGRESS.md` and in their commit messages.
These are this session's.

### 2.1 The interruption test passed with the interruption removed — FIXED

The strongest-looking test in the suite was not evidence.

`a fly-to stops where it is when the user takes hold` starts an eight-second `flyTo`,
presses the mouse down on the map, and asserts the camera stopped where it had got to.
Stubbing `CameraController.#handleUserInput` to return immediately — deleting the entire
mechanism the test is named after — left it **green**.

The reason is that MapLibre's own `dragPan` handler stops an in-flight camera the moment
you grab the map. The criterion was being met; it was being met by the library, while the
test claimed to be watching the controller. Had the controller's interruption been broken
by a later refactor, every input MapLibre does *not* treat as a camera gesture — a
two-finger tap, a key, a wheel over a panel — would have stopped interrupting anything, and
this test would have gone on passing.

**Fixed** by asserting `camera.animating` alongside `map.isMoving()`. `animating` is the
controller's own record of a move it started, nothing else clears it, and with the handler
stubbed it stays true for the full eight seconds. Red-green verified in both directions.

The general form is worth keeping: *when a library and your code both implement a
behaviour, a test of the behaviour is not a test of your code.* Assert the state only your
code owns.

### 2.2 The map's accessible name was "Map" — FIXED

`CityMap` set `role="application"` and a carefully written `aria-label` — *"New York City
map. Every role on this map is also in the list view."* — on the wrapper `div`. MapLibre
gives its **canvas** `tabindex="0"`, `role="region"` and the name "Map", and the canvas is
the node that takes focus. Measured tab order from the top of the document:

```
1 Skip to content   2 Explore   3 Operate   4 Analyze   5 canvas "Map"
```

So the sentence written for screen-reader users sat on a node with `tabindex="-1"` that
nothing ever focuses, and what a screen reader actually announced on reaching the main
content of the page was the word "Map". The second half of that sentence is the part that
matters — it is where §5.6's promise that every map action has a non-3D equivalent gets
told to the person most likely to need it.

**Fixed** by setting the role and the label on the canvas and removing both from the
wrapper, and covered by `a keyboard alone reaches the city and drives it`, which walks the
tab order with no click anywhere, asserts the name and role on whatever took focus, and
then steers the city with an arrow key.

Two things that were checked at the same time and were already right: the global
`:focus-visible` outline does reach a canvas (asserted now, because a canvas is unusual
enough to be worth not assuming), and `role="application"` is the correct role here rather
than a heavier-handed one — it asks the screen reader to pass keystrokes through instead of
consuming arrows for browse-mode navigation, which is the difference between a camera you
can drive and one you cannot.

### 2.3 A whole-viewport feature query returns zero over a fully drawn city — RECORDED

Not a defect in this slice. A trap set for the next one.

`map.queryRenderedFeatures({ layers: ['buildings'] })` returns **0** at the pose this city
opens at, while the same frame has thirty thousand building features loaded and visibly
drawn:

| Pose | Viewport query | Box below the horizon | In the source |
|---|---|---|---|
| z13.6, pitch 76 — the opening view | **0** | 1,599 | 30,573 |
| z15, pitch 76 | **0** | 351 | 18,533 |
| z14.2, pitch 76 | **0** | 599 | 17,996 |
| z13.6, pitch 0 | 9,225 | — | 38,408 |

The viewport rectangle at 76° of pitch is mostly sky. The query unprojects its corners onto
the ground plane, and the corners above the horizon have no ground to land on. Pass an
explicit box below the horizon and the answer is correct.

M4c needs picking and list↔map synchronisation, and the obvious implementation of *"which
roles are on screen"* is a whole-viewport query — which will return an empty array,
silently, in the default view, and read as "no roles in New York" rather than as a bug.
Recorded in `PROGRESS.md`, in the test that depends on it, and in the type declaration of
the debug handle.

### 2.4 Playwright's documented reduced-motion switch does not reach the page — WORKED AROUND

`test.use({ reducedMotion: 'reduce' })` is the documented API and on this version it does
nothing observable in the page: `matchMedia('(prefers-reduced-motion: reduce)').matches`
stays `false`, so the controller builds itself with the preference off.
`page.emulateMedia({ reducedMotion: 'reduce' })` before navigation works.

Called out because of the shape of the failure rather than its size. A reduced-motion test
written the documented way exercises the *ordinary* camera while claiming to exercise the
reduced one. It fails here only because the assertions happen to be written the way round
that notices — "no orbit button" fails when the button is present. Written the other way
round it would have been a permanently green test of nothing.

### 2.5 Four Playwright workers failed two tests that had nothing wrong with them — FIXED

Adding `city.spec.ts` to the existing suite made `shell.spec.ts`'s navigation test fail —
a test untouched since M0, about links.

Playwright's default worker count is half the cores, four on this machine, and each city
worker builds a MapLibre map with no GPU behind it. Four of them rasterise a million
footprints on the same CPU, everything times out, and the failure names a navigation link.
**Fixed** by capping `workers: 2` in `playwright.config.ts`, with the measurement in the
comment: at four, two failures; at two, twenty-three passes.

A suite that fails for machine-speed reasons teaches people to re-run it rather than read
it, which is a worse outcome than a slower suite.

### 2.6 The CI e2e job had no tiles — FIXED

`city.spec.ts` would have failed on every push. The `e2e` job never fetched the archives —
only the `api` job did — and with the tile route answering 503 the page shows its "cannot
be drawn" card, which is *correct behaviour* and proves nothing about M4b.

**Fixed** by restoring the same tile cache in that job and fetching with
`scripts/fetch_tiles.py --strict`, and raising its budget from 15 to 25 minutes. The
alternative — skipping the suite when the archives are absent — is the failure this
pipeline already learned once, where a suite went green having checked nothing.

### 2.7 `HEAD` does not check the archive size while `GET` does — OPEN, low

`/api/tiles/[artifact]` refuses to serve a file whose length does not match the pinned
manifest, and says so in a sentence naming the fix. Its `HEAD` handler checks only that the
file exists. A truncated or swapped archive therefore answers `200` to a probe and `503` to
the fetch.

Nothing reaches that state today: `CityMap` probes with a ranged `GET`, so the honest error
is what a user sees. Left open rather than fixed because the two handlers are about to be
read again in M4c and the fix is one shared helper, not one more copy of the check.

---

## 3. The defect classes `CLAUDE.md` §5 names, each answered

| Class | Checked how | Answer |
|---|---|---|
| Hallucinated certainty | Every number in the M4b acceptance walk traced to a measurement made today | The two claims that could not be measured — physical touch hardware, Safari's trackpad rotation — are written as limits in `PROGRESS.md` rather than counted as passes |
| Silent data loss | The 732 footprints with no measured roof height | Drawn at a documented 25 ft **and named on screen**, with the count read from the manifest rather than typed |
| Wrong merges | — | Not applicable: this slice merges no records |
| Race conditions | Read `CityMap`'s effect and `CameraController`'s timers | The double-mount guard holds (`cancelled` is checked after every await, and a map created after cancellation is removed immediately); the orbit chain is held by `#orbit` rather than by its timer, so a leg in flight when the user interrupts cannot schedule a successor; `destroy()` clears both timers and every listener |
| Retry storms | Read every fetch on this page | Three: two sixteen-byte archive probes, and MapLibre's own tile requests. No retry loop anywhere, and nothing polls |
| GPU leaks | **Measured**: 21 mounts of the city with navigations away in between | All 21 built a map. Chromium's context ceiling is around 16, so a per-mount leak would have failed somewhere after the sixteenth. `map.remove()` on teardown really does release |
| Unbounded render work | Read the style; watched the frame | One extrusion layer, `minzoom: 13`, height ramped from zero across a single zoom level so the whole city is never both visible and full-height at low zoom. Nothing data-driven but height. No React state changes per frame — `CameraControls` subscribes to three state changes, not to the camera |
| Mobile gesture conflicts | Not checkable here | **Open.** Touch is driven through CDP in a desktop Chromium with touch emulation; the events are trusted and indistinguishable from hardware to MapLibre, but a mobile browser's own pan-and-zoom fighting the map's cannot be reproduced without a phone |
| Accessibility gaps | Walked the tab order; asserted name, role and focus ring | One found and fixed (§2.2). The keyboard path to the map now has a test that uses no pointer at all |
| Privacy overreach | Read what the page requests | Nothing. The city needs no API, no database and no network; it made **zero** off-machine requests in the suite. No user data has ever reached this page — there is none to reach it until M4c |
| Tests that assert nothing | Broke the product on purpose, once per gesture | Every gesture test shown red: `dragPan.disable()` reddens both pan tests, `touchZoomRotate.disable()` reddens pinch and rotate, `scrollZoom.disable()` reddens wheel and trackpad pinch, stubbing `#handleUserInput` reddens the orbit and (after §2.1) the fly-to |

---

## 4. What M4b shipped that is not real yet

Repeated here because `CLAUDE.md` §7 wants it in one place and because three of these are
easy to mistake for finished work when looking at the screenshot.

| Thing | State |
|---|---|
| Job data on the map | **None, by design.** M4c. The page says so on screen |
| Three.js | Not imported. The signal layer is M4c |
| Map labels — neighbourhood and street names | Not drawn. Every symbol layer needs a `glyphs` URL and every glyph URL is a network call. Needs a second baked artifact or a decision to accept the call |
| Window speckle on the towers | Needs a texture, a texture needs a sprite, and a sprite is a network call this style has spent two tasks refusing. §2.1's treatment is half-built and the half that is missing is named |
| Trackpad rotation | Handled in code, untested in any browser: `gesturestart`/`gesturechange` are Safari-only events |
| Touch on a phone | Untested. See §3 |
| Nominatim | Still unbuilt, still deferred. Only rung 1 can produce a building |
| `data/company-locations.yaml` | Nine companies, every `street_address` blank. Blank is a correct answer, and until one is filled the honest render is every role in the unresolved layer |

---

## 5. What to carry into M4c

1. **Do not write a whole-viewport feature query.** §2.3. It answers zero in the view the
   product opens in.
2. **Assert the state only our code owns.** §2.1. MapLibre implements a lot of what this
   product needs; a test of shared behaviour proves nothing about the half we wrote.
3. **The label goes on the node that takes focus.** §2.2. For every control M4c adds to the
   canvas, the question is not "is there an `aria-label`" but "on what, and does anything
   focus it".
4. **The instrument for a renderer is a renderer.** The 44 jsdom tests around the camera are
   worth keeping and could not have caught a single defect in this review. Every M4c
   feature that is visible needs a browser test, and the budget for it is now 25 minutes of
   CI.
5. **A frame is not the same as a query.** Buildings were being drawn perfectly while the
   API for asking about them returned nothing. When M4c's beacons appear correct on screen,
   that is not evidence the selection layer can find them.
