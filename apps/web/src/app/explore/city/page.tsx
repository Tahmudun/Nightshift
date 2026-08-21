import Link from 'next/link';

import { CityMap } from '@/components/CityMap';
import { CityRail } from '@/components/CityRail';
import { basemapManifest, buildingsManifest } from '@/lib/tiles';

/**
 * The city: New York, with open roles standing on the buildings that have an
 * address and floating above the ones that do not.
 *
 * `city.md` §4.1 measured that no ATS posting in this corpus names a street, so
 * a role reaches a structure only by inheriting an office a human confirmed
 * (§4.4, ADR 0024). For four milestones nobody had confirmed one and every role
 * floated; §4.8 designs that state as **the default view rather than the
 * fallback**, which is why it was built first and built properly.
 *
 * The first addresses landed on 2026-08-17 and the copy below changed with
 * them. It had said "there is nothing this map is permitted to place on a
 * building" — true when written, false the moment somebody typed an address,
 * and the kind of sentence that goes on being read as current long after it
 * stops being true.
 *
 * A map that looks finished and is empty is indistinguishable from a map that
 * is broken, and the person looking at it should not have to guess which one
 * this is.
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
          The signals are open roles. One <span className="text-paper">standing on a roof</span> is
          at an office somebody confirmed and dated; one{' '}
          <span className="text-paper">floating free of the skyline</span> is at an employer who has
          published no address, and its position there means its employer and nothing about New
          York.
        </p>
        <Link
          href="/explore"
          className="mt-3 inline-block border border-ink-700 px-3 py-1.5 font-mono text-[10px] tracking-[0.14em] text-signal-400 uppercase hover:border-signal-400"
        >
          Back to the list
        </Link>
      </section>

      {/* The right rail: the camera controls, who is hiring, and what the field
          above the skyline actually contains. One component owns where all
          three go — see `CityRail`, which exists because two panels that each
          placed themselves ended up in the same corner. */}
      <CityRail />

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
