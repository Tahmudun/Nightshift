import { describe, expect, it } from 'vitest';

import {
  BUDGET_MS,
  createFrameTimer,
  describeRenderer,
  FRAME_WINDOW,
  type RendererIdentity,
} from './frameTimer';

/**
 * The instrument, before anything is measured with it.
 *
 * M4d's acceptance criterion is a pair of numbers, and a number is the easiest
 * thing in this project to publish dishonestly: it carries no units, no
 * conditions and no account of the machine that produced it. So these tests are
 * mostly about what the timer *refuses* to say — no percentiles from three
 * frames, no claim about a GPU it has not identified, and no silent inclusion
 * of the pause while a tab was in the background.
 */

/** Feed a run of frame timestamps, in ms, as if `render` had fired for each. */
function feed(timer: ReturnType<typeof createFrameTimer>, intervals: readonly number[]): void {
  let at = 1_000;
  timer.frame(at);
  for (const interval of intervals) {
    at += interval;
    timer.frame(at);
  }
}

describe('the frame timer', () => {
  it('reports nothing at all until it has a window to report on', () => {
    const timer = createFrameTimer();
    expect(timer.report()).toBeNull();

    feed(
      timer,
      Array.from({ length: 5 }, () => 16),
    );
    expect(timer.report(), 'five frames is not a measurement').toBeNull();
  });

  it('measures the intervals between frames, not the frames', () => {
    const timer = createFrameTimer();
    // One fewer interval than timestamps: the first `frame` starts the clock
    // and cannot itself be an interval. Getting this wrong puts a spurious
    // zero-length frame in every window and drags every percentile down.
    feed(
      timer,
      Array.from({ length: FRAME_WINDOW }, () => 16),
    );

    const report = timer.report()!;
    expect(report.frames).toBe(FRAME_WINDOW);
    expect(report.p50).toBe(16);
  });

  it('reports the slow tail rather than the average', () => {
    const timer = createFrameTimer();
    // Ninety fast frames and ten catastrophic ones. The mean is 26 ms and reads
    // like a healthy 38fps; the experience is a visible hitch ten times in a
    // hundred. §9 asks about the experience.
    const intervals = [
      ...Array.from({ length: (FRAME_WINDOW * 9) / 10 }, () => 5),
      ...Array.from({ length: FRAME_WINDOW / 10 }, () => 200),
    ];
    feed(timer, intervals);

    const report = timer.report()!;
    expect(report.p50).toBe(5);
    expect(report.p95).toBe(200);
    expect(report.worst).toBe(200);
    expect(report.missed).toBeCloseTo(0.1, 5);
  });

  /**
   * The defect the *first real measurement* found, in the instrument rather
   * than in the city.
   *
   * A display refreshing at 60 Hz presents frames 16.67 ms apart, and the
   * intervals a timer sees jitter either side of that — 16.6, 16.8, 16.6, 16.7.
   * Counting every interval strictly greater than the budget as a failure
   * therefore reports **about half of a perfectly vsync-locked city as over
   * budget**, which is what the first run of the metrics scenarios printed:
   * p50 of 16.7 ms — pinned at exactly 60fps — beside "53% over budget".
   *
   * A missed frame is not "a nanosecond late". It is the renderer failing to
   * present in time for the next refresh, which shows up as an interval of two
   * refreshes or thereabouts.
   */
  it('does not count vsync jitter as a missed frame', () => {
    const timer = createFrameTimer();
    feed(
      timer,
      Array.from({ length: FRAME_WINDOW }, (_, i) => (i % 2 === 0 ? 16.6 : 16.8)),
    );

    const report = timer.report()!;
    expect(report.p50).toBeGreaterThan(BUDGET_MS.desktop - 0.2);
    expect(report.missed, 'a city pinned at 60fps missed nothing').toBe(0);
  });

  it('counts a frame that missed the next refresh', () => {
    const timer = createFrameTimer();
    // One interval in ten is a doubled frame — the renderer missed a vsync and
    // the display showed the previous frame twice. That is the thing a person
    // sees as a stutter, and the only thing this number should be counting.
    feed(
      timer,
      Array.from({ length: FRAME_WINDOW }, (_, i) => (i % 10 === 0 ? 33.4 : 16.7)),
    );

    expect(timer.report()!.missed).toBeCloseTo(0.1, 2);
  });

  it('keeps only the most recent window, so a report is about now', () => {
    const timer = createFrameTimer();
    feed(
      timer,
      Array.from({ length: FRAME_WINDOW }, () => 200),
    );
    expect(timer.report()!.p50).toBe(200);

    // A window's worth of good frames after a bad patch: the report has to
    // follow the city, not remember it. A cumulative timer makes every
    // improvement invisible for as long as it has been running.
    feed(
      timer,
      Array.from({ length: FRAME_WINDOW }, () => 8),
    );
    expect(timer.report()!.p50).toBe(8);
    expect(timer.report()!.frames).toBe(FRAME_WINDOW);
  });

  it('throws away a gap no renderer produced', () => {
    const timer = createFrameTimer();
    feed(
      timer,
      Array.from({ length: FRAME_WINDOW }, () => 16),
    );

    // A backgrounded tab, a breakpoint, a laptop lid. The next `render` after
    // one of those is separated from the last by seconds, and counting it makes
    // the worst-frame number a measurement of how long nobody was looking.
    // Dropped rather than clamped: a clamped 250 ms frame is still a frame that
    // never happened.
    timer.frame(1_000 + FRAME_WINDOW * 16 + 9_000);
    const report = timer.report()!;
    expect(report.worst).toBe(16);
    expect(report.dropped).toBe(1);
  });

  it('names the frame rate it is judging against, and does not invent one', () => {
    // 60fps is 16.67 ms and 30fps is 33.33 ms — the two numbers `CLAUDE.md` §6
    // names. They are exported so a caller cannot quietly grade against 20fps.
    expect(BUDGET_MS.desktop).toBeCloseTo(1000 / 60, 5);
    expect(BUDGET_MS.mobile).toBeCloseTo(1000 / 30, 5);
  });

  it('grades against the budget it was given, not the one it prefers', () => {
    const timer = createFrameTimer({ budgetMs: BUDGET_MS.mobile });
    feed(
      timer,
      Array.from({ length: FRAME_WINDOW }, () => 20),
    );

    // 20 ms is over the desktop budget and inside the mobile one. A timer with
    // one hard-coded budget reports a phone that is meeting its target as
    // failing on every frame.
    expect(timer.report()!.missed).toBe(0);
    expect(createFrameTimer().budgetMs).toBeCloseTo(BUDGET_MS.desktop, 5);
  });

  it('resets to knowing nothing, rather than to knowing zero', () => {
    const timer = createFrameTimer();
    feed(
      timer,
      Array.from({ length: FRAME_WINDOW }, () => 16),
    );
    timer.reset();

    // Null, not a report of zero frames at 0 ms. A scenario runner that reads a
    // zeroed report between scenarios publishes "0.0 ms p95" for a scenario
    // that never ran, which is the most flattering possible lie.
    expect(timer.report()).toBeNull();
  });
});

/**
 * The half of this that M4c's review predicted would matter.
 *
 * A frame time with no account of the machine is not evidence. Headless
 * Chromium reports a renderer string naming SwiftShader — Google's software
 * rasteriser — and a p95 measured there is a fact about a CPU.
 */
describe('the renderer identity', () => {
  const gpu: RendererIdentity = {
    vendor: 'Google Inc. (Apple)',
    renderer: 'ANGLE (Apple, ANGLE Metal Renderer: Apple M4 Pro, Unspecified Version)',
  };

  it('accepts a real GPU as a real GPU', () => {
    const described = describeRenderer(gpu);
    expect(described.hardware).toBe(true);
    expect(described.summary).toContain('Apple M4 Pro');
  });

  it.each([
    ['SwiftShader', 'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (LLVM 16))), SwiftShader'],
    ['llvmpipe', 'llvmpipe (LLVM 15.0.7, 256 bits)'],
    ['the word software', 'ANGLE (Software Adapter, Direct3D11)'],
    ['Mesa’s soft renderer', 'Mesa/X.org, softpipe'],
  ])('refuses to call %s a GPU', (_what, renderer) => {
    const described = describeRenderer({ vendor: 'Google Inc.', renderer });
    expect(described.hardware).toBe(false);
    expect(described.caveat).toMatch(/software/i);
  });

  it('treats an unavailable identity as unknown, never as hardware', () => {
    // `WEBGL_debug_renderer_info` is absent in some privacy configurations, and
    // Firefox masks it by default. The honest reading of "we could not ask" is
    // not "it is fine": a number with no machine behind it cannot be published
    // as a desktop claim either.
    const described = describeRenderer(null);
    expect(described.hardware).toBe(false);
    expect(described.summary).toMatch(/unknown/i);
    expect(described.caveat).toMatch(/could not be identified/i);
  });
});
