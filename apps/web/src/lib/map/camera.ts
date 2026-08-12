/**
 * The camera controller: everything about how the city moves, with no React in
 * it.
 *
 * `city.md` §5.4 asks for a dedicated controller that *wraps* MapLibre's camera
 * rather than replacing it, and the split it implies is the whole design of this
 * file. MapLibre already has a good, well-tested handler for every direct
 * manipulation gesture — drag to pan, right-drag to orbit, wheel and trackpad
 * pinch to zoom, two-finger touch to pinch, rotate and pitch. Rewriting those
 * would be a worse version of code that already exists. So this controller does
 * four things MapLibre does not:
 *
 * 1. **It decides which handlers are on**, in one place, with a test that fails
 *    if the division changes. Two of them are deliberately *off* because this
 *    controller owns those behaviours instead, and leaving one of them on is a
 *    double-handling bug rather than a redundancy: the map would pan twice per
 *    arrow key, or zoom *and* fly on a double-click.
 * 2. **It honours `prefers-reduced-motion` at the controller** rather than per
 *    call site — §5.4's second acceptance criterion. A rule enforced at each
 *    call site is one new call site away from being broken. MapLibre's own
 *    camera happens to check the same media query, and that is not enough:
 *    nothing in this codebase should depend on a library's private courtesy for
 *    an accessibility guarantee it has written down as acceptance.
 * 3. **It makes every animation yield instantly** — §5.4's first criterion. Any
 *    pointer, wheel, touch or key input stops the camera where it has reached.
 *    No queue, no snap-back, no "let me finish".
 * 4. **It adds the pieces §9.3 lists that MapLibre has no handler for**: focus
 *    on double-click rather than zoom-around-centre, keyboard navigation whose
 *    steps are ours to size, orbit-around-a-selection, "move only if needed",
 *    and trackpad rotation on the one platform that reports it.
 *
 * ## Why the map is an interface rather than `maplibregl.Map`
 *
 * `CameraMap` below is the exact subset of MapLibre this file touches. The real
 * `Map` satisfies it structurally, so `CityMap` passes one straight in — but the
 * test suite passes a fake, which is how the whole of this behaviour is tested
 * in jsdom with no GPU, no WebGL context and no tile archive. A controller whose
 * tests need a real map is a controller with no tests.
 *
 * ## What is deliberately not here
 *
 * **Selection.** `focusOn` and `orbitAround` take a coordinate, not a job. What
 * a selection *is* arrives with the signal layer in M4c, and a camera that knows
 * about jobs is a camera that has to be rewritten when jobs change shape.
 *
 * **Ground avoidance.** §9.3 lists it as *"if needed"*. It is not: the pitch
 * ceiling of 78° keeps the camera above the ground plane at every zoom this map
 * allows, and there is nothing to collide with — the buildings are drawn by the
 * GPU as extrusions, not held as geometry the camera could be inside of.
 */

import { BASEMAP_BOUNDS } from '@/lib/tiles';

/** A complete camera position. Every animation here moves between two of these. */
export interface CameraPose {
  readonly center: readonly [number, number];
  readonly zoom: number;
  readonly pitch: number;
  readonly bearing: number;
}

/**
 * Chelsea, looking down the island, tilted far enough to put the horizon on
 * screen.
 *
 * The pitch is the whole point of these numbers. At the 55° the first version
 * used, the frame is entirely ground: the sky, the horizon glow and the haze
 * between the viewer and the far city — the `dusk-*` atmosphere, which is where
 * most of the reference images' feeling actually lives — were all built,
 * shipped, and permanently off the top of the screen. A camera that never looks
 * up cannot show a skyline, which is a problem worth fixing before there is a
 * skyline to show.
 *
 * It lives here rather than in the component because it is also where the
 * keyboard's reset key goes, and two copies of a home position drift.
 */
export const INITIAL_POSE: CameraPose = {
  center: [-73.9903, 40.7449],
  zoom: 13.6,
  pitch: 76,
  bearing: 202,
};

/**
 * The edges of what this camera may do, and every one of them is a property of
 * the archives rather than a taste.
 *
 * `bounds` is the basemap's own bbox: panning past it shows empty tiles, which
 * reads as a broken map rather than as the edge of the data.
 *
 * `minZoom` keeps the city filling the frame. Below roughly z9.5 the NYC extract
 * is a lit island in a void, and the void is not information.
 *
 * `maxZoom` is one and a half steps past the buildings archive's z16, which is
 * as far as overzoom stays honest — past it the extrusions are visibly a
 * magnified z16 tile.
 *
 * `maxPitch` is where the ground plane approaches edge-on: the tile budget
 * explodes for a view of almost nothing, and the sky is already fully in frame
 * well before it.
 */
export const CAMERA_LIMITS = {
  minZoom: 9.5,
  maxZoom: 18,
  minPitch: 0,
  maxPitch: 78,
  bounds: [
    [BASEMAP_BOUNDS.west, BASEMAP_BOUNDS.south],
    [BASEMAP_BOUNDS.east, BASEMAP_BOUNDS.north],
  ],
} as const;

/** How long the controller's own moves take, in milliseconds. */
const DURATION = {
  /** A keyboard step: long enough to read as motion, short enough to hold a key. */
  key: 220,
  /** A double-click focus, and any programmatic `flyTo` with no duration given. */
  focus: 900,
  /** One 90° leg of an orbit. Four of them make a revolution in 24 seconds. */
  orbitLeg: 6000,
} as const;

/** How far one keypress moves the camera. */
const STEP = {
  /** Pan, as a fraction of the shorter viewport axis. */
  pan: 0.18,
  /** Rotate, in degrees. */
  bearing: 15,
  /** Pitch, in degrees. */
  pitch: 5,
  /** Zoom, in zoom levels. */
  zoom: 0.5,
} as const;

/**
 * Somewhere to move the camera to. Any subset of a pose.
 *
 * This is the type every *caller* uses, and it is readonly all the way down
 * because a target is a value. `CameraUpdate` below is the same thing with
 * mutable tuples, which is what MapLibre's `LngLatLike` insists on; `clampUpdate`
 * is the single point where one becomes the other, so the copy happens once
 * rather than at every call site.
 */
export interface CameraTarget {
  readonly center?: readonly [number, number];
  readonly zoom?: number;
  readonly pitch?: number;
  readonly bearing?: number;
  /** The point the move pivots around, for rotation that is not about the centre. */
  readonly around?: readonly [number, number];
}

/** A partial pose, in the shape MapLibre's camera methods accept. */
interface CameraUpdate {
  center?: [number, number];
  zoom?: number;
  pitch?: number;
  bearing?: number;
  around?: [number, number];
}

interface AnimationOptions {
  duration?: number;
  /**
   * MapLibre skips an animation it considers non-essential when the user
   * prefers reduced motion. This controller has already made that decision by
   * the time it calls, so every animation it starts is one it means — hence
   * `essential: true` on all of them, and a `jumpTo` when the answer is no.
   */
  essential?: boolean;
  easing?: (t: number) => number;
}

/** A MapLibre gesture handler, as far as this file is concerned. */
interface Toggleable {
  enable(): void;
  disable(): void;
  isEnabled(): boolean;
}

/**
 * The subset of `maplibregl.Map` this controller uses.
 *
 * Every member here is one the real map has with a compatible signature, so no
 * adapter is needed at the call site — and the fake in `camera.test.ts` is the
 * only other implementation that will ever exist.
 */
export interface CameraMap {
  getCenter(): { lng: number; lat: number };
  getZoom(): number;
  getBearing(): number;
  getPitch(): number;
  getContainer(): HTMLElement;
  // Mutable tuples, unlike everything else here, because MapLibre's `LngLatLike`
  // is a mutable `[number, number]` and TypeScript will not pass a `readonly`
  // one to it. The readonly-ness is kept where it matters — the poses this
  // controller stores — and dropped at the one boundary that refuses it.
  project(lngLat: [number, number]): { x: number; y: number };
  unproject(point: [number, number]): { lng: number; lat: number };
  jumpTo(options: CameraUpdate): void;
  easeTo(options: CameraUpdate & AnimationOptions): void;
  flyTo(options: CameraUpdate & AnimationOptions): void;
  panBy(offset: [number, number], options?: AnimationOptions): void;
  stop(): void;
  readonly dragPan: Toggleable;
  readonly dragRotate: Toggleable;
  readonly scrollZoom: Toggleable;
  readonly touchPitch: Toggleable;
  readonly keyboard: Toggleable;
  readonly doubleClickZoom: Toggleable;
  readonly touchZoomRotate: Toggleable & { enableRotation(): void };
}

/**
 * Safari on macOS is the only engine that reports a trackpad *rotation*, and it
 * reports it through three non-standard events. §9.3 asks for trackpad rotation
 * "where supported", and this is the whole of where it is supported.
 */
interface GestureEventLike extends Event {
  readonly rotation?: number;
  readonly scale?: number;
}

export interface FocusOptions {
  /** The zoom to arrive at, if the camera has to move at all. */
  readonly zoom?: number;
  /**
   * How much of each edge counts as "not really on screen", as a fraction. A
   * point behind the detail panel is a point the user cannot see.
   */
  readonly margin?: number;
}

export interface OrbitOptions {
  /** Degrees per second. Slow enough to read the city while it turns. */
  readonly degreesPerSecond?: number;
}

export interface CameraControllerOptions {
  readonly map: CameraMap;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

/** Bearings are an angle, and an angle of 375° is 15° written badly. */
function normaliseBearing(bearing: number): number {
  return ((bearing % 360) + 360) % 360;
}

/**
 * Hold a programmatic move inside the limits, so a caller cannot fly the camera
 * somewhere a gesture is forbidden from reaching. A camera with two different
 * sets of limits depending on how it got there is a camera with none.
 */
export function clampUpdate(update: CameraTarget): CameraUpdate {
  const clamped: CameraUpdate = {};
  if (update.center !== undefined) clamped.center = [update.center[0], update.center[1]];
  if (update.around !== undefined) clamped.around = [update.around[0], update.around[1]];
  if (update.zoom !== undefined) clamped.zoom = update.zoom;
  if (update.pitch !== undefined) clamped.pitch = update.pitch;
  if (update.bearing !== undefined) clamped.bearing = update.bearing;
  if (clamped.zoom !== undefined) {
    clamped.zoom = clamp(clamped.zoom, CAMERA_LIMITS.minZoom, CAMERA_LIMITS.maxZoom);
  }
  if (clamped.pitch !== undefined) {
    clamped.pitch = clamp(clamped.pitch, CAMERA_LIMITS.minPitch, CAMERA_LIMITS.maxPitch);
  }
  if (clamped.bearing !== undefined) {
    clamped.bearing = normaliseBearing(clamped.bearing);
  }
  return clamped;
}

/**
 * Does this browser, right now, prefer reduced motion?
 *
 * Guarded rather than assumed: `matchMedia` is absent in jsdom and on the
 * server, and an accessibility check that throws is worse than one that is
 * missing.
 */
function reducedMotionQuery(): MediaQueryList | null {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null;
  return window.matchMedia('(prefers-reduced-motion: reduce)');
}

/**
 * Typing into a field is not navigating a map.
 *
 * The city's overlays hold a search box and links, and an arrow key inside a
 * text input belongs to the input. Without this the map steals the caret.
 */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
}

/** Events that mean the user has taken control of the camera. */
const INTERRUPTING_EVENTS = ['pointerdown', 'wheel', 'touchstart', 'keydown'] as const;

export class CameraController {
  readonly #map: CameraMap;
  readonly #container: HTMLElement;
  readonly #media: MediaQueryList | null;
  readonly #listeners = new Set<() => void>();
  #version = 0;

  #reducedMotion: boolean;
  /** Set while a move this controller started is still running. */
  #animating = false;
  /** Cleared when an orbit is cancelled; every scheduled leg checks it first. */
  #orbit: { readonly around: readonly [number, number]; readonly step: number } | null = null;
  #orbitTimer: ReturnType<typeof setTimeout> | null = null;
  #animationTimer: ReturnType<typeof setTimeout> | null = null;
  #destroyed = false;

  constructor({ map }: CameraControllerOptions) {
    this.#map = map;
    this.#container = map.getContainer();
    this.#media = reducedMotionQuery();
    this.#reducedMotion = this.#media?.matches ?? false;

    this.#configureGestures();

    for (const type of INTERRUPTING_EVENTS) {
      // Capture, so the interruption lands before MapLibre's own handler starts
      // moving the camera — and passive, because none of this ever calls
      // `preventDefault` and a non-passive wheel listener costs scroll latency
      // on every wheel event in the app.
      this.#container.addEventListener(type, this.#handleUserInput, {
        capture: true,
        passive: true,
      });
    }
    this.#container.addEventListener('keydown', this.#handleKeyDown);
    this.#container.addEventListener('dblclick', this.#handleDoubleClick);
    this.#container.addEventListener('gesturestart', this.#handleGestureStart);
    this.#container.addEventListener('gesturechange', this.#handleGestureChange);
    this.#media?.addEventListener('change', this.#handleMotionPreferenceChange);
  }

  /**
   * Watch for the three things a user interface can be wrong about: the camera
   * being taken back by the user, an orbit starting or ending, and the motion
   * preference changing under the page.
   *
   * Deliberately not "on every camera move". A listener that fires per frame
   * would make a React component the thing driving the render loop, which
   * `CLAUDE.md` §8 and §9.4 both name as an anti-pattern. What a control panel
   * needs is state changes, and there are three of them.
   *
   * An arrow so its identity is stable across renders — `useSyncExternalStore`
   * resubscribes whenever the function changes.
   */
  readonly subscribe = (listener: () => void): (() => void) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  /** Bumped on every change `subscribe` reports. The snapshot React compares. */
  get version(): number {
    return this.#version;
  }

  /** Whether this camera is currently refusing to animate anything. */
  get reducedMotion(): boolean {
    return this.#reducedMotion;
  }

  /** Whether a move this controller started is still running. */
  get animating(): boolean {
    return this.#animating;
  }

  /** Whether the camera is turning around a point. */
  get orbiting(): boolean {
    return this.#orbit !== null;
  }

  getPose(): CameraPose {
    const center = this.#map.getCenter();
    return {
      center: [center.lng, center.lat],
      zoom: this.#map.getZoom(),
      pitch: this.#map.getPitch(),
      bearing: this.#map.getBearing(),
    };
  }

  /**
   * Move the camera somewhere, over time — or immediately, if the user has
   * asked for that.
   *
   * This is the only path a programmatic move takes, which is what makes the
   * reduced-motion rule enforceable: there is one `if` and every caller is
   * behind it.
   */
  flyTo(update: CameraTarget, options: { readonly duration?: number } = {}): void {
    if (this.#destroyed) return;
    const target = clampUpdate(update);
    if (this.#reducedMotion) {
      this.#map.jumpTo(target);
      return;
    }
    const duration = options.duration ?? DURATION.focus;
    this.#map.flyTo({ ...target, duration, essential: true });
    this.#markAnimating(duration);
  }

  /**
   * Put a coordinate on screen — **and do nothing at all if it already is.**
   *
   * §5.6: selecting something "moves the camera only if needed". A camera that
   * flies on every selection makes a list of results unusable, because reading
   * the second one means waiting out a journey from the first. The margin
   * exists because a point three pixels inside the window edge, behind the
   * detail panel, is not on screen in any sense the user recognises.
   *
   * Returns whether it moved, so a caller can tell the difference.
   */
  focusOn(lngLat: readonly [number, number], options: FocusOptions = {}): boolean {
    if (this.#destroyed) return false;
    const zoom = options.zoom ?? 15.5;
    const margin = options.margin ?? 0.18;

    const rect = this.#container.getBoundingClientRect();
    const point = this.#map.project([lngLat[0], lngLat[1]]);
    const visible =
      point.x >= rect.width * margin &&
      point.x <= rect.width * (1 - margin) &&
      point.y >= rect.height * margin &&
      point.y <= rect.height * (1 - margin);
    // Being on screen is not enough if the whole city is on screen. Half a zoom
    // level of slack keeps a run of nearby selections from ratcheting inwards.
    const closeEnough = this.#map.getZoom() >= zoom - 0.75;

    if (visible && closeEnough) return false;

    this.flyTo({ center: lngLat, zoom: Math.max(this.#map.getZoom(), zoom) });
    return true;
  }

  /**
   * Turn slowly around a point until the user touches anything.
   *
   * Built as a chain of 90° legs rather than one 360° animation because a
   * single long animation cannot be resumed after an interruption and cannot
   * change speed; a chain can simply stop scheduling. Each leg pivots `around`
   * the point, so the thing being orbited stays where it is on screen instead of
   * swinging across it.
   *
   * **Under reduced motion this does nothing but frame the point.** A camera
   * that circles forever is the exact motion the preference is asking not to
   * see, and there is no reduced version of it that is still an orbit.
   */
  orbitAround(lngLat: readonly [number, number], options: OrbitOptions = {}): void {
    if (this.#destroyed) return;
    this.stopOrbit();
    if (this.#reducedMotion) {
      this.focusOn(lngLat);
      return;
    }
    const degreesPerSecond = options.degreesPerSecond ?? 15;
    this.#orbit = { around: lngLat, step: degreesPerSecond };
    this.#scheduleOrbitLeg();
    this.#emit();
  }

  /** Stop turning. The camera stays wherever the orbit had reached. */
  stopOrbit(): void {
    const wasOrbiting = this.#orbit !== null;
    this.#orbit = null;
    if (this.#orbitTimer !== null) {
      clearTimeout(this.#orbitTimer);
      this.#orbitTimer = null;
    }
    if (wasOrbiting) this.#emit();
  }

  /**
   * Stop everything, now, wherever the camera has got to.
   *
   * `map.stop()` leaves the camera at its current position rather than at either
   * end of the animation, which is the no-snap-back half of §5.4's first
   * criterion.
   */
  stop(): void {
    this.stopOrbit();
    this.#map.stop();
    this.#clearAnimating();
  }

  /** Return to the opening view of the city. Bound to `0` and `Home`. */
  reset(): void {
    this.stopOrbit();
    this.flyTo(INITIAL_POSE, { duration: 1400 });
  }

  destroy(): void {
    this.#destroyed = true;
    this.stopOrbit();
    this.#clearAnimating();
    this.#listeners.clear();
    for (const type of INTERRUPTING_EVENTS) {
      this.#container.removeEventListener(type, this.#handleUserInput, { capture: true });
    }
    this.#container.removeEventListener('keydown', this.#handleKeyDown);
    this.#container.removeEventListener('dblclick', this.#handleDoubleClick);
    this.#container.removeEventListener('gesturestart', this.#handleGestureStart);
    this.#container.removeEventListener('gesturechange', this.#handleGestureChange);
    this.#media?.removeEventListener('change', this.#handleMotionPreferenceChange);
  }

  // --- gestures -----------------------------------------------------------

  /**
   * The whole gesture surface of §9.3, decided in one place.
   *
   * Written out even where it matches MapLibre's default, because a default is
   * a thing that changes in a minor release and this list is an acceptance
   * criterion. The two `disable` calls are the load-bearing lines: both of those
   * behaviours exist below, and leaving MapLibre's version on means every arrow
   * key pans twice and every double-click both zooms and flies.
   */
  #configureGestures(): void {
    const map = this.#map;
    map.dragPan.enable(); // mouse and touch pan
    map.dragRotate.enable(); // right-drag and ctrl-drag orbit
    map.scrollZoom.enable(); // wheel zoom, and trackpad pinch as ctrl+wheel
    map.touchZoomRotate.enable(); // two-finger pinch
    map.touchZoomRotate.enableRotation(); // two-finger rotate
    map.touchPitch.enable(); // two-finger vertical drag to tilt
    map.keyboard.disable(); // ours: see #handleKeyDown
    map.doubleClickZoom.disable(); // ours: focus, not zoom-around-centre
  }

  /**
   * Any input at all cancels any move in progress.
   *
   * Deliberately indiscriminate. The alternative — cancelling only for gestures
   * that MapLibre recognises as camera gestures — means a keypress or a
   * two-finger tap during a fly-to leaves the user watching the camera finish a
   * journey they have already tried to stop, and "which inputs count" is a
   * question with no good answer at the moment it is being asked.
   */
  readonly #handleUserInput = (): void => {
    if (!this.#animating && this.#orbit === null) return;
    this.stopOrbit();
    this.#map.stop();
    this.#clearAnimating();
    this.#emit();
  };

  /**
   * Keyboard navigation, and the reason MapLibre's own handler is off.
   *
   * Not because MapLibre's is bad — because the steps have to be ours. Arrow
   * keys pan in *screen* space through `panBy`, so "up" is up the screen
   * whatever the bearing is; a keyboard that pans north while the city is
   * rotated 202° is a keyboard nobody can aim.
   */
  readonly #handleKeyDown = (event: KeyboardEvent): void => {
    if (event.defaultPrevented || isTypingTarget(event.target)) return;
    // A browser or OS shortcut is not a camera move. Shift is the exception:
    // it is this controller's modifier for "rotate and tilt instead of pan".
    if (event.metaKey || event.ctrlKey || event.altKey) return;

    const rect = this.#container.getBoundingClientRect();
    const pan = Math.max(60, Math.min(rect.width, rect.height) * STEP.pan);
    const duration = this.#reducedMotion ? 0 : DURATION.key;
    const rotate = (delta: number): void =>
      this.#ease({ bearing: this.#map.getBearing() + delta }, duration);
    const tilt = (delta: number): void =>
      this.#ease({ pitch: this.#map.getPitch() + delta }, duration);

    switch (event.key) {
      case 'ArrowUp':
        if (event.shiftKey) tilt(STEP.pitch);
        else this.#panBy([0, -pan], duration);
        break;
      case 'ArrowDown':
        if (event.shiftKey) tilt(-STEP.pitch);
        else this.#panBy([0, pan], duration);
        break;
      case 'ArrowLeft':
        if (event.shiftKey) rotate(-STEP.bearing);
        else this.#panBy([-pan, 0], duration);
        break;
      case 'ArrowRight':
        if (event.shiftKey) rotate(STEP.bearing);
        else this.#panBy([pan, 0], duration);
        break;
      case '+':
      case '=':
        this.#ease({ zoom: this.#map.getZoom() + STEP.zoom }, duration);
        break;
      case '-':
      case '_':
        this.#ease({ zoom: this.#map.getZoom() - STEP.zoom }, duration);
        break;
      case '0':
      case 'Home':
        this.reset();
        break;
      case 'Escape':
        // Escape means stop, at every level of this product. Here it ends an
        // orbit; in M4c it will also clear the selection, and the ordering is
        // deliberate — the camera stops first so the user is looking at a still
        // frame by the time anything else happens.
        this.stop();
        break;
      default:
        return;
    }
    event.preventDefault();
  };

  /**
   * Double-click focuses rather than zooming.
   *
   * MapLibre's `doubleClickZoom` zooms around the pointer with the pitch and
   * bearing untouched, which is nearly right; what it is missing is that this
   * camera is usually looking at something, and a focus that keeps the tilt and
   * heading preserves spatial orientation (§9.3) while a zoom-around-centre
   * throws the frame's subject off the edge.
   */
  readonly #handleDoubleClick = (event: MouseEvent): void => {
    const rect = this.#container.getBoundingClientRect();
    const lngLat = this.#map.unproject([event.clientX - rect.left, event.clientY - rect.top]);
    const delta = event.shiftKey ? -1.4 : 1.4;
    this.flyTo({ center: [lngLat.lng, lngLat.lat], zoom: this.#map.getZoom() + delta });
    event.preventDefault();
  };

  /**
   * Trackpad rotation, on the one engine that reports it.
   *
   * Safari on macOS emits `gesturestart`/`gesturechange` with a `rotation` in
   * degrees. It *also* emits `wheel` with `ctrlKey` for the pinch component of
   * the same gesture, which MapLibre's `scrollZoom` already turns into a zoom —
   * so this reads only the rotation and lets the zoom alone. Applying `scale`
   * here too would zoom twice per pinch, at a rate that feels like a bug in the
   * trackpad.
   */
  readonly #handleGestureStart = (event: Event): void => {
    this.#handleUserInput();
    event.preventDefault();
  };

  readonly #handleGestureChange = (event: Event): void => {
    const rotation = (event as GestureEventLike).rotation;
    if (rotation === undefined) return;
    // `rotation` is cumulative from the start of the gesture, so the bearing is
    // set from a base captured at `gesturestart`… except that MapLibre may also
    // be moving the camera. Reading the live bearing each time and applying the
    // frame's delta keeps the two compositions from fighting.
    this.#map.jumpTo({ bearing: normaliseBearing(this.#map.getBearing() + rotation * 0.5) });
    event.preventDefault();
  };

  readonly #handleMotionPreferenceChange = (event: MediaQueryListEvent): void => {
    this.#reducedMotion = event.matches;
    // Turning the preference on mid-orbit has to end the orbit. Waiting for the
    // next call would leave the one animation the preference most clearly
    // forbids running indefinitely.
    if (event.matches) this.stop();
    this.#emit();
  };

  // --- internals ----------------------------------------------------------

  #emit(): void {
    this.#version += 1;
    for (const listener of this.#listeners) listener();
  }

  #ease(update: CameraTarget, duration: number): void {
    const target = clampUpdate(update);
    if (duration === 0 || this.#reducedMotion) {
      this.#map.jumpTo(target);
      return;
    }
    this.#map.easeTo({ ...target, duration, essential: true });
    this.#markAnimating(duration);
  }

  #panBy(offset: [number, number], duration: number): void {
    if (duration === 0 || this.#reducedMotion) {
      this.#map.panBy(offset, { duration: 0, essential: true });
      return;
    }
    this.#map.panBy(offset, { duration, essential: true });
    this.#markAnimating(duration);
  }

  /**
   * One 90° leg of an orbit, and the scheduling of the next.
   *
   * The chain is held together by `#orbit` rather than by the timer alone: a
   * cancellation clears both, and the check at the top means a leg that is
   * already in flight when the user interrupts cannot schedule a successor.
   */
  #scheduleOrbitLeg(): void {
    const orbit = this.#orbit;
    if (orbit === null) return;
    const legDegrees = 90;
    const duration = (legDegrees / orbit.step) * 1000;
    this.#map.easeTo({
      // Through the clamp like every other programmatic move, which here means
      // the bearing comes back inside one circle. MapLibre would have coped with
      // 440° — it renormalises against the start bearing and still turns the
      // short way — but a camera whose fourth leg reads 800 is a camera whose
      // state cannot be compared to anything, including the URL M4c writes it to.
      ...clampUpdate({ bearing: this.#map.getBearing() + legDegrees, around: orbit.around }),
      duration,
      essential: true,
      // Linear, because an eased leg would slow to a stop four times per
      // revolution and read as a stutter rather than as a turn.
      easing: (t) => t,
    });
    this.#markAnimating(duration);
    this.#orbitTimer = setTimeout(() => {
      this.#orbitTimer = null;
      this.#scheduleOrbitLeg();
    }, duration);
  }

  /**
   * Remember that a move is running, and for how long.
   *
   * A timer rather than MapLibre's `moveend`, because `moveend` also fires for
   * every user gesture and this flag means specifically "the controller is
   * moving the camera". Being a few milliseconds wrong about when it ends costs
   * nothing: the flag only decides whether an interruption is worth reporting,
   * and `map.stop()` on an idle map is a no-op.
   */
  #markAnimating(duration: number): void {
    this.#animating = true;
    if (this.#animationTimer !== null) clearTimeout(this.#animationTimer);
    this.#animationTimer = setTimeout(() => {
      this.#animationTimer = null;
      this.#animating = false;
    }, duration);
  }

  #clearAnimating(): void {
    this.#animating = false;
    if (this.#animationTimer !== null) {
      clearTimeout(this.#animationTimer);
      this.#animationTimer = null;
    }
  }
}

/** The one way this is built. Keeps `new` out of the component. */
export function createCameraController(options: CameraControllerOptions): CameraController {
  return new CameraController(options);
}

/** Named steps, exported so the on-screen keyboard help cannot drift from them. */
export const KEYBOARD_HELP: readonly { readonly keys: string; readonly does: string }[] = [
  { keys: '↑ ↓ ← →', does: 'Pan' },
  { keys: 'Shift ← →', does: 'Rotate' },
  { keys: 'Shift ↑ ↓', does: 'Tilt' },
  { keys: '+ −', does: 'Zoom' },
  { keys: '0', does: 'Reset the view' },
  { keys: 'Esc', does: 'Stop the camera' },
];

/** Also the DURATION and STEP tables, for the tests that pin them. */
export const CAMERA_TIMING = DURATION;
export const CAMERA_STEP = STEP;
