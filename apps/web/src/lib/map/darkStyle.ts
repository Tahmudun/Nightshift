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
 * So the basemap tops out at `ink-400`, the dimmest shade cleared for a non-text
 * indicator. Nothing here is allowed to be as bright as a job.
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
 * **Light is linear, not surface.** Nothing here is a lit fill. The one bright
 * line is the shoreline, drawn as the outline of the water rather than as a
 * colour on the land.
 *
 * **The purple is in the air.** The `sky` block is the whole of the reference
 * images' violet field: a graded dusk overhead, a glow at the horizon, fog
 * between the viewer and the far city. §3 permits `dusk-*` here and nowhere
 * else.
 *
 * ## What is deliberately absent
 *
 * **Buildings.** The archive carries an OSM `buildings` layer and this style
 * does not draw it. §5.3 takes heights from NYC Open Data's `height_roof`
 * precisely so the skyline is measured rather than guessed, and drawing OSM
 * footprints now would either double-draw against that layer or quietly become
 * it. M4b Task 3 adds the real one.
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

import type { LayerSpecification, StyleSpecification } from 'maplibre-gl';

import { basemapManifest, BASEMAP_URL } from '@/lib/basemap';

import { MAP_PALETTE as C } from './palette';

/** The id every layer draws from, and the id M4c's beacons will sit above. */
export const BASEMAP_SOURCE = 'protomaps';

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
 * **Importance is carried by weight, not by brightness.** The two busiest
 * classes share `ink-400` and are separated by width: a motorway is four times
 * the line a footpath is. That is §2.1's "light is linear" taken seriously, and
 * it is also what the `ink-400` cap forces — there is no brighter shade to
 * promote a motorway into that would not start competing with a job.
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
    color: C.ink600,
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
    color: C.ink600,
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
    color: C.ink500,
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
    color: C.ink400,
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
    color: C.ink400,
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
 * The whole style, as a value.
 *
 * A function rather than a constant so it stays cheap to test and impossible to
 * mutate by accident — MapLibre takes ownership of the object it is handed and
 * a shared constant would be modified in place by the first `setPaintProperty`.
 */
export function buildDarkStyle(): StyleSpecification {
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
    },
    // The reference images' violet field, and the only place it is permitted.
    sky: {
      'sky-color': C.dusk900,
      'horizon-color': C.dusk300,
      'fog-color': C.dusk500,
      'sky-horizon-blend': 0.6,
      'horizon-fog-blend': 0.5,
      'fog-ground-blend': 0.6,
      'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 4, 0.9, 12, 0.6, 16, 0.2],
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
          'fill-color': C.ink950,
          // The one lit edge on the basemap. §2.1's "light is linear, not
          // surface" applied to the coast: the harbour reads as an edge rather
          // than as a lighter shade of anything.
          'fill-outline-color': C.ink600,
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
    ],
  } as StyleSpecification;
}
