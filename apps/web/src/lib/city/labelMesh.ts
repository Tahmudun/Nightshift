/**
 * The name plates: one instanced quad per employer, all sampling one atlas.
 *
 * Split out of `signalLayer.ts` rather than added to it, because a custom layer
 * that owns a context, a scene, a beacon buffer, a texture, a shader and a
 * billboard calculation is the 400-line component of `CLAUDE.md` §8 wearing a
 * different hat. This file owns the plates and knows nothing about MapLibre.
 *
 * **Two things here are not obvious and both fail silently.**
 *
 * *The per-instance UV.* An `InstancedMesh` shares one geometry, so every plate
 * would sample the same rectangle of the atlas and all of them would read the
 * first company's name. `uvOffset`/`uvScale` are per-instance attributes and
 * the shader adds them to the geometry's own `uv`; that is the whole reason
 * this uses a `ShaderMaterial` rather than `MeshBasicMaterial`. Note that
 * `instanceMatrix`, `position`, `uv`, `projectionMatrix` and `modelViewMatrix`
 * are all declared by three.js itself for a non-raw `ShaderMaterial` —
 * redeclaring any of them is a compile error, and the shader below deliberately
 * declares only what three does not.
 *
 * *The billboard.* Nothing here faces the camera on its own. `Sprite` and
 * three's usual billboard trick both work off `modelViewMatrix`, and in this
 * architecture there is no view matrix to work off — MapLibre hands over one
 * composed projection and the three camera is an identity (see ADR 0025). So
 * the orientation is computed from the map's own bearing and pitch and written
 * into each instance matrix. A plate that is not oriented is not invisible; it
 * lies flat over the city like a sticker, which reads as a bug in the texture.
 */

import {
  CanvasTexture,
  DoubleSide,
  Euler,
  InstancedBufferAttribute,
  InstancedMesh,
  LinearFilter,
  NormalBlending,
  Object3D,
  PlaneGeometry,
  ShaderMaterial,
  Vector3,
} from 'three';
import type { Texture } from 'three';

import type { FieldColumn } from './unresolvedField';
import { CELL_HEIGHT, CELL_WIDTH, MAX_LABELS, paintAtlas, planAtlas } from './labelAtlas';

/**
 * Height of a name plate in metres, and the width that follows from the cell.
 *
 * 72 m is as large as the plate can be: the cell is 8:1, so the width is
 * 576 m and the columns are 620 m apart, and anything larger would reach into
 * the neighbouring employer's airspace and appear to label it. The tests
 * assert that relationship rather than the numbers, because the day someone
 * tightens the field is the day this silently starts mislabelling columns.
 *
 * It was 55 m for the first draft, which was legible in a screenshot and small
 * on a screen — these are read from kilometres away at 76° of pitch, and the
 * only honest way to size them was to look.
 */
export const LABEL_HEIGHT = 72;
export const LABEL_WIDTH = (LABEL_HEIGHT * CELL_WIDTH) / CELL_HEIGHT;

/**
 * Which way a positive bearing turns the plates.
 *
 * The scene reaches mercator space through a transform whose y is negated
 * (`anchorTransform`), and a negated axis reverses the apparent direction of
 * every rotation about z. Deriving the sign on paper through that mirror is
 * how you get plates that face the camera at bearing 0 and turn the wrong way
 * as soon as the map is rotated — which looks correct in every screenshot
 * taken from the opening pose. It was settled by rotating a real map instead.
 */
const BEARING_SIGN = -1;

export interface LabelMesh {
  readonly mesh: InstancedMesh;
  /** Rebuild the plates. Repaints the atlas, so not a per-frame call. */
  setColumns(columns: readonly FieldColumn[], colour: string): void;
  /** Turn every plate to face a camera at this bearing and pitch, in degrees. */
  orient(bearingDegrees: number, pitchDegrees: number): void;
  /** How many plates are drawn. */
  readonly drawn: number;
  /**
   * The camera angles the plates are currently turned to, in degrees.
   *
   * Exposed because "the plates stopped reorienting" is invisible: they stay
   * on their columns, keep their names, and simply face the wrong way, which
   * reads as a texture problem rather than as a listener that never fired. It
   * is the same class of failure as attaching the layer to `load` — the bug
   * M4b already paid for once.
   */
  readonly orientedTo: { readonly bearing: number; readonly pitch: number };
  /** Employers past the atlas ceiling, which have no plate at all. */
  readonly unlabelled: number;
  dispose(): void;
}

export function createLabelMesh(): LabelMesh {
  // A 1×1 plane scaled per instance, rather than a plane sized in metres: the
  // instance matrix has to carry a scale anyway to billboard, so baking the
  // size into the geometry would just be a second place for it to live.
  const geometry = new PlaneGeometry(1, 1);

  const uvOffset = new InstancedBufferAttribute(new Float32Array(MAX_LABELS * 2), 2);
  const uvScale = new InstancedBufferAttribute(new Float32Array(MAX_LABELS * 2), 2);
  geometry.setAttribute('uvOffset', uvOffset);
  geometry.setAttribute('uvScale', uvScale);

  const material = new ShaderMaterial({
    uniforms: { atlas: { value: null as Texture | null } },
    vertexShader: /* glsl */ `
      attribute vec2 uvOffset;
      attribute vec2 uvScale;
      varying vec2 vUv;

      void main() {
        vUv = uvOffset + uv * uvScale;
        gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform sampler2D atlas;
      varying vec2 vUv;

      void main() {
        vec4 texel = texture2D(atlas, vUv);
        // Discard rather than blend the empty parts of a cell. A transparent
        // fragment still writes nothing here, but discarding keeps the plate's
        // silhouette out of the depth test for anything drawn after it.
        if (texel.a < 0.02) discard;
        gl_FragColor = texel;
      }
    `,
    transparent: true,
    // Normal, not additive. The plates carry a dark halo so a name stays
    // readable against a lit tower, and additive blending would erase exactly
    // that halo — the darker the halo, the less it would contribute.
    blending: NormalBlending,
    // Readable from behind, so a plate does not vanish when the map is rotated
    // past it.
    side: DoubleSide,
    // **Writes depth, unlike the beacons.** The usual rule for a transparent
    // material is not to, because its invisible corners then occlude whatever
    // is drawn after it — but this shader `discard`s those fragments, so they
    // never reach the depth buffer and only the glyphs themselves write. What
    // that buys is the thing depth is for: with `depthWrite: false` the plates
    // paint in instance order, so an employer at the back of the field can
    // draw its name over one at the front. Seen at bearing 90°, where the
    // columns line up and three names overlapped in the wrong order.
    depthWrite: true,
  });

  const mesh = new InstancedMesh(geometry, material, MAX_LABELS);
  mesh.frustumCulled = false;
  mesh.count = 0;
  // Drawn after the beacons, so a plate is never hidden by the stack it names.
  mesh.renderOrder = 1;

  let texture: CanvasTexture | null = null;
  let drawn = 0;
  let unlabelled = 0;
  /** Where each plate hangs. Kept because `orient` rebuilds the matrices. */
  let anchors: Vector3[] = [];
  let bearing = 0;
  let pitch = 0;

  const scratch = new Object3D();

  function writeMatrices(): void {
    // One rotation for every plate: they all face the same camera, so this is
    // computed once and reused rather than per instance.
    const rotation = new Euler(
      (pitch * Math.PI) / 180,
      0,
      (BEARING_SIGN * bearing * Math.PI) / 180,
      // Tilt first, then spin about the world's up axis. 'XYZ' would apply the
      // spin in the plate's own tilted frame and lean every name sideways as
      // soon as the map is both pitched and rotated.
      'ZYX',
    );

    for (let i = 0; i < drawn; i += 1) {
      const anchor = anchors[i];
      if (!anchor) break;
      scratch.position.copy(anchor);
      scratch.rotation.copy(rotation);
      scratch.scale.set(LABEL_WIDTH, LABEL_HEIGHT, 1);
      scratch.updateMatrix();
      mesh.setMatrixAt(i, scratch.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  }

  return {
    mesh,

    get drawn() {
      return drawn;
    },

    get unlabelled() {
      return unlabelled;
    },

    get orientedTo() {
      return { bearing, pitch };
    },

    setColumns(columns, colour) {
      const plan = planAtlas(columns.length);
      drawn = plan.drawn;
      unlabelled = plan.dropped;

      const canvas = paintAtlas(
        columns.slice(0, drawn).map((column) => column.name),
        colour,
      );

      texture?.dispose();
      texture = null;
      if (canvas) {
        texture = new CanvasTexture(canvas);
        // Linear rather than mipmapped: a mipmapped atlas bleeds one cell's
        // pixels into its neighbour at distance, which shows up as a ghost of
        // another company's name under this one.
        texture.minFilter = LinearFilter;
        texture.magFilter = LinearFilter;
        texture.generateMipmaps = false;
        texture.needsUpdate = true;
      }
      material.uniforms.atlas!.value = texture;

      anchors = [];
      plan.cells.forEach((cell, index) => {
        const column = columns[index];
        if (!column) return;
        anchors.push(new Vector3(column.x, column.y, column.labelAltitude));
        uvOffset.setXY(index, cell.u, cell.v);
        uvScale.setXY(index, cell.uw, cell.vh);
      });
      uvOffset.needsUpdate = true;
      uvScale.needsUpdate = true;

      mesh.count = drawn;
      writeMatrices();
    },

    orient(bearingDegrees, pitchDegrees) {
      // Cheap enough to call per frame, but it is called on move rather than
      // on render, so a still map costs nothing at all.
      if (bearingDegrees === bearing && pitchDegrees === pitch) return;
      bearing = bearingDegrees;
      pitch = pitchDegrees;
      writeMatrices();
    },

    dispose() {
      geometry.dispose();
      material.dispose();
      mesh.dispose();
      texture?.dispose();
      texture = null;
      anchors = [];
    },
  };
}
