/**
 * The reticle: a ring drawn around whichever role is selected.
 *
 * **Why a ring, and why white, when §6 has already spent both.** §6's table
 * encodes *states of a role* — saved is a thin white outline, an exceptional
 * match is a gold beacon, an offer is a green core. Selection is not one of
 * those. It is a state of the *interface*: which role the panel on the right is
 * currently describing. Giving it a colour from that table would make the city
 * claim something about the job that is not true, and every remaining colour in
 * the palette is either already spoken for or reads as an error.
 *
 * So it is deliberately a different *kind* of mark. An annulus around the
 * beacon, touching nothing, reads as a cursor rather than as a property — the
 * same way a marquee around an icon is not a claim about the file. §6's white
 * outline is a thin line *on the body* of a saved beacon; this is a ring in the
 * air around it, at twice its radius, and the two are distinguishable at a
 * glance. Task 5 draws the §6 treatments and has to keep them so.
 *
 * **It faces the camera, and nothing here does that on its own.** ADR 0025
 * leaves no view matrix — MapLibre hands over one composed projection — so the
 * orientation is pushed in from the map's bearing and pitch, exactly as the
 * name plates do it, including the sign that had to be settled by rotating a
 * real map. A ring that is not oriented is not invisible: it lies flat over the
 * city and reads as a circle painted on the ground, which is the one thing an
 * unresolved role must never appear to be.
 */

import {
  AdditiveBlending,
  Color,
  DoubleSide,
  Euler,
  Mesh,
  MeshBasicMaterial,
  RingGeometry,
} from 'three';

/**
 * `paper`, the interface's own foreground colour, duplicated out of
 * `globals.css` for the same reason `SIGNAL_COLOR` is — a WebGL material cannot
 * read a CSS custom property — and checked against the stylesheet by
 * `selectionMesh.test.ts` rather than hoped for.
 */
export const SELECTION_COLOR = '#eaf1fa';

/**
 * The ring's radii in metres, around a column 9 m wide and 90 m tall.
 *
 * Clear of the *whole* body, not merely of its width — ADR 0034. A ring at
 * three times the column's radius would be a hoop around its middle, and the
 * interview arc is already a hoop around its middle at 23 m. ADR 0027's
 * standing requirement is that selection and the §6 treatments stay
 * distinguishable at a glance; two rings at similar radii are not.
 *
 * So it is sized against the column's *height* and encloses it end to end,
 * which keeps it clear of the arc by a factor of two and keeps its own
 * character — a thing in the air around the role, touching nothing.
 *
 * Large enough to survive the range this field is read at, too: the name
 * plates were sized 55 m, looked fine in a screenshot and were too small on a
 * screen, and this is read from the same kilometres away.
 */
export const SELECTION_INNER_RADIUS = 58;
export const SELECTION_OUTER_RADIUS = 72;

/**
 * How far up the column the reticle is centred, in metres.
 *
 * A beacon's anchor is now the *base* of its column rather than its middle, so
 * a ring drawn at the anchor would circle the roof the role stands on instead
 * of the role.
 */
export const SELECTION_LIFT = 45;

/** Which way a positive bearing turns the ring — see `labelMesh`'s `BEARING_SIGN`. */
const BEARING_SIGN = -1;

export interface SelectionMesh {
  readonly mesh: Mesh;
  /** Put the reticle at a point in scene metres, and show it. */
  moveTo(x: number, y: number, altitude: number): void;
  /** Nothing is selected: take it off the city entirely. */
  clear(): void;
  /** Turn it to face a camera at this bearing and pitch, in degrees. */
  orient(bearingDegrees: number, pitchDegrees: number): void;
  /** Is the reticle on the city? */
  readonly visible: boolean;
  /** Where it is, in scene metres, or null when nothing is selected. */
  readonly at: readonly [number, number, number] | null;
  dispose(): void;
}

export function createSelectionMesh(): SelectionMesh {
  const geometry = new RingGeometry(SELECTION_INNER_RADIUS, SELECTION_OUTER_RADIUS, 48);
  // Lifted here rather than at every call site: `moveTo` is handed a beacon's
  // anchor, and there is exactly one right offset from it.
  geometry.translate(0, 0, SELECTION_LIFT);
  const material = new MeshBasicMaterial({
    color: new Color(SELECTION_COLOR),
    transparent: true,
    opacity: 0.9,
    // Additive, like the beacons: the ring brightens whatever it crosses rather
    // than punching a grey hole in the stack behind it.
    blending: AdditiveBlending,
    // Visible from behind, so rotating the map past the ring does not lose it.
    side: DoubleSide,
    // Reads depth so a tower in front still hides it, writes none so its own
    // transparent interior does not occlude the beacon it is drawn around —
    // which would hide the very thing it is pointing at.
    depthWrite: false,
  });

  const mesh = new Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.visible = false;
  // After the beacons and before the plates: a name should still win, but the
  // reticle must not be lost inside the additive glow of the stack it marks.
  mesh.renderOrder = 1;

  let bearing = 0;
  let pitch = 0;
  let at: readonly [number, number, number] | null = null;

  function writeRotation(): void {
    // Tilt first, then spin about the world's up axis — 'XYZ' would apply the
    // spin in the ring's own tilted frame and skew it into an ellipse leaning
    // the wrong way as soon as the map is both pitched and rotated.
    mesh.rotation.copy(
      new Euler((pitch * Math.PI) / 180, 0, (BEARING_SIGN * bearing * Math.PI) / 180, 'ZYX'),
    );
    mesh.updateMatrix();
  }

  writeRotation();

  return {
    mesh,

    get visible() {
      return mesh.visible;
    },

    get at() {
      return at;
    },

    // Position only. The orientation belongs to `orient` and persists across a
    // move — re-applying it here looked prudent and was dead code: the layer
    // orients the reticle when the map is attached and on every move, so the
    // ring is always already facing the camera by the time anything selects a
    // role. Verified by deleting the call and finding nothing could fail.
    moveTo(x, y, altitude) {
      at = [x, y, altitude];
      mesh.position.set(x, y, altitude);
      mesh.visible = true;
    },

    clear() {
      at = null;
      mesh.visible = false;
    },

    orient(bearingDegrees, pitchDegrees) {
      if (bearingDegrees === bearing && pitchDegrees === pitch) return;
      bearing = bearingDegrees;
      pitch = pitchDegrees;
      writeRotation();
    },

    dispose() {
      geometry.dispose();
      material.dispose();
      at = null;
    },
  };
}
