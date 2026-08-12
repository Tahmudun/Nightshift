/**
 * The beacons themselves: one instanced octahedron, and the four things §6 lets
 * a role change about its own body.
 *
 * Split out of `signalLayer.ts` when the §6 treatments arrived, for the reason
 * `labelMesh.ts` was: a custom layer that owns a context, a beacon buffer, a
 * shader, four mark meshes, an atlas and a reticle is `CLAUDE.md` §8's
 * 400-line component wearing a different hat. This file owns the bodies and
 * knows nothing about MapLibre.
 *
 * **Why a shader, when the beacons used a `MeshBasicMaterial` for two tasks.**
 * §6 gives different roles different colours, different strengths and different
 * pulse rates, and a material carries exactly one of each for the whole mesh.
 * The alternative to per-instance attributes is one mesh per state, which is
 * one draw call per state and a new mesh every time §6 grows a row.
 *
 * **The pulse is not the only thing that says "new".** `prefers-reduced-motion`
 * turns every pulse off, and a treatment that is motion alone disappears
 * entirely for the people who asked for less of it. So a new role is also drawn
 * larger — `NEW_SCALE` — which survives with the animation switched off, and
 * the roster and the legend name it in words besides.
 */

import {
  AdditiveBlending,
  Color,
  InstancedBufferAttribute,
  InstancedMesh,
  Object3D,
  OctahedronGeometry,
  ShaderMaterial,
} from 'three';

/**
 * `signal-400`, the cyan the whole encoding is built on.
 *
 * Duplicated out of `globals.css` because a WebGL material cannot read a CSS
 * custom property, and checked against the stylesheet by `beacon.test.ts`
 * rather than hoped for.
 */
export const SIGNAL_COLOR = '#5ce8ff';

/**
 * `ink-450`, for a rejected or withdrawn role.
 *
 * §6 is explicit that this is *not* a red fracture: this tool is opened daily
 * during a job search, and accumulating red across the skyline makes it worse
 * to use over exactly the period it is needed most. The ink family is the one
 * that carries no meaning of its own, which is what "dim neutral" needs.
 */
export const ARCHIVED_COLOR = '#56698f';

/**
 * Half-height of one beacon in metres.
 *
 * Large, and deliberately: these are read from a camera kilometres away at a
 * 76° pitch, where a marker sized like a map pin is a single pixel. This is
 * roughly a twelve-storey building, which is the smallest thing that reads at
 * this range at all.
 *
 * Exported for the marks that surround it and for the selection reticle's
 * radii, so those are asserted against this rather than against a number
 * somebody copied — a ring drawn inside the beacon is a ring nobody can see.
 */
export const BEACON_RADIUS = 34;

/**
 * The most beacons this mesh will allocate room for.
 *
 * An `InstancedMesh` allocates its buffers once at its declared count, so this
 * is a real ceiling rather than a hint. It matches `MAX_SIGNALS` on the API,
 * which is the most the endpoint will ever send.
 */
export const MAX_BEACONS = 5_000;

/**
 * How fast each §6 pulse runs, in Hz.
 *
 * Both are far below WCAG 2.3.1's three-flashes-a-second threshold, and the
 * test pins that — "make the new ones more obvious" is the most natural change
 * anyone will ever make to this file, and the natural way to make it is to
 * raise these numbers.
 */
export const PULSE_HZ = { none: 0, slow: 0.28, rapid: 0.75 } as const;

/**
 * What a dimmed role's strength is multiplied by.
 *
 * §6: reduced opacity for a stale or unverified listing, and explicitly "not a
 * glitch — a glitch reads as a bug, gets reported as one, and then gets
 * ignored". So it dims to something clearly still there. A role faded to
 * nothing would be indistinguishable from one that had closed, which is the
 * exact confusion I3 exists to prevent.
 */
export const DIM_FACTOR = 0.45;

/** How much larger a new role is drawn, before any pulse. */
export const NEW_SCALE = 1.22;

/** One beacon, as the buffer holds it. */
export interface Beacon {
  readonly x: number;
  readonly y: number;
  readonly z: number;
  readonly tint: string;
  /** Strength before the pulse. Dimming is already applied by the caller. */
  readonly alpha: number;
  /** Hz. Zero means still, and a buffer of zeroes means no repaints at all. */
  readonly pulse: number;
  /** Base size multiplier — `NEW_SCALE` for a new role, 1 otherwise. */
  readonly scale: number;
}

export interface BeaconMesh {
  readonly mesh: InstancedMesh;
  set(beacons: readonly Beacon[]): void;
  readonly drawn: number;
  /** Move the shader's clock, in seconds. The only per-frame call. */
  tick(seconds: number): void;
  /** The clock the buffer currently holds. */
  readonly timeAt: number;
  /** Is anything in this buffer moving? What decides whether to ask for a frame. */
  readonly animating: boolean;
  tintAt(index: number): string | null;
  alphaAt(index: number): number | null;
  pulseAt(index: number): number | null;
  scaleAt(index: number): number | null;
  /** The altitude the *matrix* holds, not the one that was handed in. */
  altitudeAt(index: number): number | null;
  dispose(): void;
}

export function createBeaconMesh(capacity: number = MAX_BEACONS): BeaconMesh {
  // One geometry, one material, one mesh, N transforms — §5.5. An octahedron
  // reads as a signal rather than as a pin, and eight faces is cheap enough
  // that the instance count is what costs, not the geometry.
  const geometry = new OctahedronGeometry(BEACON_RADIUS, 0);

  const tint = new InstancedBufferAttribute(new Float32Array(capacity * 3), 3);
  const alpha = new InstancedBufferAttribute(new Float32Array(capacity), 1);
  const pulse = new InstancedBufferAttribute(new Float32Array(capacity), 1);
  geometry.setAttribute('tint', tint);
  geometry.setAttribute('alpha', alpha);
  geometry.setAttribute('pulse', pulse);

  const material = new ShaderMaterial({
    uniforms: { time: { value: 0 } },
    // `instanceMatrix`, `position`, `projectionMatrix` and `modelViewMatrix`
    // are declared by three itself for a non-raw `ShaderMaterial` —
    // redeclaring any of them is a compile error, so this declares only what
    // three does not.
    vertexShader: /* glsl */ `
      uniform float time;
      attribute vec3 tint;
      attribute float alpha;
      attribute float pulse;
      varying vec3 vTint;
      varying float vAlpha;

      void main() {
        // A pulse of zero must be perfectly still, not slow: 'new' is a claim
        // about a role and a beacon that breathes at 0 Hz would make every
        // role look new.
        float wave = pulse > 0.0 ? 0.5 + 0.5 * sin(time * pulse * 6.28318530718) : 1.0;
        vTint = tint;
        // Never below half strength. A beacon that blinks out is a role that
        // appears to have closed, twice a second.
        vAlpha = alpha * mix(0.55, 1.0, wave);
        // The body swells with the pulse as well as brightening. Brightness
        // alone is nearly invisible at the range this field is read from.
        vec3 swollen = position * mix(0.92, 1.08, wave);
        gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(swollen, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec3 vTint;
      varying float vAlpha;

      void main() {
        gl_FragColor = vec4(vTint, vAlpha);
      }
    `,
    transparent: true,
    // Additive, so overlapping beacons brighten instead of flattening into one
    // silhouette — a stack of roles at one employer should read as a stack.
    blending: AdditiveBlending,
    // Written depth from an additive, transparent mesh occludes the beacons
    // behind it with an invisible surface. Reading depth is still on, which is
    // the half that matters: a building in front of a beacon still hides it.
    depthWrite: false,
  });

  const mesh = new InstancedMesh(geometry, material, capacity);
  mesh.frustumCulled = false;
  mesh.count = 0;

  const scratch = new Object3D();
  const colour = new Color();

  let drawn = 0;
  let animating = false;
  let scales: number[] = [];

  return {
    mesh,

    get drawn() {
      return drawn;
    },

    get animating() {
      return animating;
    },

    get timeAt() {
      return material.uniforms.time?.value as number;
    },

    set(beacons) {
      const count = Math.min(beacons.length, capacity);
      animating = false;
      scales = [];

      for (let i = 0; i < count; i += 1) {
        const item = beacons[i];
        if (!item) break;
        scratch.position.set(item.x, item.y, item.z);
        scratch.scale.setScalar(item.scale);
        scratch.updateMatrix();
        mesh.setMatrixAt(i, scratch.matrix);

        colour.set(item.tint);
        tint.setXYZ(i, colour.r, colour.g, colour.b);
        alpha.setX(i, item.alpha);
        pulse.setX(i, item.pulse);
        scales.push(item.scale);
        if (item.pulse > 0) animating = true;
      }

      mesh.count = count;
      mesh.instanceMatrix.needsUpdate = true;
      tint.needsUpdate = true;
      alpha.needsUpdate = true;
      pulse.needsUpdate = true;
      // three caches the bounding sphere on first raycast and gates every later
      // one on it, so a field that grows keeps a sphere too small to admit its
      // new columns — and picking silently stops working for exactly the
      // employers that just arrived. `pick.test.ts` demonstrates it.
      mesh.boundingSphere = null;
      drawn = count;
    },

    tick(seconds) {
      if (material.uniforms.time) material.uniforms.time.value = seconds;
    },

    tintAt(index) {
      if (index < 0 || index >= drawn) return null;
      colour.setRGB(tint.getX(index), tint.getY(index), tint.getZ(index));
      return `#${colour.getHexString()}`;
    },

    alphaAt(index) {
      if (index < 0 || index >= drawn) return null;
      return alpha.getX(index);
    },

    pulseAt(index) {
      if (index < 0 || index >= drawn) return null;
      return pulse.getX(index);
    },

    scaleAt(index) {
      if (index < 0 || index >= drawn) return null;
      return scales[index] ?? null;
    },

    altitudeAt(index) {
      if (index < 0 || index >= drawn) return null;
      const matrix = mesh.matrix.clone();
      mesh.getMatrixAt(index, matrix);
      // Element 14 of a column-major 4×4 is the z translation, and the scene's
      // z is metres above the anchor's ground plane.
      return matrix.elements[14] ?? null;
    },

    dispose() {
      geometry.dispose();
      material.dispose();
      mesh.dispose();
      scales = [];
    },
  };
}
