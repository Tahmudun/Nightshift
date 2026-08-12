/**
 * Flying the camera to a place in the field, in one definition.
 *
 * Two things now point the camera at a column — the roster's rows and a
 * selection arriving from the URL — and §5.6's rule that a selection "moves the
 * camera only if needed" is a rule about *how far away* and *how much of the
 * screen is covered*. Both of those are numbers, and two call sites with their
 * own copies of them are two behaviours a person would experience as the map
 * being inconsistent about when it moves.
 *
 * The margin in particular is not a taste: it is the width of the rail, and it
 * has already been wrong once — a column drawn *behind* the roster satisfied
 * `focusOn`'s default 18% and counted as "already visible", so the camera
 * declined to move and clicking a row appeared to do nothing.
 */

import type { CameraController } from '@/lib/map/camera';
import { INITIAL_POSE } from '@/lib/map/camera';

import { lngLatFromScene } from './mercator';

/**
 * The zoom a column is read from.
 *
 * Lower than `focusOn`'s own default, which is set for a single building. A
 * column is 620 m from its neighbours and this field is kilometres wide, so
 * arriving at street zoom puts one stack of diamonds across the whole window
 * with nothing around it to say where you are.
 */
export const COLUMN_ZOOM = 14;

/**
 * How much of each edge does not count as on screen.
 *
 * Wider than `focusOn`'s own default, because of the rail: it is 21rem, about
 * a quarter of a laptop window, so a column drawn behind it satisfies the
 * default margin while being completely invisible.
 */
export const COLUMN_MARGIN = 0.3;

/**
 * Put a point in the field on screen, if it is not already.
 *
 * `x` and `y` are metres east and north of the scene anchor. The anchor is
 * `INITIAL_POSE.center` — the same one the signal layer is constructed with,
 * read from the same constant, because a second definition of where the field
 * is would send the camera somewhere the beacons are not.
 *
 * The altitude is deliberately not part of this. `focusOn` frames a ground
 * coordinate, and the coordinate under a floating column is **not a claim
 * about where the role is** (I1) — it is where the camera has to stand to see
 * an arrangement on screen.
 *
 * Returns whether the camera actually moved, so a caller can tell a no-op from
 * a journey.
 */
export function focusColumn(camera: CameraController | null, x: number, y: number): boolean {
  if (camera === null) return false;
  return camera.focusOn(lngLatFromScene(INITIAL_POSE.center, x, y), {
    zoom: COLUMN_ZOOM,
    margin: COLUMN_MARGIN,
  });
}
