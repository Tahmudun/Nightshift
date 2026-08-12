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
 */
export const metadata = {
  title: 'The city — Nightshift',
};

export default function CityPage() {
  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-[22px] font-medium tracking-tight text-paper">The city</h1>
        <p className="mt-1 max-w-2xl text-[14px] leading-relaxed text-paper-dim">
          New York, drawn from a tile archive on this machine. No network, no key, no tile server.{' '}
          <span className="text-paper">There are no jobs on it yet</span> — the signal layer is the
          next milestone, and until a company address has been confirmed there is nothing this map
          is permitted to place on a building.
        </p>
      </section>

      <CityMap />

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          What you are looking at
        </h2>
        <dl className="mt-3 grid gap-x-8 gap-y-2 font-mono text-[11px] sm:grid-cols-2">
          <div className="flex justify-between gap-4 border-b border-ink-800 pb-1">
            <dt className="text-paper-faint">Tiles</dt>
            <dd className="text-paper-dim">Protomaps build {basemapManifest.protomaps_build}</dd>
          </div>
          <div className="flex justify-between gap-4 border-b border-ink-800 pb-1">
            <dt className="text-paper-faint">OpenStreetMap as of</dt>
            <dd className="text-paper-dim">{basemapManifest.osm_replication_time}</dd>
          </div>
          <div className="flex justify-between gap-4 border-b border-ink-800 pb-1">
            <dt className="text-paper-faint">Detail to zoom</dt>
            <dd className="text-paper-dim">{basemapManifest.maxzoom}</dd>
          </div>
          <div className="flex justify-between gap-4 border-b border-ink-800 pb-1">
            <dt className="text-paper-faint">Licence</dt>
            <dd className="text-paper-dim">{basemapManifest.licence}</dd>
          </div>
        </dl>
        <p className="mt-3 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          Buildings are not drawn yet. The archive carries OpenStreetMap&rsquo;s own footprints with
          guessed heights; New York publishes measured ones, and the skyline waits for those rather
          than settling for the guess.
        </p>
      </section>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          The list is the full product
        </h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          Every role is reachable without this page, and always will be. The map is a second view of
          the list, never a replacement for it.
        </p>
        <Link
          href="/explore"
          className="mt-3 inline-block border border-ink-700 px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400 hover:border-signal-400"
        >
          Back to the list
        </Link>
      </section>
    </div>
  );
}
