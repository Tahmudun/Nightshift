/**
 * The closure vocabulary.
 *
 * The load-bearing test is the one asserting that `possibly_stale` and
 * `unverified` do not read alike. They are the two facts invariant I3 exists to
 * keep apart — one is evidence about the job, the other only about the source —
 * and if the interface blurs them, the invariant is true in the database and
 * false to the person reading the screen.
 */

import { describe, expect, it } from 'vitest';

import { JOB_STATUS_ORDER, JOB_STATUS_SCALE, jobStatusMeta } from './jobStatus';
import { jobStatusSchema } from './schemas';

describe('job status vocabulary', () => {
  it('covers exactly the states the API can send', () => {
    expect(new Set(JOB_STATUS_ORDER)).toEqual(new Set(jobStatusSchema.options));
  });

  it('orders the states as a life cycle, not an alphabet', () => {
    expect(JOB_STATUS_ORDER).toEqual(['open', 'possibly_stale', 'unverified', 'closed']);
  });

  it('throws rather than silently accepting an unrecognised status', () => {
    // A fallback would render an unknown state as though it were fine, which is
    // the one direction this must never fail in.
    expect(() => jobStatusMeta('invented' as never)).toThrow(/unrecognised job status/);
  });

  it('gives every state a distinct plain-language meaning', () => {
    const meanings = JOB_STATUS_SCALE.map((meta) => meta.meaning);
    expect(new Set(meanings).size).toBe(meanings.length);
    for (const meaning of meanings) {
      expect(meaning.length).toBeGreaterThan(30);
    }
  });

  it('explains stale as being about the job and unverified as being about the source', () => {
    const stale = jobStatusMeta('possibly_stale').meaning;
    const unverified = jobStatusMeta('unverified').meaning;

    // Stale: the board spoke and the job was absent.
    expect(stale).toMatch(/board answered/i);
    // Unverified: we could not check, and nothing was concluded from that.
    expect(unverified).toMatch(/not been able to check/i);
    expect(unverified).toMatch(/outage is not evidence/i);
  });

  it('does not tell the user to stop applying to a job that may still be open', () => {
    // Only `closed` has been absent long enough under ADR 0009 to say so.
    expect(jobStatusMeta('open').stillWorthApplying).toBe(true);
    expect(jobStatusMeta('possibly_stale').stillWorthApplying).toBe(true);
    expect(jobStatusMeta('unverified').stillWorthApplying).toBe(true);
    expect(jobStatusMeta('closed').stillWorthApplying).toBe(false);
  });

  it('gives every state a label that is readable without its colour', () => {
    // §12.4: essential information must not be carried by a visual channel
    // alone, so the label has to stand on its own.
    for (const meta of JOB_STATUS_SCALE) {
      expect(meta.label.trim().length).toBeGreaterThan(0);
      expect(meta.label).not.toMatch(/^#|rgb|text-/);
    }
  });
});
