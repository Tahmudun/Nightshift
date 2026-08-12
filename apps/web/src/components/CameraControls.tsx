'use client';

/**
 * A pointer, and a keyboard, for a camera that otherwise only answers to a
 * drag.
 *
 * This is not decoration on top of the gestures. §9.3's gesture list assumes a
 * trackpad and two working hands: orbiting the city means holding the right
 * mouse button and dragging, and there are people for whom that is not
 * available. Every one of these buttons is the only route to its behaviour for
 * somebody — and `city.md` §5.6's rule that every map action has a non-3D
 * equivalent points the same way.
 *
 * The orbit toggle is also the reason `CameraController` has a subscription.
 * A gesture cancels the orbit at the controller, and this component holds no
 * copy of that fact — it reads `camera.orbiting` and re-reads it when the
 * controller says so. A local `useState` mirror would keep claiming the camera
 * was turning after the user had already grabbed it, which is the general
 * failure of a control whose label is a guess about state it does not own.
 */

import { useState, useSyncExternalStore } from 'react';

import { useCityScene } from '@/lib/city/scene';
import type { CameraController } from '@/lib/map/camera';
import { KEYBOARD_HELP } from '@/lib/map/camera';

/** No controller yet: a stable no-op pair, so the hook order never changes. */
const NO_SUBSCRIPTION = { subscribe: () => () => {}, version: 0 };

const BUTTON =
  'pointer-events-auto border border-ink-700 bg-ink-950/70 px-3 py-1.5 text-left font-mono ' +
  'text-[10px] tracking-[0.14em] uppercase backdrop-blur-md transition-colors ' +
  'hover:border-signal-400 focus-visible:border-signal-400 focus-visible:outline-none';

/**
 * The controller is a prop *or* the one in the scene store.
 *
 * The prop is what the unit tests drive, and it wins when given. The fallback
 * is what the page uses: this panel is rendered from the overlay rail, which
 * is several components away from the map that builds the controller, and
 * threading it through would mean prop-drilling through a component whose
 * whole job is lifecycle.
 */
export function CameraControls({ camera: given }: { readonly camera?: CameraController | null }) {
  const [keysOpen, setKeysOpen] = useState(false);
  const stored = useCityScene((state) => state.camera);
  const camera = given === undefined ? stored : given;
  const source = camera ?? NO_SUBSCRIPTION;
  // The server has no camera and no motion preference, so the server snapshot
  // is a constant — otherwise React warns about a mismatched hydration.
  useSyncExternalStore(
    source.subscribe,
    () => source.version,
    () => 0,
  );

  if (camera === null) return null;

  const orbiting = camera.orbiting;

  const toggleOrbit = (): void => {
    if (orbiting) {
      camera.stopOrbit();
      return;
    }
    // Around the middle of what is on screen. With no selection to orbit — that
    // is M4c — the centre is the only point the user has actually chosen, by
    // putting it there.
    camera.orbitAround(camera.getPose().center);
  };

  return (
    // Deliberately unpositioned. It used to place itself at `top-24 right-4`,
    // and the roster rail was later given the same corner — which covered these
    // buttons completely while every test kept passing, because Playwright's
    // "visible" means a non-empty box rather than a reachable one. `CityRail`
    // owns where everything on this side of the screen goes, so a panel can no
    // longer be hidden by a sibling that never knew it existed.
    // `shrink-0`, so the rail takes its slack out of the roster instead. These
    // are five fixed buttons; the roster is the only panel here whose height is
    // a function of the corpus, so it is the only one that should give.
    <div className="pointer-events-none flex w-44 shrink-0 flex-col items-stretch gap-2 self-end">
      <button type="button" className={`${BUTTON} text-paper-dim`} onClick={() => camera.reset()}>
        Reset view
      </button>

      {/* Reduced motion is a controller-level decision, and this is it made
          visible. The orbit button is gone rather than disabled: the controller
          refuses to orbit under that preference, so the button would do nothing
          — and a disabled control invites the user to work out how to enable it
          when the answer is in the operating system, not on this page. */}
      {camera.reducedMotion ? (
        <p className="pointer-events-auto border border-ink-800 bg-ink-950/70 p-2 font-mono text-[10px] leading-relaxed text-paper-faint backdrop-blur-md">
          Reduced motion is on. The camera cuts instead of flying, and does not orbit.
        </p>
      ) : (
        <button
          type="button"
          className={`${BUTTON} ${orbiting ? 'border-signal-400 text-signal-400' : 'text-paper-dim'}`}
          aria-pressed={orbiting}
          onClick={toggleOrbit}
        >
          {orbiting ? 'Stop orbit' : 'Orbit'}
        </button>
      )}

      <button
        type="button"
        className={`${BUTTON} text-paper-faint`}
        aria-expanded={keysOpen}
        onClick={() => setKeysOpen((open) => !open)}
      >
        {keysOpen ? 'Hide keys' : 'Keyboard'}
      </button>

      {keysOpen && (
        <dl className="pointer-events-auto grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 border border-ink-800 bg-ink-950/70 p-3 font-mono text-[10px] backdrop-blur-md">
          {KEYBOARD_HELP.map((row) => (
            <div key={row.keys} className="contents">
              <dt className="text-paper">{row.keys}</dt>
              <dd className="text-paper-faint">{row.does}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
