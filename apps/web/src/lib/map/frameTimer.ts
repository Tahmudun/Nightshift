/**
 * How long the city's frames take, and what drew them.
 *
 * `CLAUDE.md` §6 makes M4's acceptance a pair of numbers — 60fps desktop, 30fps
 * mobile — and `city.md` §7 says they must be *"numbers in `PROGRESS.md` rather
 * than impressions"*. A number is the easiest thing in this project to publish
 * dishonestly, because it arrives with no units, no conditions and no account of
 * the machine that produced it.
 *
 * **So the renderer identity is part of the instrument, not a footnote.** The
 * browser suite runs headless Chromium, which has no GPU and rasterises through
 * SwiftShader on the CPU; a p95 measured there is a true statement about a
 * software rasteriser and a false one about a desktop. That is exactly the trap
 * M4c's review named — a corpus, or a machine, that cannot produce the failure
 * cannot test the guard against it — so nothing here reports a frame time
 * without reporting what drew the frames.
 *
 * Two more refusals, both learned from what the number is *for*:
 *
 * - **No mean.** Ninety frames at 5 ms and ten at 200 ms average to 26 ms and
 *   read as a healthy 38fps. The experience is a visible hitch ten times in a
 *   hundred, so this reports p50, p95, p99, the worst frame, and the share of
 *   frames that missed the next refresh.
 * - **No report before a window.** Three frames is not a measurement. `report()`
 *   returns null rather than a confident number from nothing.
 *
 * Pure: no MapLibre, no React, no `performance` — the caller passes the
 * timestamp. That is what lets the tests feed it a hundred frames in a
 * microsecond and assert what it says about them.
 */

/** The two frame budgets `CLAUDE.md` §6 names, in milliseconds. */
export const BUDGET_MS = {
  /** 60fps. */
  desktop: 1000 / 60,
  /** 30fps. */
  mobile: 1000 / 30,
} as const;

/**
 * How many frame intervals a report is computed from.
 *
 * 120 — about two seconds at 60fps. Long enough that one slow frame does not
 * dominate a percentile, short enough that a report is about the gesture
 * happening now rather than about the whole session. A cumulative timer makes
 * every improvement invisible for as long as it has been running.
 */
export const FRAME_WINDOW = 120;

/**
 * How far past the budget an interval must be before it counts as a miss.
 *
 * **This number exists because the first real measurement caught the instrument
 * lying.** A 60 Hz display presents frames 16.67 ms apart and the intervals
 * jitter either side of it — 16.6, 16.8, 16.6 — so counting everything strictly
 * greater than the budget reported a city pinned at exactly 60fps as "53% over
 * budget". The p50 in the same table was 16.7 ms. Both numbers were computed
 * correctly and one of them was nonsense.
 *
 * 1.5 is the standard reading: a renderer that fails to present in time for the
 * next refresh produces an interval of about two refreshes, and anything shorter
 * than one-and-a-half is a frame that arrived. It is what a person sees as a
 * stutter, which is the only thing this number is for.
 */
export const MISS_FACTOR = 1.5;

/**
 * A gap this long is not a slow frame; it is an absence of frames.
 *
 * A backgrounded tab, a breakpoint, or a laptop lid separates two `render`
 * events by seconds. Counted, that becomes the worst frame in the window and
 * turns the headline number into a measurement of how long nobody was looking.
 * Dropped rather than clamped — a clamped 250 ms frame is still a frame that
 * never happened — and counted separately, so a report can say how many.
 */
export const STALL_MS = 1_000;

export interface FrameReport {
  /** Intervals in this window. Never more than `FRAME_WINDOW`. */
  readonly frames: number;
  readonly p50: number;
  readonly p95: number;
  readonly p99: number;
  readonly worst: number;
  /**
   * Share of frames that missed the next refresh, 0–1.
   *
   * Not "slower than the budget" — see `MISS_FACTOR` for the measurement that
   * made the difference matter.
   */
  readonly missed: number;
  /** The budget this report was graded against, in ms. */
  readonly budgetMs: number;
  /** Gaps discarded as stalls since the last reset. */
  readonly dropped: number;
}

export interface FrameTimer {
  /** Record that a frame was presented at this timestamp, in ms. */
  frame(atMs: number): void;
  /** The current window, or null if there is not enough of one to speak about. */
  report(): FrameReport | null;
  /** Forget everything. Used between scenarios, so one cannot bleed into the next. */
  reset(): void;
  readonly budgetMs: number;
}

/**
 * The smallest window that may be reported on.
 *
 * A tenth of the full window. Below it the percentiles are being computed from
 * so few samples that p95 and `worst` are the same frame, which reads as
 * precision and is not.
 */
const MIN_FRAMES = FRAME_WINDOW / 10;

export function createFrameTimer(options?: { readonly budgetMs?: number }): FrameTimer {
  const budgetMs = options?.budgetMs ?? BUDGET_MS.desktop;
  /** A ring buffer would save an allocation and cost the reader ten minutes. */
  let intervals: number[] = [];
  let last: number | null = null;
  let dropped = 0;

  return {
    budgetMs,

    frame(atMs) {
      if (last === null) {
        // The first frame starts the clock and is not itself an interval.
        // Counting it puts a spurious zero-length frame in every window.
        last = atMs;
        return;
      }
      const interval = atMs - last;
      last = atMs;
      // Non-positive intervals come from a clock that was adjusted underneath
      // us, and there is nothing honest to do with one.
      if (interval <= 0) return;
      if (interval >= STALL_MS) {
        dropped += 1;
        return;
      }
      intervals.push(interval);
      if (intervals.length > FRAME_WINDOW) intervals = intervals.slice(-FRAME_WINDOW);
    },

    report() {
      if (intervals.length < MIN_FRAMES) return null;
      const sorted = [...intervals].sort((a, b) => a - b);
      const missedFrames = intervals.filter((interval) => interval > budgetMs * MISS_FACTOR).length;
      return {
        frames: sorted.length,
        p50: percentile(sorted, 0.5),
        p95: percentile(sorted, 0.95),
        p99: percentile(sorted, 0.99),
        worst: sorted[sorted.length - 1]!,
        missed: missedFrames / intervals.length,
        budgetMs,
        dropped,
      };
    },

    reset() {
      intervals = [];
      last = null;
      dropped = 0;
    },
  };
}

/**
 * Nearest-rank, on an ascending array.
 *
 * Not interpolated: an interpolated p95 reports a frame duration that no frame
 * had, which is a small invention in a number whose whole job is to be
 * believable.
 */
function percentile(sorted: readonly number[], fraction: number): number {
  const rank = Math.ceil(fraction * sorted.length);
  return sorted[Math.min(sorted.length - 1, Math.max(0, rank - 1))]!;
}

/** What `WEBGL_debug_renderer_info` says, when it says anything. */
export interface RendererIdentity {
  readonly vendor: string;
  readonly renderer: string;
}

export interface DescribedRenderer {
  /** Did hardware draw these frames? */
  readonly hardware: boolean;
  /** One line naming the machine, for a page and for `PROGRESS.md`. */
  readonly summary: string;
  /** What a number from this renderer may not be used to claim, or null. */
  readonly caveat: string | null;
}

/**
 * Every software rasteriser this product is likely to meet, by name.
 *
 * SwiftShader is Chromium's (and headless Chrome's default), llvmpipe and
 * softpipe are Mesa's, and "software adapter" is what ANGLE calls Direct3D's.
 * Matched case-insensitively against the renderer string.
 */
const SOFTWARE = ['swiftshader', 'llvmpipe', 'softpipe', 'software', 'swiftgl', 'microsoft basic'];

export function describeRenderer(identity: RendererIdentity | null): DescribedRenderer {
  if (identity === null) {
    // Absent under some privacy settings, and masked by Firefox by default. The
    // honest reading of "we could not ask" is *not* "it is fine": a frame time
    // with no machine behind it cannot be published as a desktop claim either.
    return {
      hardware: false,
      summary: 'Renderer unknown',
      caveat:
        'The graphics device could not be identified, so these frame times cannot be ' +
        'attributed to hardware.',
    };
  }

  const haystack = `${identity.vendor} ${identity.renderer}`.toLowerCase();
  const software = SOFTWARE.some((name) => haystack.includes(name));
  return {
    hardware: !software,
    summary: identity.renderer,
    caveat: software
      ? 'These frames were drawn by a software rasteriser on the CPU, not by a GPU. ' +
        'The numbers describe this machine’s processor and say nothing about a desktop ' +
        'or a phone.'
      : null,
  };
}

/**
 * Ask a live context what drew it, or null if it will not say.
 *
 * Separated from `describeRenderer` so the judgement above is testable without a
 * WebGL context, which is the half that has rules in it.
 */
export function identifyRenderer(
  gl: WebGLRenderingContext | WebGL2RenderingContext,
): RendererIdentity | null {
  const info = gl.getExtension('WEBGL_debug_renderer_info');
  if (!info) return null;
  const vendor = gl.getParameter(info.UNMASKED_VENDOR_WEBGL);
  const renderer = gl.getParameter(info.UNMASKED_RENDERER_WEBGL);
  if (typeof vendor !== 'string' || typeof renderer !== 'string') return null;
  return { vendor, renderer };
}
