import Link from 'next/link';

import { CityMap } from '@/components/CityMap';
import { basemapManifest } from '@/lib/basemap';

/**
 * The city, at M4b: New York with no jobs on it.
 *
 * That is the milestone rather than a shortfall. `city.md` §7 puts the basemap
 * and the camera in M4b and the signal layer in M4c, because a renderer over
 * zero coordinates has nothing it is permitted to draw — invariant I1 — and
 * building it in the other order means writing the interesting half against
 * placeholder data and then rewriting it.
 *
 * The page says so on screen, in the same words. A map that looks finished and
 * is empty is indistinguishable from a map that is broken, and the person
 * looking at it should not have to guess which one this is.
 *
 * Everything here is an overlay. The map is fixed to the viewport and this page
 * contributes no document flow at all, so there is nothing to scroll and the
 * city is the whole surface.
 */
export const metadata = {
  title: 'The city — Nightshift',
};

/** Shared panel treatment: readable over a moving image, without a hard box. */
const PANEL = 'pointer-events-auto border border-ink-700/80 bg-ink-950/70 backdrop-blur-md';

export default function CityPage() {
  return (
    <CityMap>
      {/* Top left, clear of the header. What this is, and what it is not. */}
      <section className={`absolute top-24 left-4 max-w-sm p-4 sm:left-6 ${PANEL}`}>
        <h1 className="text-[18px] font-medium tracking-tight text-paper">The city</h1>
        <p className="mt-1.5 text-[13px] leading-relaxed text-paper-dim">
          New York, drawn from a tile archive on this machine. No network, no key, no tile server.{' '}
          <span className="text-paper">There are no roles on it yet</span> — until a company address
          has been confirmed, there is nothing this map is permitted to place on a building.
        </p>
        <Link
          href="/explore"
          className="mt-3 inline-block border border-ink-700 px-3 py-1.5 font-mono text-[10px] tracking-[0.14em] text-signal-400 uppercase hover:border-signal-400"
        >
          Back to the list
        </Link>
      </section>

      {/* Bottom left, out of the way of the attribution control. Provenance:
          how old the world in these tiles is, and who it belongs to. */}
      <section
        className={`absolute bottom-4 left-4 hidden max-w-md p-4 sm:left-6 sm:block ${PANEL}`}
      >
        <h2 className="font-mono text-[10px] tracking-[0.16em] text-paper-faint uppercase">
          What you are looking at
        </h2>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 font-mono text-[11px]">
          <dt className="text-paper-faint">Tiles</dt>
          <dd className="text-paper-dim">Protomaps build {basemapManifest.protomaps_build}</dd>
          <dt className="text-paper-faint">World as of</dt>
          <dd className="text-paper-dim">{basemapManifest.osm_replication_time}</dd>
          <dt className="text-paper-faint">Buildings</dt>
          <dd className="text-paper-dim">Not drawn yet — waiting on measured heights</dd>
        </dl>
      </section>
    </CityMap>
  );
}
