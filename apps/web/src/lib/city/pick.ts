/**
 * Which beacon is under the pointer.
 *
 * **`queryRenderedFeatures` cannot answer this, and it does not fail loudly.**
 * Two separate reasons, and either one alone is fatal:
 *
 * 1. The beacons are not MapLibre features. They are Three.js instances inside
 *    a custom layer (ADR 0025), and MapLibre's feature index has never heard of
 *    them. There is no pose at which a query returns one.
 * 2. Even for real features, M4b measured the whole-viewport query returning
 *    **zero** at the 76° pitch this city opens at, with thirty thousand building
 *    features loaded and visibly drawn — the viewport rect is mostly sky and the
 *    corners above the horizon have no ground to unproject onto.
 *
 * So picking is a raycast, and the rule that makes it correct is that it uses
 * **the same matrix the layer drew with**. Recomputing a projection here — from
 * the map's centre, zoom, pitch and bearing — would be a second implementation
 * of MapLibre's camera, free to disagree with the first by a few pixels at the
 * horizon and by a whole building near it. The layer keeps the composed matrix
 * from its last `render` and this file inverts it.
 *
 * Everything here is pure and has no GPU in it: a matrix and a pointer in,
 * a ray out; a ray and a mesh in, an instance index out. That is deliberate —
 * the maths is the part that is wrong silently, and the part jsdom can check.
 */

import { Matrix4, Raycaster, Vector3 } from 'three';
import type { InstancedMesh } from 'three';

/** A ray in scene space: metres from the anchor, the space the field lays out in. */
export interface SceneRay {
  readonly origin: Vector3;
  readonly direction: Vector3;
}

/** A pointer position in CSS pixels, measured from the canvas's top-left. */
export interface PointerPoint {
  readonly x: number;
  readonly y: number;
}

/** The canvas's size in CSS pixels — not its backing-store size. */
export interface Viewport {
  readonly width: number;
  readonly height: number;
}

/**
 * Pointer pixels to normalised device coordinates.
 *
 * The y flip is not cosmetic: clip space grows upward and a canvas grows
 * downward, so without it every pick lands on the mirror image of the thing
 * clicked — which, in a field of near-identical diamonds arranged in a grid,
 * selects a *plausible* wrong beacon rather than nothing at all.
 */
export function ndcFromPointer(
  point: PointerPoint,
  viewport: Viewport,
): readonly [number, number] | null {
  if (!(viewport.width > 0) || !(viewport.height > 0)) return null;
  return [(point.x / viewport.width) * 2 - 1, -((point.y / viewport.height) * 2 - 1)];
}

/**
 * The ray through a point on screen, in scene space.
 *
 * `projection` takes scene metres all the way to clip space — it is
 * `mainMatrix · anchorTransform`, the exact product the layer assigns to its
 * camera. Its inverse takes the near and far points of the clip-space line
 * under the pointer back to metres, and those two points are the ray.
 *
 * `Vector3.applyMatrix4` performs the perspective divide, which is the step
 * that makes this work under a projection with a real w. Doing it by hand and
 * forgetting the divide produces a ray that is right at the centre of the
 * screen and increasingly wrong towards its edges.
 */
export function sceneRayFromNdc(projection: Matrix4, ndcX: number, ndcY: number): SceneRay | null {
  // three's `invert()` returns the zero matrix for a singular input rather than
  // throwing, and a zero matrix turns every point into the origin — so every
  // pick would "hit" whatever is nearest the anchor. Checked, not hoped for.
  if (projection.determinant() === 0) return null;
  const inverse = new Matrix4().copy(projection).invert();

  const near = new Vector3(ndcX, ndcY, -1).applyMatrix4(inverse);
  const far = new Vector3(ndcX, ndcY, 1).applyMatrix4(inverse);
  const direction = new Vector3().subVectors(far, near);
  if (direction.lengthSq() === 0) return null;

  return { origin: near, direction: direction.normalize() };
}

/** Both steps at once: the ray through a pointer position. */
export function sceneRayFromPointer(
  projection: Matrix4,
  point: PointerPoint,
  viewport: Viewport,
): SceneRay | null {
  const ndc = ndcFromPointer(point, viewport);
  if (ndc === null) return null;
  return sceneRayFromNdc(projection, ndc[0], ndc[1]);
}

/**
 * One raycaster, reused.
 *
 * `pick` runs on every `mousemove` — for the hover cursor, which is the only
 * thing on the canvas that says a beacon is clickable — so a trackpad produces
 * a hundred of these a second. It holds no state between calls beyond the ray
 * overwritten at the top of `pickInstance`, and nothing here is reentrant.
 */
const raycaster = new Raycaster();

/**
 * The nearest instance the ray passes through, or null.
 *
 * `boundingSphere` is nulled by the layer whenever the buffer is rewritten,
 * because three caches it and its cached value is over the *previous* set of
 * instances: a field that shrinks would keep a sphere large enough to admit
 * rays that now hit nothing, and one that grows would reject rays that now hit
 * something. The second failure is the bad one — picking silently stops working
 * for the newest employers in the field.
 */
export function pickInstance(mesh: InstancedMesh, ray: SceneRay): number | null {
  if (mesh.count === 0) return null;

  // Raycaster does not update matrices itself; the docs are explicit that the
  // caller must. Normally `renderer.render` has just done it, but a pick can
  // arrive between two frames of a still map, and a stale `matrixWorld` picks
  // against wherever the field used to be.
  mesh.updateMatrixWorld(true);

  raycaster.ray.origin.copy(ray.origin);
  raycaster.ray.direction.copy(ray.direction);

  // `intersectObject` sorts by distance, so the first hit is the nearest —
  // which is what a click on a stack of overlapping beacons should select.
  const hits = raycaster.intersectObject(mesh, false);
  const nearest = hits[0];
  if (nearest === undefined || nearest.instanceId === undefined) return null;
  return nearest.instanceId;
}
