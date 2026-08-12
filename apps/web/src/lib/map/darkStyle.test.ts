/**
 * The style, checked for the four things that would go wrong silently.
 *
 * A map style is data, and a broken one rarely throws. A filter naming a `kind`
 * the archive stopped emitting draws an empty layer. A `glyphs` URL slipped in
 * by a copied snippet makes `make demo` reach the network. A colour brighter
 * than the cap steals the brightness M4c's beacons need, and nobody notices
 * until there are beacons to lose. And drawing the archive's own OSM buildings
 * would put a second, guessed skyline underneath the measured one.
 *
 * None of those show up as an error. All four show up here.
 */

import { describe, expect, it } from 'vitest';

import { BASEMAP_URL } from '@/lib/basemap';

import { BASEMAP_SOURCE, buildDarkStyle } from './darkStyle';
import { MAP_PALETTE } from './palette';

const style = buildDarkStyle();
const json = JSON.stringify(style);

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

  it('declares no glyphs and no sprite', () => {
    // Both are network calls, and `make demo` runs offline. This is also why
    // there are no labels: a symbol layer without glyphs does not render.
    expect(style.glyphs).toBeUndefined();
    expect(style.sprite).toBeUndefined();
  });

  it('has no symbol layer that would need them', () => {
    expect(style.layers.filter((l) => l.type === 'symbol').map((l) => l.id)).toEqual([]);
  });

  it('names no http URL anywhere', () => {
    expect(json).not.toMatch(/https?:\/\/(?!www\.openstreetmap\.org)/);
  });
});

describe('the basemap never draws a building', () => {
  it('touches no layer of the archive it does not style deliberately', () => {
    const used = new Set(
      style.layers
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
    const offenders = style.layers.filter(
      (l) => 'source-layer' in l && l['source-layer'] === 'buildings',
    );
    expect(offenders.map((l) => l.id)).toEqual([]);
  });

  it('extrudes nothing yet', () => {
    expect(style.layers.filter((l) => l.type === 'fill-extrusion').map((l) => l.id)).toEqual([]);
  });
});

describe('nothing on the basemap is as bright as a job will be', () => {
  const CAP = luminance(MAP_PALETTE.ink400);

  it('caps every drawn colour at ink-400', () => {
    // The brightness budget belongs to the data (§2.2). ink-400 is the dimmest
    // shade cleared for a non-text indicator and it is where the basemap stops.
    const drawn = style.layers.flatMap((l) => ('paint' in l ? colours(l.paint) : []));
    expect(drawn.length, 'the style must actually contain colours').toBeGreaterThan(5);

    const tooBright = drawn.filter((hex) => luminance(hex) > CAP + 1e-9);
    expect(tooBright, 'the basemap may not outshine ink-400').toEqual([]);
  });

  it('keeps the road ramp in order, so a motorway reads as one', () => {
    // Importance is carried by *weight*, not brightness — the cap leaves no
    // brighter shade to promote a motorway into. So the rule is: never darker,
    // and always wider.
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
  /**
   * CIE L*, not a WCAG contrast ratio.
   *
   * The ratio used everywhere else in this repository is the right tool for
   * text, and the wrong one here. Its `+0.05` flare term dominates at these
   * luminances: `ink-800` against `ink-950` scores 1.09:1, which sounds like
   * "invisible" and is in fact a perfectly visible step between two large
   * fills. Judging the map by that number would push the whole basemap several
   * shades brighter and spend the budget §2.2 reserves for jobs.
   *
   * L* is perceptually uniform. A ΔL* of 2-3 is roughly the smallest difference
   * a person can see between two large adjacent areas, so these thresholds are
   * stated as multiples of a just-noticeable difference rather than as taste.
   */
  function lightness(hex: string): number {
    const y = luminance(hex);
    return y <= 0.008856 ? 903.3 * y : 116 * Math.cbrt(y) - 16;
  }

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

  it('leaves the brightness budget the signal layer needs', () => {
    // The other half of the same constraint. A basemap that cleared every
    // threshold above by simply getting brighter would pass those tests and
    // ruin M4c. `signal-400` is the cyan a beacon is drawn in.
    const brightest = Math.max(
      ...style.layers.flatMap((l) => ('paint' in l ? colours(l.paint).map(lightness) : [])),
    );
    expect(lightness('#5ce8ff') - brightest).toBeGreaterThan(40);
  });
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
