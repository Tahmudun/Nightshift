/**
 * What the geometry must be, and nothing about how it looks.
 *
 * ADR 0031 puts the *look* of the buildings under the human's eye holding
 * reference 02, and says why in the sharpest terms this repository has: "a test
 * that pins taste is how the city stayed grey for two milestones." So there is
 * nothing here about a colour, a window density, an edge width or a haze.
 *
 * What is pinned is the part that would be wrong *silently*. A projection off
 * by a constant still lands in Midtown and still looks like a city. A ring
 * wound the wrong way still draws — from the inside, or not at all, depending
 * on which face the driver culls. A roof height applied twice renders a
 * perfectly plausible New York three times too tall. Every one of those is a
 * picture that looks deliberate, which is exactly the class of failure a test
 * has to catch because looking cannot.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import {
  buildBuildingArrays,
  DEFAULT_ROOF_FEET,
  readFootprints,
  ringTurn,
  roofMetresOf,
  wallSeed,
  type TileFootprint,
} from './buildingGeometry';
import { sceneFromLngLat } from './mercator';

/** The scene anchor the city actually opens at. */
const ANCHOR = [-73.9857, 40.7484] as const;

/** Due west-north-west, which is where `skyLayer.ts` puts the sun. */
const SUN = [-0.966, 0.259] as const;

/** A square building, counter-clockwise, roughly 30 m on a side near the anchor. */
function square(bin: string, feet: string | number | null, size = 0.0003): TileFootprint {
  const [lng, lat] = ANCHOR;
  return {
    properties: { bin, height_roof: feet },
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [lng, lat],
          [lng + size, lat],
          [lng + size, lat + size],
          [lng, lat + size],
          [lng, lat],
        ],
      ],
    },
  };
}

describe('a tile feature becomes a footprint', () => {
  it('projects every point exactly where the rest of the scene would put it', () => {
    // Against `sceneFromLngLat` rather than against a table of metre offsets:
    // the reason this file inlines the projection is speed, and the risk of
    // inlining it is that the copy drifts. A table would let both drift
    // together the day the anchor moves.
    const [footprint] = readFootprints([square('1', '100')], ANCHOR, new Set());
    expect(footprint).toBeDefined();
    const ring = footprint!.polygons[0]![0]!;

    const expected = sceneFromLngLat(ANCHOR, ANCHOR[0], ANCHOR[1]);
    expect(ring[0]).toBeCloseTo(expected.x, 6);
    expect(ring[1]).toBeCloseTo(expected.y, 6);

    const corner = sceneFromLngLat(ANCHOR, ANCHOR[0] + 0.0003, ANCHOR[1] + 0.0003);
    // The ring may have been reversed to make it counter-clockwise, so the
    // far corner is looked up rather than assumed to be at a fixed index.
    const points: Array<[number, number]> = [];
    for (let i = 0; i < ring.length; i += 2) points.push([ring[i]!, ring[i + 1]!]);
    const match = points.find(
      ([x, y]) => Math.abs(x - corner.x) < 1e-6 && Math.abs(y - corner.y) < 1e-6,
    );
    expect(match, 'the far corner is not where the shared projection puts it').toBeDefined();
  });

  it('drops the closing point rather than extruding a wall of zero length', () => {
    const [footprint] = readFootprints([square('1', '100')], ANCHOR, new Set());
    // Five points in, four out: GeoJSON repeats the first point to close a
    // ring, and a repeated point is an edge whose two ends are the same place.
    expect(footprint!.polygons[0]![0]!.length / 2).toBe(4);
  });

  it('winds the outer ring counter-clockwise however the tile wound it', () => {
    const clockwise: TileFootprint = {
      properties: { bin: '2', height_roof: '100' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [ANCHOR[0], ANCHOR[1]],
            [ANCHOR[0], ANCHOR[1] + 0.0003],
            [ANCHOR[0] + 0.0003, ANCHOR[1] + 0.0003],
            [ANCHOR[0] + 0.0003, ANCHOR[1]],
          ],
        ],
      },
    };
    const [footprint] = readFootprints([clockwise], ANCHOR, new Set());
    // Two things ride on this and both fail silently: which way a wall's
    // outward normal points, and whether a roof is visible under backface
    // culling at all.
    expect(ringTurn(footprint!.polygons[0]![0]!)).toBeGreaterThan(0);
  });

  it('winds a hole the other way, so a courtyard is a hole and not a second roof', () => {
    const withHole: TileFootprint = {
      properties: { bin: '3', height_roof: '100' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [ANCHOR[0], ANCHOR[1]],
            [ANCHOR[0] + 0.001, ANCHOR[1]],
            [ANCHOR[0] + 0.001, ANCHOR[1] + 0.001],
            [ANCHOR[0], ANCHOR[1] + 0.001],
          ],
          // Deliberately given counter-clockwise, the same way as the outer.
          [
            [ANCHOR[0] + 0.0003, ANCHOR[1] + 0.0003],
            [ANCHOR[0] + 0.0007, ANCHOR[1] + 0.0003],
            [ANCHOR[0] + 0.0007, ANCHOR[1] + 0.0007],
            [ANCHOR[0] + 0.0003, ANCHOR[1] + 0.0007],
          ],
        ],
      },
    };
    const [footprint] = readFootprints([withHole], ANCHOR, new Set());
    const [outer, hole] = footprint!.polygons[0]!;
    expect(ringTurn(outer!)).toBeGreaterThan(0);
    expect(ringTurn(hole!)).toBeLessThan(0);
  });

  it('keeps a multi-polygon building as separate polygons, not as one with holes', () => {
    const multi: TileFootprint = {
      properties: { bin: '4', height_roof: '100' },
      geometry: {
        type: 'MultiPolygon',
        coordinates: [
          [
            [
              [ANCHOR[0], ANCHOR[1]],
              [ANCHOR[0] + 0.0003, ANCHOR[1]],
              [ANCHOR[0] + 0.0003, ANCHOR[1] + 0.0003],
            ],
          ],
          [
            [
              [ANCHOR[0] + 0.001, ANCHOR[1]],
              [ANCHOR[0] + 0.0013, ANCHOR[1]],
              [ANCHOR[0] + 0.0013, ANCHOR[1] + 0.0003],
            ],
          ],
        ],
      },
    };
    const [footprint] = readFootprints([multi], ANCHOR, new Set());
    // Flattened, the second wing would be triangulated as a hole in the first
    // — a roof with a building-shaped void in it. 47 structures in one view of
    // New York are multi-polygons, so this is not a hypothetical shape.
    expect(footprint!.polygons).toHaveLength(2);
    expect(footprint!.polygons[0]).toHaveLength(1);
    expect(footprint!.polygons[1]).toHaveLength(1);
  });

  it('admits a footprint once, however many tiles carry it', () => {
    const seen = new Set<string>();
    expect(readFootprints([square('5', '100')], ANCHOR, seen)).toHaveLength(1);
    // The same BIN arriving from the neighbouring tile, or from the same tile
    // after a camera move. Built twice, it is drawn twice — and two coincident
    // skins z-fight into a shimmering building.
    expect(readFootprints([square('5', '100')], ANCHOR, seen)).toHaveLength(0);
  });

  it('ignores a feature with no BIN rather than drawing a building it cannot name', () => {
    const anonymous: TileFootprint = { properties: { height_roof: '100' }, geometry: {} };
    expect(readFootprints([anonymous], ANCHOR, new Set())).toHaveLength(0);
  });
});

describe('the roof height is the one the rest of the city uses', () => {
  it('reads the measured height, quoted as the tiles quote it', () => {
    expect(roofMetresOf({ height_roof: '339.64' })).toEqual({
      metres: 339.64 * 0.3048,
      measured: true,
    });
  });

  it.each([[''], [null], [undefined], ['0'], ['not a number']])(
    'falls back to the documented default for %p, and says it did',
    (value) => {
      const result = roofMetresOf({ height_roof: value });
      expect(result.measured).toBe(false);
      expect(result.metres).toBeCloseTo(DEFAULT_ROOF_FEET * 0.3048, 10);
    },
  );

  it('uses the same default the MapLibre style did, to the foot', () => {
    // The failure this catches is a city that silently changes height the day
    // the renderer is swapped — every unmeasured structure in New York a
    // different size than it was, for a reason no screenshot would name.
    // Read out of the source rather than imported: an import would make the
    // two agree by construction and prove nothing.
    const style = readFileSync(resolve(process.cwd(), 'src', 'lib', 'map', 'darkStyle.ts'), 'utf8');
    const declared = style.match(/const DEFAULT_HEIGHT_FEET = (\d+(?:\.\d+)?);/)?.[1];
    expect(declared, 'darkStyle.ts no longer declares DEFAULT_HEIGHT_FEET').toBeDefined();
    expect(Number(declared)).toBe(DEFAULT_ROOF_FEET);
  });
});

describe('a footprint becomes vertices', () => {
  it('gives every wall four vertices and two triangles, and the roof its own', () => {
    const footprints = readFootprints([square('6', '100')], ANCHOR, new Set());
    const arrays = buildBuildingArrays(footprints, SUN);

    // Four walls at four vertices each, plus a four-point roof.
    expect(arrays.position.length / 3).toBe(4 * 4 + 4);
    // Two triangles per wall, two for the roof.
    expect(arrays.index.length / 3).toBe(4 * 2 + 2);
    expect(arrays.buildings).toBe(1);
  });

  it('marks a roof with a zero wall length, which no wall can carry', () => {
    const footprints = readFootprints([square('7', '100')], ANCHOR, new Set());
    const arrays = buildBuildingArrays(footprints, SUN);

    let roofs = 0;
    let walls = 0;
    for (let v = 0; v < arrays.roof.length; v++) {
      if (arrays.span[v * 4 + 1] === 0) roofs++;
      else {
        walls++;
        // The sentinel only works because nothing shorter than MIN_EDGE_METRES
        // is ever written. If that guard goes, a 0.0 m wall becomes a roof.
        expect(arrays.span[v * 4 + 1]!).toBeGreaterThan(0.19);
      }
    }
    expect(roofs).toBe(4);
    expect(walls).toBe(16);
  });

  it('stands every wall on the ground and stops it at the measured roof', () => {
    const footprints = readFootprints([square('8', '328.084')], ANCHOR, new Set());
    const arrays = buildBuildingArrays(footprints, SUN);

    const heights = new Set<number>();
    for (let v = 0; v < arrays.roof.length; v++) heights.add(arrays.position[v * 3 + 2]!);
    // 328.084 ft is 100 m. A conversion applied twice renders a perfectly
    // plausible city 3.3 times too tall, which is what makes that bug expensive.
    expect([...heights].sort((a, b) => a - b)).toEqual([0, 100]);
  });

  it('leaves no zero triangle behind when a degenerate edge is dropped', () => {
    // Vector tiles quantise geometry, so a simplified footprint arrives with
    // repeated points. The budget assumes a wall per edge; the writer skips
    // some. An untrimmed tail is a triangle at index 0 — a black shard drawn
    // from the scene origin through the middle of New York.
    const [lng, lat] = ANCHOR;
    const degenerate: TileFootprint = {
      properties: { bin: '9', height_roof: '100' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [lng, lat],
            [lng, lat],
            [lng + 0.0003, lat],
            [lng + 0.0003, lat + 0.0003],
          ],
        ],
      },
    };
    const footprints = readFootprints([degenerate], ANCHOR, new Set());
    const arrays = buildBuildingArrays(footprints, SUN);

    const vertices = arrays.position.length / 3;
    for (let i = 0; i < arrays.index.length; i++) {
      expect(arrays.index[i]!).toBeLessThan(vertices);
    }
    // Three walls, not four: the repeated point produced one.
    const walls = [...arrays.span.filter((_, i) => i % 4 === 1)].filter((n) => n > 0).length;
    expect(walls).toBe(3 * 4);
  });

  it('faces a wall into the sun by its outward normal, not its inward one', () => {
    const footprints = readFootprints([square('10', '100')], ANCHOR, new Set());
    const arrays = buildBuildingArrays(footprints, SUN);

    // The sun is west-north-west, so exactly one wall of an axis-aligned box
    // faces most squarely into it and its opposite faces most squarely away.
    // If the winding were inverted, every sign here would flip — and the city
    // would be lit from the east while the sun set over the Hudson.
    const facings: number[] = [];
    for (let v = 0; v < arrays.roof.length; v++) {
      if (arrays.span[v * 4 + 1] !== 0) facings.push(arrays.span[v * 4 + 3]!);
    }
    expect(Math.max(...facings)).toBeGreaterThan(0.9);
    expect(Math.min(...facings)).toBeLessThan(-0.9);
  });

  it('seeds a wall from where it is, so a rebuild does not reshuffle the city', () => {
    // Pan away and back and a tower's windows have to be where they were. A
    // counter would be simpler and would reshuffle every façade in New York
    // each time a tile reloaded, which reads as the city flickering.
    expect(wallSeed(123.5, -87.25)).toBe(wallSeed(123.5, -87.25));
    expect(wallSeed(123.5, -87.25)).not.toBe(wallSeed(123.6, -87.25));
    expect(wallSeed(123.5, -87.25)).toBeGreaterThanOrEqual(0);
    expect(wallSeed(123.5, -87.25)).toBeLessThan(1);
  });

  it('is byte-identical when handed the same footprints twice', () => {
    const first = buildBuildingArrays(
      readFootprints([square('11', '250')], ANCHOR, new Set()),
      SUN,
    );
    const second = buildBuildingArrays(
      readFootprints([square('11', '250')], ANCHOR, new Set()),
      SUN,
    );
    expect([...second.position]).toEqual([...first.position]);
    expect([...second.span]).toEqual([...first.span]);
    expect([...second.index]).toEqual([...first.index]);
  });
});
