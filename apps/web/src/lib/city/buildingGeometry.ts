/**
 * NYC's footprints, turned into something a shader can light.
 *
 * ADR 0031 moves the buildings out of MapLibre's `fill-extrusion` and into the
 * Three.js layer, for one reason: `fill-extrusion`'s only expressive channel is
 * a colour ramp. It has no outline, no texture that can coexist with a colour,
 * and one fixed white light. Everything reference 02 builds a tower out of —
 * lit corners, a lit roofline, windows, a base that glows where it meets the
 * street — is a per-fragment quantity, and this file is what gives the fragment
 * shader enough to compute them.
 *
 * **The geometry source does not change.** Same pinned tile archive (ADR 0022),
 * same measured `height_roof`, same documented 25 ft default. This reads the
 * features MapLibre has already loaded and parsed; it adds no source, no
 * request and no second copy of NYC's building table.
 *
 * ## What a vertex carries, and why each one is needed
 *
 * | attribute  | meaning                                                    |
 * |------------|------------------------------------------------------------|
 * | `position` | metres east / north / up from the scene anchor              |
 * | `span.x`   | metres along this wall from its start                       |
 * | `span.y`   | this wall's length in metres — **0 marks a roof**           |
 * | `span.z`   | a per-wall seed, so two walls do not share a window pattern |
 * | `span.w`   | how squarely this wall faces the sun, −1..1                 |
 * | `roof`     | the whole building's roof height in metres                  |
 *
 * `span.x` and `position.z` are the wall's own coordinate system, which is what
 * a window grid needs: rows are metres up, columns are metres along. `span.y`
 * turns that into a fraction, which is what an *edge* needs — a corner is where
 * the fraction reaches 0 or 1, and that is the read all four reference images
 * are built from. `roof` gates the crown, because a lit roofline on every
 * structure in New York is a bright fog at head height, not a skyline (the
 * count that settled that threshold is in `darkStyle.ts`).
 *
 * **No normals.** Nothing here does diffuse shading — the one directional cue
 * is `span.w`, computed once per wall on the CPU, and the rest of the light is
 * emissive. A normal per vertex would be 12 bytes each across ~1.2M vertices to
 * carry three numbers that are constant per wall.
 */

import { ShapeUtils, Vector2 } from 'three';

import { mercatorFromLngLat, metreInMercatorUnits } from './mercator';

/** Feet to metres. The same factor `darkStyle.ts` applies, applied once here. */
const FEET_TO_METRES = 0.3048;

/**
 * What a footprint with no measured height is drawn as, in feet.
 *
 * Deliberately the same number `darkStyle.ts` uses, and deliberately *not*
 * imported from it: that module builds a MapLibre style and this one builds
 * geometry, and a shared import would be the only thing tying them together.
 * `buildingGeometry.test.ts` asserts the two agree, which is the check that
 * actually matters — the failure mode is a city that changes height the day the
 * renderer is swapped, and a test catches that where an import only hides it.
 */
export const DEFAULT_ROOF_FEET = 25;

/**
 * Edges shorter than this are dropped.
 *
 * Vector tiles quantise geometry to the tile's own grid, so a simplified
 * footprint arrives with occasional zero-length and near-zero-length edges.
 * A zero-length wall divides by its own length when the shader normalises
 * `span.x`, and the result is a NaN fragment — which on most drivers is a black
 * quad and on some is a white one.
 */
const MIN_EDGE_METRES = 0.2;

/** One polygon: its outer ring first, then any holes. Flat `[x, y, x, y, …]`. */
export type Ring = Float64Array;

/** A building, already in scene metres. One entry per polygon it is made of. */
export interface Footprint {
  /** NYC's building identification number, as the tiles carry it. */
  readonly bin: string;
  /** The roof, in metres. Measured where NYC measured it, defaulted where not. */
  readonly roofMetres: number;
  /** Whether `roofMetres` was measured or is the documented default. */
  readonly measured: boolean;
  /**
   * The polygons this footprint is made of, each `[outer, ...holes]`.
   *
   * Nested rather than flattened because the nesting *is* the meaning: a second
   * ring inside one polygon is a courtyard, and a second polygon is a separate
   * piece of the same building. Flattened, the two are indistinguishable, and
   * the 47 multi-polygon structures in one view of New York get their outlying
   * wings triangulated as holes in their main mass — a roof with a building-
   * shaped void in it, which reads as a hole in the city.
   */
  readonly polygons: readonly (readonly Ring[])[];
}

/** The shape this reads off a tile feature. Anything else on it is ignored. */
export interface TileFootprint {
  readonly properties?: unknown;
  readonly geometry?: unknown;
}

/**
 * The arrays one chunk of city becomes.
 *
 * Interleaving would save a little bandwidth and cost every reader the ability
 * to check one attribute in isolation. These are handed straight to
 * `BufferAttribute`, which is happy either way.
 */
export interface BuildingArrays {
  /** 3 floats per vertex. Metres east, north, up. */
  readonly position: Float32Array;
  /** 4 floats per vertex. See the table at the head of this file. */
  readonly span: Float32Array;
  /** 1 float per vertex. The building's roof height in metres. */
  readonly roof: Float32Array;
  readonly index: Uint32Array;
  /** How many footprints are in here. Reported, not inferred from the arrays. */
  readonly buildings: number;
}

/**
 * The roof height on a tile feature, in metres, with the default substituted.
 *
 * The attribute arrives as a **string** — NYC's export quotes its numbers and
 * tippecanoe preserves the type it was given — so this coerces rather than
 * trusting. An empty string, a null and an absent key all mean "not measured"
 * and all take the default.
 */
export function roofMetresOf(properties: unknown): { metres: number; measured: boolean } {
  const fallback = { metres: DEFAULT_ROOF_FEET * FEET_TO_METRES, measured: false };
  if (typeof properties !== 'object' || properties === null) return fallback;
  const feet = Number((properties as Record<string, unknown>).height_roof);
  if (!Number.isFinite(feet) || feet <= 0) return fallback;
  return { metres: feet * FEET_TO_METRES, measured: true };
}

/**
 * A coordinate out of a flat ring.
 *
 * `noUncheckedIndexedAccess` types every typed-array read as `number |
 * undefined`. That is true of an out-of-range index and false of every index in
 * this file — all of them are derived from the array's own length. The
 * alternatives are an assertion on some two dozen reads in the hottest loop in
 * the renderer, or `?? 0`, which would turn a real indexing bug into a vertex
 * quietly placed at the origin and a black shard across the city. This says it
 * once, and V8 inlines it away.
 */
function coord(ring: Ring, index: number): number {
  return ring[index] as number;
}

/** Twice the signed area of a flat ring. Positive is counter-clockwise. */
export function ringTurn(ring: Ring): number {
  let sum = 0;
  const n = ring.length / 2;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    sum +=
      coord(ring, j * 2) * coord(ring, i * 2 + 1) - coord(ring, i * 2) * coord(ring, j * 2 + 1);
  }
  return sum;
}

/** Reverse a flat ring in place, point by point rather than number by number. */
function reverseRing(ring: Ring): void {
  const n = ring.length / 2;
  for (let i = 0, j = n - 1; i < j; i++, j--) {
    const x = coord(ring, i * 2);
    const y = coord(ring, i * 2 + 1);
    ring[i * 2] = coord(ring, j * 2);
    ring[i * 2 + 1] = coord(ring, j * 2 + 1);
    ring[j * 2] = x;
    ring[j * 2 + 1] = y;
  }
}

/**
 * A stable pseudo-random number for a point, 0..1.
 *
 * Seeded from the wall's own start coordinate so it survives a rebuild: pan
 * away and back and a tower's windows are where they were. A counter would be
 * simpler and would reshuffle every façade in New York each time a tile
 * reloaded, which is the sort of thing that reads as the city flickering.
 */
export function wallSeed(x: number, y: number): number {
  const v = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453;
  return v - Math.floor(v);
}

/** Rings out of a GeoJSON geometry, in whatever nesting it arrived with. */
function polygonsOf(geometry: unknown): unknown[][] {
  if (typeof geometry !== 'object' || geometry === null) return [];
  const g = geometry as { type?: unknown; coordinates?: unknown };
  if (!Array.isArray(g.coordinates)) return [];
  if (g.type === 'Polygon') return [g.coordinates as unknown[]];
  if (g.type === 'MultiPolygon') return g.coordinates as unknown[][];
  return [];
}

/**
 * Tile features to footprints in scene metres.
 *
 * The projection is inlined rather than calling `sceneFromLngLat` per point:
 * that function recomputes the anchor's mercator origin and the latitude scale
 * on every call, and this runs a quarter of a million times for one view of
 * New York. The maths is identical and `buildingGeometry.test.ts` asserts it
 * against `sceneFromLngLat` rather than against a table of numbers, so the two
 * cannot drift.
 *
 * `seen` is how a footprint that straddles a tile boundary — or one that is
 * still loaded from the last camera position — is admitted exactly once. It is
 * the caller's set, because the caller is what knows when the city is being
 * rebuilt rather than extended.
 */
export function readFootprints(
  features: readonly TileFootprint[],
  anchor: readonly [number, number],
  seen: Set<string>,
): Footprint[] {
  const origin = mercatorFromLngLat(anchor[0], anchor[1]);
  const scale = metreInMercatorUnits(anchor[1]);
  const footprints: Footprint[] = [];

  for (const feature of features) {
    const properties = feature.properties;
    if (typeof properties !== 'object' || properties === null) continue;
    const bin = (properties as Record<string, unknown>).bin;
    if (typeof bin !== 'string' && typeof bin !== 'number') continue;
    const key = String(bin);
    if (key === '' || seen.has(key)) continue;

    const source = polygonsOf(feature.geometry);
    if (source.length === 0) continue;

    const { metres, measured } = roofMetresOf(properties);
    const polygons: Ring[][] = [];

    for (const polygon of source) {
      if (!Array.isArray(polygon)) continue;
      const rings: Ring[] = [];
      for (let r = 0; r < polygon.length; r++) {
        const points = polygon[r];
        // Three, not four. A tile always closes its rings, so a triangle
        // arrives with four points — but a ring handed over already open is a
        // valid triangle at three, and rejecting it here would drop a real
        // building for a reason nothing on screen could explain. The count
        // that actually has to hold is checked below, after the closing point
        // has been stripped.
        if (!Array.isArray(points) || points.length < 3) continue;
        // GeoJSON closes its rings; the last point repeats the first. Kept
        // open here, because a closed ring triangulates into a degenerate ear
        // and extrudes a wall of length zero.
        const first: unknown = points[0];
        const last: unknown = points[points.length - 1];
        const closed =
          Array.isArray(first) &&
          Array.isArray(last) &&
          first[0] === last[0] &&
          first[1] === last[1];
        const count = closed ? points.length - 1 : points.length;
        if (count < 3) continue;

        const ring = new Float64Array(count * 2);
        for (let i = 0; i < count; i++) {
          const point = points[i] as [number, number];
          const mx = (180 + point[0]) / 360;
          const my =
            (180 - (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (point[1] * Math.PI) / 360))) /
            360;
          ring[i * 2] = (mx - origin.x) / scale;
          // Mercator y grows southward; the scene's y is metres north.
          ring[i * 2 + 1] = -(my - origin.y) / scale;
        }

        // Outer ring counter-clockwise, holes clockwise. Two things depend on
        // it and both fail silently otherwise: the outward wall normal, which
        // decides which walls the sun catches, and the roof's own winding,
        // which decides whether the roof is visible at all under backface
        // culling.
        const turn = ringTurn(ring);
        const outer = rings.length === 0;
        if ((outer && turn < 0) || (!outer && turn > 0)) reverseRing(ring);
        rings.push(ring);
      }
      if (rings.length > 0) polygons.push(rings);
    }

    if (polygons.length === 0) continue;
    seen.add(key);
    footprints.push({ bin: key, roofMetres: metres, measured, polygons });
  }

  return footprints;
}

/**
 * How many vertices and indices a set of footprints will need.
 *
 * Counted before anything is written so the arrays are allocated once at their
 * final size. Growing them instead means copying a megabyte of city several
 * times per chunk, in the middle of a gesture.
 *
 * The wall count is exact. The roof count is an **upper bound** — a contour of
 * `n` points with `h` hole points triangulates into at most `n + 2h − 2`
 * triangles — so the arrays are trimmed to what was actually written rather
 * than trusted here.
 */
function budget(footprints: readonly Footprint[]): { vertices: number; indices: number } {
  let vertices = 0;
  let indices = 0;
  for (const footprint of footprints) {
    for (const polygon of footprint.polygons) {
      let points = 0;
      for (const ring of polygon) points += ring.length / 2;
      // Four vertices and two triangles per wall, and one wall per edge.
      vertices += points * 4;
      indices += points * 6;
      // The roof reuses every point of every ring once, at roof height.
      vertices += points;
      indices += Math.max(0, points + 2 * (polygon.length - 1) - 2) * 3;
    }
  }
  return { vertices, indices };
}

/**
 * Footprints to vertex arrays.
 *
 * One pass, no intermediate objects per vertex, and every array sized up front.
 * This is the hot loop of the whole renderer — a quarter of a million points
 * for one view of New York — and it runs inside a frame budget, so the shape of
 * the code here is the difference between the city assembling smoothly and the
 * page hitching every time a tile lands.
 *
 * `sun` is the horizontal direction the light comes from, east and north. It is
 * baked into `span.w` here rather than passed as a uniform and dotted per
 * fragment, because it is constant for the whole scene and per-wall on the CPU
 * is four floats written once against a normalise-and-dot in every pixel.
 */
export function buildBuildingArrays(
  footprints: readonly Footprint[],
  sun: readonly [number, number],
): BuildingArrays {
  const size = budget(footprints);
  const position = new Float32Array(size.vertices * 3);
  const span = new Float32Array(size.vertices * 4);
  const roof = new Float32Array(size.vertices);
  const index = new Uint32Array(size.indices);

  let v = 0;
  let i = 0;

  // Reused across every ring in the chunk. `triangulateShape` mutates the
  // arrays it is given — it pops a duplicated end point — so the *lists* are
  // rebuilt per polygon, but the `Vector2` objects in them are pooled. That is
  // the allocation that would otherwise happen a quarter of a million times.
  const pool: Vector2[] = [];
  const vector = (n: number): Vector2 => {
    while (pool.length <= n) pool.push(new Vector2());
    return pool[n] as Vector2;
  };

  for (const footprint of footprints) {
    const h = footprint.roofMetres;

    for (const polygon of footprint.polygons) {
      // --- Walls -----------------------------------------------------------
      for (const ring of polygon) {
        const n = ring.length / 2;
        for (let a = 0; a < n; a++) {
          const b = (a + 1) % n;
          const x0 = coord(ring, a * 2);
          const y0 = coord(ring, a * 2 + 1);
          const x1 = coord(ring, b * 2);
          const y1 = coord(ring, b * 2 + 1);
          const dx = x1 - x0;
          const dy = y1 - y0;
          const length = Math.hypot(dx, dy);
          if (length < MIN_EDGE_METRES) continue;

          // Outward normal of a counter-clockwise ring. Used only for the sun
          // term; the winding above is what makes it point away from the mass.
          const facing = (dy / length) * sun[0] + (-dx / length) * sun[1];
          const seed = wallSeed(x0, y0);

          const base = v;
          // Base-start, base-end, top-end, top-start: counter-clockwise seen
          // from outside, which is what backface culling needs.
          const xs = [x0, x1, x1, x0];
          const ys = [y0, y1, y1, y0];
          const zs = [0, 0, h, h];
          const us = [0, length, length, 0];
          for (let k = 0; k < 4; k++) {
            position[v * 3] = xs[k] as number;
            position[v * 3 + 1] = ys[k] as number;
            position[v * 3 + 2] = zs[k] as number;
            span[v * 4] = us[k] as number;
            span[v * 4 + 1] = length;
            span[v * 4 + 2] = seed;
            span[v * 4 + 3] = facing;
            roof[v] = h;
            v++;
          }
          index[i++] = base;
          index[i++] = base + 1;
          index[i++] = base + 2;
          index[i++] = base;
          index[i++] = base + 2;
          index[i++] = base + 3;
        }
      }

      // --- Roof --------------------------------------------------------------
      const outer = polygon[0];
      if (outer === undefined) continue;
      const outerCount = outer.length / 2;
      if (outerCount < 3) continue;

      const contour: Vector2[] = [];
      for (let k = 0; k < outerCount; k++) {
        contour.push(vector(k).set(coord(outer, k * 2), coord(outer, k * 2 + 1)));
      }
      let pooled = outerCount;
      const holes: Vector2[][] = [];
      for (let r = 1; r < polygon.length; r++) {
        const hole = polygon[r];
        if (hole === undefined) continue;
        const count = hole.length / 2;
        const points: Vector2[] = [];
        for (let k = 0; k < count; k++) {
          points.push(vector(pooled++).set(coord(hole, k * 2), coord(hole, k * 2 + 1)));
        }
        holes.push(points);
      }

      // Triangulated **before** the vertices are written, not after.
      // `triangulateShape` mutates what it is given — it pops a duplicated end
      // point — and the indices it returns are into the list as it left it. The
      // rings arriving here have already had their closing point stripped, so
      // nothing is popped in practice; doing it in this order means that stays
      // a fact about the data rather than a thing the code depends on.
      const faces = ShapeUtils.triangulateShape(contour, holes);

      const base = v;
      const write = (points: readonly Vector2[]): void => {
        for (const point of points) {
          position[v * 3] = point.x;
          position[v * 3 + 1] = point.y;
          position[v * 3 + 2] = h;
          span[v * 4] = 0;
          // Zero length is the sentinel for "this is a roof". No wall can carry
          // it: anything under MIN_EDGE_METRES was dropped above.
          span[v * 4 + 1] = 0;
          span[v * 4 + 2] = wallSeed(point.x, point.y);
          span[v * 4 + 3] = 0;
          roof[v] = h;
          v++;
        }
      };
      // The contour and its holes are one list to `triangulateShape`, in
      // exactly this order, and the faces index into it.
      write(contour);
      for (const hole of holes) write(hole);

      for (const face of faces) {
        index[i++] = base + (face[0] as number);
        index[i++] = base + (face[1] as number);
        index[i++] = base + (face[2] as number);
      }
    }
  }

  return {
    // Trimmed to what was actually written. The roof budget is an upper bound
    // and the wall budget drops degenerate edges, so the tail of every array is
    // zeros — and a zero in `index` is a triangle at the origin, which draws a
    // black shard through the middle of the city.
    position: position.subarray(0, v * 3),
    span: span.subarray(0, v * 4),
    roof: roof.subarray(0, v),
    index: index.subarray(0, i),
    buildings: footprints.length,
  };
}
