/**
 * The fake map, and the fake motion preference, shared by the camera's tests.
 *
 * A fixture module rather than a copy in each test file, because the two things
 * it fakes are the two things the controller cannot be tested without — a
 * MapLibre map needs a WebGL context and a tile archive, and jsdom implements no
 * `matchMedia` at all. `CLAUDE.md` §7 wants fakes named as fakes and kept behind
 * the real interface: `FakeMap` implements `CameraMap` and nothing in the
 * product imports this file.
 */

import { vi } from 'vitest';

import { INITIAL_POSE, type CameraMap } from './camera';

export interface Call {
  readonly method: 'jumpTo' | 'easeTo' | 'flyTo' | 'panBy' | 'stop';
  readonly options: Record<string, unknown>;
}

/** A gesture handler that only remembers whether it is on. */
class FakeHandler {
  #enabled = false;
  rotationEnabled = false;
  enable(): void {
    this.#enabled = true;
  }
  disable(): void {
    this.#enabled = false;
  }
  isEnabled(): boolean {
    return this.#enabled;
  }
  enableRotation(): void {
    this.rotationEnabled = true;
  }
}

/**
 * A MapLibre map with no map in it.
 *
 * The camera state is real — `easeTo` and `jumpTo` apply their target — because
 * several of the behaviours under test are about what the *next* call computes
 * from the current pose, and a fake that records without applying would make an
 * orbit look like four legs to the same bearing.
 */
export class FakeMap implements CameraMap {
  readonly container: HTMLElement;
  readonly calls: Call[] = [];
  center = { lng: INITIAL_POSE.center[0], lat: INITIAL_POSE.center[1] };
  zoom = INITIAL_POSE.zoom;
  pitch = INITIAL_POSE.pitch;
  bearing = INITIAL_POSE.bearing;
  /** Whatever `unproject` should answer, regardless of the point given. */
  unprojectTo = { lng: -73.98, lat: 40.75 };
  /** Whatever `project` should answer, regardless of the coordinate given. */
  projectTo = { x: 500, y: 400 };

  readonly dragPan = new FakeHandler();
  readonly dragRotate = new FakeHandler();
  readonly scrollZoom = new FakeHandler();
  readonly touchPitch = new FakeHandler();
  readonly keyboard = new FakeHandler();
  readonly doubleClickZoom = new FakeHandler();
  readonly touchZoomRotate = new FakeHandler();

  constructor() {
    this.container = document.createElement('div');
    // jsdom gives every element a zero-sized rect, and the pan step and the
    // focus margin are both fractions of the viewport. Without a size the
    // keyboard would pan by its floor and `focusOn` would consider nothing
    // visible.
    this.container.getBoundingClientRect = () =>
      ({ width: 1000, height: 800, left: 0, top: 0, right: 1000, bottom: 800 }) as DOMRect;
    document.body.append(this.container);
    // Every handler starts enabled, as MapLibre's do, so a test that finds one
    // disabled has found the controller disabling it rather than a fake that
    // never turned it on.
    for (const handler of [
      this.dragPan,
      this.dragRotate,
      this.scrollZoom,
      this.touchPitch,
      this.keyboard,
      this.doubleClickZoom,
      this.touchZoomRotate,
    ]) {
      handler.enable();
    }
  }

  getCenter() {
    return this.center;
  }
  getZoom() {
    return this.zoom;
  }
  getBearing() {
    return this.bearing;
  }
  getPitch() {
    return this.pitch;
  }
  getContainer() {
    return this.container;
  }
  project() {
    return this.projectTo;
  }
  unproject() {
    return this.unprojectTo;
  }

  jumpTo(options: Record<string, unknown>) {
    this.calls.push({ method: 'jumpTo', options });
    this.#apply(options);
  }
  easeTo(options: Record<string, unknown>) {
    this.calls.push({ method: 'easeTo', options });
    this.#apply(options);
  }
  flyTo(options: Record<string, unknown>) {
    this.calls.push({ method: 'flyTo', options });
    this.#apply(options);
  }
  panBy(offset: readonly [number, number], options: Record<string, unknown> = {}) {
    this.calls.push({ method: 'panBy', options: { offset, ...options } });
  }
  stop() {
    this.calls.push({ method: 'stop', options: {} });
  }

  #apply(options: Record<string, unknown>) {
    if (typeof options.zoom === 'number') this.zoom = options.zoom;
    if (typeof options.pitch === 'number') this.pitch = options.pitch;
    if (typeof options.bearing === 'number') this.bearing = options.bearing;
    if (Array.isArray(options.center)) {
      this.center = { lng: options.center[0] as number, lat: options.center[1] as number };
    }
  }

  /** Every call of one kind, in order. */
  of(method: Call['method']): Record<string, unknown>[] {
    return this.calls.filter((call) => call.method === method).map((call) => call.options);
  }
  get last(): Call | undefined {
    return this.calls.at(-1);
  }
}

/** The media query, controllable, since jsdom does not implement `matchMedia`. */
export function stubReducedMotion(matches: boolean): { set(value: boolean): void } {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  let current = matches;
  const list = {
    get matches() {
      return current;
    },
    media: '(prefers-reduced-motion: reduce)',
    addEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener);
    },
    removeEventListener: (_: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener);
    },
  };
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => list),
  );
  return {
    set(value: boolean) {
      current = value;
      for (const listener of listeners) listener({ matches: value } as MediaQueryListEvent);
    },
  };
}
