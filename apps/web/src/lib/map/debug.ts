/**
 * A handle on the live map, for the acceptance suite and for nobody else.
 *
 * M4b's acceptance criteria are about what a *browser* does — "every gesture in
 * §9.3 works on trackpad and touch", "every animation is interruptible" — and
 * the unit tests cannot answer either one. They drive a fake map in jsdom, so
 * they prove that this controller calls `panBy` when you press an arrow key;
 * they cannot prove that pressing an arrow key in Chromium moves New York. The
 * gap between those two sentences is the gap I6 exists to close.
 *
 * Closing it needs a way to read the camera from Playwright, because the pose is
 * not in the DOM: MapLibre keeps it in a WebGL transform and this product
 * deliberately does not mirror it into React state (a component re-rendering per
 * frame is the anti-pattern in `CLAUDE.md` §8). So the map and its controller are
 * published on `window` — and the guard is the whole design of this file.
 *
 * **It is compiled out of production.** Next inlines `process.env.NODE_ENV` into
 * the client bundle, so in a production build the branch below is a literal
 * `false` and the bundler drops the assignment, the type and every reference to
 * it. There is no flag to leave on by accident, and no shipped surface that lets
 * a page script drive somebody's camera.
 *
 * The cost of that guard, stated plainly: the acceptance suite must run against
 * `next dev`, which is what `playwright.config.ts` starts. Against a production
 * build the handle is absent, and `city.spec.ts` fails with a message that says
 * so rather than silently testing nothing.
 */

import type { SignalLayer } from '@/lib/city/signalLayer';
import type { CameraController, CameraMap } from '@/lib/map/camera';
import type { FrameTimer } from '@/lib/map/frameTimer';

/**
 * What the suite asks the map, beyond the pose the controller already exposes.
 *
 * Structurally satisfied by `maplibregl.Map` — this is a narrowing, not an
 * adapter — and deliberately small. Every member is here because one assertion
 * needs it: whether the skyline is really an extrusion, whether its features
 * actually reached the renderer, and whether a move is still running.
 */
export interface DebugMap extends CameraMap {
  getLayer(id: string): { readonly type?: string } | undefined;
  /**
   * Both of MapLibre's shapes: a whole-viewport query, and one bounded by a
   * screen-space box. The suite needs the box — at the pitch this city opens
   * at, the viewport form answers zero over a fully drawn skyline. The reason
   * is in `city.spec.ts`, beside the assertion that depends on it.
   */
  queryRenderedFeatures(options?: { layers?: string[] }): readonly unknown[];
  queryRenderedFeatures(
    box: readonly [readonly [number, number], readonly [number, number]],
    options?: { layers?: string[] },
  ): readonly unknown[];
  isMoving(): boolean;
  isStyleLoaded(): boolean;
  /**
   * The canvas, for its CSS size.
   *
   * Picking is in canvas pixels, and the suite has to hand `pick` the same
   * viewport the product does — reading it from `window.innerWidth` instead
   * would be a second definition that is right until something puts a border
   * on the container.
   */
  getCanvas(): HTMLCanvasElement;
}

export interface CityDebugHandle {
  readonly map: DebugMap;
  readonly camera: CameraController;
  /**
   * The signal layer, for the one question the DOM cannot answer: how many
   * beacons are actually in the instance buffer. A count in the overlay would
   * prove the *fetch* worked; this proves the renderer received them.
   */
  readonly signals: SignalLayer;
  /**
   * The frame timer, for the criterion no DOM can answer: how long the city's
   * frames actually take, on this machine, under a named gesture.
   *
   * Read by the metrics run rather than by an assertion about a number — the
   * suite's own browser has no GPU, so a threshold asserted here would be a
   * threshold about a software rasteriser. What *is* asserted is that the timer
   * sees real frames and that the page names the renderer that drew them.
   */
  readonly frames: FrameTimer;
}

/** The one global this project defines, and only outside production. */
export const CITY_DEBUG_KEY = '__nightshiftCity';

declare global {
  interface Window {
    [CITY_DEBUG_KEY]?: CityDebugHandle;
  }
}

/**
 * Publish the handle, and return the function that takes it away again.
 *
 * Removed on teardown for the same reason the map is: a handle outliving its
 * map answers questions about a camera that no longer exists, and a test that
 * reads a stale pose fails in a way that names the wrong thing.
 */
export function installCityDebug(handle: CityDebugHandle): () => void {
  if (process.env.NODE_ENV === 'production' || typeof window === 'undefined') {
    return () => {};
  }
  window[CITY_DEBUG_KEY] = handle;
  return () => {
    delete window[CITY_DEBUG_KEY];
  };
}
