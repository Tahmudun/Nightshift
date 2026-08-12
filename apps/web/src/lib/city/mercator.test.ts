import { describe, expect, it, vi } from 'vitest';

import { mercatorFromLngLat, metreInMercatorUnits } from './mercator';

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
