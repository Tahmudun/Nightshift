'use client';

/**
 * Fetches the city's roles, writes them to the scene store, and says what the
 * field on screen actually contains.
 *
 * **It renders no map and holds no map state.** `CLAUDE.md` §8 names the
 * 400-line component that renders a map, fetches data and holds filter state as
 * an anti-pattern; the way to not write one is to keep the fetch in a different
 * file from the renderer, with a store between them. This is that file. It
 * writes to `useCityScene` and the custom layer reads it — outside React, so a
 * poll resolving updates an instance buffer rather than re-rendering a
 * component that owns a WebGL context.
 *
 * **The readout is not decoration.** With no confirmed office anywhere in the
 * database, every role in the corpus is unresolved, and a field of floating
 * signals with no explanation is indistinguishable from a bug. §4.8 asks that
 * this be a good screen rather than a placeholder someone tolerates, and the
 * first requirement of a good screen is that it says what it is.
 */

import { useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

import { ApiError, fetchCitySignals } from '@/lib/api';
import { useCityScene } from '@/lib/city/scene';

const PANEL = 'pointer-events-auto border border-ink-700/80 bg-ink-950/70 backdrop-blur-md';

export function CitySignals() {
  const { data, error } = useQuery({
    queryKey: ['city-signals'],
    queryFn: () => fetchCitySignals(),
    // The corpus changes when a poll runs, not between two blinks. Refetching
    // on every window focus would rebuild the instance buffer for a city that
    // has not changed.
    refetchOnWindowFocus: false,
  });

  const setSignals = useCityScene((state) => state.setSignals);
  const setUnavailable = useCityScene((state) => state.setUnavailable);

  useEffect(() => {
    if (data) setSignals(data.signals);
  }, [data, setSignals]);

  useEffect(() => {
    if (error) {
      setUnavailable(
        error instanceof ApiError
          ? error.message
          : 'The roles could not be loaded, and the reason was not reported.',
      );
    }
  }, [error, setUnavailable]);

  if (error) {
    // I3's habit of mind applied to a renderer: an unreachable API is not
    // evidence that nobody is hiring. An empty sky with no explanation says
    // exactly that, so the sky says why instead.
    return (
      <section
        aria-labelledby="city-signals-heading"
        className={`absolute right-4 bottom-9 z-20 max-w-sm p-4 ${PANEL}`}
      >
        <h2
          id="city-signals-heading"
          className="font-mono text-[10px] tracking-[0.16em] text-alert-400 uppercase"
        >
          No roles on the city
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-paper-dim">
          The API could not be reached, so this map is showing none of the corpus. An empty sky here
          is a missing connection, not an empty market.
        </p>
      </section>
    );
  }

  if (!data) return null;

  const { counts, truncated } = data;

  return (
    // Named so it is a landmark rather than an anonymous box: §5.6 requires a
    // non-3D equivalent for everything the map says, and a screen reader
    // reaching this account of the city is that equivalent.
    <section
      aria-labelledby="city-signals-heading"
      className={`absolute right-4 bottom-9 z-20 max-w-sm p-4 ${PANEL}`}
    >
      <h2
        id="city-signals-heading"
        className="font-mono text-[10px] tracking-[0.16em] text-paper-faint uppercase"
      >
        What is on the city
      </h2>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 font-mono text-[11px]">
        <dt className="text-signal-400">Floating</dt>
        <dd className="text-paper-dim">
          {counts.unresolved.toLocaleString('en-US')} of {counts.total.toLocaleString('en-US')}{' '}
          roles, grouped by employer
        </dd>
        <dt className="text-paper-faint">On a building</dt>
        <dd className="text-paper-dim">{counts.building.toLocaleString('en-US')}</dd>
        <dt className="text-paper-faint">In an area</dt>
        <dd className="text-paper-dim">{counts.area.toLocaleString('en-US')}</dd>
      </dl>
      <p className="mt-3 text-[12px] leading-relaxed text-paper-dim">
        {counts.building === 0 ? (
          <>
            <span className="text-paper">Nothing is on a building yet</span>, because no posting in
            this corpus names a street — 0 of 247 measured. A role stands on a structure only by
            inheriting an office a person confirmed. Until then it floats, connected to nothing, and
            its position here means its employer and nothing about New York.
          </>
        ) : (
          <>
            A role stands on a structure only by inheriting an office a person confirmed. A floating
            signal is connected to nothing, and its position means its employer and nothing about
            New York.
          </>
        )}
      </p>
      {truncated ? (
        <p className="mt-2 font-mono text-[10px] tracking-[0.12em] text-gold-400 uppercase">
          Showing the first {data.limit.toLocaleString('en-US')} — this is a partial city
        </p>
      ) : null}
    </section>
  );
}
