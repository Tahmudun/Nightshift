import { describe, expect, it, vi } from 'vitest';

import {
  lngLatFromMercator,
  lngLatFromScene,
  mercatorFromLngLat,
  metreInMercatorUnits,
  sceneFromLngLat,
} from './mercator';

/**
 * Values chosen to be checkable by hand rather than copied from a run of the
 * code they are testing — which is the failure mode of every "golden number"
 * test and would make this file agree with any bug it happened to encode.
 *
 * `city.spec.ts` does the other half in a real browser: it compares these
 * against MapLibre's own `MercatorCoordinate`, which is the only check that can
 * catch this file being self-consistently wrong.
 */

describe('mercatorFromLngLat', () => {
  it('puts the prime meridian and the equator at the middle of the world', () => {
    const origin = mercatorFromLngLat(0, 0);
    expect(origin.x).toBeCloseTo(0.5, 12);
    expect(origin.y).toBeCloseTo(0.5, 12);
  });

  it('spans the antimeridian from zero to one', () => {
    expect(mercatorFromLngLat(-180, 0).x).toBeCloseTo(0, 12);
    expect(mercatorFromLngLat(180, 0).x).toBeCloseTo(1, 12);
  });

  it('grows southward, which is the opposite of latitude', () => {
    // The sign that goes wrong silently: a field mirrored about its anchor
    // still looks like a plausible arrangement.
    expect(mercatorFromLngLat(0, 40).y).toBeLessThan(0.5);
    expect(mercatorFromLngLat(0, -40).y).toBeGreaterThan(0.5);
  });

  it('is linear in longitude', () => {
    const a = mercatorFromLngLat(-74, 40.75);
    const b = mercatorFromLngLat(-73, 40.75);
    expect(b.x - a.x).toBeCloseTo(1 / 360, 12);
  });
});

describe('metreInMercatorUnits', () => {
  it('makes one equatorial circumference of metres span the whole world', () => {
    // 2πR metres at the equator is exactly one mercator unit, by definition.
    expect(metreInMercatorUnits(0) * (2 * Math.PI * 6_371_008.8)).toBeCloseTo(1, 12);
  });

  it('grows with latitude, because mercator stretches away from the equator', () => {
    const equator = metreInMercatorUnits(0);
    const newYork = metreInMercatorUnits(40.75);
    expect(newYork).toBeGreaterThan(equator);
    // 1/cos(40.75°) ≈ 1.32. Using the equatorial value at New York would shrink
    // the whole field by a quarter, which reads as a design choice rather than
    // as a bug.
    expect(newYork / equator).toBeCloseTo(1 / Math.cos((40.75 * Math.PI) / 180), 12);
  });
});

describe('against MapLibre’s own MercatorCoordinate', () => {
  /**
   * The check that catches this file being self-consistently wrong.
   *
   * Every assertion above pins a property — the origin, the span, the sign,
   * linearity — and a projection can satisfy all four and still disagree with
   * the one MapLibre actually draws with. Only comparing the two implementations
   * catches that, and this is the only place both can exist at once.
   *
   * `maplibre-gl` calls `URL.createObjectURL` at module scope to build its
   * worker, which jsdom does not implement, so the import happens **after** the
   * stub and dynamically. That is the whole reason `mercator.ts` exists as its
   * own module rather than importing MapLibre directly: this cost is paid once,
   * here, instead of by every test that touches the scene.
   */
  it('agrees to better than a millionth of a mercator unit', async () => {
    vi.stubGlobal('URL', {
      ...globalThis.URL,
      createObjectURL: () => 'blob:stub',
      revokeObjectURL: () => {},
    });
    const { MercatorCoordinate } = await import('maplibre-gl');

    for (const [lng, lat] of [
      [-74.0, 40.7],
      [-73.9, 40.8],
      [0, 0],
      [151.2, -33.9],
      [-122.4, 37.8],
    ] as const) {
      const theirs = MercatorCoordinate.fromLngLat([lng, lat], 0);
      const ours = mercatorFromLngLat(lng, lat);

      // A mercator unit is the whole world. 1e-12 of one is far under a
      // millimetre.
      expect(ours.x).toBeCloseTo(theirs.x, 12);
      expect(ours.y).toBeCloseTo(theirs.y, 12);
      expect(metreInMercatorUnits(lat)).toBeCloseTo(theirs.meterInMercatorCoordinateUnits(), 15);
    }

    vi.unstubAllGlobals();
  });
});

describe('lngLatFromMercator', () => {
  it('is the inverse of the projection, not a second implementation of it', () => {
    // Round-tripping rather than a table of constants: a table can only ever
    // agree with whatever the code did on the day it was written, and these two
    // functions being mutually consistent is the entire property that matters.
    for (const [lng, lat] of [
      [0, 0],
      [-73.98, 40.75],
      [-180, -60],
      [179.9, 72.3],
      [12.5, -33.9],
    ] as const) {
      const [backLng, backLat] = lngLatFromMercator(mercatorFromLngLat(lng, lat));
      expect(backLng).toBeCloseTo(lng, 9);
      expect(backLat).toBeCloseTo(lat, 9);
    }
  });

  it('puts the middle of the world back on the equator', () => {
    const [lng, lat] = lngLatFromMercator({ x: 0.5, y: 0.5 });
    expect(lng).toBeCloseTo(0, 12);
    expect(lat).toBeCloseTo(0, 12);
  });
});

describe('lngLatFromScene', () => {
  const ANCHOR = [-73.98, 40.75] as const;

  it('leaves the anchor exactly where it is', () => {
    const [lng, lat] = lngLatFromScene(ANCHOR, 0, 0);
    expect(lng).toBeCloseTo(ANCHOR[0], 9);
    expect(lat).toBeCloseTo(ANCHOR[1], 9);
  });

  it('sends +y north and +x east', () => {
    // The flip that mirrors an entire field about its anchor while still
    // looking like a plausible arrangement of columns. Mercator y grows
    // *southward*; the scene's y is metres north.
    const [, north] = lngLatFromScene(ANCHOR, 0, 1_000);
    const [east] = lngLatFromScene(ANCHOR, 1_000, 0);

    expect(north).toBeGreaterThan(ANCHOR[1]);
    expect(east).toBeGreaterThan(ANCHOR[0]);
  });

  it('moves about the distance it was asked to, in metres', () => {
    // One degree of latitude is close to 111 km, so 1110 m north is roughly
    // 0.01°. Checked to two significant figures, which is enough to catch the
    // scale being wrong by the cos(latitude) factor — the mistake that shrinks
    // a whole field by a quarter and looks like a design choice.
    const [, lat] = lngLatFromScene(ANCHOR, 0, 1_110);
    expect(lat - ANCHOR[1]).toBeCloseTo(0.01, 3);
  });

  it('puts a real coordinate back where it came from', () => {
    // `sceneFromLngLat` is the direction a *placed* role travels: an office was
    // geocoded to a point on Earth and the scene has to draw it there. The
    // unresolved field never uses it, because nothing in that field has a
    // position to convert (I1).
    //
    // Asserted as a round trip against the inverse that already exists, rather
    // than against two metre literals. A projection that is wrong by a constant
    // factor still produces a building in Midtown, and no screenshot catches it.
    const [lng, lat] = [-73.989658, 40.755913];

    const { x, y } = sceneFromLngLat(ANCHOR, lng, lat);
    const [backLng, backLat] = lngLatFromScene(ANCHOR, x, y);

    expect(backLng).toBeCloseTo(lng, 9);
    expect(backLat).toBeCloseTo(lat, 9);
  });

  it('puts the anchor itself at the scene origin', () => {
    // The one value that can be checked without any arithmetic at all, and the
    // one an off-by-an-origin error cannot survive.
    expect(sceneFromLngLat(ANCHOR, ANCHOR[0], ANCHOR[1])).toEqual({ x: 0, y: 0 });
  });

  it('round-trips through the transform the renderer uses', () => {
    // The scene positions the field with `anchorTransform`; this reverses it.
    // If the two ever disagree, the roster flies the camera to empty sky beside
    // the column it named.
    const origin = mercatorFromLngLat(ANCHOR[0], ANCHOR[1]);
    const scale = metreInMercatorUnits(ANCHOR[1]);
    const [x, y] = [620, -1_240];

    const [lng, lat] = lngLatFromScene(ANCHOR, x, y);
    const forward = mercatorFromLngLat(lng, lat);

    expect(forward.x).toBeCloseTo(origin.x + x * scale, 12);
    expect(forward.y).toBeCloseTo(origin.y - y * scale, 12);
  });
});
