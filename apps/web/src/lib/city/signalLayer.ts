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
import { Camera, Matrix4, Scene, Vector3, WebGLRenderer } from 'three';

import type { CitySignal } from '@/lib/schemas';

import {
  ARCHIVED_COLOR,
  BEACON_RADIUS,
  createBeaconMesh,
  DIM_FACTOR,
  MAX_BEACONS,
  NEW_SCALE,
  PULSE_HZ,
  SIGNAL_COLOR,
  type Beacon,
} from './beacon';
import { createLabelMesh } from './labelMesh';
import { createMarkMesh, MARK_KINDS, type Mark, type MarkKind } from './markMesh';
import { mercatorFromLngLat, metreInMercatorUnits } from './mercator';
import { pickInstance, sceneRayFromPointer, type PointerPoint, type Viewport } from './pick';
import { createSelectionMesh } from './selectionMesh';
import type { SignalTreatment } from './treatments';
import { arrangeOnBuildings, type HiringBuilding } from './buildingField';
import { createRoofBeamMesh } from './roofBeamMesh';
import {
  arrangeUnresolved,
  type FieldColumn,
  type FieldPlacement,
  type FieldSort,
} from './unresolvedField';

/** The layer's id in the style, and the handle every test reaches for. */
export const SIGNAL_LAYER_ID = 'nightshift-signals';

// Re-exported rather than moved-and-forgotten: these lived here for two tasks
// and `beacon.ts` is where they belong now, but every caller that had the old
// import is still right about what it wanted.
export { BEACON_RADIUS, MAX_BEACONS, SIGNAL_COLOR };

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

export interface SignalLayerOptions {
  /** Scene origin. Everything is metres from here. */
  readonly anchor: readonly [number, number];
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

  let renderer: WebGLRenderer | null = null;
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
      // §6 asks an applied role to be "solid illuminated". Nothing here stands
      // on a building to illuminate, so the beacon itself fills in: a core at
      // most of the body's own radius, which reads as solid matter rather than
      // as more glow. At the small default size it read as nothing at all.
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

      if (!renderer || drawn === 0) return;

      if (layer.animating) {
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

      // Deliberately *not* unconditional. A `triggerRepaint()` on every frame
      // is how every Three-in-MapLibre example animates, and it is also how a
      // map pins a core at 60fps forever with nothing moving on it. The next
      // frame is asked for only while something is actually moving — a pulse
      // or a ring — and under `prefers-reduced-motion` nothing ever is, so the
      // city goes completely still rather than animating invisibly.
      if (layer.animating) map?.triggerRepaint();
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
      renderer?.dispose();
      renderer = null;
      map = null;
      columns = [];
      buildings = [];
      placements = [];
      treatments = new Map();
      selected = null;
      projection = null;
      clockStartedAt = null;
    },
  };

  return layer;
}
