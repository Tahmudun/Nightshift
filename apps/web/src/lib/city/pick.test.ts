import {
  BoxGeometry,
  InstancedMesh,
  Matrix4,
  MeshBasicMaterial,
  Object3D,
  PerspectiveCamera,
  Ray,
  Vector3,
} from 'three';
import { describe, expect, it } from 'vitest';

import { ndcFromPointer, pickInstance, sceneRayFromNdc, sceneRayFromPointer } from './pick';

/**
 * A projection with a real perspective divide in it, tilted and off-axis.
 *
 * An axis-aligned camera looking down -z would let a broken unprojection pass:
 * the divide is uniform, the y flip cancels against itself in the middle of the
 * screen, and everything looks right until the map is rotated. This one is
 * pitched and rotated so none of those coincidences hold, which is also the
 * only pose this product is ever actually in.
 */
function tiltedProjection(): Matrix4 {
  const camera = new PerspectiveCamera(45, 16 / 9, 1, 40_000);
  camera.position.set(1_200, -3_400, 2_100);
  camera.lookAt(new Vector3(0, 0, 700));
  camera.updateMatrixWorld(true);
  return new Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
}

function instancedAt(positions: readonly Vector3[], size = 60): InstancedMesh {
  const mesh = new InstancedMesh(
    new BoxGeometry(size, size, size),
    new MeshBasicMaterial(),
    Math.max(positions.length, 1),
  );
  mesh.frustumCulled = false;
  const scratch = new Object3D();
  positions.forEach((position, index) => {
    scratch.position.copy(position);
    scratch.updateMatrix();
    mesh.setMatrixAt(index, scratch.matrix);
  });
  mesh.count = positions.length;
  mesh.instanceMatrix.needsUpdate = true;
  return mesh;
}

describe('ndcFromPointer', () => {
  it('puts the top-left pixel at the top-left of clip space', () => {
    expect(ndcFromPointer({ x: 0, y: 0 }, { width: 800, height: 600 })).toEqual([-1, 1]);
  });

  it('flips y, because a canvas grows downward and clip space grows up', () => {
    // The failure this pins is not "nothing is picked". It is that a click near
    // the top of the field picks a beacon near the bottom of it — a plausible
    // wrong answer in a grid of near-identical diamonds.
    expect(ndcFromPointer({ x: 400, y: 600 }, { width: 800, height: 600 })).toEqual([0, -1]);
  });

  it('refuses a canvas with no area rather than dividing by zero', () => {
    // A map in a collapsed container reports 0×0, and without this the pointer
    // becomes NaN, the ray becomes NaN, and the raycast quietly answers null
    // for every click on a perfectly good field.
    expect(ndcFromPointer({ x: 10, y: 10 }, { width: 0, height: 600 })).toBeNull();
    expect(ndcFromPointer({ x: 10, y: 10 }, { width: 800, height: 0 })).toBeNull();
  });
});

describe('sceneRayFromNdc', () => {
  /**
   * The property that actually matters, and it holds for any projection:
   * a point that projects to some place on screen must lie on the ray cast
   * through that place.
   *
   * Asserted as a round trip rather than against a table of expected
   * coordinates, because a table computed with the same wrong formula agrees
   * with itself.
   */
  it('casts a ray that passes through the point the pointer is over', () => {
    const projection = tiltedProjection();

    for (const point of [
      new Vector3(0, 0, 700),
      new Vector3(1_860, -620, 745),
      new Vector3(-1_240, 1_240, 880),
    ]) {
      const clip = point.clone().applyMatrix4(projection);
      const ray = sceneRayFromNdc(projection, clip.x, clip.y);
      expect(ray).not.toBeNull();

      const distance = new Ray(ray!.origin, ray!.direction).distanceToPoint(point);
      // Sub-millimetre, over a scene measured in kilometres.
      expect(distance).toBeLessThan(0.001);
    }
  });

  it('points away from the viewer rather than towards them', () => {
    const projection = tiltedProjection();
    const target = new Vector3(0, 0, 700);
    const clip = target.clone().applyMatrix4(projection);

    const ray = sceneRayFromNdc(projection, clip.x, clip.y)!;

    // A direction negated by a sign error still produces a ray *through* the
    // point, so the round trip above cannot catch it — and every pick then
    // answers null, because the geometry is all behind the origin.
    expect(ray.direction.dot(target.clone().sub(ray.origin))).toBeGreaterThan(0);
  });

  it('refuses a singular matrix instead of inverting it to zeros', () => {
    // three's `invert()` answers the zero matrix for a singular input rather
    // than throwing. A zero matrix maps every clip point to the origin, so
    // every pick would return whatever instance is closest to the anchor —
    // a wrong answer that looks like a working feature.
    const singular = new Matrix4();
    singular.elements.fill(0);
    expect(sceneRayFromNdc(singular, 0, 0)).toBeNull();
  });
});

describe('sceneRayFromPointer', () => {
  it('finds the point under a pixel, all the way from the pointer', () => {
    const projection = tiltedProjection();
    const viewport = { width: 1_600, height: 900 };
    const point = new Vector3(620, -620, 790);

    const clip = point.clone().applyMatrix4(projection);
    const pixel = {
      x: ((clip.x + 1) / 2) * viewport.width,
      y: ((1 - clip.y) / 2) * viewport.height,
    };

    const ray = sceneRayFromPointer(projection, pixel, viewport)!;

    expect(new Ray(ray.origin, ray.direction).distanceToPoint(point)).toBeLessThan(0.001);
  });

  it('answers null for a canvas with no area', () => {
    expect(
      sceneRayFromPointer(tiltedProjection(), { x: 5, y: 5 }, { width: 0, height: 0 }),
    ).toBeNull();
  });
});

describe('pickInstance', () => {
  it('finds the instance the ray goes through', () => {
    const mesh = instancedAt([new Vector3(0, 0, 700), new Vector3(2_000, 0, 700)]);
    const ray = { origin: new Vector3(2_000, -5_000, 700), direction: new Vector3(0, 1, 0) };

    expect(pickInstance(mesh, ray)).toBe(1);
  });

  it('answers the nearest of two the ray goes through, not the first written', () => {
    // A click on a stack selects the one in front. Written back-to-front on
    // purpose: an implementation that returns `hits[0]` without sorting, or
    // that scans the buffer in order, gets this backwards and selects a role
    // hidden behind the one the user aimed at.
    const mesh = instancedAt([new Vector3(0, 3_000, 700), new Vector3(0, -3_000, 700)]);
    const ray = { origin: new Vector3(0, -9_000, 700), direction: new Vector3(0, 1, 0) };

    expect(pickInstance(mesh, ray)).toBe(1);
  });

  it('answers null for a ray through empty sky', () => {
    const mesh = instancedAt([new Vector3(0, 0, 700)]);
    const ray = { origin: new Vector3(0, -5_000, 700), direction: new Vector3(1, 0, 0) };

    expect(pickInstance(mesh, ray)).toBeNull();
  });

  it('answers null when nothing is drawn', () => {
    const mesh = instancedAt([]);
    const ray = { origin: new Vector3(0, -5_000, 700), direction: new Vector3(0, 1, 0) };

    expect(pickInstance(mesh, ray)).toBeNull();
  });

  it('cannot see a new instance while three is holding the old bounding sphere', () => {
    // This is the trap, stated as a test rather than as a comment. three caches
    // `boundingSphere` on first raycast and gates every later one on it, so a
    // field that *grows* keeps a sphere too small to admit the new columns and
    // picking silently stops working for exactly the newest employers.
    const mesh = new InstancedMesh(new BoxGeometry(60, 60, 60), new MeshBasicMaterial(), 2);
    const scratch = new Object3D();
    scratch.position.set(0, 0, 700);
    scratch.updateMatrix();
    mesh.setMatrixAt(0, scratch.matrix);
    mesh.count = 1;

    const near = { origin: new Vector3(0, -5_000, 700), direction: new Vector3(0, 1, 0) };
    expect(pickInstance(mesh, near)).toBe(0);

    scratch.position.set(9_000, 0, 700);
    scratch.updateMatrix();
    mesh.setMatrixAt(1, scratch.matrix);
    mesh.count = 2;
    mesh.instanceMatrix.needsUpdate = true;

    const far = { origin: new Vector3(9_000, -5_000, 700), direction: new Vector3(0, 1, 0) };
    expect(pickInstance(mesh, far)).toBeNull();

    // The one line the layer has to remember on every rewrite of the buffer.
    mesh.boundingSphere = null;
    expect(pickInstance(mesh, far)).toBe(1);
  });
});
