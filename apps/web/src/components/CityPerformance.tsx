'use client';

/**
 * How fast this city is drawing, and on what.
 *
 * `CLAUDE.md` §6 makes M4's acceptance a pair of numbers — 60fps desktop, 30fps
 * mobile — and `city.md` §7 asks that they be *"numbers in `PROGRESS.md` rather
 * than impressions"*. A number that only ever appears in a document is a number
 * nobody can check, so it is on the screen it describes as well.
 *
 * **The renderer line is not a detail; it is the reason this panel is
 * trustworthy.** A frame time with no account of the machine cannot be read: 40
 * ms on a phone and 40 ms on a workstation are different sentences, and 40 ms on
 * a software rasteriser is not a sentence about graphics hardware at all. When
 * the frames were drawn on the CPU this panel says so, in words, above the
 * numbers. That is M4c's finding carried forward — an instrument that cannot
 * report the conditions of its measurement will eventually publish one.
 *
 * **It polls; it is not pushed.** The timer is a handle in the scene store and
 * this reads it twice a second. Writing a frame time into the store would be a
 * store write sixty times a second and a re-render of every subscriber, so the
 * instrument would become the largest thing it measures. Two renders a second
 * is a cost this panel can pay for itself.
 */

import { useEffect, useState } from 'react';

import { useCityScene } from '@/lib/city/scene';
import { BUDGET_MS, type FrameReport } from '@/lib/map/frameTimer';

const PANEL = 'pointer-events-auto border border-ink-700/80 bg-ink-950/70 backdrop-blur-md';

/** Twice a second. Fast enough to feel live, slow enough to be free. */
const POLL_MS = 500;

/** Frames per second, from a frame duration. */
function fps(ms: number): string {
  if (ms <= 0) return '—';
  return (1000 / ms).toFixed(0);
}

export function CityPerformance() {
  const frames = useCityScene((state) => state.frames);
  const renderer = useCityScene((state) => state.renderer);
  const [report, setReport] = useState<FrameReport | null>(null);

  useEffect(() => {
    if (frames === null) {
      setReport(null);
      return;
    }
    const id = setInterval(() => setReport(frames.report()), POLL_MS);
    return () => clearInterval(id);
  }, [frames]);

  if (frames === null) return null;

  return (
    <section aria-labelledby="city-performance-heading" className={`shrink-0 p-4 ${PANEL}`}>
      <h2
        id="city-performance-heading"
        className="font-mono text-[10px] tracking-[0.16em] text-paper-faint uppercase"
      >
        How this is drawing
      </h2>

      {report === null ? (
        // Not "0 fps", and not a spinner. The city paints only when something
        // is moving — an idle map with reduced motion on presents no frames at
        // all — so "nothing to measure" is a normal, correct state and saying
        // it is more useful than implying a stall.
        <p className="mt-2 text-[12px] leading-relaxed text-paper-dim">
          Nothing has been drawn recently enough to measure. The city paints only when something
          moves; take hold of it and this fills in.
        </p>
      ) : (
        <>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 font-mono text-[11px]">
            <dt className="text-signal-400">Typical</dt>
            <dd className="text-paper-dim">
              {report.p50.toFixed(1)} ms · {fps(report.p50)} fps
            </dd>
            <dt className="text-paper-faint">Slowest 5%</dt>
            <dd className="text-paper-dim">
              {report.p95.toFixed(1)} ms · {fps(report.p95)} fps
            </dd>
            <dt className="text-paper-faint">Worst frame</dt>
            <dd className="text-paper-dim">{report.worst.toFixed(1)} ms</dd>
            <dt className="text-paper-faint">Missed</dt>
            <dd className="text-paper-dim">
              {(report.missed * 100).toFixed(0)}% of {report.frames} frames missed the next refresh,
              against {report.budgetMs === BUDGET_MS.desktop ? '60' : '30'} fps
            </dd>
          </dl>
          {report.dropped > 0 && (
            // Named rather than absorbed. A gap of seconds is not a slow frame,
            // and a "worst frame: 9,412 ms" that was really a backgrounded tab
            // is the kind of number that makes a whole panel untrustworthy.
            <p className="mt-2 text-[11px] leading-relaxed text-paper-dim">
              {report.dropped.toLocaleString('en-US')}{' '}
              {report.dropped === 1 ? 'gap was' : 'gaps were'} discarded as pauses rather than
              counted as slow frames.
            </p>
          )}
        </>
      )}

      {renderer !== null && (
        <p className="mt-3 text-[12px] leading-relaxed text-paper-dim">
          <span className={renderer.hardware ? 'text-paper' : 'text-gold-400'}>
            {renderer.summary}
          </span>
          {renderer.caveat !== null && <> — {renderer.caveat}</>}
        </p>
      )}
    </section>
  );
}
