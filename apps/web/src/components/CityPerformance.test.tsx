import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CityPerformance } from './CityPerformance';
import { useCityScene } from '@/lib/city/scene';
import { BUDGET_MS, createFrameTimer, type FrameReport } from '@/lib/map/frameTimer';

/**
 * The panel that publishes M4's acceptance numbers.
 *
 * Its one job beyond arithmetic is to make a number unreadable-in-isolation
 * impossible: every frame time appears with the machine that produced it, and
 * when that machine is a software rasteriser the panel says so before it says
 * anything else about speed.
 */

function reportOf(overrides: Partial<FrameReport> = {}): FrameReport {
  return {
    frames: 120,
    p50: 16,
    p95: 28,
    p99: 40,
    worst: 52,
    missed: 0.25,
    budgetMs: BUDGET_MS.desktop,
    dropped: 0,
    ...overrides,
  };
}

/** A timer stub that answers with whatever the test wants to publish. */
function timerReporting(report: FrameReport | null) {
  const timer = createFrameTimer();
  return { ...timer, report: () => report };
}

beforeEach(() => {
  vi.useFakeTimers();
  act(() => {
    useCityScene.setState({ frames: null, renderer: null });
  });
});

afterEach(() => {
  vi.useRealTimers();
});

/** Render, then let one poll interval elapse. */
function show(): void {
  render(<CityPerformance />);
  act(() => {
    vi.advanceTimersByTime(600);
  });
}

describe('the frame-time panel', () => {
  it('is absent entirely when there is no map to measure', () => {
    show();
    expect(screen.queryByRole('region', { name: /how this is drawing/i })).toBeNull();
  });

  it('says there is nothing to measure rather than showing a zero', () => {
    act(() => {
      useCityScene.setState({ frames: timerReporting(null), renderer: null });
    });
    show();

    // An idle city paints nothing on purpose. "0 fps" would read as a stall for
    // what is actually the renderer doing exactly what it was designed to.
    expect(screen.getByText(/nothing has been drawn recently enough to measure/i)).toBeVisible();
    expect(screen.queryByText(/0 fps/)).toBeNull();
  });

  it('reports the slow tail, not only the typical frame', () => {
    act(() => {
      useCityScene.setState({ frames: timerReporting(reportOf()), renderer: null });
    });
    show();

    expect(screen.getByText(/16\.0 ms · 63 fps/)).toBeVisible();
    expect(screen.getByText(/28\.0 ms · 36 fps/)).toBeVisible();
    expect(
      screen.getByText(/25% of 120 frames missed the next refresh, against 60 fps/),
    ).toBeVisible();
  });

  it('will not let a software rasteriser be read as a graphics card', () => {
    act(() => {
      useCityScene.setState({
        frames: timerReporting(reportOf()),
        renderer: {
          hardware: false,
          summary: 'SwiftShader Device (LLVM 16)',
          caveat: 'These frames were drawn by a software rasteriser on the CPU, not by a GPU.',
        },
      });
    });
    show();

    // The panel is at its most dangerous here: the numbers look like ordinary
    // frame times and mean something entirely different. This is the assertion
    // that keeps them from being quoted as a desktop claim.
    expect(screen.getByText(/software rasteriser on the CPU/i)).toBeVisible();
    expect(screen.getByText('SwiftShader Device (LLVM 16)')).toBeVisible();
  });

  it('names a discarded pause instead of counting it as a slow frame', () => {
    act(() => {
      useCityScene.setState({
        frames: timerReporting(reportOf({ dropped: 2 })),
        renderer: null,
      });
    });
    show();

    expect(screen.getByText(/2 gaps were discarded as pauses/i)).toBeVisible();
  });

  it('stops polling when the map goes away', () => {
    const timer = createFrameTimer();
    const report = vi.spyOn(timer, 'report');
    act(() => {
      useCityScene.setState({ frames: timer, renderer: null });
    });
    show();
    const polls = report.mock.calls.length;
    expect(polls).toBeGreaterThan(0);

    act(() => {
      useCityScene.setState({ frames: null, renderer: null });
    });
    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    // An interval left running after unmount reads a timer whose map has been
    // destroyed, which is the leak that outlives the page it belonged to.
    expect(report.mock.calls.length).toBe(polls);
  });
});
