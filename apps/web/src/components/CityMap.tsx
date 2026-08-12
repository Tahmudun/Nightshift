'use client';

/**
 * New York, dark, from a file on this machine.
 *
 * The component's whole job is lifecycle: create one map, hand it the style,
 * and take it down completely. Everything about how the city *looks* is in
 * `lib/map/darkStyle.ts`, where it can be tested without a GPU — a 400-line
 * component that renders a map, fetches data and holds filter state is named as
 * an anti-pattern in `CLAUDE.md` §8, and the way to not write one is to keep
 * the style out of it from the first commit.
 *
 * Three things here are deliberate rather than incidental.
 *
 * **MapLibre is imported inside the effect**, not at module scope. It touches
 * `window` and it is roughly 800 KB; a static import would break server
 * rendering and would ship the renderer to everybody reading a list.
 *
 * **MapLibre is pinned to v5 and that is load-bearing.** On v6.3.0 this map
 * builds, resolves the pmtiles TileJSON on the main thread, fires
 * `sourcedataloading`, and then hangs forever: no tile request, no `load`, no
 * `error`. Tile fetches go through a web worker, and v6's worker-side bridge for
 * custom protocols does not reach `pmtiles@4.5.0`. It fails as a silent stall
 * rather than an exception, which is why it cost an evening — see PROGRESS.
 * Upgrading needs a `pmtiles` release that names v6, and this comment as the
 * test to run.
 *
 * **The archive is probed before the map is built.** Sixteen bytes. If the tile
 * route answers 503 — a clean clone that never ran `make setup` — this shows
 * that response's own text, which was written to name the command that fixes
 * it. Letting MapLibre discover the problem instead produces a blank canvas and
 * a decoding error from inside pmtiles.js, which is the failure `city.md` §5.2
 * spent an ADR avoiding. It would be a waste to write that message and then not
 * show it to anybody.
 *
 * **Teardown removes the map.** `map.remove()` releases the WebGL context, and
 * a context leaked per navigation reaches the browser's limit — around sixteen
 * — after which every later map fails to create with an error that names none
 * of this.
 */

import { useEffect, useRef, useState } from 'react';

import { BASEMAP_BOUNDS, BASEMAP_URL } from '@/lib/basemap';
import { buildDarkStyle } from '@/lib/map/darkStyle';

// MapLibre's own stylesheet, for the attribution control and the canvas
// positioning. A static import so Next can hoist it into the CSS bundle; the
// *library* is still loaded lazily below, which is the part that costs 800 KB.
import 'maplibre-gl/dist/maplibre-gl.css';

/** Midtown, looking downtown. A starting view, not yet a camera — that is Task 4. */
const INITIAL = {
  center: [-73.9855, 40.7484] as [number, number],
  zoom: 12.5,
  pitch: 55,
  bearing: -17.5,
} as const;

/**
 * `addProtocol` writes into a module-global registry and registering twice is a
 * silent overwrite rather than an error, so the guard has to live out here —
 * component state would re-register on every mount. MapLibre v6 exposes no way
 * to ask whether a protocol is already registered.
 */
let protocolRegistered = false;

type Status =
  | { readonly kind: 'loading' }
  | { readonly kind: 'ready' }
  | { readonly kind: 'unavailable'; readonly detail: string };

/**
 * Ask the tile route for the archive's first sixteen bytes.
 *
 * Returns the server's own explanation on failure, because the route's 503 body
 * is a sentence written for exactly this moment.
 */
async function probeArchive(): Promise<string | null> {
  try {
    const response = await fetch(BASEMAP_URL, { headers: { Range: 'bytes=0-15' } });
    if (response.ok) return null;
    const detail = (await response.text()).trim();
    return detail || `The basemap route answered ${response.status}.`;
  } catch (error) {
    return `Could not reach the basemap route: ${String(error)}`;
  }
}

export function CityMap() {
  const container = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'loading' });

  useEffect(() => {
    // React 18+ mounts effects twice in development. `cancelled` keeps the
    // second mount from adopting a map the first one is still building, which
    // would leak the first context for the life of the page.
    let cancelled = false;
    let map: { remove: () => void } | null = null;

    void (async () => {
      try {
        await build();
      } catch (error) {
        // An exception during setup — an invalid style, a renderer that will
        // not construct — otherwise leaves the spinner turning forever, which
        // is the least informative failure this component can produce. It
        // looks exactly like a slow load.
        if (!cancelled) {
          setStatus({ kind: 'unavailable', detail: String(error) });
        }
      }
    })();

    async function build(): Promise<void> {
      const problem = await probeArchive();
      if (cancelled) return;
      if (problem !== null) {
        setStatus({ kind: 'unavailable', detail: problem });
        return;
      }

      const [maplibregl, pmtiles] = await Promise.all([import('maplibre-gl'), import('pmtiles')]);
      if (cancelled || !container.current) return;

      // The protocol is stateless and global, so one registration serves every
      // map this page ever creates.
      if (!protocolRegistered) {
        maplibregl.addProtocol('pmtiles', new pmtiles.Protocol().tile);
        protocolRegistered = true;
      }

      const created = new maplibregl.Map({
        container: container.current,
        style: buildDarkStyle(),
        ...INITIAL,
        // The archive covers New York and nothing else. Panning past its edge
        // would show empty tiles, which reads as a broken map rather than as
        // the edge of the data.
        maxBounds: [
          [BASEMAP_BOUNDS.west, BASEMAP_BOUNDS.south],
          [BASEMAP_BOUNDS.east, BASEMAP_BOUNDS.north],
        ],
        maxPitch: 75,
        // The city is the point; MapLibre's default control set is not.
        attributionControl: { compact: true },
      });

      created.on('load', () => {
        if (!cancelled) setStatus({ kind: 'ready' });
      });
      created.on('error', (event: { error?: { message?: string } }) => {
        if (cancelled) return;
        setStatus({
          kind: 'unavailable',
          detail: event.error?.message ?? 'MapLibre reported an error with no message.',
        });
      });

      if (cancelled) {
        created.remove();
        return;
      }
      map = created;
    }

    return () => {
      cancelled = true;
      map?.remove();
    };
  }, []);

  return (
    <div className="relative h-[70vh] min-h-[420px] w-full border border-ink-700 bg-ink-950">
      <div
        ref={container}
        // MapLibre owns everything inside this node, so React must never try to
        // reconcile its children.
        className="absolute inset-0"
        role="application"
        aria-label="New York City map. Every role on this map is also in the list below."
      />

      {status.kind !== 'ready' && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center p-6">
          <div className="pointer-events-auto max-w-lg border border-ink-700 bg-ink-950/90 p-5">
            {status.kind === 'loading' ? (
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
                Drawing the city…
              </p>
            ) : (
              <>
                <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
                  The map cannot be drawn
                </h2>
                <p className="mt-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-paper-dim">
                  {status.detail}
                </p>
                <p className="mt-3 text-[13px] leading-relaxed text-paper-dim">
                  Nothing else is affected. The list view is the full product and does not need the
                  map.
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
