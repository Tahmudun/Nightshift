/**
 * Web Mercator, written out rather than imported.
 *
 * MapLibre exports `MercatorCoordinate` and it does exactly this. Importing it
 * costs two things that both matter here:
 *
 * - **jsdom.** `maplibre-gl`'s entry point calls `URL.createObjectURL` at
 *   module scope to set up its worker, which does not exist in jsdom. A single
 *   value import would make every unit test that touches the scene layer fail
 *   before it ran a line.
 * - **The bundle.** `CityMap` imports MapLibre *inside an effect* precisely
 *   because it is 800 KB and touches `window`. A module-scope import anywhere
 *   in the scene code would undo that for every page that reaches it.
 *
 * So the projection lives here, in fifteen lines with a test that pins it to
 * values anybody can check by hand, and `city.spec.ts` compares it against the
 * real `MercatorCoordinate` in a browser where both exist. Duplicated maths is
 * only dangerous when nothing checks it.
 */

/** WGS84 authalic mean radius, the value MapLibre projects with. */
const EARTH_RADIUS_METRES = 6_371_008.8;

const EARTH_CIRCUMFERENCE_METRES = 2 * Math.PI * EARTH_RADIUS_METRES;

/** A point in MapLibre's mercator world: the unit square, y growing southward. */
export interface Mercator {
  readonly x: number;
  readonly y: number;
}

export function mercatorFromLngLat(lng: number, lat: number): Mercator {
  return {
    x: (180 + lng) / 360,
    y: (180 - (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))) / 360,
  };
}

/**
 * How much of a mercator unit one metre is, at this latitude.
 *
 * Mercator stretches away from the equator, so this is the number that lets the
 * scene be written in metres. At New York's latitude it is about 1.3× the
 * equatorial value, and using the equatorial one instead would shrink the whole
 * field by a quarter — a mistake that looks like a design choice.
 */
export function metreInMercatorUnits(lat: number): number {
  return 1 / (EARTH_CIRCUMFERENCE_METRES * Math.cos((lat * Math.PI) / 180));
}

/**
 * Back the other way: a mercator point to the coordinate it came from.
 *
 * The inverse exists because the roster panel flies the camera to a column,
 * and a column knows only where it is in metres from the anchor. Something has
 * to turn that back into a longitude and a latitude, and doing it by inverting
 * the forward function is the only version that cannot drift from it —
 * `mercator.test.ts` asserts the round trip rather than a table of constants.
 */
export function lngLatFromMercator(point: Mercator): readonly [number, number] {
  const lng = point.x * 360 - 180;
  const lat = ((Math.atan(Math.exp(Math.PI * (1 - 2 * point.y))) - Math.PI / 4) * 360) / Math.PI;
  return [lng, lat];
}

/**
 * The other direction: a real coordinate to its place in the scene.
 *
 * This is the trip a **placed** role takes. An office was geocoded to a point
 * on Earth (`city.md` §4.4) and the scene, which is written in metres from an
 * anchor, has to draw it at that point and nowhere else.
 *
 * It is deliberately the only way into the scene from a coordinate, and the
 * inverse of `lngLatFromScene` down to floating point — `mercator.test.ts`
 * asserts the round trip rather than a table of metre offsets, because a
 * projection wrong by a constant factor still lands in Midtown and still looks
 * like a building.
 *
 * Nothing in the unresolved field may call this. There is no coordinate there
 * to convert: those roles have no position, which is the whole of I1.
 */
export function sceneFromLngLat(
  anchor: readonly [number, number],
  lng: number,
  lat: number,
): { readonly x: number; readonly y: number } {
  const origin = mercatorFromLngLat(anchor[0], anchor[1]);
  const point = mercatorFromLngLat(lng, lat);
  const scale = metreInMercatorUnits(anchor[1]);
  // The same southward flip `lngLatFromScene` undoes, applied here instead. A
  // scene y is metres *north*; mercator y grows south.
  //
  // `|| 0` normalises negative zero, which the negation produces for any point
  // exactly on the anchor's parallel. It renders identically and compares equal
  // under `===`, so it survives every obvious check and then fails a deep-equal
  // in a caller's test with a diff reading `0` versus `-0`. `unresolvedField`
  // carries the same guard for the same reason, and this is the second time it
  // has been needed.
  return { x: (point.x - origin.x) / scale || 0, y: -(point.y - origin.y) / scale || 0 };
}

/**
 * Where a point in the scene actually is on Earth.
 *
 * `x` and `y` are metres east and north of the anchor, which is the space
 * `unresolvedField` lays out in. The `-y` is the same flip `anchorTransform`
 * applies for the same reason: mercator y grows southward while the field's y
 * is metres north, and getting it wrong mirrors the whole field about the
 * anchor — an error that still produces a plausible-looking city.
 *
 * A caveat that matters for what this is used for: the scene's altitude has no
 * part in this. The result is the ground position beneath a column, which is
 * what a camera flies to, and it is **not** a claim about where any role is.
 * Nothing in the unresolved field has a real position (I1); these coordinates
 * describe an arrangement on screen and nothing about New York.
 */
export function lngLatFromScene(
  anchor: readonly [number, number],
  x: number,
  y: number,
): readonly [number, number] {
  const origin = mercatorFromLngLat(anchor[0], anchor[1]);
  const scale = metreInMercatorUnits(anchor[1]);
  return lngLatFromMercator({ x: origin.x + x * scale, y: origin.y - y * scale });
}
