/**
 * Scene state, held outside React so the renderer can read it without one.
 *
 * `city.md` §5.5: *"React never drives the render loop. Zustand holds scene
 * state; the loop reads it."* This is that store, and the shape of it is the
 * whole point — one place holds the signals, a React component writes them
 * after a fetch, and the custom layer subscribes **outside** React and pushes
 * them into an instance buffer.
 *
 * The alternative that looks simpler and is the anti-pattern `CLAUDE.md` §8
 * names: pass the signals into `CityMap` as a prop, and every data change
 * re-renders a component that owns a WebGL context. Here a data change is a
 * store write and a buffer update, and no component renders at all.
 *
 * Deliberately small. This holds what is *on* the city, not what the city looks
 * like: the style lives in `map/darkStyle.ts` and every rule about how the
 * camera behaves lives in `map/camera.ts`, and pulling either in here would
 * make this the god object those two files were split to avoid.
 *
 * The camera *controller* is the one exception, and it is a handle rather than
 * state — no pose, no limits, no behaviour, just the object overlays call. It
 * is here because `CityMap` builds the controller and the panels that need to
 * drive it are passed to that map as `children`, so the alternative is prop
 * drilling through a component whose entire job is lifecycle. It is set on
 * build and nulled on teardown, and nothing reads it after that.
 */

import { create } from 'zustand';

import type { CameraController } from '@/lib/map/camera';
import type { CitySignal } from '@/lib/schemas';

import type { FieldSort } from './unresolvedField';

/**
 * Why the signals are not on screen, when they are not.
 *
 * An explicit state rather than `signals.length === 0`, because "nobody is
 * hiring" and "the API is not running" are different sentences and the city has
 * to say which one it means. An empty map that does not distinguish them is the
 * failure mode M0's shell tests were written for, reappearing in three
 * dimensions.
 */
export type SignalsStatus =
  | { readonly kind: 'loading' }
  | { readonly kind: 'ready' }
  | { readonly kind: 'unavailable'; readonly detail: string };

interface CityScene {
  readonly signals: readonly CitySignal[];
  readonly status: SignalsStatus;
  /** How the field is ordered — §4.8's "sortable". Shared by the roster and the layer. */
  readonly sort: FieldSort;
  /** The live camera, or null when no map is mounted. A handle, not state. */
  readonly camera: CameraController | null;
  /**
   * Has the map painted a frame?
   *
   * Not the same question as "is there a camera": the controller exists from
   * the moment the map is constructed, several seconds before New York is on
   * screen. The rail uses this to keep from offering camera buttons over a
   * blank canvas — a gate `CityMap` used to hold in its own state, moved here
   * when the controls moved into the rail.
   */
  readonly mapReady: boolean;
  /**
   * The selected role's `job_id`, or null.
   *
   * **One piece of state shared by the map and the list**, which is §5.6's
   * rule stated as a field: "selection is one piece of state shared by both."
   * The alternative — a highlight in the renderer and a highlighted row in the
   * roster, each holding its own copy — is precisely the way a list and a map
   * come to disagree, and §5.6 makes "they cannot disagree" an M4c acceptance
   * criterion rather than a nicety.
   *
   * The URL is kept in step with this by `CityDetail`, in one place, rather
   * than by every control that can change a selection.
   */
  readonly selected: string | null;
  setSignals(signals: readonly CitySignal[]): void;
  setUnavailable(detail: string): void;
  setSort(sort: FieldSort): void;
  setCamera(camera: CameraController | null): void;
  setMapReady(ready: boolean): void;
  select(jobId: string | null): void;
  reset(): void;
}

export const useCityScene = create<CityScene>((set) => ({
  signals: [],
  status: { kind: 'loading' },
  sort: 'company',
  camera: null,
  mapReady: false,
  selected: null,
  setSignals: (signals) => set({ signals, status: { kind: 'ready' } }),
  setUnavailable: (detail) => set({ signals: [], status: { kind: 'unavailable', detail } }),
  setSort: (sort) => set({ sort }),
  setCamera: (camera) => set({ camera }),
  setMapReady: (mapReady) => set({ mapReady }),
  select: (selected) => set({ selected }),
  // Called when the map unmounts. A store that kept the last city would hand
  // the next map a frame of stale beacons before its own fetch resolved.
  //
  // The sort is deliberately *not* reset: it is a choice the person made, and
  // returning from a job's detail page to find the field reordered would be
  // the interface forgetting something they did on purpose.
  //
  // The selection is not reset either, and for a stronger reason than the
  // sort: it lives in the URL. Clearing it here would make an unmount rewrite
  // the address bar, so following a link to a role and then navigating back
  // would land on a page whose `?job=` had been quietly deleted.
  reset: () => set({ signals: [], status: { kind: 'loading' }, camera: null, mapReady: false }),
}));
