import { describe, expect, it } from 'vitest';

import { signalFixture } from './signal.fixture';
import {
  EXCEPTIONAL_FRACTION,
  NEW_WINDOW_DAYS,
  TREATMENTS,
  URGENT_DEADLINE_DAYS,
  treatmentFor,
  type TreatmentContext,
} from './treatments';

/**
 * §6's table, asserted row by row.
 *
 * This file is the reason the table is a function rather than a `switch` inside
 * a shader: every row of `city.md` §6 is a claim about a role, and a claim that
 * cannot be tested without a GPU is a claim nobody checks. Nothing here draws
 * anything — `signalLayer.test.ts` covers the buffers and `city.spec.ts` covers
 * the pixels.
 */

const NOW = Date.parse('2026-08-12T12:00:00Z');

/** N days before `NOW`, as the ISO string the payload carries. */
function daysAgo(days: number): string {
  return new Date(NOW - days * 86_400_000).toISOString();
}

/** N days after `NOW`. */
function daysAhead(days: number): string {
  return new Date(NOW + days * 86_400_000).toISOString();
}

/** An empty context: nothing saved, nothing scored. The cold-load case. */
function context(overrides: Partial<TreatmentContext> = {}): TreatmentContext {
  return { stages: new Map(), matches: new Map(), now: NOW, ...overrides };
}

describe('treatmentFor — the lifecycle marks', () => {
  it('gives an untouched role no mark at all', () => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', first_seen_at: daysAgo(90) }),
      context(),
    );

    expect(treatment.track).toBe('none');
    expect(treatment.pulse).toBe('none');
    expect(treatment.beam).toBe('none');
    expect(treatment.dimmed).toBe(false);
  });

  it('outlines a saved role', () => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', first_seen_at: daysAgo(90) }),
      context({ stages: new Map([['a', 'saved']]) }),
    );

    expect(treatment.track).toBe('saved');
  });

  it.each(['discovered', 'saved', 'preparing'] as const)(
    'treats %s as saved — none of the three has been sent anywhere yet',
    (stage) => {
      const treatment = treatmentFor(
        signalFixture({ job_id: 'a' }),
        context({ stages: new Map([['a', stage]]) }),
      );

      expect(treatment.track).toBe('saved');
    },
  );

  it('fills in an applied role', () => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a' }),
      context({ stages: new Map([['a', 'applied']]) }),
    );

    expect(treatment.track).toBe('applied');
  });

  it.each(['assessment', 'interview'] as const)('rings a role at %s', (stage) => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a' }),
      context({ stages: new Map([['a', stage]]) }),
    );

    expect(treatment.track).toBe('in_process');
  });

  it('gives an offer its own core', () => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a' }),
      context({ stages: new Map([['a', 'offer']]) }),
    );

    expect(treatment.track).toBe('offer');
  });

  it.each(['rejected', 'withdrawn', 'closed'] as const)('archives a role at %s', (stage) => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a' }),
      context({ stages: new Map([['a', stage]]) }),
    );

    expect(treatment.track).toBe('archived');
  });
});

describe('treatmentFor — the pulse, which is about what is new', () => {
  it('pulses slowly for a role first seen inside the window', () => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', first_seen_at: daysAgo(NEW_WINDOW_DAYS - 1) }),
      context(),
    );

    expect(treatment.pulse).toBe('slow');
  });

  it('pulses rapidly for a new internship, which is the role with a season', () => {
    const treatment = treatmentFor(
      signalFixture({
        job_id: 'a',
        employment_type: 'internship',
        first_seen_at: daysAgo(NEW_WINDOW_DAYS - 1),
      }),
      context(),
    );

    expect(treatment.pulse).toBe('rapid');
  });

  it('stops pulsing once the role is older than the window', () => {
    const treatment = treatmentFor(
      signalFixture({
        job_id: 'a',
        employment_type: 'internship',
        first_seen_at: daysAgo(NEW_WINDOW_DAYS + 1),
      }),
      context(),
    );

    expect(treatment.pulse).toBe('none');
  });

  it('does not pulse a role you have already applied to', () => {
    // A7's principle: intensity tracks what you can act on. "New" is an
    // invitation to look, and a role you have already acted on is not one.
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', first_seen_at: daysAgo(1) }),
      context({ stages: new Map([['a', 'applied']]) }),
    );

    expect(treatment.pulse).toBe('none');
  });
});

describe('treatmentFor — gold, and the two things that earn it', () => {
  it('beams for an exceptional match', () => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a' }),
      context({
        matches: new Map([['a', { fraction: EXCEPTIONAL_FRACTION, eligibility: 'eligible' }]]),
      }),
    );

    expect(treatment.beam).toBe('match');
  });

  it('refuses gold to a high score that is not eligible', () => {
    // `matching.md` §5.2: the state sits beside the number and is never inside
    // it. A posting can be a 92 and `uncertain`, and gold on that beacon would
    // be the number having quietly absorbed the verdict.
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a' }),
      context({ matches: new Map([['a', { fraction: 0.99, eligibility: 'uncertain' }]]) }),
    );

    expect(treatment.beam).toBe('none');
  });

  it('refuses gold to an eligible posting nothing could be assessed on', () => {
    // I2 and I4: `fraction: null` means nothing was measured. Reading it as a
    // zero would be wrong in one direction and reading it as a pass would be a
    // fabricated qualification.
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a' }),
      context({ matches: new Map([['a', { fraction: null, eligibility: 'eligible' }]]) }),
    );

    expect(treatment.beam).toBe('none');
  });

  it('beams for a deadline inside the urgent window', () => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', application_deadline: daysAhead(URGENT_DEADLINE_DAYS - 1) }),
      context(),
    );

    expect(treatment.beam).toBe('deadline');
  });

  it('leaves a distant deadline alone', () => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', application_deadline: daysAhead(URGENT_DEADLINE_DAYS + 1) }),
      context(),
    );

    expect(treatment.beam).toBe('none');
  });

  it('leaves a deadline that has already passed alone', () => {
    // Urgency is a thing you can still act on. A closed window is not urgent,
    // it is over, and lighting it gold sends a person to a form that will not
    // take them.
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', application_deadline: daysAgo(1) }),
      context(),
    );

    expect(treatment.beam).toBe('none');
  });

  it('prefers the deadline when a role has both', () => {
    // Both are gold, so the beacon looks the same either way — but the panel
    // has to name one, and the deadline is the half with a clock on it.
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', application_deadline: daysAhead(2) }),
      context({ matches: new Map([['a', { fraction: 0.95, eligibility: 'eligible' }]]) }),
    );

    expect(treatment.beam).toBe('deadline');
  });

  it('takes the beam off an archived role', () => {
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', application_deadline: daysAhead(2) }),
      context({ stages: new Map([['a', 'rejected']]) }),
    );

    expect(treatment.beam).toBe('none');
  });
});

describe('treatmentFor — dimming, which is a claim about us and not about them', () => {
  it.each(['possibly_stale', 'unverified'] as const)('dims a %s listing', (status) => {
    const treatment = treatmentFor(signalFixture({ job_id: 'a', status }), context());

    expect(treatment.dimmed).toBe(true);
  });

  it('leaves an open listing at full strength', () => {
    const treatment = treatmentFor(signalFixture({ job_id: 'a', status: 'open' }), context());

    expect(treatment.dimmed).toBe(false);
  });

  it('dims a stale role without touching the mark that says you applied', () => {
    // The two are orthogonal and both are true: our knowledge of the listing is
    // old, and you have an application against it. Overwriting one with the
    // other would lose a fact a person needs.
    const treatment = treatmentFor(
      signalFixture({ job_id: 'a', status: 'possibly_stale' }),
      context({ stages: new Map([['a', 'applied']]) }),
    );

    expect(treatment.dimmed).toBe(true);
    expect(treatment.track).toBe('applied');
  });
});

describe('TREATMENTS — the legend’s own source of truth', () => {
  it('carries every row of §6, including the ones this corpus cannot draw', () => {
    // The table is the deliverable, not the subset that happens to be live.
    // PRODUCT-SPEC §4.3's last line asks for the meanings to be documented in
    // the interface; a legend that silently omitted the undrawable rows would
    // be documenting the renderer rather than the language.
    expect(TREATMENTS.length).toBeGreaterThanOrEqual(12);
    expect(TREATMENTS.some((row) => row.status.kind === 'deferred')).toBe(true);
  });

  it('gives every deferred row a reason a reader can check', () => {
    for (const row of TREATMENTS) {
      if (row.status.kind === 'deferred') {
        expect(row.status.because.length).toBeGreaterThan(20);
      }
    }
  });

  it('never lets a colour carry a meaning on its own — §12.4', () => {
    // Every row that has a colour also has a shape or a motion, so the language
    // survives a viewer who cannot tell cyan from gold.
    for (const row of TREATMENTS) {
      if (row.swatch !== null) expect(row.form.length).toBeGreaterThan(0);
    }
  });

  it('names each row exactly once', () => {
    expect(new Set(TREATMENTS.map((row) => row.id)).size).toBe(TREATMENTS.length);
  });
});
