/**
 * The column of light over a building somebody is hiring in.
 *
 * ADR 0023 decides what a hiring building looks like, and the reasoning is a
 * ratio rather than a taste. The extrusion layer draws tens of thousands of
 * footprints in view; the number that will ever be hiring is tens. **A
 * brightness difference cannot carry ten in fifty thousand** — a bright thing
 * pops against black and merges into a bright field, and this city is a bright
 * field now (ADR 0029). So the mark differs in *shape and behaviour*: a narrow
 * vertical column where the city is horizontal, leaving the roof and
 * dissipating into the sky. `02-skyline-grid-plane` in
 * `docs/design/references/` is that beam, drawn before this product drew it.
 *
 * **One beam per building, not per role.** A beam says "somebody is hiring
 * here", which is one fact about a structure however many openings are behind
 * it. Two stacked in a column would also be twice as bright as one, encoding a
 * count nobody asked the light to carry — how many roles are open is what the
 * stack of beacons standing in the beam is for.
 *
 * **Its height is the stack's height.** A fixed length is what `markMesh`'s
 * gold beam uses, and that beam decorates a single beacon. This one has to
 * reach past every role standing on the roof, or the top ones hang above the
 * light they are supposed to be standing in — which is how the untethered
 * field reads (§4.8), and the two states must never be able to look the same.
 *
 * The height is a per-instance scale rather than a per-building geometry: one
 * geometry, one draw call, N transforms (§5.5). A cylinder per building would
 * be the one-object-per-job anti-pattern with the object one level up.
 */

import {
  AdditiveBlending,
  Color,
  CylinderGeometry,
  DoubleSide,
  DynamicDrawUsage,
  InstancedMesh,
  Matrix4,
  Object3D,
  ShaderMaterial,
} from 'three';

import { SIGNAL_COLOR } from './beacon';
import type { HiringBuilding } from './buildingField';

/**
 * How many beams the mesh allocates room for.
 *
 * Far below `MAX_BEACONS`, and for the reason ADR 0023 gives: a beam marks a
 * *building*, and the number of distinct buildings with a confirmed address
 * will trail the number of roles by orders of magnitude for the life of this
 * product. Allocating five thousand columns to draw two would be reserving GPU
 * memory against a corpus that cannot exist — every one of them needs a street
 * address a person typed.
 */
export const MAX_ROOF_BEAMS = 500;

/** Radius of the column, in metres. Narrow: §2.1's beam is a line, not a tower. */
const BEAM_RADIUS = 9;

export interface RoofBeamMesh {
  readonly mesh: InstancedMesh;
  /** Rewrite the whole buffer. The only way the beams change. */
  set(buildings: readonly HiringBuilding[]): void;
  readonly drawn: number;
  /** The matrix instance `index` is drawn with, or null if nothing is there. */
  matrixAt(index: number): Matrix4 | null;
  /** How tall instance `index` is, in metres, or null. */
  heightAt(index: number): number | null;
  dispose(): void;
}

export function createRoofBeamMesh(): RoofBeamMesh {
  // A unit-height cylinder, open-ended, scaled per instance. Three's cylinder
  // runs along y and the scene's up is z, so it is rotated once here rather
  // than per instance — which keeps the instance matrix a translate-and-scale
  // and makes the orientation impossible for a caller to forget.
  //
  // Open-ended matters: a capped cylinder puts a lit disc on top of the beam,
  // and a disc is a hard edge exactly where ADR 0023 asks the light to
  // dissipate.
  const geometry = new CylinderGeometry(BEAM_RADIUS, BEAM_RADIUS, 1, 12, 1, true);
  geometry.rotateX(Math.PI / 2);

  const material = new ShaderMaterial({
    uniforms: { tint: { value: new Color(SIGNAL_COLOR) } },
    // `uv.y` runs 0 at the base of the cylinder to 1 at its top, which after
    // the rotation above is roof to sky. The alpha falls off over it, so the
    // column is brightest where it leaves the building and gone by the top —
    // "dissipating into the sky" as a gradient rather than as a length.
    vertexShader: `
      varying float vRise;
      void main() {
        vRise = uv.y;
        gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 tint;
      varying float vRise;
      void main() {
        // Squared rather than linear: a linear ramp still has visible light
        // most of the way up and reads as a solid shaft with a soft top.
        float fade = 1.0 - vRise;
        gl_FragColor = vec4(tint, fade * fade * 0.55);
      }
    `,
    transparent: true,
    // Additive, so a beam brightens whatever it passes through rather than
    // occluding it — and no depth write, or the invisible far side of the
    // column would hide the beacons standing inside it.
    blending: AdditiveBlending,
    depthWrite: false,
    side: DoubleSide,
  });

  const mesh = new InstancedMesh(geometry, material, MAX_ROOF_BEAMS);
  mesh.instanceMatrix.setUsage(DynamicDrawUsage);
  mesh.count = 0;
  // The beams are positioned in scene metres and the whole scene is transformed
  // by the layer's anchor matrix each frame, so three's own culling — which
  // works from a bounding sphere computed in local space — would cull them at
  // arbitrary camera angles. The same setting every mesh in this directory
  // carries, for the same reason.
  mesh.frustumCulled = false;

  const scratch = new Object3D();
  /** Heights as written, so a test can ask what the buffer holds. */
  let heights: number[] = [];

  return {
    mesh,

    set(buildings) {
      const drawn = Math.min(buildings.length, MAX_ROOF_BEAMS);
      heights = [];

      for (let index = 0; index < drawn; index += 1) {
        const building = buildings[index]!;
        scratch.position.set(
          building.x,
          building.y,
          // Half a beam above the roof. The geometry is centred on its own
          // origin, so placing it *at* the roof would sink half the column
          // into the building — a shaft of light through thirty floors, which
          // reads as a rendering fault rather than as a mark.
          building.roofAltitude + building.beamHeight / 2,
        );
        scratch.scale.set(1, 1, building.beamHeight);
        scratch.updateMatrix();
        mesh.setMatrixAt(index, scratch.matrix);
        heights.push(building.beamHeight);
      }

      // Set *after* writing, and the count is what stops the stale matrices
      // past it from being drawn. Every instanced mesh in this directory has
      // the same trap: shrink the city and the old buffer still holds a beam
      // over a building nobody is hiring in any more.
      mesh.count = drawn;
      mesh.instanceMatrix.needsUpdate = true;
    },

    get drawn() {
      return mesh.count;
    },

    matrixAt(index) {
      if (index < 0 || index >= mesh.count) return null;
      const matrix = new Matrix4();
      mesh.getMatrixAt(index, matrix);
      return matrix;
    },

    heightAt(index) {
      return heights[index] ?? null;
    },

    dispose() {
      geometry.dispose();
      material.dispose();
      mesh.dispose();
      heights = [];
    },
  };
}
