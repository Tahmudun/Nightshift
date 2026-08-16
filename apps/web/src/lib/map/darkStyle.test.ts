/**
 * The style, checked for the four things that would go wrong silently.
 *
 * A map style is data, and a broken one rarely throws. A filter naming a `kind`
 * the archive stopped emitting draws an empty layer. A `glyphs` URL slipped in
 * by a copied snippet makes `make demo` reach the network. A colour that climbs
 * past the headroom rule steals the brightness M4c's beacons need, and nobody
 * notices until there are beacons to lose — and a style that quietly goes dark
 * again satisfies that rule perfectly, which is how the city spent four
 * milestones grey under a green suite. And drawing the archive's own OSM
 * buildings would put a second, guessed skyline underneath the measured one.
 *
 * None of those show up as an error. All four show up here.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { BASEMAP_URL, buildingsManifest, BUILDINGS_URL } from '@/lib/tiles';

import { BASEMAP_SOURCE, BUILDINGS_SOURCE, buildDarkStyle } from './darkStyle';
import { MAP_PALETTE } from './palette';

const style = buildDarkStyle();
const json = JSON.stringify(style);

const CSS = readFileSync(resolve(process.cwd(), 'src', 'app', 'globals.css'), 'utf8');

/**
 * A token the map palette deliberately does not carry, read from the
 * stylesheet. `signal-400` is the ceiling every assertion below is stated
 * against, and writing its hex here would mean the ceiling could drift away
 * from the colour a beacon is actually drawn in without a test noticing.
 */
function cssToken(name: string): string {
  const hex = CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1];
  if (hex === undefined) throw new Error(`--color-${name} is not in globals.css`);
  return hex;
}

/** ADR 0029. The margin every colour in the style keeps below `signal-400`. */
const MIN_HEADROOM_L = 20;

/** Every layer in the archive, measured from its own metadata. */
const ARCHIVE_LAYERS = [
  'boundaries',
  'buildings',
  'earth',
  'landcover',
  'landuse',
  'places',
  'pois',
  'roads',
  'water',
];

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const h = hex.replace('#', '');
  return (
    0.2126 * channel(parseInt(h.slice(0, 2), 16)) +
    0.7152 * channel(parseInt(h.slice(2, 4), 16)) +
    0.0722 * channel(parseInt(h.slice(4, 6), 16))
  );
}

/**
 * CIE L*, not a WCAG contrast ratio.
 *
 * The ratio used everywhere else in this repository is the right tool for text
 * and the wrong one here. Its `+0.05` flare term dominates at these luminances:
 * `ink-800` against `ink-950` scores 1.09:1, which sounds like "invisible" and
 * is in fact a perfectly visible step between two large fills. Judging the map
 * by that number would push the whole basemap several shades brighter.
 *
 * L* is perceptually uniform. A ΔL* of 2-3 is roughly the smallest difference a
 * person can see between two large adjacent areas, so every threshold below is
 * a multiple of a just-noticeable difference rather than a matter of taste.
 */
function lightness(hex: string): number {
  const y = luminance(hex);
  return y <= 0.008856 ? 903.3 * y : 116 * Math.cbrt(y) - 16;
}

function layer(id: string) {
  const found = style.layers.find((candidate) => candidate.id === id);
  expect(found, `no layer '${id}' in the style`).toBeDefined();
  return found!;
}

/** A layer's filter, which the union type only exposes on the non-background arms. */
function filterOf(id: string): unknown {
  const found = layer(id);
  return 'filter' in found ? found.filter : undefined;
}

/** Everything in a layer's paint, flattened, so a colour cannot hide in an expression. */
function colours(value: unknown): string[] {
  if (typeof value === 'string') return /^#[0-9a-f]{6}$/i.test(value) ? [value.toLowerCase()] : [];
  if (Array.isArray(value)) return value.flatMap(colours);
  if (value && typeof value === 'object') return Object.values(value).flatMap(colours);
  return [];
}

describe('the style asks nothing of the network', () => {
  it('reads its tiles through the pmtiles protocol, from the local route', () => {
    const source = style.sources[BASEMAP_SOURCE];
    expect(source).toBeDefined();
    expect(source).toMatchObject({ type: 'vector', url: `pmtiles://${BASEMAP_URL}` });
  });

  it('reads the buildings archive the same way, from the same origin', () => {
    const source = style.sources[BUILDINGS_SOURCE];
    expect(source).toBeDefined();
    expect(source).toMatchObject({ type: 'vector', url: `pmtiles://${BUILDINGS_URL}` });
  });

  it('declares no glyphs and no sprite', () => {
    // Both are network calls, and `make demo` runs offline. This is also why
    // there are no labels: a symbol layer without glyphs does not render.
    expect(style.glyphs).toBeUndefined();
    expect(style.sprite).toBeUndefined();
  });

  it('has no symbol layer that would need them', () => {
    expect(style.layers.filter((l) => l.type === 'symbol').map((l) => l.id)).toEqual([]);
  });

  it('names no http URL outside an attribution', () => {
    // Attributions are the one legitimate place: they are licence text rendered
    // into the corner of the map as a link a person may click, and MapLibre
    // never fetches them. Everything else — tiles, glyphs, sprites — must be
    // local, so they are stripped out and the rest is checked.
    const withoutAttribution = json.replace(/"attribution":"(\\.|[^"\\])*"/g, '""');
    expect(withoutAttribution).not.toMatch(/https?:\/\//);
    // …and the stripping must actually be finding something, or this test has
    // quietly stopped checking anything.
    expect(json).toMatch(/"attribution":"(?:\\.|[^"\\])*https/);
  });
});

describe('the basemap never draws a building', () => {
  it('touches no layer of the archive it does not style deliberately', () => {
    const used = new Set(
      style.layers
        .filter((l) => 'source' in l && l.source === BASEMAP_SOURCE)
        .map((l) => ('source-layer' in l ? l['source-layer'] : undefined))
        .filter((name): name is string => name !== undefined),
    );
    for (const name of used) {
      expect(ARCHIVE_LAYERS, `'${name}' is not a layer this archive has`).toContain(name);
    }
  });

  it('does not read the archive buildings layer at all', () => {
    // §5.3 takes heights from NYC Open Data's `height_roof` so the skyline is
    // measured. The archive's `buildings` layer is OSM's guesses, and drawing it
    // would either double-draw against the real extrusion or quietly become it.
    //
    // Both archives call the layer `buildings`, which is the whole reason this
    // test names the *source*: the version that only checked `source-layer`
    // would have started failing the moment the measured skyline arrived, and
    // the tempting fix is to delete it.
    const offenders = style.layers.filter(
      (l) =>
        'source' in l &&
        l.source === BASEMAP_SOURCE &&
        'source-layer' in l &&
        l['source-layer'] === 'buildings',
    );
    expect(offenders.map((l) => l.id)).toEqual([]);
  });

  it('extrudes exactly these layers, all from the measured archive', () => {
    // An explicit list rather than a count. `buildings-crown` joined `buildings`
    // in M4e and a third arrives with the hiring building — the thing worth
    // pinning is that every extrusion reads the *measured* archive, because one
    // reading the basemap's OSM heights would draw a guessed skyline while
    // looking exactly like these.
    const extrusions = style.layers.filter((l) => l.type === 'fill-extrusion');
    expect(extrusions.map((l) => l.id)).toEqual(['buildings', 'buildings-crown']);
    for (const extrusion of extrusions) {
      expect(extrusion, extrusion.id).toMatchObject({ source: BUILDINGS_SOURCE });
    }
  });

  it('stacks the crown on the mass instead of overlapping it', () => {
    // Two coplanar extrusion walls at identical depth resolve differently per
    // driver, and the symptom is a band that flickers or mottles as the camera
    // moves — which reads as a GPU problem and is a geometry problem. The mass
    // stops where the crown starts, so they share a plane and no volume.
    const mass = JSON.stringify(
      (layer('buildings') as unknown as { paint: Record<string, unknown> }).paint[
        'fill-extrusion-height'
      ],
    );
    const crownBase = JSON.stringify(
      (layer('buildings-crown') as unknown as { paint: Record<string, unknown> }).paint[
        'fill-extrusion-base'
      ],
    );
    expect(mass).toBe(crownBase);
  });

  it('lights only the towers, so the low-rise stays a dark mat', () => {
    // A crown on everything is a bright fog at head height: most of New York is
    // under 60 feet, so the band would land in a continuous sheet across the
    // low-rise and read as haze rather than as a skyline.
    expect(JSON.stringify(filterOf('buildings-crown'))).toContain('height_roof');
  });
});

describe('the skyline is the measured one, in the units it was measured in', () => {
  const buildings = layer('buildings') as unknown as { paint: Record<string, unknown> };
  const height = JSON.stringify(buildings.paint['fill-extrusion-height']);

  it('reads height_roof and nothing else', () => {
    // `height` and `render_height` are the OSM archive's field names. Reading
    // one of them here would draw a skyline out of the guessed heights while
    // looking exactly like this layer.
    expect(height).toContain('height_roof');
    expect(height).not.toContain('render_height');
  });

  it('converts feet to metres exactly once', () => {
    // The bake keeps the source's own units so that nothing in the pipeline can
    // apply the factor twice. A city 3.3 times too tall renders perfectly, which
    // is what makes this worth a test rather than a comment.
    const factors = height.match(/0\.3048/g) ?? [];
    expect(factors.length, 'one conversion, at the point of use').toBe(1);
  });

  it('gives a footprint with no measured height a stated default, not a guess', () => {
    // §5.3. The default is deliberately unremarkable — a two-storey building —
    // because the alternative is a plausible skyline built from data nobody
    // measured. 732 of 1,083,024 structures take it; the count is in the
    // manifest so the number is auditable rather than an impression.
    expect(buildingsManifest.structures_without_height).toBeGreaterThan(0);
    expect(height).toContain('25');

    const stated = buildingsManifest.structures_without_height / buildingsManifest.structures;
    expect(stated, 'if this rises the skyline is more default than measured').toBeLessThan(0.01);
  });

  it('drops the source as well as the layer when the archive is absent', () => {
    // A layer removed but a source kept is the worst of both: MapLibre still
    // tries to load the archive, still raises `error`, and CityMap still
    // replaces a perfectly good city with a card about a missing file.
    const flat = buildDarkStyle({ buildings: false });
    expect(flat.layers.filter((l) => l.type === 'fill-extrusion')).toEqual([]);
    expect(flat.sources[BUILDINGS_SOURCE]).toBeUndefined();
    expect(JSON.stringify(flat)).not.toContain(BUILDINGS_URL);

    // …and the ground is still there. A missing skyline must not take the city
    // with it.
    expect(flat.layers.map((l) => l.id)).toContain('earth');
  });

  it('does not extrude below the zoom the archive carries', () => {
    // The buildings archive is z13-z16. A layer drawn below its source's minzoom
    // is not an error and not empty either — MapLibre serves the z13 tile for
    // the whole viewport, which at z10 is a million footprints in one frame.
    expect(layer('buildings').minzoom).toBeGreaterThanOrEqual(buildingsManifest.minzoom);
  });
});

describe('nothing on the map is as bright as a job will be', () => {
  /**
   * This block used to hold the two assertions that made the city grey, and
   * replacing them is ADR 0029 rather than a loosened test.
   *
   * The first capped every colour outside the buildings source at `ink-400`.
   * The second required the brightest colour anywhere in the style to sit 40 L*
   * below `signal-400`. Both were written to protect one real thing — a beacon
   * must be the brightest object in frame — and both did it by proxy, through a
   * token that happened to be dim. The proxy then became the design: `ink-450`
   * at 44.3 L* was the brightest pixel on the map, and it is a desaturated grey.
   *
   * What replaces them is the rule itself, stated twice from opposite ends:
   * every colour keeps a **stated margin below `signal-400`**, and the style may
   * only paint with colours from `MAP_PALETTE`, whose every entry is held to
   * that margin at the source (`palette.test.ts`). A neon street cannot get in
   * by being written inline, and cannot get in through the palette either.
   */
  const beacon = lightness(cssToken('signal-400'));

  it('paints with the palette and nothing else', () => {
    // The structural half. `palette.test.ts` holds every MAP_PALETTE entry a
    // stated distance below `signal-400`; this holds the style to MAP_PALETTE.
    // Between them, no colour can reach a layer without having cleared the
    // ceiling — including one typed straight into a paint property, which is
    // how a "just this once" cyan arrives.
    const allowed = new Set(Object.values(MAP_PALETTE).map((hex) => hex.toLowerCase()));
    const drawn = style.layers.flatMap((l) => ('paint' in l ? colours(l.paint) : []));
    expect(drawn.length, 'the style must actually contain colours').toBeGreaterThan(5);

    const strangers = [...new Set(drawn)].filter((hex) => !allowed.has(hex));
    expect(strangers, 'every colour on a layer must be a MAP_PALETTE token').toEqual([]);
  });

  it('keeps a stated margin below the colour a beacon is drawn in', () => {
    // The numeric half, and the one that actually protects M4c. 20 L* is not a
    // round guess: `alert-400` — the hiring building, the brightest thing the
    // city itself is allowed to draw — sits 22.0 below `signal-400`, so 20
    // admits it and admits nothing above it.
    const brightest = Math.max(
      ...style.layers.flatMap((l) => ('paint' in l ? colours(l.paint).map(lightness) : [])),
    );
    expect(beacon - brightest).toBeGreaterThan(MIN_HEADROOM_L);
  });

  it('is a city with the lights on, not a headroom rule satisfied by darkness', () => {
    // The direction that would otherwise never fail.
    //
    // Every assertion above is satisfied perfectly by a map drawn entirely in
    // `ink-950`, which is the city M4e exists to replace — and for four
    // milestones a suite of exactly those assertions was green over exactly
    // that city. A test that cannot fail is not a test (CLAUDE.md §7), and a
    // one-sided bound on brightness cannot fail in the direction the product
    // went wrong.
    //
    // 50 L*, and the number was chosen by finding out what a weaker one lets
    // through. The first draft of this test said 40, which passed on `ink-400`
    // at 40.2 — the *old* motorway grey, the exact colour ADR 0029 exists to
    // replace. It would have gone green over the unlit city it was written to
    // catch. 50 is above every shade in the ink family and is reached only by
    // `neon-400`, so it fails the moment the neon comes back out.
    const brightest = Math.max(
      ...style.layers.flatMap((l) => ('paint' in l ? colours(l.paint).map(lightness) : [])),
    );
    expect(brightest, 'nothing on this map is lit; see ADR 0029').toBeGreaterThan(50);
  });

  it('keeps the road ramp in order, so a motorway reads as one', () => {
    // Importance is carried by weight *and* brightness, and the rule is that
    // the two never disagree: never darker, and always wider. Under the old
    // `ink-400` cap there was no brighter shade to promote a motorway into and
    // width was carrying the whole read; the `neon-*` family gives the ramp its
    // other half back. Either alone is legible. The two inverted is soup.
    const RAMP = ['road-path', 'road-minor', 'road-major', 'road-highway'];
    const rungs = RAMP.map((id) => {
      const paint = (layer(id) as unknown as { paint: Record<string, unknown> }).paint;
      const stops = paint['line-width'] as [string, unknown, unknown, ...number[]];
      // ['interpolate', ['linear'], ['zoom'], z, w, z, w, …] — read the widest.
      const widths = stops.slice(3).filter((_, index) => index % 2 === 1) as number[];
      return { lum: luminance(String(paint['line-color'])), widest: Math.max(...widths) };
    });

    for (let i = 1; i < rungs.length; i += 1) {
      expect(
        rungs[i]!.lum,
        `${RAMP[i]} must not be dimmer than ${RAMP[i - 1]}`,
      ).toBeGreaterThanOrEqual(rungs[i - 1]!.lum);
      expect(rungs[i]!.widest, `${RAMP[i]} must be wider than ${RAMP[i - 1]}`).toBeGreaterThan(
        rungs[i - 1]!.widest,
      );
    }
  });
});

describe('the ground is visible against the void', () => {
  /**
   * The first draft of this style failed here and nothing caught it.
   *
   * Land sat one shade above the background and the whole map read as an
   * unbroken black rectangle — every layer drawing, 1,263 features on screen,
   * and nothing a person could see. "Most of the city should remain dark" (§2.2)
   * is about the *brightness budget*, not about being unreadable, and the
   * difference between the two is a number rather than a matter of taste.
   */
  function delta(a: string, b: string): number {
    return Math.abs(lightness(a) - lightness(b));
  }

  function fillOf(id: string): string {
    const paint = (layer(id) as unknown as { paint: Record<string, unknown> }).paint;
    return String(paint['fill-color']);
  }

  it('separates land from water, which is the main read of a harbour city', () => {
    // Manhattan has to look like an island. This was 1.4 in the first draft —
    // land one shade above the background — and the map rendered as an unbroken
    // black rectangle with 1,263 features on it and nothing anyone could see.
    expect(delta(fillOf('earth'), fillOf('water'))).toBeGreaterThan(3.5);
  });

  it('separates parks from the land around them', () => {
    expect(delta(fillOf('green'), fillOf('earth'))).toBeGreaterThan(3);
  });

  it('separates the busiest roads from the land they cross', () => {
    const highway = String(
      (layer('road-highway') as unknown as { paint: Record<string, unknown> }).paint['line-color'],
    );
    expect(delta(highway, fillOf('earth'))).toBeGreaterThan(20);
  });

  // The brightness ceiling that used to live here — "brightest colour anywhere
  // sits 40 L* below signal-400" — moved to `nothing on the map is as bright as
  // a job will be` above, at the margin ADR 0029 states, alongside the floor
  // that keeps it from being satisfied by darkness.
});

describe('dusk stays in the air', () => {
  const DUSK = [
    MAP_PALETTE.dusk900,
    MAP_PALETTE.dusk700,
    MAP_PALETTE.dusk500,
    MAP_PALETTE.dusk300,
  ].map((hex) => hex.toLowerCase());

  it('uses a dusk shade in the sky block', () => {
    expect(colours(style.sky).filter((hex) => DUSK.includes(hex)).length).toBeGreaterThan(0);
  });

  it('uses no dusk shade on any layer', () => {
    // `city.md` §3: atmosphere only, never a mark, never a surface you can
    // click. A violet that can appear on an object makes `alert-*` unreadable.
    const offenders = style.layers.filter(
      (l) => 'paint' in l && colours(l.paint).some((hex) => DUSK.includes(hex)),
    );
    expect(offenders.map((l) => l.id)).toEqual([]);
  });
});

describe('the filters match the kinds this archive actually emits', () => {
  // Measured by decoding tiles at z8, z10, z12, z14 and z15 across Midtown,
  // Lower Manhattan, Brooklyn, Staten Island and JFK. Pinned here because a
  // filter naming a kind the schema dropped draws an empty layer in silence —
  // the harbour would simply stop existing.
  it.each([
    ['water', 'ocean'],
    ['water', 'river'],
    ['water', 'bay'],
    ['green', 'park'],
    ['green', 'cemetery'],
    ['road-highway', 'highway'],
    ['road-major', 'major_road'],
    ['road-minor', 'minor_road'],
    ['road-path', 'path'],
    ['road-rail', 'rail'],
    ['boundary-county', 'county'],
  ])('%s draws %s', (id, kind) => {
    expect(JSON.stringify(filterOf(id))).toContain(`"${kind}"`);
  });

  it('does not tint the whole city by styling built landuse', () => {
    // `landuse` also carries school, hospital, industrial, commercial and
    // residential, which between them cover most of New York. Drawing those
    // makes the city read as uniformly half-lit and leaves a beacon nothing to
    // stand against.
    const green = JSON.stringify(filterOf('green'));
    for (const kind of ['residential', 'commercial', 'industrial', 'school', 'hospital']) {
      expect(green, `'${kind}' would light most of the city`).not.toContain(`"${kind}"`);
    }
  });
});

describe('the layer order is the one that renders', () => {
  it('draws land, then water, then roads, then boundaries', () => {
    const order = style.layers.map((l) => l.id);
    const at = (id: string) => order.indexOf(id);
    expect(at('background')).toBe(0);
    expect(at('earth')).toBeLessThan(at('water'));
    expect(at('green')).toBeLessThan(at('road-highway'));
    expect(at('water')).toBeLessThan(at('road-highway'));
    expect(at('road-highway')).toBeLessThan(at('boundary-county'));
  });

  it('gives every layer a unique id, so none silently replaces another', () => {
    const ids = style.layers.map((l) => l.id);
    expect(ids.length).toBe(new Set(ids).size);
  });

  it('is a fresh object each call, so MapLibre cannot mutate a shared one', () => {
    expect(buildDarkStyle()).not.toBe(buildDarkStyle());
    expect(buildDarkStyle()).toEqual(buildDarkStyle());
  });

  it('carries the OpenStreetMap attribution, which is a licence condition', () => {
    expect(JSON.stringify(style.sources[BASEMAP_SOURCE])).toContain('OpenStreetMap');
  });
});
