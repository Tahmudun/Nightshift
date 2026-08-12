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
