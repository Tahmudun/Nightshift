/**
 * The four marks §6 puts *on* a beacon, each as one instanced mesh.
 *
 * `city.md` §6 gives a role's state a shape as well as a colour (§12.4: colour
 * never carries a meaning alone). Four of those shapes are geometry the beacon
 * itself cannot be — an outline around it, a core inside it, a ring about it, a
 * beam through it — and each is drawn as its own `InstancedMesh` for the reason
 * §5.5 gives: one geometry, one draw call, N transforms. Twenty saved roles are
 * twenty matrices in one buffer, not twenty objects.
 *
 * One factory rather than four modules, because the four differ only in their
 * geometry and material. What they share is the part that goes wrong: an
 * instance buffer that must be rewritten in full every time the field moves
 * under it. A mark written once at the moment a role was saved stays at the old
 * coordinates through the next sort and ends up decorating a different
 * employer's role — the same trap the reticle has, one mesh over.
 *
 * **The beam has a hard limit and it is an invariant, not a taste.** §4.8: the
 * unresolved field touches nothing, and "the absence of a ground connection is
 * the entire message". A gold shaft long enough to reach the street would draw
 * a line from a floating role to a building nobody confirmed — I1 broken by a
 * decoration. `BEAM_LENGTH` is checked against the field's altitude in the
 * tests rather than left as a number somebody might raise.
 */

import {
  AdditiveBlending,
  Color,
  CylinderGeometry,
  DoubleSide,
  Euler,
  InstancedMesh,
  MeshBasicMaterial,
  NormalBlending,
  Object3D,
  OctahedronGeometry,
  Quaternion,
  TorusGeometry,
  Vector3,
  type BufferGeometry,
} from 'three';

/** Half-height of one beacon, in metres. Duplicated from `signalLayer` would be
 * a second source of truth, so it is imported. */
import { BEACON_RADIUS } from './beacon';

/** The four shapes, and the whole of what this module can draw. */
export const MARK_KINDS = ['outline', 'core', 'ring', 'beam'] as const;
export type MarkKind = (typeof MARK_KINDS)[number];

/**
 * How tall the gold shaft is, in metres.
 *
 * Centred on the beacon, so it reaches half this far above and below. The field
 * base is 700 m and this is 460 m, which leaves the bottom of a beam on the
 * lowest role in a stack 470 m above the ground — clear of One World Trade
 * Center's 541 m only because the field itself is, and clear of the *street*
 * with room nobody can misread as a connection to it.
 */
export const BEAM_LENGTH = 460;

/**
 * How much of a circle the interview arc covers, in radians.
 *
 * Two thirds. Enough to read as a ring at a glance, open enough that its
 * rotation is visible — a closed circle spun about its own axis draws the same
 * pixels every frame.
 */
export const RING_ARC = (Math.PI * 4) / 3;

/** One mark: where it goes, what colour it is, and how big. */
export interface Mark {
  readonly x: number;
  readonly y: number;
  readonly z: number;
  /** Hex, from the palette. Per instance because one mesh serves two rows. */
  readonly tint: string;
  /**
   * Size multiplier on the kind's own geometry. Defaults to 1.
   *
   * Per instance for the same reason the tint is: the core mesh serves two
   * rows of §6 that want different sizes as well as different colours.
   * `applied` is "solid illuminated" and fills its beacon; `offer` is a *soft*
   * core and sits small inside it. One mesh, two readings.
   */
  readonly scale?: number;
}

export interface MarkMesh {
  readonly mesh: InstancedMesh;
  /** Rewrite the whole buffer. The only way marks change. */
  set(marks: readonly Mark[]): void;
  readonly drawn: number;
  /** Where instance `index` is, in scene metres, or null if nothing is there. */
  positionAt(index: number): readonly [number, number, number] | null;
  /** The colour instance `index` is drawn in, as hex, or null. */
  tintAt(index: number): string | null;
  /** The size multiplier instance `index` is drawn at, or null. */
  scaleAt(index: number): number | null;
  /**
   * Turn every mark. `spin` rotates about the mark's own axis (the ring's
   * animation); `bearing` and `pitch` face it at the camera, as the plates and
   * the reticle do.
   */
  orient(spin: number, bearingDegrees: number, pitchDegrees: number): void;
  /** The spin the buffer currently holds, in radians. */
  readonly spunTo: number;
  dispose(): void;
}

/** The shape each kind is drawn with. Exported so a test can require one. */
export function markGeometry(kind: MarkKind): BufferGeometry {
  switch (kind) {
    case 'outline':
      // Larger than the beacon, so the line sits *around* the body rather than
      // cutting through it, and drawn as wireframe by the material below.
      return new OctahedronGeometry(BEACON_RADIUS * 1.34, 0);
    case 'core':
      // Inside the beacon, and the beacon is additive — so a core reads as a
      // denser centre rather than as a second object.
      return new OctahedronGeometry(BEACON_RADIUS * 0.46, 0);
    case 'ring':
      // An **arc**, not a closed ring, and that is the difference between a
      // treatment and a decoration: §6 asks for a "rotating ring / orbiting
      // arcs", and a closed torus is rotationally symmetric about its own
      // axis — spinning it produces an identical image every frame. The first
      // version of this was a full circle and the animation was invisible by
      // construction, which no screenshot would ever have shown.
      return new TorusGeometry(BEACON_RADIUS * 1.7, BEACON_RADIUS * 0.09, 8, 36, RING_ARC);
    case 'beam': {
      // Three's cylinder runs along y; the scene's up is z. Rotated once here
      // rather than per instance, so the instance matrix stays a translation
      // and the orientation cannot be forgotten by a caller.
      const geometry = new CylinderGeometry(
        BEACON_RADIUS * 0.16,
        BEACON_RADIUS * 0.16,
        BEAM_LENGTH,
        10,
        1,
        true,
      );
      geometry.rotateX(Math.PI / 2);
      return geometry;
    }
  }
}

/** The material each kind is drawn with. */
export function markMaterial(kind: MarkKind): MeshBasicMaterial {
  const shared = {
    transparent: true,
    // Every one of these decorates a beacon, and a mark that wrote depth would
    // occlude the very thing it is pointing at with an invisible surface.
    depthWrite: false,
    side: DoubleSide,
  } as const;

  switch (kind) {
    case 'outline':
      // §6 asks for a *thin* outline. A filled shell at this size would read as
      // a larger beacon, which is what `applied` looks like.
      return new MeshBasicMaterial({ ...shared, wireframe: true, opacity: 0.9 });
    case 'core':
      // Normal, not additive: the core is the one mark that should read as
      // solid matter inside the glow rather than as more glow.
      return new MeshBasicMaterial({ ...shared, blending: NormalBlending, opacity: 0.95 });
    case 'ring':
      return new MeshBasicMaterial({ ...shared, blending: AdditiveBlending, opacity: 0.75 });
    case 'beam':
      // Faint, and additive, so a beam brightens the air it passes through
      // rather than drawing a solid gold bar over the city behind it.
      return new MeshBasicMaterial({ ...shared, blending: AdditiveBlending, opacity: 0.34 });
  }
}

export interface MarkMeshOptions {
  readonly kind: MarkKind;
  /** The buffer is allocated once at this size, so it is a real ceiling. */
  readonly capacity: number;
}

/** Which way a positive bearing turns a mark — see `labelMesh`'s `BEARING_SIGN`. */
const BEARING_SIGN = -1;

/**
 * The axis a mark spins about: its own normal, the one pointing at the viewer
 * once the billboard rotation has been applied.
 */
const SPIN_AXIS = new Vector3(0, 0, 1);

export function createMarkMesh({ kind, capacity }: MarkMeshOptions): MarkMesh {
  const geometry = markGeometry(kind);
  const material = markMaterial(kind);

  const mesh = new InstancedMesh(geometry, material, capacity);
  mesh.frustumCulled = false;
  mesh.count = 0;
  // After the beacons, so a mark is never lost inside the additive glow of the
  // body it decorates, and before the plates, which still win.
  mesh.renderOrder = 1;

  const scratch = new Object3D();
  const colour = new Color();
  /** Reused per rewrite rather than allocated per instance. */
  const billboard = new Quaternion();
  const own = new Quaternion();
  const facing = new Euler();

  let marks: readonly Mark[] = [];
  let spin = 0;
  let bearing = 0;
  let pitch = 0;

  /**
   * Write every instance matrix from the marks and the current angles.
   *
   * In full, every time, rather than patching the instances that moved: a mark
   * is only ever correct relative to the field it was placed against, and the
   * field is rebuilt whole on every sort. Partial updates are how a ring ends
   * up around the wrong employer's role.
   */
  function writeMatrices(): void {
    // Two rotations, composed in this order and not the other, and getting it
    // wrong is not subtle-but-invisible — it is visible and wrong.
    //
    // The first turns the mark to face the camera, exactly as the plates and
    // the reticle do, including the 'ZYX' order that keeps a pitched *and*
    // rotated map from leaning everything sideways.
    //
    // The second is the mark's own spin, and it must happen **in the mark's own
    // frame, after the billboard** — about the axis now pointing at the viewer.
    // Folding it into the billboard Euler as a y-rotation, which is what the
    // first version did, inserts it between the tilt and the turn and rolls the
    // arc out of the camera plane: on screen it stops being a ring around a
    // beacon and becomes a flat ellipse lying across it.
    billboard.setFromEuler(
      facing.set((pitch * Math.PI) / 180, 0, (BEARING_SIGN * bearing * Math.PI) / 180, 'ZYX'),
    );
    own.setFromAxisAngle(SPIN_AXIS, spin);
    billboard.multiply(own);

    for (let i = 0; i < mesh.count; i += 1) {
      const mark = marks[i];
      if (!mark) break;
      scratch.position.set(mark.x, mark.y, mark.z);
      scratch.quaternion.copy(billboard);
      scratch.scale.setScalar(mark.scale ?? 1);
      scratch.updateMatrix();
      mesh.setMatrixAt(i, scratch.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  }

  return {
    mesh,

    get drawn() {
      return mesh.count;
    },

    get spunTo() {
      return spin;
    },

    set(next) {
      marks = next.slice(0, capacity);
      mesh.count = marks.length;
      for (let i = 0; i < marks.length; i += 1) {
        const mark = marks[i];
        if (!mark) break;
        mesh.setColorAt(i, colour.set(mark.tint));
      }
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      writeMatrices();
    },

    positionAt(index) {
      const mark = marks[index];
      if (index < 0 || index >= mesh.count || mark === undefined) return null;
      return [mark.x, mark.y, mark.z];
    },

    tintAt(index) {
      if (index < 0 || index >= mesh.count) return null;
      if (!mesh.instanceColor) return null;
      mesh.getColorAt(index, colour);
      return `#${colour.getHexString()}`;
    },

    scaleAt(index) {
      if (index < 0 || index >= mesh.count) return null;
      return marks[index]?.scale ?? 1;
    },

    orient(nextSpin, bearingDegrees, pitchDegrees) {
      if (nextSpin === spin && bearingDegrees === bearing && pitchDegrees === pitch) return;
      spin = nextSpin;
      bearing = bearingDegrees;
      pitch = pitchDegrees;
      writeMatrices();
    },

    dispose() {
      geometry.dispose();
      material.dispose();
      mesh.dispose();
      marks = [];
    },
  };
}
