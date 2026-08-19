/**
 * What the buildings are *not allowed* to do — and nothing about how they look.
 *
 * ADR 0031 makes the human holding
 * `docs/design/references/02-skyline-grid-plane-light-columns.jpg` the
 * acceptance test for this milestone's look, and is explicit about why there is
 * no assertion here about a window density, an edge width, a gradient stop or a
 * haze: "a test that pins taste is how the city stayed grey for two
 * milestones." Every one of those numbers is tuned by looking, and every one of
 * them will move again.
 *
 * Three things are pinned, because all three go wrong *silently*:
 *
 * 1. **ADR 0029's brightness stack.** The city is the surface data is read
 *    against. A window that gains four shades during a tuning pass quietly
 *    becomes brighter than a role, and nothing about the resulting screenshot
 *    looks wrong — it looks nicer. That is the failure this file exists for.
 * 2. **The city never goes buildingless.** MapLibre's own extrusions are
 *    retired the moment this renderer reports ready, so "ready" must mean the
 *    city is actually on the GPU. The first draft reported ready on an empty
 *    queue and produced a screenshot of New York with no buildings in it.
 * 3. **The camera comes out of the matrix that drew the frame.** The haze
 *    reads it per pixel; a position derived a second way is free to disagree
 *    with the projection, and the result is a correct-looking city fogged from
 *    somewhere the camera is not.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { Matrix4, PerspectiveCamera, Vector3 } from 'three';
import { describe, expect, it } from 'vitest';

import {
  BUILDING_COLOURS,
  cameraPositionFrom,
  createCityBuildings,
  DEFAULT_WINDOW_DENSITY,
} from './cityBuildings';
import type { TileFootprint } from './buildingGeometry';

const CSS = readFileSync(resolve(process.cwd(), 'src', 'app', 'globals.css'), 'utf8');

function cssToken(name: string): string {
  const hex = CSS.match(new RegExp(`--color-${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1];
  if (hex === undefined) throw new Error(`--color-${name} is not in globals.css`);
  return hex;
}

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** CIE L*, the same measure `palette.test.ts` and `skyLayer.test.ts` use. */
function lightness(hex: string): number {
  const h = hex.replace('#', '');
  const y =
    0.2126 * channel(parseInt(h.slice(0, 2), 16)) +
    0.7152 * channel(parseInt(h.slice(2, 4), 16)) +
    0.0722 * channel(parseInt(h.slice(4, 6), 16));
  return y <= 0.008856 ? 903.3 * y : 116 * Math.cbrt(y) - 16;
}

/** Hue in degrees, for the one rule that is about hue rather than brightness. */
function hue(hex: string): number {
  const h = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as [
    number,
    number,
    number,
  ];
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  if (max === min) return 0;
  const d = max - min;
  const raw = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (raw * 60 + 360) % 360;
}

const ANCHOR = [-73.9857, 40.7484] as const;

function square(bin: string, offset: number, feet = '200'): TileFootprint {
  const [lng, lat] = ANCHOR;
  const size = 0.0003;
  return {
    properties: { bin, height_roof: feet },
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [lng + offset, lat],
          [lng + offset + size, lat],
          [lng + offset + size, lat + size],
          [lng + offset, lat + size],
          [lng + offset, lat],
        ],
      ],
    },
  };
}

describe('the city stays under the things that mean something', () => {
  it('leaves a role somewhere brighter to be, colour by colour', () => {
    const role = lightness(cssToken('signal-400'));
    for (const [key, value] of Object.entries(BUILDING_COLOURS)) {
      const headroom = role - lightness(value);
      expect(
        headroom,
        `building ${key} (${value}) leaves only ${headroom.toFixed(1)} L*`,
      ).toBeGreaterThan(20);
    }
  });

  it('stays under a hiring building, which is the dimmest thing that carries a state', () => {
    // ADR 0029's stack, stated where it can fail: city < hiring building <
    // open role. A window is exactly the sort of thing that gets brighter
    // during a tuning pass, and a city whose scenery outshines its data has
    // spent the encoding on decoration.
    //
    // **With a stated margin, not a bare `<`.** ADR 0033's first draft put the
    // brightest window 0.8 L* under `alert-400`: it passed this assertion and
    // defeated what the assertion is for, because a difference the eye cannot
    // see is not a stack. Three is the smallest gap that survives a screenshot.
    const hiring = lightness(cssToken('alert-400'));
    for (const [key, value] of Object.entries(BUILDING_COLOURS)) {
      const margin = hiring - lightness(value);
      expect(
        margin,
        `building ${key} (${value}) leaves only ${margin.toFixed(1)} L* under a hiring building`,
      ).toBeGreaterThan(3);
    }
  });

  it('keeps its cyan further from the signal than a brightness rule alone would', () => {
    // ADR 0034's rule, and the one that made the facade pass shippable.
    //
    // Cyan is a role. Four milestones of encoding say so and `globals.css`
    // says so out loud. The general 20 L* headroom below treats every hue
    // alike, and it should not: a magenta window 20 L* under a beacon is
    // obviously not a beacon, and a *cyan* one 20 L* under it is a beacon
    // somebody turned down. Same-hue confusion is the worse failure, so it
    // earns the tighter bar.
    //
    // The palette this ADR shipped with was proposed at `#00dfff`, which is
    // 3.8 L* under `signal-400` in nearly the same hue — a window all but
    // indistinguishable from an open role. `aqua-400` is what it became.
    const signalHue = hue(cssToken('signal-400'));
    const role = lightness(cssToken('signal-400'));
    for (const [key, value] of Object.entries(BUILDING_COLOURS)) {
      const apart = Math.abs(((hue(value) - signalHue + 540) % 360) - 180);
      if (180 - apart > 20) continue;
      const headroom = role - lightness(value);
      expect(
        headroom,
        `building ${key} (${value}) is within 20 deg of the signal hue and only ${headroom.toFixed(1)} L* under it`,
      ).toBeGreaterThan(25);
    }
  });

  it('draws nothing in a family that carries meaning', () => {
    // `city.md` §3: cyan is a role, magenta is something you can act on, gold
    // is urgency, green is an offer, violet is the weather. The city's own
    // light has to be a colour that means nothing, or the encoding pays for
    // the scenery — which is the whole of ADR 0029's `neon-*` family.
    const reserved = ['signal-400', 'alert-400', 'gold-400', 'dusk-300', 'dusk-500', 'dusk-700'];
    const forbidden = new Set(reserved.map((name) => cssToken(name).toLowerCase()));
    for (const [key, value] of Object.entries(BUILDING_COLOURS)) {
      expect(forbidden.has(value.toLowerCase()), `building ${key} draws in a reserved colour`).toBe(
        false,
      );
    }
  });

  it('spends every colour out of the map palette rather than inventing one', () => {
    // The palette is what `palette.test.ts` holds against the stylesheet. A
    // hex typed straight into this file would be a colour with no assertion
    // over it and no row in the design tokens.
    const source = readFileSync(
      resolve(process.cwd(), 'src', 'lib', 'city', 'cityBuildings.ts'),
      'utf8',
    );
    const table = source.slice(
      source.indexOf('export const BUILDING_COLOURS'),
      source.indexOf('} as const;', source.indexOf('export const BUILDING_COLOURS')),
    );
    expect(table).not.toMatch(/#[0-9a-fA-F]{6}/);
  });
});

describe('the city is on the GPU before MapLibre stops drawing one', () => {
  it('does not report ready when there was simply nothing to build', () => {
    // The exact first-draft bug, and the one that produced a screenshot of an
    // empty New York: `querySourceFeatures` answers 0 on a map still fetching
    // its tiles, the queue drained instantly, ready fired, and the extrusions
    // were retired in exchange for nothing.
    const city = createCityBuildings({ anchor: ANCHOR });
    expect(city.step(10)).toBe(false);
    expect(city.ready).toBe(false);
    expect(city.group.visible).toBe(false);
    city.dispose();
  });

  it('reports ready once real footprints have reached a mesh, and shows them then', () => {
    const city = createCityBuildings({ anchor: ANCHOR });
    city.ingest([square('1', 0), square('2', 0.001), square('3', 0.002)]);
    expect(city.pending).toBe(3);

    // A budget large enough to drain in one call; the slicing itself is what
    // the frame-budget path exercises, and it is the same code.
    while (city.step(1000));

    expect(city.ready).toBe(true);
    expect(city.group.visible).toBe(true);
    expect(city.stats.buildings).toBe(3);
    expect(city.stats.meshes).toBeGreaterThan(0);
    expect(city.stats.vertices).toBeGreaterThan(0);
    expect(city.pending).toBe(0);
    city.dispose();
  });

  it('ignores a footprint it has already built, so a re-query costs nothing', () => {
    const city = createCityBuildings({ anchor: ANCHOR });
    city.ingest([square('1', 0), square('2', 0.001)]);
    while (city.step(1000));
    const vertices = city.stats.vertices;

    // What `idle` does after every gesture: hand over everything loaded,
    // most of which is already standing. Built twice, a building is two
    // coincident skins that z-fight into a shimmer.
    city.ingest([square('1', 0), square('2', 0.001)]);
    while (city.step(1000));
    expect(city.stats.buildings).toBe(2);
    expect(city.stats.vertices).toBe(vertices);
    city.dispose();
  });

  it('lets go of everything it holds when the layer goes', () => {
    const city = createCityBuildings({ anchor: ANCHOR });
    city.ingest([square('1', 0)]);
    while (city.step(1000));
    expect(city.group.children.length).toBeGreaterThan(0);

    city.dispose();
    // A hundred megabytes of New York across a few dozen buffers. Left
    // behind, it outlives the page's own teardown, and the context that
    // reaches the browser's limit fails to create the *next* map with an
    // error naming none of this.
    expect(city.group.children).toHaveLength(0);
    expect(city.stats.buildings).toBe(0);
    expect(city.stats.vertices).toBe(0);
  });

  it('starts at a window density inside the range the shader can use', () => {
    expect(DEFAULT_WINDOW_DENSITY).toBeGreaterThan(0);
    expect(DEFAULT_WINDOW_DENSITY).toBeLessThan(1);
  });
});

describe('the camera comes out of the matrix that drew the frame', () => {
  it('recovers a known eye position from a known projection', () => {
    const camera = new PerspectiveCamera(45, 1.6, 1, 10_000);
    camera.position.set(1_200, -3_400, 900);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld(true);

    // Exactly what the layer composes: what MapLibre hands over, times the
    // anchor transform. Any perspective matrix at all should give its own eye
    // back.
    const projection = new Matrix4().multiplyMatrices(
      camera.projectionMatrix,
      camera.matrixWorldInverse,
    );

    const eye = cameraPositionFrom(projection, new Vector3());
    expect(eye.x).toBeCloseTo(1_200, 1);
    expect(eye.y).toBeCloseTo(-3_400, 1);
    expect(eye.z).toBeCloseTo(900, 1);
  });

  it('keeps the last position rather than falling to the origin on a singular matrix', () => {
    // Three's `invert()` returns the zero matrix on a singular input rather
    // than complaining, which would park the camera on the anchor and fog the
    // whole city uniformly — a wrong picture that looks like a deliberate one.
    const previous = new Vector3(10, 20, 30);
    const singular = new Matrix4();
    singular.elements.fill(0);
    const result = cameraPositionFrom(singular, previous);
    expect(result.toArray()).toEqual([10, 20, 30]);
  });
});
