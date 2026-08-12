'use client';

/**
 * New York, dark, from a file on this machine — and filling the window.
 *
 * The component's whole job is lifecycle: create one map, hand it the style,
 * and take it down completely. Everything about how the city *looks* is in
 * `lib/map/darkStyle.ts`, where it can be tested without a GPU — a 400-line
 * component that renders a map, fetches data and holds filter state is named as
 * an anti-pattern in `CLAUDE.md` §8, and the way to not write one is to keep
 * the style out of it from the first commit.
 *
 * **The map is the page, not a panel on it.** The canvas is fixed to the
 * viewport and everything else floats above it, including the app header, which
 * is translucent and lets the city show through. The first version put the city
 * in a 70vh box on a scrolling document and it read as a widget — which is what
 * it was. §9 asks for an immersive interface and a boxed map cannot be one.
 * Overlays are passed in as `children` so their positioning lives here, in the
 * one file that knows where the canvas is.
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
 * spent an ADR avoiding.
 *
 * **Teardown removes the map.** `map.remove()` releases the WebGL context, and
 * a context leaked per navigation reaches the browser's limit — around sixteen
 * — after which every later map fails to create with an error that names none
 * of this.
 */

import { useEffect, useRef, useState } from 'react';

import { BASEMAP_BOUNDS, BASEMAP_URL, BUILDINGS_URL } from '@/lib/tiles';
import { buildDarkStyle } from '@/lib/map/darkStyle';

// MapLibre's own stylesheet, for the attribution control and the canvas
// positioning. A static import so Next can hoist it into the CSS bundle; the
// *library* is still loaded lazily below, which is the part that costs 800 KB.
import 'maplibre-gl/dist/maplibre-gl.css';

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
 */
const INITIAL = {
  center: [-73.9903, 40.7449] as [number, number],
  zoom: 13.6,
  pitch: 76,
  bearing: 202,
} as const;

/**
 * `addProtocol` writes into a module-global registry and registering twice is a
 * silent overwrite rather than an error, so the guard has to live out here —
 * component state would re-register on every mount.
 */
let protocolRegistered = false;

type Status =
  | { readonly kind: 'loading' }
  | { readonly kind: 'ready' }
  | { readonly kind: 'unavailable'; readonly detail: string };

/**
 * Ask the tile route for an archive's first sixteen bytes.
 *
 * Returns the server's own explanation on failure, because the route's 503 body
 * is a sentence written for exactly this moment.
 */
async function probeArchive(url: string, name: string): Promise<string | null> {
  try {
    const response = await fetch(url, { headers: { Range: 'bytes=0-15' } });
    if (response.ok) return null;
    const detail = (await response.text()).trim();
    return detail || `The ${name} route answered ${response.status}.`;
  } catch (error) {
    return `Could not reach the ${name} route: ${String(error)}`;
  }
}

export function CityMap({ children }: { readonly children?: React.ReactNode }) {
  const container = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'loading' });
  /** The route's explanation for a missing skyline, or null when there is one. */
  const [skyline, setSkyline] = useState<string | null>(null);

  // Stand down the document shell — the centred column, the page padding, the
  // footer — for as long as this map is mounted. The rules live in globals.css
  // beside the shell they modify; this only flips the switch, and it flips it
  // back on unmount so navigating away does not leave the rest of the product
  // unable to scroll.
  useEffect(() => {
    document.documentElement.setAttribute('data-immersive', '');
    return () => document.documentElement.removeAttribute('data-immersive');
  }, []);

  useEffect(() => {
    // React mounts effects twice in development. `cancelled` keeps the second
    // mount from adopting a map the first one is still building, which would
    // leak the first WebGL context for the life of the page.
    let cancelled = false;
    let map: { remove: () => void } | null = null;

    void (async () => {
      try {
        await build();
      } catch (error) {
        // An exception during setup — an invalid style, a renderer that will
        // not construct — otherwise leaves the spinner turning forever, which
        // is the least informative failure this component can produce. It looks
        // exactly like a slow load.
        if (!cancelled) setStatus({ kind: 'unavailable', detail: String(error) });
      }
    })();

    async function build(): Promise<void> {
      // Two archives, and they fail differently. Without the basemap there is no
      // map at all and the honest thing is the card. Without the buildings there
      // is a city with a flat skyline, which is a real map missing a real thing —
      // so it draws, and says what is missing, rather than hiding New York
      // behind an error about a file.
      const [problem, skylineProblem] = await Promise.all([
        probeArchive(BASEMAP_URL, 'basemap'),
        probeArchive(BUILDINGS_URL, 'buildings'),
      ]);
      if (cancelled) return;
      if (problem !== null) {
        setStatus({ kind: 'unavailable', detail: problem });
        return;
      }
      setSkyline(skylineProblem);

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
        style: buildDarkStyle({ buildings: skylineProblem === null }),
        ...INITIAL,
        // The archive covers New York and nothing else. Panning past its edge
        // would show empty tiles, which reads as a broken map rather than as
        // the edge of the data.
        maxBounds: [
          [BASEMAP_BOUNDS.west, BASEMAP_BOUNDS.south],
          [BASEMAP_BOUNDS.east, BASEMAP_BOUNDS.north],
        ],
        // Past about 78° the ground plane approaches edge-on and the tile
        // budget explodes for a view of almost nothing. The sky is already
        // fully in frame well before that.
        maxPitch: 78,
        attributionControl: { compact: true },
      });

      // Ready means "the style is applied and a frame has painted" — nothing
      // about tiles.
      //
      // Both of MapLibre's obvious signals are wrong here, for the same reason.
      // `load` and `isStyleLoaded()` each wait for every source in the viewport
      // to finish loading, and this viewport reaches past the edge of a
      // city-sized archive: at high pitch you are looking at New Jersey, New
      // York's archive has no tiles there, and the source never reports itself
      // loaded. Both were observed never firing. The card would then sit over a
      // perfectly good city forever.
      //
      // What the card covers is an unpainted canvas, so a painted frame is the
      // honest thing to wait for — and it is the *only* thing waited for.
      //
      // This was `once('styledata')` wrapping `once('render')`, and the second
      // archive broke it. The buildings TileJSON resolves seconds after the
      // basemap's, so `styledata` now arrives long after New York is on screen;
      // the nested listener then waits for the *next* frame, which on an idle
      // map may be a long way off. Measured: the card sat over a fully drawn
      // city for more than ten seconds. A style that has not been applied cannot
      // produce a painted frame anyway, so the outer wait was buying nothing.
      created.once('render', () => {
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
    <div className="fixed inset-0 z-0 bg-ink-950">
      <div
        ref={container}
        // Sized with `h-full w-full`, not `absolute inset-0`, and that is not a
        // style preference. MapLibre's own stylesheet sets
        // `.maplibregl-map { position: relative }`, it is imported after
        // globals.css, and it therefore beats Tailwind's `absolute` on equal
        // specificity — which silently drops `inset-0` and leaves the container
        // at its content height. The canvas rendered 300px tall for the whole
        // of Task 2 because of this, inside a box that hid it.
        //
        // MapLibre also owns everything inside this node, so React must never
        // try to reconcile its children.
        className="h-full w-full"
        role="application"
        aria-label="New York City map. Every role on this map is also in the list view."
      />

      {/* Overlays sit above the canvas and below the app header. `pointer-events`
          is off on the layer and back on inside each panel, so a gap between
          panels is still a place you can drag the city by. */}
      <div className="pointer-events-none absolute inset-0 z-10">{children}</div>

      {/* A city drawing without its skyline says so, in place, rather than
          looking like a New York where nothing was ever built. I3's habit of
          mind applied to a renderer: the absence of the archive is not evidence
          the buildings are not there. */}
      {status.kind === 'ready' && skyline !== null && (
        <div className="absolute right-3 bottom-9 z-20 max-w-sm border border-ink-700 bg-ink-950/90 p-3 backdrop-blur-sm">
          <h2 className="font-mono text-[10px] tracking-[0.16em] text-gold-400 uppercase">
            No skyline
          </h2>
          <p className="mt-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-paper-dim">
            {skyline}
          </p>
        </div>
      )}

      {status.kind !== 'ready' && (
        <div className="absolute inset-0 z-20 grid place-items-center p-6">
          <div className="max-w-lg border border-ink-700 bg-ink-950/90 p-5 backdrop-blur-sm">
            {status.kind === 'loading' ? (
              <p className="font-mono text-[10px] tracking-[0.16em] text-paper-faint uppercase">
                Drawing the city…
              </p>
            ) : (
              <>
                <h2 className="font-mono text-[10px] tracking-[0.16em] text-alert-400 uppercase">
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
