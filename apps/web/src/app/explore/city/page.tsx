import Link from 'next/link';

import { CityMap } from '@/components/CityMap';
import { CitySignals } from '@/components/CitySignals';
import { basemapManifest, buildingsManifest } from '@/lib/tiles';

/**
 * The city, at M4c: New York with every open role floating above it.
 *
 * Not one of them is on a building, and that is the milestone rather than a
 * shortfall. `city.md` §4.1 measured that no ATS posting in this corpus names a
 * street, so a role reaches a structure only by inheriting an office a human
 * confirmed (§4.4, ADR 0024) — and `data/company-locations.yaml` is still
 * blank, which is a correct answer. §4.8 designs this state as **the default
 * view rather than the fallback**, and the field of untethered signals is what
 * that looks like.
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
          New York, drawn from a tile archive on this machine. No network, no key, no tile server.
          The signals above the skyline are open roles,{' '}
          <span className="text-paper">floating because nobody has said where they are</span> —
          until a company address has been confirmed, there is nothing this map is permitted to
          place on a building.
        </p>
        <Link
          href="/explore"
          className="mt-3 inline-block border border-ink-700 px-3 py-1.5 font-mono text-[10px] tracking-[0.14em] text-signal-400 uppercase hover:border-signal-400"
        >
          Back to the list
        </Link>
      </section>

      {/* Bottom right. What the field above the skyline actually contains, and
          why none of it is on a building. Fetches into the scene store; the
          renderer reads that store outside React. */}
      <CitySignals />

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
          <dd className="text-paper-dim">
            {buildingsManifest.structures.toLocaleString('en-US')} structures, NYC Open Data{' '}
            {buildingsManifest.protomaps_build}
          </dd>
          {/* §5.3: a footprint with no measured height takes a documented
              default *and is recorded as having taken it*. This is the record,
              on the page rather than in a comment, because a skyline presented
              as measured where part of it is a default is the kind of small lie
              this project does not keep a category of. */}
          <dt className="text-paper-faint">Heights</dt>
          <dd className="text-paper-dim">
            Measured roof heights, in feet.{' '}
            {buildingsManifest.structures_without_height.toLocaleString('en-US')} have none recorded
            and are drawn at a default 25 ft.
          </dd>
        </dl>
      </section>
    </CityMap>
  );
}
