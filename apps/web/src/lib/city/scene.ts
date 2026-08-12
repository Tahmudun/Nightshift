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
 * like: the camera lives in `map/camera.ts` and the style in `map/darkStyle.ts`,
 * and pulling either in here would make this the god object those two files
 * were split to avoid.
 */

import { create } from 'zustand';

import type { CitySignal } from '@/lib/schemas';

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
  setSignals(signals: readonly CitySignal[]): void;
  setUnavailable(detail: string): void;
  reset(): void;
}

export const useCityScene = create<CityScene>((set) => ({
  signals: [],
  status: { kind: 'loading' },
  setSignals: (signals) => set({ signals, status: { kind: 'ready' } }),
  setUnavailable: (detail) => set({ signals: [], status: { kind: 'unavailable', detail } }),
  // Called when the map unmounts. A store that kept the last city would hand
  // the next map a frame of stale beacons before its own fetch resolved.
  reset: () => set({ signals: [], status: { kind: 'loading' } }),
}));
