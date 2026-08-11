# The living city — the M4 design

- **Status:** accepted
- **Date:** 2026-08-11
- **Milestone:** M4 (four slices, M4a–M4d)
- **Implements:** PRODUCT-SPEC §4.2–4.3, §9, §12.4
- **Constrained by:** invariants I1, I4, I6, I7; AMENDMENTS A4, A7, A9, A14, A15
- **Visual reference:** `docs/design/references/`

M3 made the product able to explain itself. M4 makes it able to show you the city,
and A15 calls it the ship: at the end of M4 this is deployable, demoable and
defensible, and everything after it is upside on a project that already counts.

Read this before writing any M4 plan, any geocoder, any MapLibre and any Three.js.
It decides the shapes and the order; the plans sequence them.

---

## 1. What M4 delivers, and why the map is not the first slice

`CLAUDE.md` §6 lists M4's acceptance: 60fps desktop and 30fps mobile during normal
exploration; every gesture working on trackpad and touch; interruptible camera
animations; **no fake precise placement**; thousands of markers that are not
thousands of React components; list and map synchronised; every map action with a
non-3D equivalent; metrics recorded.

Every one of those is a statement about a renderer. None of them can be earned yet,
because **the renderer has nothing it is permitted to draw.**

No coordinate has ever been written to this database. `job_locations.geom` is a
column with a GiST index and no values. `mappable_locations` reads 0 and the
Explore page says "nothing geocoded yet", honestly. Geocoding was labelled "real at
M1" in `PROGRESS.md` for four consecutive milestones and was never built — M1
closed, M2 closed, M3 closed, and the number of coordinates stayed at zero.

So the temptation at the top of M4 is precise, predictable, and needs naming before
it arrives: **a beautiful renderer over an empty geo table will want to put the jobs
somewhere.** The nearest available lie is a Manhattan centroid with a small random
scatter, and it would look correct, demo well, and violate I1 on every frame.

The order is therefore:

| Slice | Delivers | Renders |
|---|---|---|
| **M4a** | The geo spine: geocoding, `company_locations`, the confidence ladder filled in with real values | Nothing 3D. A count, a table, and an honest coverage readout |
| **M4b** | Basemap, building footprints, extrusion, the camera controller | The dark city, empty of data |
| **M4c** | The signal layer: beacons, the unresolved layer, selection, list↔map sync | The city with the jobs in it |
| **M4d** | Performance instrumentation, quality tiers, accessibility, the ship | The same city, measured |

M4b is where it starts to look like something. M4a is where it starts to be true.

---

## 2. The references, translated

Four images were supplied on 2026-08-11 as the intended feel — `docs/design/references/`.
They are consistent with each other and with §4.2, and they are worth reading
carefully rather than imitating, because three of the four contain a structural idea
this product needs and all four contain one it must refuse.

### 2.1 What to take

**Light is linear, not surface.** In `01-street-canyon` the towers are black masses;
what glows is a set of vertical bars and edge strips applied to them. In
`04-edge-outlined-towers` the buildings are near-black with a lit outline along their
silhouette edges and a sparse speckle of windows. Neither image lights a façade. This
is the single most useful thing in the set: an edge-lit dark mass reads unmistakably
as a building at a fraction of the visual weight of a lit one, which leaves the
brightness budget free for data.

**A beam that rises out of a building and fades into the sky.** `02-skyline-grid-plane`
draws exactly the job beacon this product needs, before the product drew it — a
narrow column of light leaving a rooftop and dissipating with height. It reads at
any zoom, it survives being small, and it does not obscure the building it belongs
to. It is also naturally instanceable: one quad, one shader, N transforms.

**A ground plane you can read distance on.** Both `02` and `04` put a grid on the
ground. On a real basemap this is already there in the form of the street network —
which means the street layer is not decoration, it is the depth cue, and the style
should treat it as the primary read of the ground rather than as a label substrate.

**Atmosphere for depth.** Haze behind the skyline in `02`, a starfield above in `02`
and `04`, a sky gradient in `03`. §9.2 asks for atmospheric perspective and careful
fog; the references show what "careful" looks like — the haze is behind the city and
between the viewer and the far buildings, never in front of the near ones.

### 2.2 What to refuse

**Every building glows.** In all four images the whole skyline is lit. That is the
one thing this city may never do, and not for taste reasons: §9.2 says *"most of the
city should remain dark so active data can breathe"*, and if every building is lit
then illumination carries no information. Nightshift's city is these images **with
the lights off**, where a building is lit because a company there is hiring and for
no other reason. The neon is the encoding, not the wallpaper.

The practical consequence is that Nightshift will look *emptier* than these
references, especially at the current corpus size, and that is correct rather than a
shortfall. A skyline with nine lit buildings is telling you there are nine employers
with open roles in view. A skyline with four hundred lit buildings is telling you
nothing.

**Heavy bloom.** §4.2's avoid-list names excessive bloom and hard-to-read glowing
text explicitly. The references are bloom-heavy because they are stills; on a
surface a person reads job titles off, bloom eats the small type first. Bloom is a
quality-tier setting (§5.5), tuned to be visible at Ultra and absent at Battery
saver, and no text is ever rendered inside it.

**`03-ground-level-saturated` as a whole.** Palms, signage, a sunset gradient and
near-total saturation. It is a scene and this is an instrument. Its sky gradient and
its notion of a building surface carrying content are worth keeping; the rest is
retro furniture that would make the product read as a toy — §4.2's "toy-like sci-fi"
and "cheap cyberpunk clutter" are on the avoid-list for a reason.

**The reflective wet ground.** Beautiful in `02` and `04`, and it doubles the
apparent number of light sources — which is a direct fight with legibility over a
basemap that has to carry roads, water and neighbourhood labels. Not in M4. Revisit
at M5 as a quality-tier extra, where it belongs.

---

## 3. The palette, and the one conflict the references create

The tokens exist already, in `apps/web/src/app/globals.css`, and they came from
§4.2: `ink-*` for blackened masses, `signal-*` for cyan energy, `alert-*` for
controlled magenta, `gold-400` for sparse urgency, `paper-*` for text. Every text
token clears WCAG AA against every surface it appears on, asserted in
`colour-contrast.test.ts`. M4 adds tokens; it does not restyle.

**The conflict.** The stylesheet's own rule reads: *"Magenta means 'something is
wrong and you can act on it'. It is never decorative."* The reference images use
magenta as roughly half of all the light in frame, decoratively, everywhere. Taken
literally, the references would require magenta to mean nothing, which would cost
the product the meaning it has spent four milestones establishing.

**The resolution: the purple is in the air, not on the objects.**

A new `dusk-*` family carries the references' violet field — sky gradient,
atmospheric haze, the horizon glow behind the skyline, the far-distance fog. It is
**atmosphere only**: never a data mark, never a building, never text, never a
selection state. `alert-*` keeps its meaning on marks, where meaning lives.

This gets the look honestly. The synthwave read in those images comes mostly from
the *field* — the graded violet sky and haze — rather than from the marks, which is
why the discipline costs nothing visually and buys the encoding everything.

| Family | Role in the city | May carry a meaning? |
|---|---|---|
| `ink-*` | Building mass, water, land, panel surfaces | No — surfaces only, never text |
| `dusk-*` **(new)** | Sky gradient, haze, fog, horizon glow, starfield | **No — atmosphere only** |
| `signal-*` | Beacons, building edge-light, selection, the active state | Yes |
| `alert-*` | Degradation, staleness, source failure | Yes, and only this |
| `gold-400` | Urgency — a deadline you can still act on | Yes, and sparingly |
| `paper-*` | All text, on every surface | Yes |

Every `dusk-*` value is added with its assertion in `colour-contrast.test.ts` per
`CLAUDE.md` §7 — for `dusk-*` the assertion is the inverse of the usual one: it
proves the token is **never** used as a text or accent colour, because a token that
cannot clear AA must not be able to reach text.

---

## 4. M4a — the geo spine

### 4.1 The count comes before the geocoder

**The first task of M4 is a measurement nobody in this project has run:** of the
location strings already sitting in `job_locations` and in the raw
`source_job_records` payloads, how many contain a street address, how many are a
bare place name ("New York, NY"), how many are remote, and how many are nothing at
all?

It decides the product. If most postings carry a resolvable address, the city is
buildings with a modest unresolved layer beside it. If most carry a bare place name,
then **the unresolved layer is the main view and the buildings are the minority**,
and §4.7 is a headline feature rather than an edge case.

Nothing in the repository measures this yet. ADR 0008 is the nearest thing and it
does not answer the question — it decides how the single string `"New York"` parses,
and it is worth reading first because it is the shape of the problem: that ADR exists
because bare place names were common enough in real payloads to threaten the polling
tiers. Suggestive, not a measurement. Run the count.

Those are two different products. Designing the renderer before knowing which one
this is would be guessing, and the guess would be discovered late, in M4c, after the
expensive part was built.

Write the number into `PROGRESS.md`. Then build the geocoder.

### 4.2 The fallback chain

A4, unchanged, implemented behind one Protocol so nothing else imports an HTTP
client:

| Order | Source | Yields |
|---|---|---|
| 1 | **NYC GeoSearch** — Pelias over the city's Property Address Directory, free, no key | `verified` |
| 2 | **Nominatim** — 1 req/sec, self-identifying, cached hard | `approximate` |
| 3 | **Neighbourhood centroid** — a static committed lookup | `approximate`, flagged with its method |
| 4 | Nothing resolved | `city_only`, `remote` or `unknown` |

Every result is cached permanently by normalised address string, with its provider,
its confidence and its timestamp. **An address is never geocoded twice.** The cache
is a table, not a dict, because it has to survive a restart and be inspectable when
a placement is questioned.

`resolution_method` on the row records which rung of the ladder answered, so
"why is this here?" is answerable from the data rather than from the logs.

### 4.3 `company_locations`, which does not exist yet

§6.6 specifies it and the schema does not have it. Only `job_locations` exists, fed
from ATS location strings, which are usually the bare place name the geocoder can do
least with.

A company's office address is both the better geocoding input and the better
anchor: **buildings are companies, beacons are jobs.** A job with no address of its
own inherits its company's building when the company has one — and that inheritance
is recorded as its own `resolution_method`, never silently, because "this job is at
its employer's known office" is a different and weaker claim than "this posting
stated this address", and the UI must be able to say which.

The two tables stay separate. A job that states its own address keeps it, and a
company moving its office does not retroactively move a posting that named a
different one.

### 4.4 Ashby's structured address, finally read

`address.postalAddress` is recorded verbatim in every Ashby payload and deliberately
unread, because feeding a second location source into `job_locations` before
geocoding existed would have meant two code paths writing one table. That condition
is exactly what M4a builds, so M4a reads it, with its own fixtures.

### 4.5 What is enforced, and where

I1's teeth are already in the schema — ADR 0002 put them there. M4a is the first
milestone that can actually trip them, so the guarantees get restated as tests that
attack the database directly rather than the code:

- A row with coordinates and `location_confidence = 'city_only'` is refused.
- A row with `location_confidence = 'verified'` and no coordinates is refused.
- No write path can produce a coordinate without a `resolution_method`.
- Deleting a geocode cache entry does not silently downgrade a placement — it is
  either re-resolved or the placement is withdrawn.

### 4.6 The honest coverage readout

M4a's visible deliverable, before anything is 3D: `/analyze/coverage` gains the
geocoding picture — how many jobs are placeable, at what confidence, by which rung
of the ladder, and **how many are not**. The page already names what is *not*
covered rather than only what is (an M1 acceptance criterion), and this extends it.

If M4a ends with 12% of the corpus placeable, the page says 12%. That number being
low is a fact about ATS data, not a failure of the milestone, and hiding it would be
the exact failure mode I7 exists to prevent.

### 4.7 The unresolved layer is a feature, not a fallback

§9.7 asks that jobs specifying only "New York, NY" not receive fake building
placement, and suggests floating signal stacks, a holographic queue, a ring around
the city edge.

Until §4.1's count says otherwise, plan for this to be **large**. It gets designed as
a first-class view: a legible, navigable, sortable field of signals above the city,
in which a role can be inspected, saved and applied to exactly as it can from a
building. Nothing about a job is worse because its address was not stated.

The visual grammar: unresolved signals are the same beacon geometry, **untethered**
— floating, with no building beneath them and no line drawn to one — arranged by
something honest (company, then role family), never by a spatial guess. The absence
of a ground connection is the whole message, and it is the one piece of the visual
language that is load-bearing for an invariant.

---

## 5. M4b and M4c — how it is rendered

### 5.1 One WebGL context

MapLibre GL JS owns the projection, the camera, the basemap and the building
extrusion. Three.js draws the signal layers **into MapLibre's context** as a custom
layer, taking the projection matrix MapLibre hands it each frame.

One context, one camera, one depth buffer. Two stacked canvases would drift out of
register on every gesture and would have no shared depth, so a beacon could not be
occluded by a building in front of it — and occlusion is most of what makes a scene
read as three-dimensional.

This is the single most consequential technical decision in M4 and it gets an ADR.

### 5.2 Tiles must be local, which settles A4's open choice

A4 offers "OpenFreeMap or self-hosted Protomaps" and does not choose. `CLAUDE.md` §4
does choose, indirectly and firmly: **`make demo` working offline from a clean clone
is a hard requirement, and fixing it is the highest-priority task in the repo if it
breaks.** OpenFreeMap is a network call. A basemap that fetches from a hosted tile
service cannot satisfy that.

So: **self-hosted Protomaps.** A single `.pmtiles` extract of the NYC bounding box,
served by the local stack, read directly by MapLibre through the pmtiles protocol.
No tile server process, no quota, no key, no network at render time.

The file is too large to commit. The split that keeps both requirements true:
`make setup` downloads it once and caches it — `make setup` already needs the
network to install dependencies — and `make demo` never touches the network. The
download is checksummed, its absence is a clear error message naming the command to
fix it rather than a broken map, and `docs/architecture/costs.md` gets its row: zero
dollars, no key, one cached artifact.

### 5.3 Buildings

NYC Open Data Building Footprints, which carry per-building roof height and ground
elevation — real extrusion heights for the whole city instead of OSM's guesses.
Loaded into PostGIS once, filtered to the boroughs rendered, baked into vector tiles
in the same offline pipeline as the basemap, refreshed quarterly. **Never queried
per frame**, per A4's practical note.

A building's appearance is dark mass plus edge light, per §2.1. Height comes from
`heightroof`; a footprint missing a height gets a documented default and is recorded
as having taken it, because a wrong building height is a small lie and this project
does not keep a category of small lies.

### 5.4 The camera

A dedicated controller with no React in it, wrapping MapLibre's camera rather than
replacing it. It owns everything in §9.3 — orbit, pan, wheel zoom, trackpad pinch
and rotate, touch pinch/rotate/pan, double-click focus, keyboard navigation,
programmatic fly-to and orbit-around-selection, bounds and pitch limits.

Two behaviours are acceptance criteria rather than niceties:

- **Any animation yields instantly to the user.** A gesture during a fly-to cancels
  it from wherever it has reached — no queue, no snap-back, no "let me finish".
- **`prefers-reduced-motion` is honoured at the controller**, not per-call-site, so
  a fly-to becomes an immediate cut and nothing has to remember to check.

### 5.5 Instancing and the render loop

Beacons, pulses, rings and markers are instanced: one geometry, one draw call, N
transforms. §9.5 and `CLAUDE.md` §8 both name one-object-per-job as an
anti-pattern, and at a few thousand jobs it is the difference between the milestone
passing and failing.

React never drives the render loop. Zustand holds scene state; the loop reads it.
A filter change updates an instance buffer — it does not rebuild the scene, and it
does not re-render a component tree per frame.

Adaptive quality tiers (Ultra / High / Balanced / Battery saver) adjust pixel ratio,
bloom, particle count, fog density, building detail and animation density. Measured
in M4d and **gated in M5**, per A14.

### 5.6 Selection, and the non-3D equivalent

Selecting anything highlights it, moves the camera only if needed, opens the detail
panel, preserves filters, works from the keyboard, writes to the URL so it is
shareable, and returns cleanly on escape.

The rule underneath it: **the map is a second view of the M2 list, never a
replacement for it.** Every action available on the map is available without it. The
list stays first-class, selection is one piece of state shared by both, and the
degraded path — `make test-e2e`, which runs with no API behind it — must still show
a usable product.

---

## 6. What the city encodes

§4.3's table, with A7's two corrections applied. A7 wins where they conflict.

| State | Treatment |
|---|---|
| New internship | Rapid cyan pulse |
| New non-intern role | Slow cyan pulse |
| Saved | Thin white outline |
| Applied | Solid illuminated building |
| Assessment / interview stage | Rotating ring / orbiting arcs |
| Exceptional match or urgent deadline | Gold vertical beacon |
| Offer | Soft green core |
| Closed | Fading afterimage |
| **Stale or unverified** | **Reduced opacity + an explicit "last verified N days ago" in the detail panel.** Not a glitch — a glitch reads as a bug, gets reported as one, and then gets ignored |
| **Rejection** | **Dim neutral archived state**, visible in Analyze, behind a toggle that is off by default. Not a red fracture: this tool is opened daily during a job search and accumulating red across the skyline makes it worse to use over exactly the period it is needed most |
| Approximate location | Translucent radius — an **area**, never a point |
| City-only / unresolved | Untethered floating signal (§4.7) |

The governing principle, from A7: **visual intensity tracks what you can act on, not
what happened to you.** A deadline earns gold. A rejection from three weeks ago earns
dimming.

Two standing rules apply to every row. Colour never carries a meaning alone (§12.4)
— every state with a colour also has a label or a shape. And §4.3's last line is a
deliverable, not a note: these meanings are documented **in the interface**, on a
legend the user can open, not only in this file.

---

## 7. The slice plan

### M4a — the geo spine

The count first (§4.1). Then: geocoding behind a Protocol with the A4 ladder;
the permanent geocode cache; `company_locations` and its migration; the NYC
GeoSearch adapter with committed fixtures; Nominatim, rate-limited, fixture-tested,
never reached in `make demo`; the static neighbourhood centroid file; Ashby's
`postalAddress`; the I1 enforcement tests of §4.5; the coverage readout of §4.6.

**Done when:** a real coordinate exists, `mappable_locations > 0`, every placement
traces to a rung of the ladder, and the coverage page publishes what could not be
placed.

### M4b — the dark city

The pmtiles pipeline and the `make setup` cache; footprints into PostGIS and out to
tiles; MapLibre with a hand-written dark style; extrusion at real heights; the
camera controller and its full gesture surface; `dusk-*` and the atmosphere.

**Done when:** NYC renders dark, extruded and offline in `make demo`; every gesture
in §9.3 works on trackpad and touch; every animation is interruptible; no job data
is on screen yet.

### M4c — the signal layer

Three.js in MapLibre's context; instanced beacons; the confidence treatments of §6;
the unresolved layer as a real view; selection synced to URL; list↔map sync; the
in-interface legend.

**Done when:** no placement is fabricated at any confidence, thousands of markers
are not thousands of components, and the list and the map cannot disagree.

### M4d — measured, accessible, shipped

Frame-time instrumentation and recorded metrics; adaptive quality tiers; reduced
motion end to end; a keyboard path to every map action; automated accessibility
tests (A14 puts them here); the M4 review; the deploy and the case study.

**Done when:** 60fps desktop and 30fps mobile are numbers in `PROGRESS.md` rather
than impressions, and A15's ship has actually shipped.

---

## 8. Deferred, and open

**Deferred to M5+, deliberately:** the cinematic visual system, hiring-pulse
propagation and replay (§9.8), the skill-demand layer (§9.9), timeline scrubbing
(§9.10), visual regression tests and 3D performance gates (A14), and the reflective
ground of §2.2. M4 is the honest interactive city. M5 is the cinematic one, and it
is a much better milestone on top of a city that already tells the truth.

**Open — Q2, the deployment target.** A15 calls M4 a real ship, and the shape needed
is one Next.js app, one Python service, Postgres with PostGIS and pgvector, and
Redis. What changes with the answer:

- **A paid target** (Fly.io, Railway, a small VPS — roughly $5–10/month): M4d ends
  with a live link, and the pmtiles artifact needs somewhere to live that is not the
  repository, which is a deploy-time decision rather than a design one.
- **Local only:** M4d ends with a recorded walkthrough, A9's $0 target holds
  literally, and the case study links to the repo rather than to a running city.

Not blocking M4a, M4b or M4c. Blocking M4d. An ADR gets written with the number
either way.

**Needing an ADR during M4**, decided here and recorded properly when built: the
single-WebGL-context decision (§5.1), Protomaps over OpenFreeMap and why offline
settled it (§5.2), company-inherited placement as its own resolution method (§4.3),
and `dusk-*` as atmosphere that may never carry meaning (§3).
