/**
 * Three.js drawing into MapLibre's WebGL context, as one custom layer.
 *
 * `city.md` §5.1 calls this the single most consequential technical decision in
 * M4 and asks for an ADR; it is ADR 0025. The short version: MapLibre owns the
 * projection, the camera, the basemap and the building extrusion, and Three.js
 * draws the signal layers **into MapLibre's own context** rather than onto a
 * second canvas stacked over it. One context, one camera, one depth buffer —
 * two stacked canvases would drift out of register on every gesture and would
 * share no depth, so a beacon could not be occluded by a building in front of
 * it, and occlusion is most of what makes a scene read as three-dimensional.
 *
 * **Scene coordinates are metres, relative to a fixed anchor.** Mercator units
 * are a fraction of the world and vary in metres-per-unit with latitude, which
 * makes every number in the layout code a quantity nobody can check by eye. The
 * anchor transform below converts the whole scene once per frame instead, so
 * `unresolvedField.ts` can say "700 metres up" and mean it.
 *
 * **No React, and no per-frame component.** Zustand holds the scene state and
 * this reads it directly; `CLAUDE.md` §8 names one-object-per-job and a
 * component re-rendering per frame as anti-patterns, and §5.5 asks for one
 * geometry, one draw call and N transforms. A filter change updates an instance
 * buffer — it does not rebuild a scene and it does not touch a component tree.
 *
 * **It repaints only when there is a reason to.** `map.triggerRepaint()` in the
 * render method is how every Three-in-MapLibre example animates, and it is also
 * how a map pins a core at 60fps forever with nothing moving on it. This asks
 * for the next frame only while something is actually animating, and under
 * `prefers-reduced-motion` nothing ever is.
 */

// Types only — erased at build time. The *value* side of `maplibre-gl` is
// deliberately not imported here; see `mercator.ts` for what that costs and why
// the projection is written out instead.
import type {
  CustomLayerInterface,
  CustomRenderMethodInput,
  Map as MapLibreMap,
} from 'maplibre-gl';
import {
  AdditiveBlending,
  Camera,
  Color,
  InstancedMesh,
  Matrix4,
  MeshBasicMaterial,
  OctahedronGeometry,
  Object3D,
  Scene,
  Vector3,
  WebGLRenderer,
} from 'three';

import type { CitySignal } from '@/lib/schemas';

import { mercatorFromLngLat, metreInMercatorUnits } from './mercator';
import { arrangeUnresolved } from './unresolvedField';

/** The layer's id in the style, and the handle every test reaches for. */
export const SIGNAL_LAYER_ID = 'nightshift-signals';

/**
 * `signal-400`, the cyan the whole encoding is built on.
 *
 * Duplicated out of `globals.css` for the same reason `MAP_PALETTE` is — a
 * WebGL material cannot read a CSS custom property — and checked against the
 * stylesheet by `signalLayer.test.ts` rather than hoped for.
 */
export const SIGNAL_COLOR = '#5ce8ff';

/**
 * Half-height of one beacon in metres.
 *
 * Large, and deliberately: these are read from a camera kilometres away at a
 * 76° pitch, where a marker sized like a map pin is a single pixel. This is
 * roughly a twelve-storey building, which is the smallest thing that reads at
 * this range at all.
 */
const BEACON_RADIUS = 34;

/**
 * The most beacons this layer will allocate room for.
 *
 * An `InstancedMesh` allocates its buffers once at its declared count, so this
 * is a real ceiling rather than a hint. It matches `MAX_SIGNALS` on the API,
 * which is the most the endpoint will ever send.
 */
export const MAX_BEACONS = 5_000;

export interface SignalLayerOptions {
  /** Scene origin. Everything is metres from here. */
  readonly anchor: readonly [number, number];
}

/**
 * Deliberately absent: a `reducedMotion` flag.
 *
 * Nothing in this layer animates yet, so a knob honouring the preference would
 * be a knob that does nothing — a setting that looks like a feature, which is
 * what I7 is about. It arrives with the §6 pulses that need it, and the camera
 * controller already honours the preference for everything that moves today.
 */

/**
 * What the layer exposes beyond MapLibre's own interface.
 *
 * Narrow on purpose. The only thing outside this file that may change what is
 * drawn is the set of signals.
 */
export interface SignalLayer extends CustomLayerInterface {
  /** Rebuild the instance buffer. Cheap enough to call on every data change. */
  setSignals(signals: readonly CitySignal[]): void;
  /** How many beacons the last `setSignals` actually drew. */
  readonly drawn: number;
  /**
   * The altitude, in metres, of one instance **as the buffer holds it**.
   *
   * Read back rather than recomputed, which is the point: `arrangeUnresolved`
   * already has a test saying what altitude it produces, and repeating that
   * sum here would assert the field agrees with itself. This asks the mesh
   * what was actually written, so a transform that mirrored or mis-scaled the
   * whole field — which still produces the right *number* of beacons, in
   * entirely the wrong place — has somewhere to be caught.
   */
  altitudeOf(index: number): number | null;
}

/**
 * Metres-from-anchor to MapLibre's mercator world space.
 *
 * The `-scale` on the second axis is not a typo and is the thing that goes
 * wrong silently: mercator y grows *southward* while the field's y is metres
 * north, so without the flip the whole field appears mirrored about the anchor
 * — which still looks like a plausible arrangement, which is why it is worth a
 * sentence here.
 */
export function anchorTransform(anchor: readonly [number, number]): Matrix4 {
  const [lng, lat] = anchor;
  const origin = mercatorFromLngLat(lng, lat);
  const scale = metreInMercatorUnits(lat);
  return new Matrix4()
    .makeTranslation(origin.x, origin.y, 0)
    .scale(new Vector3(scale, -scale, scale));
}

export function createSignalLayer(options: SignalLayerOptions): SignalLayer {
  const scene = new Scene();
  const camera = new Camera();
  const transform = anchorTransform(options.anchor);

  // One geometry, one material, one mesh, N transforms — §5.5. An octahedron
  // reads as a signal rather than as a pin, and eight faces is cheap enough
  // that the instance count is what costs, not the geometry.
  const geometry = new OctahedronGeometry(BEACON_RADIUS, 0);
  const material = new MeshBasicMaterial({
    color: new Color(SIGNAL_COLOR),
    transparent: true,
    opacity: 0.85,
    // Additive, so overlapping beacons brighten instead of flattening into one
    // silhouette — a stack of roles at one employer should read as a stack.
    blending: AdditiveBlending,
    // Written depth from an additive, transparent mesh occludes the beacons
    // behind it with an invisible surface. Reading depth is still on, which is
    // the half that matters: a building in front of a beacon still hides it.
    depthWrite: false,
  });

  const mesh = new InstancedMesh(geometry, material, MAX_BEACONS);
  mesh.frustumCulled = false;
  mesh.count = 0;
  scene.add(mesh);

  let renderer: WebGLRenderer | null = null;
  let map: MapLibreMap | null = null;
  let drawn = 0;

  const scratch = new Object3D();

  const layer: SignalLayer = {
    id: SIGNAL_LAYER_ID,
    type: 'custom',
    // '3d' rather than '2d': it puts this layer after the extrusions with the
    // depth buffer live, which is the whole reason for sharing a context.
    renderingMode: '3d',

    get drawn() {
      return drawn;
    },

    altitudeOf(index) {
      if (index < 0 || index >= drawn) return null;
      const matrix = new Matrix4();
      mesh.getMatrixAt(index, matrix);
      // Element 14 of a column-major 4×4 is the z translation, and the scene's
      // z is metres above the anchor's ground plane.
      return matrix.elements[14] ?? null;
    },

    setSignals(signals) {
      const field = arrangeUnresolved(signals);
      const count = Math.min(field.placements.length, MAX_BEACONS);

      for (let i = 0; i < count; i += 1) {
        const placement = field.placements[i];
        if (!placement) break;
        scratch.position.set(placement.x, placement.y, placement.altitude);
        scratch.updateMatrix();
        mesh.setMatrixAt(i, scratch.matrix);
      }

      mesh.count = count;
      mesh.instanceMatrix.needsUpdate = true;
      drawn = count;
      map?.triggerRepaint();
    },

    onAdd(addedMap, gl) {
      map = addedMap;
      // The renderer shares MapLibre's canvas *and* its context. Passing the
      // canvas without the context makes Three create a second one, and the
      // browser then hands back a canvas that already has a context — the
      // failure is a blank layer with no error.
      renderer = new WebGLRenderer({
        canvas: addedMap.getCanvas(),
        context: gl,
        antialias: true,
      });
      // MapLibre has already drawn the city into this buffer. Clearing would
      // erase it and leave beacons floating on black.
      renderer.autoClear = false;
    },

    render(_gl: WebGLRenderingContext | WebGL2RenderingContext, args: CustomRenderMethodInput) {
      if (!renderer || mesh.count === 0) return;

      // MapLibre hands over the matrix that takes mercator world space to clip
      // space; the anchor transform takes metres to mercator. Composed, they
      // take the scene straight to the screen, so the Three camera needs no
      // position, no orientation and no field of view of its own — MapLibre's
      // camera is the only camera, which is what "one camera" means.
      //
      // **`defaultProjectionData.mainMatrix`, not `modelViewProjectionMatrix`.**
      // Both are on the render argument, both are 4×4, and both typecheck. They
      // are in different spaces: `mainMatrix` takes spherical mercator 0..1,
      // which is what `MercatorCoordinate` produces and what this scene is
      // anchored in, while `modelViewProjectionMatrix` is MapLibre's internal
      // world space. Measured with the anchor point at the opening pose:
      // `mainMatrix` puts it at clip x ≈ 0, y = 0.41 — centre frame — and
      // `modelViewProjectionMatrix` at x = -3.02, three screens off to the left.
      //
      // The failure is silent and total. Every count is right, the layer is in
      // the style, the buffer is full, and the canvas shows nothing at all —
      // which reads as "the beacons are not drawing" rather than "the beacons
      // are drawing somewhere else", and sends you looking at the material.
      camera.projectionMatrix = new Matrix4()
        .fromArray(args.defaultProjectionData.mainMatrix as unknown as number[])
        .multiply(transform);

      // Three and MapLibre each cache what they believe the GL state to be, and
      // they are both wrong after the other has drawn. This is the line whose
      // absence produces a correct scene rendered with somebody else's blend
      // mode.
      renderer.resetState();
      renderer.render(scene, camera);

      // Deliberately *not* an unconditional `triggerRepaint()`. Nothing in this
      // layer animates yet, so asking for the next frame here would hold a core
      // at 60fps to redraw an identical image. When the §6 pulses arrive they
      // ask for their own frames, and under reduced motion they never will.
    },

    onRemove() {
      // Every one of these leaks GPU memory that outlives the page's own
      // teardown, and a context reaching the browser's limit fails to create
      // the *next* map with an error naming none of this.
      geometry.dispose();
      material.dispose();
      mesh.dispose();
      renderer = null;
      map = null;
    },
  };

  return layer;
}
