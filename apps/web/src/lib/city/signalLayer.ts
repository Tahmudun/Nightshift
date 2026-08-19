/**
 * Three.js drawing into MapLibre's WebGL context, as one custom layer.
 *
 * `city.md` §5.1 calls this the single most consequential technical decision in
 * M4 and asks for an ADR; it is ADR 0025. The short version: MapLibre owns the
 * projection, the camera and the basemap, and Three.js draws everything above
 * it **into MapLibre's own context** rather than onto a second canvas stacked
 * over it. One context, one camera, one depth buffer — two stacked canvases
 * would drift out of register on every gesture and would share no depth, so a
 * beacon could not be occluded by a building in front of it, and occlusion is
 * most of what makes a scene read as three-dimensional.
 *
 * **Since ADR 0031 the buildings are here too.** MapLibre used to own the
 * skyline as well, as a `fill-extrusion`; it is now `cityBuildings.ts` in this
 * scene, for the reason that decision spells out at length — an extrusion's one
 * expressive channel is a colour ramp, and everything the reference images
 * build a tower out of is beyond it. So this file's scene is the whole visible
 * city, not just what is floating over it.
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
import { Camera, Matrix4, Scene, Vector3, WebGLRenderer } from 'three';

import { cameraDistanceMetres, HAZE_CAMERA_DISTANCES } from '@/lib/map/skyLayer';
import type { CitySignal } from '@/lib/schemas';

import {
  ARCHIVED_COLOR,
  COLUMN_HEIGHT,
  COLUMN_RADIUS,
  createBeaconMesh,
  DIM_FACTOR,
  MAX_BEACONS,
  NEW_SCALE,
  PULSE_HZ,
  SIGNAL_COLOR,
  type Beacon,
} from './beacon';
import { createBloom, type Bloom } from './bloom';
import { createLabelMesh } from './labelMesh';
import { createMarkMesh, MARK_KINDS, type Mark, type MarkKind } from './markMesh';
import { mercatorFromLngLat, metreInMercatorUnits } from './mercator';
import { pickInstance, sceneRayFromPointer, type PointerPoint, type Viewport } from './pick';
import { createSelectionMesh } from './selectionMesh';
import type { SignalTreatment } from './treatments';
import { arrangeOnBuildings, type HiringBuilding } from './buildingField';
import type { TileFootprint } from './buildingGeometry';
import { cameraPositionFrom, createCityBuildings } from './cityBuildings';
import { createRoofBeamMesh } from './roofBeamMesh';
import {
  arrangeUnresolved,
  type FieldColumn,
  type FieldPlacement,
  type FieldSort,
} from './unresolvedField';

/**
 * Do two roof-height lookups say the same thing?
 *
 * By value rather than by reference, because `refreshRoofHeights` builds a
 * fresh `Map` from the same tiles on every camera settle and would otherwise
 * look like a change every single time.
 */
function sameHeights(
  a: ReadonlyMap<string, number> | undefined,
  b: ReadonlyMap<string, number>,
): boolean {
  if (a === undefined) return false;
  if (a.size !== b.size) return false;
  for (const [bin, metres] of b) if (a.get(bin) !== metres) return false;
  return true;
}

/** The layer's id in the style, and the handle every test reaches for. */
export const SIGNAL_LAYER_ID = 'nightshift-signals';

// Re-exported rather than moved-and-forgotten: these lived here for two tasks
// and `beacon.ts` is where they belong now, but every caller that had the old
// import is still right about what it wanted.
export { COLUMN_HEIGHT, COLUMN_RADIUS, MAX_BEACONS, SIGNAL_COLOR };

/**
 * `verdant-400` — an offer, and nothing else in the product (§6).
 *
 * Duplicated out of `globals.css` for the same reason the cyan is, and checked
 * against the stylesheet rather than hoped for.
 */
export const OFFER_COLOR = '#5cf0a8';

/** `gold-400` — an exceptional match or an urgent deadline. */
export const URGENT_COLOR = '#ffcf5c';

/**
 * `paper` — a saved role's thin outline, and §6's word for it is *white*.
 *
 * This is the same value the selection reticle uses, and that collision is
 * deliberate rather than overlooked: ADR 0027 left a standing instruction that
 * if the two stop being distinguishable, **the reticle changes shape — §6 is
 * the spec and the reticle is not**. They are distinguishable by what they are
 * rather than by colour. The outline is a wireframe on the beacon's own body at
 * 46 m; the reticle is a camera-facing annulus in the air around it at 62–78 m,
 * touching nothing. One is a property of the role, the other is a cursor.
 *
 * The first draft of this drew the outline in cyan, which would have been the
 * one thing that note rules out.
 */
export const SAVED_COLOR = '#eaf1fa';

/**
 * How much of the beacon's body an applied role's core fills.
 *
 * The core geometry is 0.46 of the body, so this brings it to roughly
 * three-quarters — filled, not decorated. An offer keeps the default 1, which
 * is §6's word for it: a *soft* core.
 */
const APPLIED_CORE_SCALE = 1.6;

/**
 * How many marks the layer allocates room for, per kind.
 *
 * Far below `MAX_BEACONS`, and on purpose: these decorate roles you have a
 * relationship with or that the ranker singled out. A person with five hundred
 * live applications has a different problem than this ceiling.
 */
export const MAX_MARKS = 500;

/**
 * How fast the assessment/interview ring turns, in full turns per second.
 *
 * Slow — one turn every six seconds. §6 asks for a rotating ring because there
 * is something outstanding between you and that employer, which is a state to
 * notice rather than to be hurried by, and a fast spinner reads as a loading
 * indicator.
 */
const RING_TURNS_PER_SECOND = 1 / 6;

/**
 * What share of a frame may go on building city, and the floor and ceiling.
 *
 * **A share rather than a fixed number, and the fixed number was the
 * instructive mistake.** The first draft spent 4 ms a frame: a quarter of a
 * 60fps frame, which assembles the whole of New York — 35,413 footprints,
 * 269,439 points, something under a second of work — over about three seconds
 * of frames, with every one of them still landing on time. On a machine whose
 * frames take 600 ms, the same 4 ms is 0.7% of each one, and the city takes a
 * hundred seconds to appear. That is not a hypothetical: it is what headless
 * Chromium does here, and it is what a genuinely slow GPU would do to a user.
 *
 * Taking a quarter of whatever the last frame actually cost makes the wall
 * clock roughly constant instead: fast machines get many small slices, slow
 * ones get few large ones, and neither ever gives up more than a quarter of a
 * frame to it. The ceiling stops a single stalled frame — a tab coming back
 * from the background, where the delta is seconds — from turning into one very
 * long block of work.
 */
const BUILD_FRAME_SHARE = 0.25;
const BUILD_BUDGET_MIN_MS = 4;
const BUILD_BUDGET_MAX_MS = 60;

/**
 * The haze scale used before the map can be asked for one.
 *
 * Only reachable on a frame rendered without a map — which is how the unit
 * tests drive this layer. A zero would divide the fog by nothing and paint
 * every building flat magenta, which is a wrong picture that looks deliberate.
 */
const DEFAULT_HAZE_METRES = 25_000;

export interface SignalLayerOptions {
  /** Scene origin. Everything is metres from here. */
  readonly anchor: readonly [number, number];
  /**
   * Called once, the first time the whole city has been built and drawn.
   *
   * This is how ADR 0031's "the city never goes buildingless in between" is
   * made mechanical: MapLibre's own extrusion layers stay in the style and
   * stay visible until this fires, and only then does the caller retire them.
   * A boolean the caller polls would be the same rule enforced by remembering
   * to look, which is not enforcement.
   */
  readonly onBuildingsReady?: () => void;
}

/**
 * What the layer exposes beyond MapLibre's own interface.
 *
 * Narrow on purpose. The only thing outside this file that may change what is
 * drawn is the set of signals.
 */
export interface SignalLayer extends CustomLayerInterface {
  /**
   * Rebuild the instance buffer. Cheap enough to call on every data change.
   *
   * `sort` is §4.8's "sortable" reaching the renderer. It reorders the field
   * rather than filtering it, so the same roles are on screen before and
   * after — see `arrangeUnresolved`.
   */
  setSignals(signals: readonly CitySignal[], sort?: FieldSort): void;
  /**
   * Tell the layer how tall the hiring buildings are, by BIN, in metres.
   *
   * Separate from `setSignals` because the two arrive from different places
   * and in either order: the roles come from `/city/signals` and the heights
   * come from building tiles the map loads as the camera moves, which on a
   * still map may be long after. A layer that read heights only at
   * `setSignals` would strand every stack at `DEFAULT_ROOF_METRES` until
   * something else happened to re-set the signals.
   *
   * It moves markers **up and down their own building** and can move nothing
   * else. The floating field has no roof to settle onto and is untouched.
   */
  setRoofHeights(heights: ReadonlyMap<string, number>): void;
  /**
   * Apply §6's encoding: which role carries which mark, colour and pulse.
   *
   * Separate from `setSignals` because the two arrive from different fetches
   * and race on every load — the corpus from `/city/signals`, the treatments
   * from the applications and the ranked list. Either order has to produce the
   * same city, so both write to the same closure and rebuild from whatever is
   * known. A treatment naming a role that is not in the field draws nothing
   * rather than a mark at the origin.
   */
  setTreatments(treatments: ReadonlyMap<string, SignalTreatment>): void;
  /**
   * Stop everything that moves, and keep everything it was carrying.
   *
   * The pulse is §6's mark for *new*, so switching it off cannot be allowed to
   * delete that state — a new role stays drawn larger (`NEW_SCALE`) and is
   * still named in the roster and the legend. This is the whole of the layer's
   * `prefers-reduced-motion` handling; the camera holds its own.
   */
  setReducedMotion(reduced: boolean): void;
  /** How many beacons the last `setSignals` actually drew. */
  readonly drawn: number;
  /** How many of each §6 mark are on the city. */
  readonly marks: Readonly<Record<MarkKind, number>>;
  /** Where one mark is, in scene metres, or null if it is not drawn. */
  markAt(kind: MarkKind, index: number): readonly [number, number, number] | null;
  /** What colour one mark is drawn in, or null. */
  markTintAt(kind: MarkKind, index: number): string | null;
  /** What size multiplier one mark is drawn at, or null. */
  markScaleAt(kind: MarkKind, index: number): number | null;
  /** The colour, strength, pulse and size the beacon buffer holds, per instance. */
  tintAt(index: number): string | null;
  alphaAt(index: number): number | null;
  pulseAt(index: number): number | null;
  scaleAt(index: number): number | null;
  /**
   * Is anything on the city moving?
   *
   * What decides whether `render` asks for another frame. Unconditional
   * repainting is how a map pins a core at 60fps with nothing changing; never
   * repainting is how a pulse freezes mid-breath.
   */
  readonly animating: boolean;
  /** The columns as laid out, in order: what the roster panel navigates by. */
  readonly columns: readonly FieldColumn[];
  /**
   * The buildings with somebody hiring in them, in the order they were laid
   * out.
   *
   * Exposed for the same reason `columns` is: the beam layer and anything that
   * flies a camera to a building need the BIN and the position this layout
   * already computed, and recomputing them elsewhere would be a second
   * implementation free to disagree with this one.
   */
  readonly buildings: readonly HiringBuilding[];
  /**
   * How many times the layout has actually run.
   *
   * Exposed for one assertion nothing else can make: a roof height arriving
   * *unchanged* must not rebuild the city. The effect of the bug is invisible —
   * the same city, drawn again — so the count is the only evidence there is.
   */
  readonly layouts: number;
  /** How many employers have a name plate. */
  readonly labelled: number;
  /** Employers past the atlas ceiling, which have no plate. */
  readonly unlabelled: number;
  /** The camera angles the name plates are currently turned to, in degrees. */
  readonly labelsOrientedTo: { readonly bearing: number; readonly pitch: number };
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
  /**
   * Which role instance `index` draws, or null if nothing is drawn there.
   *
   * The instance buffer is written in the field's own order and that order
   * changes with the sort, so the mapping cannot be reconstructed by a caller
   * without reimplementing `arrangeUnresolved`. Exposed rather than inferred.
   */
  jobAt(index: number): string | null;
  /**
   * Which role is under this point on the canvas, or null for empty sky.
   *
   * Returns null until the layer has rendered once: the pick uses the matrix
   * the last frame drew with (see `pick.ts`), and before there is a frame there
   * is no honest answer. A guessed projection would return plausible wrong
   * roles rather than nothing.
   */
  pick(point: PointerPoint, viewport: Viewport): string | null;
  /** Draw the reticle around this role, or take it off the city with null. */
  setSelected(jobId: string | null): void;
  /** Which role the reticle is on, or null. */
  readonly selected: string | null;
  /**
   * Where the reticle is, in scene metres, or null if it is not drawn.
   *
   * Not derivable from `selected`, and that is the point of exposing it. A
   * role can be selected while its beacon is not in the field — it was
   * filtered out, or a poll returned a corpus without it — and the honest
   * render of that is a selection with no mark rather than a mark parked at
   * the origin. It is also how a test can see that a sort *moved* the reticle
   * rather than leaving it ringing whichever employer now stands where the
   * selected one used to.
   */
  readonly selectionAt: readonly [number, number, number] | null;
  /** Has a frame been drawn? Until it has, `pick` cannot answer. */
  readonly canPick: boolean;
  /**
   * Hand the layer whatever building footprints the map currently has loaded.
   *
   * ADR 0031: the towers are ours now, and they are built from the same tiles
   * MapLibre parsed for its own extrusions rather than from a second copy of
   * NYC's building table. Footprints already known are ignored, so this is
   * safe — and cheap — to call on every tile arrival.
   */
  ingestFootprints(features: readonly TileFootprint[]): void;
  /**
   * Switch the glow on or off.
   *
   * M4d Task 2 owns the quality tiers and has not run yet, so this is the knob
   * that task will reach for rather than a setting with a home of its own. It
   * exists now for two reasons that cannot wait for it: bloom is the most
   * expensive thing this layer does per pixel and the frame report has to be
   * able to measure the city with and without it in the same window, and the
   * screenshot loop ADR 0031 works by needs a before to put beside the after.
   */
  setBloom(enabled: boolean): void;
  /**
   * What the glow is doing: whether it is on, whether this GPU can run it at
   * all, and how many frames it has actually drawn on.
   *
   * `available` is false on a WebGL 1 context, where `blitFramebuffer` does not
   * exist. That is a real machine — MapLibre asks for WebGL 2 and falls back —
   * and the honest behaviour there is a city with no glow, said out loud,
   * rather than a city that renders black or an effect that silently does
   * nothing while the page claims it is on.
   */
  readonly bloom: {
    readonly enabled: boolean;
    readonly available: boolean;
    readonly drawn: number;
  };
  /**
   * What the city renderer has on the GPU, and what it still owes.
   *
   * Exposed for the same reason `drawn` is: a page that says "35,000
   * buildings" while the buffer holds four is the failure mode M4c's
   * acceptance suite caught once already, and a count nothing can read is a
   * count nothing can contradict.
   */
  readonly city: {
    readonly ready: boolean;
    readonly pending: number;
    readonly buildings: number;
    readonly meshes: number;
    readonly vertices: number;
  };
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

  // The bodies. One geometry, one material, one mesh, N transforms — §5.5.
  const beacons = createBeaconMesh(MAX_BEACONS);
  scene.add(beacons.mesh);

  // The four shapes §6 puts *on* a body, one instanced mesh each.
  const marks: Record<MarkKind, ReturnType<typeof createMarkMesh>> = {
    outline: createMarkMesh({ kind: 'outline', capacity: MAX_MARKS }),
    core: createMarkMesh({ kind: 'core', capacity: MAX_MARKS }),
    ring: createMarkMesh({ kind: 'ring', capacity: MAX_MARKS }),
    beam: createMarkMesh({ kind: 'beam', capacity: MAX_MARKS }),
  };
  for (const kind of MARK_KINDS) scene.add(marks[kind].mesh);

  // The plates live in the same scene as the beacons so they share the depth
  // buffer this layer exists to share (§5.1) — a name behind a tower is hidden
  // by it, exactly like the column it belongs to.
  const labels = createLabelMesh();
  scene.add(labels.mesh);

  // The hiring buildings' beams. Added before the reticle and after the marks
  // so it draws in the same pass; it writes no depth, so its order among the
  // transparent meshes decides only how it blends, not what hides it.
  const beams = createRoofBeamMesh();
  scene.add(beams.mesh);

  // The reticle. In the same scene for the same reason the plates are: it
  // shares the depth buffer, so a ring around a role behind a tower is hidden
  // by that tower exactly as the role is.
  const reticle = createSelectionMesh();
  scene.add(reticle.mesh);

  // New York itself — ADR 0031. It joins this scene rather than getting a
  // custom layer of its own for one reason: a second `WebGLRenderer` on
  // MapLibre's context would be two libraries caching two beliefs about the
  // same GL state, and this one already pays `resetState()` once a frame to
  // settle that argument with MapLibre alone. Sharing the scene also means the
  // buildings share the depth buffer with the beacons standing on them, which
  // is the whole reason ADR 0025 put Three in MapLibre's context at all.
  //
  // It is opaque and depth-writing, so Three draws it before every transparent
  // mesh above regardless of the order things were added here.
  const cityBuildings = createCityBuildings({ anchor: options.anchor });
  scene.add(cityBuildings.group);
  /** Fired once, when the city has been built end to end. See the option. */
  let announcedBuildings = false;
  /** Where the camera stood on the last frame, in scene metres. */
  const eye = new Vector3();
  /** When the last frame was drawn, for the build budget's share of one. */
  let lastRenderAt: number | null = null;

  let renderer: WebGLRenderer | null = null;
  /**
   * The glow. Built in `onAdd` against MapLibre's own context, because it reads
   * the frame back out of that context and cannot be given one of its own.
   */
  let bloom: Bloom | null = null;
  let bloomEnabled = true;
  let map: MapLibreMap | null = null;
  let drawn = 0;
  let columns: readonly FieldColumn[] = [];
  /** The buildings with somebody hiring in them, as the last layout found them. */
  let buildings: readonly HiringBuilding[] = [];
  /**
   * Measured roof heights by BIN, as the loaded building tiles report them.
   *
   * Empty until something fills it, and a miss is a documented default rather
   * than an error — see `DEFAULT_ROOF_METRES`. It decides how high a marker
   * hangs and never where it stands, so a stale or absent height cannot move a
   * role off its building.
   */
  let roofHeights: ReadonlyMap<string, number> | undefined;
  /** The last corpus and sort, so a roof height can re-run the layout. */
  let lastSignals: readonly CitySignal[] = [];
  let lastSort: FieldSort = 'company';
  /** How many times the layout has run. Read by one test; see `layouts`. */
  let layouts = 0;
  /** Where each drawn role is, in the buffer's own order. Index ↔ instance. */
  let placements: readonly FieldPlacement[] = [];
  let selected: string | null = null;
  /** §6, per role. Empty until the applications and the ranking have landed. */
  let treatments: ReadonlyMap<string, SignalTreatment> = new Map();
  let reducedMotion = false;
  /** The clock the pulses run on. Seconds since the first animated frame. */
  let clockStartedAt: number | null = null;
  /**
   * The matrix the last frame drew with: scene metres straight to clip space.
   *
   * Kept rather than recomputed because picking has to use *this* matrix and
   * not a second derivation of it — see the head of `pick.ts`. Null until the
   * first frame, which is what `canPick` reports.
   */
  let projection: Matrix4 | null = null;

  /**
   * §6, applied to the buffers.
   *
   * Everything the city encodes about a role is decided here, from the field's
   * placements and the treatment table, and written in one pass. Called by both
   * setters rather than by each of them doing half, because the two fetches
   * behind them race on every load: whichever lands second must produce exactly
   * the same city as the other order would have.
   *
   * A treatment naming a role that is not in the field contributes nothing. It
   * happens honestly — a poll removes a role while an application still refers
   * to it — and the alternative is a mark parked at the origin, decorating
   * whichever employer's column happens to stand there.
   */
  function writeTreatments(): void {
    const bodies: Beacon[] = [];
    const byKind: Record<MarkKind, Mark[]> = { outline: [], core: [], ring: [], beam: [] };

    for (const placement of placements) {
      const treatment = treatments.get(placement.jobId);
      const archived = treatment?.track === 'archived';
      const pulse = reducedMotion ? 0 : PULSE_HZ[treatment?.pulse ?? 'none'];

      bodies.push({
        x: placement.x,
        y: placement.y,
        z: placement.altitude,
        tint: archived ? ARCHIVED_COLOR : SIGNAL_COLOR,
        // Applied and after are drawn at full strength; an untouched role sits
        // just below it, and an archived one well below both. Dimming for
        // staleness multiplies whatever that came to, because "we have not
        // re-checked this listing" is a fact about a role at any stage.
        alpha: strengthOf(treatment),
        pulse,
        // The size stays even with the pulse switched off, which is what keeps
        // "new" legible under `prefers-reduced-motion`.
        scale: treatment?.pulse !== undefined && treatment.pulse !== 'none' ? NEW_SCALE : 1,
      });

      if (treatment === undefined) continue;
      const at = { x: placement.x, y: placement.y, z: placement.altitude };
      if (treatment.track === 'saved') byKind.outline.push({ ...at, tint: SAVED_COLOR });
      // §6 asks an applied role to be "solid illuminated". The beacon's own
      // body fills instead: a core at most of its radius, which reads as solid
      // matter rather than as more glow. At the small default size it read as
      // nothing at all.
      //
      // The original reason was that nothing in this corpus stood on a building
      // to illuminate. Since M4e Task 6 some roles do, and the translation is
      // kept for a better reason: **an application's state must not be drawn
      // differently depending on whether the employer published an address.**
      // Lighting the building for a placed role and filling the beacon for a
      // floating one would make the same fact about you look like two facts,
      // and would make the loudest version of it the one that happens to have
      // a street address.
      if (treatment.track === 'applied') {
        byKind.core.push({ ...at, tint: SIGNAL_COLOR, scale: APPLIED_CORE_SCALE });
      }
      if (treatment.track === 'in_process') byKind.ring.push({ ...at, tint: SIGNAL_COLOR });
      if (treatment.track === 'offer') byKind.core.push({ ...at, tint: OFFER_COLOR });
      if (treatment.beam !== 'none') byKind.beam.push({ ...at, tint: URGENT_COLOR });
    }

    beacons.set(bodies);
    for (const kind of MARK_KINDS) marks[kind].set(byKind[kind]);
    drawn = beacons.drawn;
  }

  /** How bright a role's body is, before its pulse. */
  function strengthOf(treatment: SignalTreatment | undefined): number {
    if (treatment === undefined) return 0.85;
    if (treatment.track === 'archived') return 0.3;
    // §6 asks an applied role to be "solid illuminated". Nothing in this corpus
    // stands on a building to illuminate, so the body itself goes to full.
    const base =
      treatment.track === 'applied' ||
      treatment.track === 'in_process' ||
      treatment.track === 'offer'
        ? 1
        : 0.85;
    return treatment.dimmed ? base * DIM_FACTOR : base;
  }

  /**
   * Turn the plates and the reticle to face wherever the camera now is.
   *
   * Bound to the map's move events rather than called from `render`, so a
   * still map does no work at all — and `orient` itself returns early when
   * neither angle has changed, which is most of a pan.
   */
  function faceCamera(): void {
    if (!map) return;
    labels.orient(map.getBearing(), map.getPitch());
    reticle.orient(map.getBearing(), map.getPitch());
    orientMarks();
  }

  /**
   * Face every mark at the camera, and spin the ring.
   *
   * The ring's rotation is §6's "rotating ring / orbiting arcs" and is the one
   * mark whose *motion* is the encoding, so it stops entirely under reduced
   * motion — a still ring is still a ring, and the roster says "interview"
   * beside it either way.
   */
  function orientMarks(): void {
    const bearing = map?.getBearing() ?? 0;
    const pitch = map?.getPitch() ?? 0;
    const spin =
      reducedMotion || clockStartedAt === null
        ? 0
        : elapsed() * RING_TURNS_PER_SECOND * Math.PI * 2;
    for (const kind of MARK_KINDS) {
      // Only the ring turns. A beam that spun would wobble, and an outline is
      // symmetrical enough that spinning it would just cost matrix writes.
      marks[kind].orient(kind === 'ring' ? spin : 0, bearing, pitch);
    }
  }

  /** Seconds since the first animated frame. */
  function elapsed(): number {
    if (clockStartedAt === null) return 0;
    return (performance.now() - clockStartedAt) / 1000;
  }

  /**
   * Put the reticle where the selected role currently is.
   *
   * Called after every rewrite of the buffer as well as on selection, because
   * a sort change moves every role in the field: a reticle written once at
   * selection time would stay at the old coordinates and end up ringing a
   * different company's beacon, which is a wrong answer that looks like a
   * working feature.
   */
  function placeReticle(): void {
    const placement = selected === null ? undefined : placements.find((p) => p.jobId === selected);
    if (placement === undefined) reticle.clear();
    else reticle.moveTo(placement.x, placement.y, placement.altitude);
  }

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
      return beacons.altitudeAt(index);
    },

    get marks() {
      return {
        outline: marks.outline.drawn,
        core: marks.core.drawn,
        ring: marks.ring.drawn,
        beam: marks.beam.drawn,
      };
    },

    markAt(kind, index) {
      return marks[kind].positionAt(index);
    },

    markTintAt(kind, index) {
      return marks[kind].tintAt(index);
    },

    markScaleAt(kind, index) {
      return marks[kind].scaleAt(index);
    },

    ingestFootprints(features) {
      cityBuildings.ingest(features);
      // The build happens inside the render loop, on a frame budget — so
      // something has to ask for a frame, or a city handed footprints while
      // nothing is animating waits for the next gesture to draw itself.
      map?.triggerRepaint();
    },

    setBloom(enabled) {
      bloomEnabled = enabled;
      // A repaint, because nothing else is going to ask for one: the city is
      // deliberately still when nothing animates, so switching the glow off on
      // an idle map would leave the last bloomed frame on screen until the
      // next gesture — which reads as the setting having no effect.
      map?.triggerRepaint();
    },

    get bloom() {
      return {
        enabled: bloomEnabled,
        available: bloom?.available ?? false,
        drawn: bloom?.drawn ?? 0,
      };
    },

    get city() {
      const stats = cityBuildings.stats;
      return {
        ready: cityBuildings.ready,
        pending: cityBuildings.pending,
        buildings: stats.buildings,
        meshes: stats.meshes,
        vertices: stats.vertices,
      };
    },

    tintAt(index) {
      return beacons.tintAt(index);
    },

    alphaAt(index) {
      return beacons.alphaAt(index);
    },

    pulseAt(index) {
      return beacons.pulseAt(index);
    },

    scaleAt(index) {
      return beacons.scaleAt(index);
    },

    get animating() {
      // The ring turns as long as one is drawn, so either is enough to keep
      // asking for frames — and under reduced motion neither ever does.
      return !reducedMotion && (beacons.animating || marks.ring.drawn > 0);
    },

    get columns() {
      return columns;
    },

    get buildings() {
      return buildings;
    },

    get layouts() {
      return layouts;
    },

    get labelled() {
      return labels.drawn;
    },

    get unlabelled() {
      return labels.unlabelled;
    },

    get labelsOrientedTo() {
      return labels.orientedTo;
    },

    get selected() {
      return selected;
    },

    get selectionAt() {
      return reticle.at;
    },

    get canPick() {
      return projection !== null;
    },

    jobAt(index) {
      if (index < 0 || index >= drawn) return null;
      return placements[index]?.jobId ?? null;
    },

    pick(point, viewport) {
      if (projection === null) return null;
      const ray = sceneRayFromPointer(projection, point, viewport);
      if (ray === null) return null;
      const index = pickInstance(beacons.mesh, ray);
      if (index === null) return null;
      return placements[index]?.jobId ?? null;
    },

    setSelected(jobId) {
      selected = jobId;
      placeReticle();
      map?.triggerRepaint();
    },

    setSignals(signals, sort = 'company') {
      // Two fields, one buffer. `arrangeOnBuildings` takes the roles somebody
      // confirmed an address for and stands them on it; `arrangeUnresolved`
      // takes the rest. Each owns its own filter, so a role appears in exactly
      // one of them — and neither can be forgotten by a caller, which is the
      // failure that draws a role twice and reads as two openings.
      //
      // **Placed roles come first in the buffer**, ahead of the floating field.
      // Any fixed order would do; what matters is that there *is* one, because
      // `jobAt`, `pick` and the reticle all index into this array and a buffer
      // whose order depended on which field happened to be non-empty would put
      // the reticle on a different role than the one that was clicked.
      // Kept so a later roof height can re-run this layout without the caller
      // having to hold the corpus and hand it back. The two inputs arrive from
      // different fetches in either order and each has to be able to produce
      // the finished city on its own — the same rule `writeTreatments` follows
      // one setter over.
      lastSignals = signals;
      lastSort = sort;
      layouts += 1;

      const roofs = arrangeOnBuildings(signals, options.anchor, roofHeights);
      const field = arrangeUnresolved(signals, sort);
      const all = [...roofs.placements, ...field.placements];

      const count = Math.min(all.length, MAX_BEACONS);
      columns = field.columns;
      buildings = roofs.buildings;
      // One beam per hiring building, rewritten with the layout rather than
      // edited alongside it: a beam left at the last city's coordinates would
      // stand over a building nobody is hiring in, which is the exact class of
      // stale-instance bug the reticle and the marks have each paid for once.
      beams.set(roofs.buildings);
      // Truncated to what is actually in the buffer, so index ↔ instance holds
      // at the ceiling too. Keeping the full list here would let `pick` name a
      // role that was never drawn, for a click that hit the beacon after it.
      placements = all.slice(0, count);

      // Every body and every mark, from the field and §6's table. The marks
      // are rewritten here and not only in `setTreatments` because a sort
      // moves the whole field under them — the reticle's trap, four meshes
      // over.
      writeTreatments();

      // The selected role has moved, if it is still here at all: every sort
      // reorders the field and a poll can remove a role outright.
      placeReticle();

      labels.setColumns(field.columns, SIGNAL_COLOR);
      // The plates are built facing bearing 0 / pitch 0. Without this they
      // stay that way until the user happens to move the map, so a field that
      // loads under an already-pitched camera — which is every load, the
      // opening pose is 76° — would show its names lying flat over the city.
      faceCamera();

      map?.triggerRepaint();
    },

    setRoofHeights(heights) {
      // Compared by value, because a fresh `Map` with identical contents is
      // what arrives on every camera settle — `refreshRoofHeights` re-queries
      // the same tiles and gets the same answer. A reference check would treat
      // each one as a change and rebuild the whole corpus on every pan-stop,
      // which at `MAX_BEACONS` is five thousand transforms to arrive at the
      // identical city.
      if (sameHeights(roofHeights, heights)) return;
      roofHeights = heights;
      // Re-runs the whole layout rather than editing altitudes in place. The
      // stacks are the only thing a height can move, but re-arranging is the
      // version that cannot drift from `arrangeOnBuildings` — an in-place edit
      // would be a second implementation of the same sum, free to disagree
      // with it the first time the clearance changes.
      this.setSignals(lastSignals, lastSort);
    },

    setTreatments(next) {
      treatments = next;
      writeTreatments();
      // The ring's spin needs a clock the moment one exists; without this the
      // first ring stands still until the map is moved.
      if (layer.animating && clockStartedAt === null) clockStartedAt = performance.now();
      map?.triggerRepaint();
    },

    setReducedMotion(reduced) {
      if (reduced === reducedMotion) return;
      reducedMotion = reduced;
      // Rewritten rather than flagged: the pulse rates live in the instance
      // buffer, so honouring the preference means writing zeroes into it. A
      // uniform would have been one line and would have left the *data* saying
      // the city is animating while the shader quietly ignored it.
      writeTreatments();
      orientMarks();
      map?.triggerRepaint();
    },

    onAdd(addedMap, gl) {
      map = addedMap;
      // 'move' rather than 'rotate'/'pitch': a fly-to changes both without
      // firing either, and a plate that only reorients on a manual gesture
      // spends every animation facing where the camera used to be.
      addedMap.on('move', faceCamera);
      faceCamera();
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

      // The glow reads the finished frame back out of this same buffer, which
      // is only the finished frame because this layer is the last one in the
      // style — see `bloom.ts`. If anything is ever inserted above it, the
      // glow stops covering whatever that is, silently.
      bloom = createBloom(gl);
    },

    render(_gl: WebGLRenderingContext | WebGL2RenderingContext, args: CustomRenderMethodInput) {
      // Composed *before* the early return below, deliberately. The projection
      // is a fact about this frame whether or not there is anything to draw
      // with it, and picking reads it — a map with an empty buffer that then
      // receives its signals would otherwise have no matrix until the next
      // frame happened to arrive. It also means the whole pick path can be
      // exercised in jsdom by calling `render` with a matrix and no renderer,
      // which is where `signalLayer.test.ts` gets its end-to-end pick from.
      //
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
      // Kept for picking, which must invert *this* matrix rather than build a
      // second one from the map's pose — see the head of `pick.ts`.
      projection = camera.projectionMatrix;

      if (!renderer) return;

      // **Not `drawn === 0`, which is what this used to return on.** The scene
      // held nothing but signals then, so an empty corpus meant an empty
      // frame. It now holds New York (ADR 0031), and a city that refused to
      // draw itself until somebody was hiring would be the most confusing
      // possible expression of I7.

      // Where the camera is, out of the matrix this frame will draw with —
      // never out of a second derivation from the pose. The haze needs it per
      // pixel and the eviction needs it per cell, and a camera position that
      // disagreed with the projection by a metre would fog the city from
      // slightly the wrong place, which reads as nothing at all being wrong.
      cameraPositionFrom(camera.projectionMatrix, eye);
      cityBuildings.setCamera(
        eye,
        map === null
          ? DEFAULT_HAZE_METRES
          : HAZE_CAMERA_DISTANCES *
              cameraDistanceMetres(
                map.getZoom(),
                map.getCenter().lat,
                map.getCanvas().clientHeight,
                args.fov,
              ),
      );

      // The column's pixel floor needs to know how tall the surface is; see
      // `MIN_COLUMN_WIDTH_PX`. Read from the same canvas the haze above reads.
      if (map !== null) beacons.setViewportHeight(map.getCanvas().clientHeight);

      // A slice of city per frame. The budget is what keeps 35,000 footprints
      // from arriving as one dropped second — see `cityBuildings.ts`.
      const now = performance.now();
      const frameMs = lastRenderAt === null ? 16.7 : now - lastRenderAt;
      lastRenderAt = now;
      const building = cityBuildings.step(
        Math.min(BUILD_BUDGET_MAX_MS, Math.max(BUILD_BUDGET_MIN_MS, BUILD_FRAME_SHARE * frameMs)),
      );
      if (!building && !announcedBuildings) {
        announcedBuildings = true;
        options.onBuildingsReady?.();
      }

      if (layer.animating && drawn > 0) {
        if (clockStartedAt === null) clockStartedAt = performance.now();
        beacons.tick(elapsed());
        orientMarks();
      }

      // Three and MapLibre each cache what they believe the GL state to be, and
      // they are both wrong after the other has drawn. This is the line whose
      // absence produces a correct scene rendered with somebody else's blend
      // mode.
      renderer.resetState();
      renderer.render(scene, camera);

      // **Last, and it has to be last.** This reads the colour buffer back and
      // adds a blurred copy of its bright half on top, so anything drawn after
      // it is a thing with no glow sitting on a city that has one. The signal
      // layer being the final layer in the style is what makes that true, and
      // it is asserted nowhere — a `beforeId` in `CityMap` would break it
      // without failing anything.
      if (bloomEnabled) bloom?.apply();

      // Deliberately *not* unconditional. A `triggerRepaint()` on every frame
      // is how every Three-in-MapLibre example animates, and it is also how a
      // map pins a core at 60fps forever with nothing moving on it. The next
      // frame is asked for only while something is actually moving — a pulse
      // or a ring — and under `prefers-reduced-motion` nothing ever is, so the
      // city goes completely still rather than animating invisibly.
      //
      // A city still assembling counts as moving, and stops counting the frame
      // it finishes. That is a bounded number of frames after a tile lands,
      // not a standing subscription to the display's refresh rate.
      if (layer.animating || building) map?.triggerRepaint();
    },

    onRemove(removedMap) {
      // A listener left on the map outlives this layer and keeps the whole
      // closure — scene, meshes, atlas — reachable, so none of the disposal
      // below is ever collected. It is removed first for that reason.
      removedMap.off('move', faceCamera);

      // Every one of these leaks GPU memory that outlives the page's own
      // teardown, and a context reaching the browser's limit fails to create
      // the *next* map with an error naming none of this.
      beacons.dispose();
      for (const kind of MARK_KINDS) marks[kind].dispose();
      labels.dispose();
      beams.dispose();
      reticle.dispose();
      // The largest allocation this layer holds by a wide margin — a hundred
      // megabytes of New York across a few dozen buffers.
      cityBuildings.dispose();
      // The geometries and materials above are this layer's; the compiled
      // programs and render lists behind them are the *renderer's*, and nulling
      // the reference leaves them on the GPU. It is a bounded leak today
      // because nothing removes this layer without destroying the map, and a
      // destroyed map takes its context with it — but "the only caller happens
      // to make this harmless" is not a property to leave undocumented in the
      // one place `city.md` §5.1 gave a second library a share of somebody
      // else's context.
      //
      // `dispose()` and not `forceContextLoss()`: the context belongs to
      // MapLibre, which is still drawing New York with it.
      // Its own programs, buffers and half a dozen render targets — a few
      // megabytes of texture that outlive the page's teardown otherwise.
      bloom?.dispose();
      bloom = null;
      renderer?.dispose();
      renderer = null;
      map = null;
      columns = [];
      buildings = [];
      lastRenderAt = null;
      placements = [];
      treatments = new Map();
      selected = null;
      projection = null;
      clockStartedAt = null;
    },
  };

  return layer;
}
