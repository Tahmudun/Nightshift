import { describe, expect, it } from 'vitest';

import { bestConfidence, confidenceMeta, CONFIDENCE_SCALE } from './confidence';

describe('CONFIDENCE_SCALE', () => {
  it('covers all five values from invariant I1 exactly once', () => {
    const values = CONFIDENCE_SCALE.map((step) => step.value).sort();
    expect(values).toEqual(['approximate', 'city_only', 'remote', 'unknown', 'verified']);
  });

  it('ranks strictly ascending, so the ladder reads as a scale', () => {
    const ranks = CONFIDENCE_SCALE.map((step) => step.rank);
    expect(ranks).toEqual([1, 2, 3, 4, 5]);
  });

  it('marks only verified and approximate as placeable on a map', () => {
    // This is the assertion that stops a future change from quietly deciding a
    // city centroid is good enough to draw a building on.
    const mappable = CONFIDENCE_SCALE.filter((step) => step.mappable).map((step) => step.value);
    expect(mappable.sort()).toEqual(['approximate', 'verified']);
  });

  it('gives every value a user-facing explanation', () => {
    for (const step of CONFIDENCE_SCALE) {
      expect(step.meaning.length).toBeGreaterThan(20);
      expect(step.label).not.toBe('');
    }
  });
});

describe('confidenceMeta', () => {
  it('throws on an unrecognised value rather than falling back', () => {
    // A silent fallback would render an unknown confidence as if it were fine.
    expect(() => confidenceMeta('made_up' as never)).toThrow(/unrecognised/);
  });
});

describe('bestConfidence', () => {
  it('returns the most precise confidence among a job’s locations', () => {
    expect(bestConfidence(['unknown', 'city_only', 'remote'])).toBe('city_only');
    expect(bestConfidence(['city_only', 'verified'])).toBe('verified');
    expect(bestConfidence(['remote', 'approximate'])).toBe('approximate');
  });

  it('returns undefined for a job with no locations', () => {
    expect(bestConfidence([])).toBeUndefined();
  });
});
