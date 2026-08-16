/**
 * The dark basemap style, written by hand over the archive's own layers.
 *
 * Hand-written rather than adapted from a published dark theme, because the
 * requirement is unusual: this map is a *surface data is read against*, not a
 * map. `city.md` §2.2 is the governing sentence — *"most of the city should
 * remain dark so active data can breathe"* — and every off-the-shelf dark style
 * spends its brightness budget on the basemap, which is exactly the budget M4c
 * needs for beacons.
 *
 * So nothing here is allowed to be as bright as a job. That used to be stated as
 * a hard cap at `ink-400`; ADR 0023 lit the city and replaced the cap with the
 * rule it stood in for — every colour on this map keeps a stated margin below
 * `signal-400`, so a beacon always has somewhere brighter to be.
 *
 * **ADR 0029 moved that margin to 20 L\* and lit the ground.** The `ink-400` cap
 * was a proxy for the real rule, and the proxy became the design: `ink-450` at
 * 44.3 L\* was the brightest pixel on the map and it is a desaturated grey.
 * Streets, rail and the shoreline now draw in `neon-*` — an electric indigo that
 * carries no meaning, so a lit city costs the encoding nothing. The stack,
 * brightest last: **city < hiring building < open role.**
 *
 * ## The three ideas taken from the references (§2.1)
 *
 * **Streets are the depth cue, not a label substrate.** `02-skyline-grid-plane`
 * and `04-edge-outlined-towers` both put a grid on the ground to read distance
 * against; on a real basemap that grid already exists as the street network. So
 * roads are the most articulated thing in this style — four widths on a ramp,
 * separated enough that a motorway reads as a motorway at a glance — and they
 * are the primary read of the ground rather than a place to hang names.
 *
 * **Light is linear, not surface.** Nothing here is a lit fill — not one. Every
 * bright thing on the ground is a line: the street ramp, and the shoreline drawn
 * as the outline of the water rather than as a colour on the land. That is what
 * lets the city be neon without becoming uniformly half-lit, which is the state
 * a beacon has nothing to stand against.
 *
 * **The purple is in the air.** The `sky` block is the whole of the reference
 * images' violet field: a graded dusk overhead, a glow at the horizon, fog
 * between the viewer and the far city. §3 permits `dusk-*` here and nowhere
 * else.
 *
 * ## What is deliberately absent
 *
 * **The archive's own buildings.** It carries an OSM `buildings` layer and this
 * style does not draw it. Those heights are mostly guesses — OSM records a real
 * height for a small fraction of buildings and estimates the rest from storey
 * counts. §5.3 takes heights from NYC Open Data's `height_roof` precisely so the
 * skyline is measured, and drawing the OSM layer now would either double-draw
 * against the real extrusion or quietly become it. The measured one is a
 * separate source, `nyc-buildings`, and it is the last layer in the style.
 *
 * **Text.** Every symbol layer needs a `glyphs` URL, and every glyph URL is a
 * network call — which `make demo` may not make. Self-hosting the font stack is
 * a second baked artifact and it buys neighbourhood names, which are not in
 * M4b's acceptance. Recorded in PROGRESS under "Not real yet" rather than left
 * as an omission somebody has to rediscover.
 *
 * **`landcover`.** The layer exists in the archive and was measured absent from
 * every NYC tile sampled at z8-z15: it carries low-zoom natural land cover, and
 * New York is urban_area all the way down. Styling it would be styling nothing.
 *
 * ## Where the `kind` values come from
 *
 * Measured, not remembered. Every filter below was read out of this exact
 * archive by decoding tiles at z8, z10, z12, z14 and z15 across Midtown, Lower
 * Manhattan, Brooklyn, Staten Island and JFK. `darkStyle.test.ts` pins the ones
 * whose absence would silently blank a layer.
 */

import type {
  ExpressionSpecification,
  FilterSpecification,
  LayerSpecification,
  StyleSpecification,
} from 'maplibre-gl';

import { basemapManifest, BASEMAP_URL, buildingsManifest, BUILDINGS_URL } from '@/lib/tiles';

import { MAP_PALETTE as C } from './palette';

/** The id the ground draws from, and the id M4c's beacons will sit above. */
export const BASEMAP_SOURCE = 'protomaps';

/** New York's own footprints, at heights the city measured. A separate archive. */
export const BUILDINGS_SOURCE = 'nyc-buildings';

/**
 * Feet to metres, applied here and nowhere else.
 *
 * The tiles carry `height_roof` in the source's own units, which is feet,
 * because a conversion done in the bake and again in the style is a factor
 * applied twice — and a city 3.3 times too tall renders perfectly, which is what
 * makes that class of bug expensive. One conversion, at the point of use.
 */
const FEET_TO_METRES = 0.3048;

/**
 * What a footprint with no measured height is drawn as, in feet.
 *
 * §5.3 asks for a documented default that is *recorded as having been taken*.
 * This is the documented part; the record is in the manifest, which counts the
 * structures NYC publishes with no `height_roof` — see `buildingsManifest`, and
 * `test_the_buildings_archive_records_what_it_could_not_measure`, which fails if
 * that fraction ever rises past 1%.
 *
 * Twenty-five feet is a two-storey building. It is chosen to be *unremarkable
 * rather than accurate*: the alternative — an average, or a guess from the
 * footprint's area — produces a plausible skyline out of data nobody measured,
 * which is exactly the small lie §5.3 is written against. A building at the
 * default should look like the low-rise it probably is and should never be
 * mistaken for a tower.
 */
const DEFAULT_HEIGHT_FEET = 25;

/**
 * `height_roof` as a number of feet, with the default substituted for a missing
 * one.
 *
 * Cast because MapLibre's `ExpressionSpecification` is a union of some ninety
 * tuple shapes and TypeScript will not infer a nested `let` into it. The cast is
 * on the smallest possible thing — this expression, not the layer — and the
 * expression itself is asserted in `darkStyle.test.ts`, which reads the built
 * style rather than trusting the type.
 */
const HEIGHT_FEET = [
  'let',
  'measured',
  // The attribute arrives as a string — NYC's GeoJSON export quotes its numbers
  // and tippecanoe preserves the type it was given. `to-number` with a fallback
  // covers the quoted number, the null and the empty string in one expression.
  ['to-number', ['get', 'height_roof'], 0],
  ['case', ['>', ['var', 'measured'], 0], ['var', 'measured'], DEFAULT_HEIGHT_FEET],
] as unknown as ExpressionSpecification;

/**
 * The height ramp, in feet, and the shade each rung is drawn at.
 *
 * **Colour carries height, and height is the one thing this layer actually
 * knows.** ADR 0023 lights the city, which raises the question of what the light
 * should mean — and the answer that costs nothing and lies about nothing is: how
 * tall the building is. NYC measured it. A brighter tower against dimmer
 * low-rise reproduces the reference images' depth read while remaining a
 * *rendering of the data*, not a decoration applied over it.
 *
 * The rungs are the city's own shape rather than an even ramp: most of New York
 * is under 60 feet, so an even ramp would render almost everything at the bottom
 * shade and waste the range on the handful of towers.
 *
 * **ADR 0029 dropped the whole ramp four shades, and that is the change that
 * makes the city look like the references rather than like a 3D model of it.**
 * It used to run `ink-800` → `ink-450`, which put pale blue-grey masses across
 * most of the frame — the brightest thing on screen, and grey. The references
 * do the opposite: the mass is near-black and the *edges* carry the light. So
 * the ramp is now `ink-950` → `ink-600`, a city of silhouettes, and the light
 * moved to `crownLayer` below. Height still reads, over a narrower range,
 * against a ground that is finally bright enough to read it against.
 */
const HEIGHT_STOPS: ReadonlyArray<readonly [feet: number, colour: string]> = [
  [0, C.ink950],
  [40, C.ink900],
  [120, C.ink800],
  [400, C.ink700],
  [900, C.ink600],
];

/**
 * How tall a building must be, in feet, before its roofline is lit.
 *
 * A crown on everything is a city with a bright fog at head height — most of New
 * York is under 60 feet, so the band would land in a continuous sheet across the
 * low-rise and read as haze rather than as a skyline. Gating it concentrates the
 * neon on the buildings that make the silhouette, which is also what makes the
 * reference images read: in `04-edge-outlined-towers-starfield` the lit edges
 * are on towers and the low-rise is a dark mat underneath them.
 *
 * **Chosen from a count, after picking it by eye twice and being wrong twice.**
 * At the opening pose there are 25,176 footprints on screen:
 *
 * | threshold | lit   | share |
 * |-----------|-------|-------|
 * | >150 ft   | 3,181 | 12.6% |
 * | >250 ft   | 1,107 |  4.4% |
 * | >400 ft   |   408 |  1.6% |
 * | >600 ft   |   103 |  0.4% |
 *
 * (Tallest on screen: 1,550 ft.) At 150 the frame reads as a carpet of lit
 * roofs. At 400 it reads as Midtown and the Financial District glowing over a
 * dark city, which is both the reference image and the actual place.
 *
 * The number also has to leave somewhere for M4e Task 6 to stand. A hiring
 * building is drawn in `alert-400`, only 8 L* above `neon-400` — so what
 * separates it is hue and *how much of the building is lit*, not brightness. A
 * city where one building in eight already glows leaves that nothing to be.
 */
const CROWN_MIN_FEET = 400;

/** The lit band at the top of a tower, in metres. Two storeys of light. */
const CROWN_METRES = 7;

/** `height_roof`, converted. The conversion appears here and is reused, never repeated. */
const HEIGHT_METRES = ['*', HEIGHT_FEET, FEET_TO_METRES] as unknown as ExpressionSpecification;

/**
 * How tall the *mass* is drawn, which is the roof minus the crown wherever a
 * crown is drawn.
 *
 * The subtraction is the whole reason the two layers do not z-fight: they meet
 * at a plane instead of sharing seven metres of wall. Written with `let` so the
 * feet-to-metres factor appears once — `darkStyle.test.ts` counts it, and a
 * conversion applied twice renders a city 3.3 times too tall, perfectly.
 */
const MASS_HEIGHT_METRES = [
  'let',
  'm',
  HEIGHT_METRES,
  ['case', ['>', HEIGHT_FEET, CROWN_MIN_FEET], ['-', ['var', 'm'], CROWN_METRES], ['var', 'm']],
] as unknown as ExpressionSpecification;

/** Water, in every form the archive labels it across the harbour and the parks. */
const WATER_KINDS = [
  'ocean',
  'water',
  'river',
  'bay',
  'strait',
  'canal',
  'dock',
  'lake',
  'basin',
  'reef',
  'stream',
  'swimming_pool',
  'fountain',
  'ditch',
];

/**
 * Green space, and only green space.
 *
 * `landuse` also carries `school`, `hospital`, `industrial`, `commercial`,
 * `residential` and a dozen more. Drawing those tiles most of New York in a
 * lighter shade, which is the opposite of §2.2 — the city would read as
 * uniformly half-lit and a beacon would have nothing to stand against.
 */
const GREEN_KINDS = [
  'park',
  'wood',
  'forest',
  'grass',
  'grassland',
  'garden',
  'meadow',
  'scrub',
  'nature_reserve',
  'recreation_ground',
  'cemetery',
  'dog_park',
  'golf_course',
  'playground',
  'pitch',
  'zoo',
];

/**
 * One layer per road weight, because a single data-driven width expression
 * cannot also vary colour, opacity and dash pattern — and the point of the ramp
 * is that a motorway and a footpath read as different *kinds* of thing rather
 * than as two thicknesses of the same thing.
 *
 * **Importance is carried by weight and by brightness, and the two never
 * disagree.** Until ADR 0029 it was weight alone: the `ink-400` cap left no
 * brighter shade to promote a motorway into, so the two busiest classes shared
 * a colour and were separated only by width. The `neon-*` family gives the ramp
 * its other half back — never darker, always wider, straight down the family.
 *
 * **This is the synthwave grid, and it is not a decoration.** §2.1 says the
 * street network *is* the grid; Manhattan reads as one because it is one. The
 * only thing the style was ever missing was the light. Nothing here is
 * fabricated to produce the look — every line is a road OpenStreetMap recorded,
 * drawn at the weight its own `kind` earns.
 */
const ROADS: ReadonlyArray<{
  readonly id: string;
  readonly kinds: readonly string[];
  readonly color: string;
  readonly minzoom: number;
  /** [zoom, width] stops, interpolated linearly. */
  readonly widths: ReadonlyArray<readonly [number, number]>;
  readonly opacity?: number;
  readonly dash?: readonly [number, number];
}> = [
  {
    id: 'road-path',
    kinds: ['path'],
    color: C.neon900,
    minzoom: 14,
    widths: [
      [14, 0.4],
      [18, 1.6],
    ],
    opacity: 0.6,
  },
  {
    id: 'road-ferry',
    kinds: ['ferry'],
    color: C.ink600,
    minzoom: 10,
    widths: [
      [10, 0.5],
      [16, 1.2],
    ],
    opacity: 0.5,
    dash: [1, 3],
  },
  {
    id: 'road-rail',
    kinds: ['rail'],
    color: C.neon900,
    minzoom: 11,
    widths: [
      [11, 0.5],
      [18, 1.6],
    ],
    dash: [3, 2],
  },
  {
    id: 'road-minor',
    kinds: ['minor_road', 'other'],
    color: C.neon700,
    minzoom: 12,
    widths: [
      [12, 0.5],
      [15, 1.4],
      [18, 6],
    ],
  },
  {
    id: 'road-major',
    kinds: ['major_road', 'aeroway'],
    color: C.neon500,
    minzoom: 8,
    widths: [
      [8, 0.5],
      [12, 1.2],
      [15, 2.6],
      [18, 12],
    ],
  },
  {
    id: 'road-highway',
    kinds: ['highway'],
    color: C.neon400,
    minzoom: 5,
    widths: [
      [5, 0.8],
      [10, 2],
      [15, 5],
      [18, 20],
    ],
  },
];
/** `['interpolate', ['linear'], ['zoom'], z0, w0, z1, w1, …]` */
function byZoom(stops: ReadonlyArray<readonly [number, number]>): unknown {
  return ['interpolate', ['linear'], ['zoom'], ...stops.flat()];
}

function roadLayers(): LayerSpecification[] {
  return ROADS.map((road) => {
    const paint: Record<string, unknown> = {
      'line-color': road.color,
      'line-width': byZoom(road.widths),
    };
    if (road.opacity !== undefined) paint['line-opacity'] = road.opacity;
    if (road.dash !== undefined) paint['line-dasharray'] = [...road.dash];

    return {
      id: road.id,
      type: 'line',
      source: BASEMAP_SOURCE,
      'source-layer': 'roads',
      minzoom: road.minzoom,
      filter: ['match', ['get', 'kind'], [...road.kinds], true, false],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint,
    } as LayerSpecification;
  });
}

/**
 * New York, extruded to the heights the city measured.
 *
 * **Why this is one layer and not two.** The reference images read as edge-lit
 * masses, and the obvious way to build that is a fill plus an outline. MapLibre
 * has no outline for an extrusion — a `line` layer on the same footprints draws
 * on the ground, under the building, where it is invisible. What it does have is
 * `fill-extrusion-vertical-gradient`, which darkens each wall toward its base;
 * against a lit sky that produces the same read, one layer, no second pass over
 * a million footprints. The remaining half of §2.1's treatment — window speckle
 * — needs a texture, a texture needs a sprite, and a sprite is a network call
 * this style has spent two tasks refusing. It belongs to the Three.js layer, and
 * it is listed under "Not real yet" rather than left as something to rediscover.
 *
 * **Nothing here is data-driven by anything but height.** Not by `feature_code`,
 * not by age, not by whether a company sits inside it. A hiring building is
 * distinguished by a beam (ADR 0023), and a beam is M4c's job; a building that
 * changed colour when a job appeared would spend the encoding twice and would
 * still be invisible at ten-in-fifty-thousand.
 */
function buildingLayer(): LayerSpecification {
  return {
    id: 'buildings',
    type: 'fill-extrusion',
    source: BUILDINGS_SOURCE,
    'source-layer': 'buildings',
    // The archive starts at z13 and MapLibre overzooms above z16, which for an
    // extrusion is exactly right: the geometry is the same, only the detail
    // budget changes. Below z13 the whole city is a texture and drawing a
    // million footprints into it costs frames for nothing.
    minzoom: 13,
    paint: {
      'fill-extrusion-height': [
        'interpolate',
        ['linear'],
        ['zoom'],
        // Buildings grow out of the ground as they come into view, over a single
        // zoom level. Popping a skyline into existence at z13 reads as a bug;
        // this reads as approach. It is also a real perf lever — at z13 the
        // extrusions are near zero height and cheap to rasterise.
        13,
        0,
        14,
        MASS_HEIGHT_METRES,
      ],
      'fill-extrusion-base': 0,
      'fill-extrusion-color': [
        'interpolate',
        ['linear'],
        HEIGHT_FEET,
        ...HEIGHT_STOPS.flatMap(([feet, colour]) => [feet, colour]),
      ],
      // Opaque, so the depth buffer sorts the city correctly. A translucent
      // extrusion layer lets the streets show through the towers, which at 76°
      // of pitch is most of the frame.
      'fill-extrusion-opacity': 1,
      'fill-extrusion-vertical-gradient': true,
    },
  } as LayerSpecification;
}

/**
 * The lit roofline. Reference 04's top edge, for one extra layer.
 *
 * §5.3 is right that MapLibre has no outline for an extrusion: a `line` layer on
 * the same footprints draws on the ground, underneath the building, where it is
 * invisible. What it does have is `fill-extrusion-base`, and a second extrusion
 * of the same footprints starting a few metres below the roof is a band of light
 * around the top of every tower — the edge-lit read, from the same geometry, no
 * texture and no second archive.
 *
 * **The two layers stack rather than overlap.** The mass below stops at
 * `height − CROWN_METRES` wherever a crown is drawn, so the two volumes are
 * disjoint and share no wall. Overlapping them would mean two coplanar surfaces
 * at identical depth, which resolves differently per driver and shows up as the
 * band flickering or mottling as the camera moves — the class of defect that
 * looks like a GPU problem and is a geometry problem.
 *
 * **The crown is not data.** It says nothing a beacon says: not that a company
 * is here, not that a role is open, not how fresh anything is. It is what a tall
 * building looks like at night in this city, and `treatments.ts` remains the
 * only place a mark means something.
 */
function crownLayer(): LayerSpecification {
  return {
    id: 'buildings-crown',
    type: 'fill-extrusion',
    source: BUILDINGS_SOURCE,
    'source-layer': 'buildings',
    minzoom: 13,
    // `['to-number', …]` directly rather than `HEIGHT_FEET`, and the difference
    // is not style.
    //
    // The first version filtered on `HEIGHT_FEET`, which wraps the lookup in a
    // `let`/`var` pair. In a *paint* expression that is fine; in a **filter** it
    // silently matched everything, and the result is in
    // `milestone-4e-buildings.png`: a neon roof on every structure in New York,
    // because a building below the threshold still drew its top cap — with
    // base equal to height, a zero-thickness extrusion is invisible from the
    // side and a solid lit polygon from above. Nothing errored. It looked like
    // a deliberate design choice.
    //
    // Reading the attribute straight also makes the missing-height case read
    // correctly on its own terms: no `height_roof` resolves to 0 and is
    // excluded, which is right. `DEFAULT_HEIGHT_FEET` exists so an unmeasured
    // footprint has a body; it must not be able to earn a crown, because a lit
    // roofline on a building nobody measured is a claim about the skyline that
    // the data does not make.
    filter: [
      '>',
      ['to-number', ['get', 'height_roof'], 0],
      CROWN_MIN_FEET,
    ] as unknown as FilterSpecification,
    paint: {
      // Grows in over the same zoom as the mass it sits on, or the crowns would
      // appear at z13 floating over buildings of zero height.
      'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 13, 0, 14, HEIGHT_METRES],
      'fill-extrusion-base': ['interpolate', ['linear'], ['zoom'], 13, 0, 14, MASS_HEIGHT_METRES],
      'fill-extrusion-color': C.neon400,
      'fill-extrusion-opacity': 1,
      // Off, deliberately. The gradient exists to darken a wall toward its base,
      // which on a seven-metre band would shade away most of the light this
      // layer is here to add.
      'fill-extrusion-vertical-gradient': false,
    },
  } as LayerSpecification;
}

/**
 * The whole style, as a value.
 *
 * A function rather than a constant so it stays cheap to test and impossible to
 * mutate by accident — MapLibre takes ownership of the object it is handed and
 * a shared constant would be modified in place by the first `setPaintProperty`.
 */
export interface DarkStyleOptions {
  /**
   * Draw the measured skyline. Default true.
   *
   * False when the buildings archive is not on this machine — `make setup`
   * fetches both, so this is the clean-clone case and the half-finished-setup
   * case. It omits the source as well as the layer, because a source MapLibre
   * cannot load raises an `error` event, and this component treats an error as
   * "the map is broken" and replaces a perfectly good city with a card. A city
   * with no skyline is a worse map and a true one; a card over a city that
   * renders is neither.
   */
  readonly buildings?: boolean;
}

export function buildDarkStyle({ buildings = true }: DarkStyleOptions = {}): StyleSpecification {
  return {
    version: 8,
    name: 'Nightshift — dark city',
    // No `glyphs` and no `sprite`: this style draws no text and no icons, and
    // both would be network calls that `make demo` may not make.
    sources: {
      [BASEMAP_SOURCE]: {
        type: 'vector',
        url: `pmtiles://${BASEMAP_URL}`,
        attribution: basemapManifest.attribution,
      },
      // A second archive, and a second attribution — NYC Open Data's terms ask
      // for one, and MapLibre shows whatever its sources declare.
      ...(buildings
        ? {
            [BUILDINGS_SOURCE]: {
              type: 'vector' as const,
              url: `pmtiles://${BUILDINGS_URL}`,
              attribution: buildingsManifest.attribution,
            },
          }
        : {}),
    },
    /**
     * The light the extrusions are shaded by, declared rather than defaulted.
     *
     * **This is what actually made the city grey**, and neither the palette nor
     * the height ramp was ever going to fix it. MapLibre shades every
     * `fill-extrusion` face by a global light, and a style that omits the block
     * gets the default: white, `intensity: 0.5`, anchored to the viewport. That
     * term is added to the fill, so it sets a floor no colour can go below — the
     * ramp was dropped four full shades to `ink-950`→`ink-600` and the towers
     * came back the same pale grey, because what was on screen was mostly the
     * light and not the paint at all.
     *
     * Found by hiding the crown layer and looking at what was left, after two
     * rounds of correctly reasoning about the wrong component.
     *
     * So: dim, and tinted. `intensity` at 0.18 lets the near-black ramp actually
     * be near-black, which is what turns the mass into the silhouette the
     * references are built from. The colour is `neon-700` because the light in
     * those images is coloured — a white key light over a violet city reads as a
     * grey model of one — and because a light is not a mark: it lands on every
     * face equally, carries no state, and cannot be mistaken for data.
     *
     * `anchor: 'viewport'` keeps the shading stable through a 360° orbit. Anchored
     * to the map instead, the lit side swings around the towers as the camera
     * rotates, which reads as the sun racing overhead.
     */
    light: {
      anchor: 'viewport',
      color: '#ffffff',
      intensity: 0.18,
      position: [1.5, 210, 30],
    },
    // The reference images' violet field, and the only place it is permitted.
    sky: {
      'sky-color': C.dusk900,
      'horizon-color': C.dusk300,
      'fog-color': C.dusk500,
      // A wide, soft transition rather than a hard band: the glow should look
      // like distance, not like a stripe someone drew across the horizon.
      // 0.8 until M4e, and it is what made the sky read as "a neon purple
      // rectangle placed at the top" rather than as a sky.
      //
      // The blend says how far the horizon colour reaches up into the sky
      // colour, and at 0.8 the magenta reached nearly all of it. At pitch 76
      // only a shallow strip of sky is in frame at all — the dark `sky-color`
      // overhead is out of view — so the whole visible band was one flat
      // horizon magenta with a hard edge where the city started. There was a
      // gradient; none of it was on screen.
      //
      // At 0.55 the magenta is compressed toward the skyline and `dusk-900`
      // takes over above it, which puts the whole gradient inside the strip a
      // person is actually looking at. 0.3 goes too far the other way and the
      // sky reads as black.
      //
      // **This is an improvement, not the fix.** Two things were measured while
      // tuning it and neither can be solved from this block:
      //
      //   * **More sky needs more pitch, and pitch is capped at 78.** Higher
      //     pitch tips the horizon down into frame; at 70 it leaves the top of
      //     the viewport entirely. So the sky is a shallow strip by
      //     construction, and `CAMERA_LIMITS.maxPitch` is where it is because
      //     the tile budget explodes past it, not by preference.
      //   * **The hard edge under the sky is the far ground, and fog does not
      //     reach it.** Beyond a few kilometres `earth` renders near-black and
      //     meets the horizon magenta with no transition, which is what reads
      //     as "a neon rectangle placed at the top". `fog-ground-blend` and
      //     `horizon-fog-blend` were swept from 0 to 0.85 and the band did not
      //     move; recolouring `background` did not move it either, because the
      //     band is drawn ground rather than void.
      //
      // The horizon glow that would actually close that gap — and the sun and
      // the starfield — belong to a custom layer, which is M4e Task 3.
      'sky-horizon-blend': 0.55,
      'horizon-fog-blend': 0.6,
      'fog-ground-blend': 0.85,
      // Haze thins as you descend into the streets. At city zooms you are
      // inside the weather; from above you are looking through it.
      'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 4, 1, 12, 0.85, 16, 0.45],
    },
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: { 'background-color': C.ink950 },
      },
      {
        id: 'earth',
        type: 'fill',
        source: BASEMAP_SOURCE,
        'source-layer': 'earth',
        paint: { 'fill-color': C.ink800 },
      },
      {
        id: 'green',
        type: 'fill',
        source: BASEMAP_SOURCE,
        'source-layer': 'landuse',
        filter: ['match', ['get', 'kind'], GREEN_KINDS, true, false],
        paint: { 'fill-color': C.ink700, 'fill-opacity': 0.7 },
      },
      {
        id: 'water',
        type: 'fill',
        source: BASEMAP_SOURCE,
        'source-layer': 'water',
        filter: ['match', ['get', 'kind'], WATER_KINDS, true, false],
        paint: {
          // The harbour stays the darkest thing in frame, and that is the
          // decision rather than an omission. A lit water *fill* would put the
          // brightest surface in the city under the part of the frame with no
          // data on it — New York is a harbour city and water is most of the
          // viewport at the opening pose. The read comes from the edge.
          'fill-color': C.ink950,
          // The brightest line on the ground, and the one that costs a single
          // property. §2.1's "light is linear, not surface" applied to the
          // coast: the Hudson, the East River and the harbour draw themselves
          // as glowing edges, which is most of the synthwave read on a real map
          // of this city. ADR 0029 is what let it climb from `ink-600`.
          'fill-outline-color': C.neon400,
        },
      },
      ...roadLayers(),
      {
        id: 'boundary-county',
        type: 'line',
        source: BASEMAP_SOURCE,
        'source-layer': 'boundaries',
        minzoom: 8,
        filter: ['==', ['get', 'kind'], 'county'],
        paint: {
          'line-color': C.ink500,
          'line-width': 0.7,
          'line-dasharray': [4, 3],
          'line-opacity': 0.6,
        },
      },
      // Last, so the city occludes the ground it stands on. The crown follows
      // the mass it sits on top of.
      ...(buildings ? [buildingLayer(), crownLayer()] : []),
    ],
  } as StyleSpecification;
}
