/**
 * The verdict on screen, and mostly what it must *not* say.
 *
 * A13 ranks a wrong `ineligible` as the worst output this engine can produce,
 * and the page is where that damage actually lands: a person reads it, believes
 * it, and does not apply. So these tests are weighted towards the wording and
 * the absences rather than towards the happy path.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { JobEligibility } from './JobEligibility';
import { eligibilitySchema, type Eligibility } from '@/lib/schemas';

/**
 * Parsed through the real schema rather than cast.
 *
 * `const BASE: JobDetail = {...}` asserts a shape without verifying one, which
 * is how M3a's component fixture went stale the instant two fields were added
 * and said nothing — the render crashed instead. Twice now in this project.
 */
function eligibility(overrides: Partial<Eligibility> = {}): Eligibility {
  return eligibilitySchema.parse({
    state: 'eligible',
    blockers: [],
    unknowns: [],
    gate_version: 'm3b.1',
    ...overrides,
  });
}

const HARD = {
  dimension: 'degree',
  outcome: 'blocks' as const,
  posting_says: 'Ph.D.',
  char_start: 120,
  char_end: 125,
  profile_says: 'bachelors',
  why: 'the posting requires a phd and your profile says bachelors',
};

const SOFT = {
  dimension: 'years_experience',
  outcome: 'soft_blocks' as const,
  posting_says: '10 years',
  char_start: 40,
  char_end: 48,
  profile_says: '1 years',
  why: 'the posting asks for 10+ years and your profile says 1',
};

describe('JobEligibility', () => {
  it('never renders a verdict without the reasons behind it', () => {
    render(<JobEligibility eligibility={eligibility({ state: 'ineligible', blockers: [HARD] })} />);

    expect(screen.getByTestId('eligibility-state')).toBeInTheDocument();
    expect(screen.getByText(/requires a phd/i)).toBeInTheDocument();
    expect(screen.getByText(/Ph\.D\./)).toBeInTheDocument();
  });

  it('quotes the posting rather than paraphrasing it', () => {
    render(<JobEligibility eligibility={eligibility({ state: 'ineligible', blockers: [HARD] })} />);
    expect(screen.getByText(/The posting says/)).toHaveTextContent('Ph.D.');
  });

  it('tells a blocked reader the rules may be wrong and to apply anyway', () => {
    // The single most important sentence on this page. A verdict that sounds
    // like a decision somebody made is a verdict a person will not argue with.
    render(<JobEligibility eligibility={eligibility({ state: 'ineligible', blockers: [HARD] })} />);
    expect(screen.getByText(/you should apply anyway/i)).toBeInTheDocument();
  });

  it('separates a shortfall from a bar, in different words', () => {
    render(
      <JobEligibility
        eligibility={eligibility({ state: 'likely_ineligible', blockers: [SOFT] })}
      />,
    );

    expect(screen.getByTestId('eligibility-gaps')).toBeInTheDocument();
    expect(screen.queryByTestId('eligibility-blockers')).not.toBeInTheDocument();
    expect(screen.getByText(/Employers hire below their stated minimums/i)).toBeInTheDocument();
  });

  it('shows both sections when a posting has one of each', () => {
    render(
      <JobEligibility eligibility={eligibility({ state: 'ineligible', blockers: [HARD, SOFT] })} />,
    );
    expect(screen.getByTestId('eligibility-blockers')).toBeInTheDocument();
    expect(screen.getByTestId('eligibility-gaps')).toBeInTheDocument();
  });

  it('turns an unknown into a link to the field that would answer it', () => {
    render(
      <JobEligibility
        eligibility={eligibility({
          state: 'uncertain',
          unknowns: [
            {
              dimension: 'graduation_window',
              profile_field: 'graduation_year',
              why: 'the posting wants a graduation date in 2026-2027 and your profile has none',
            },
          ],
        })}
      />,
    );

    const link = screen.getByRole('link', { name: /add your graduation year/i });
    expect(link).toHaveAttribute('href', '/operate/profile');
    expect(screen.getByText(/Nothing here is a no/i)).toBeInTheDocument();
  });

  it('offers no action for a question no profile field could answer', () => {
    // Task 12's browser-walk finding. The posting says "PhD or equivalent
    // experience"; the gate cannot assess that, and it is checked *before* the
    // profile's degree is read — so this reader has a degree on file and the
    // link would still have said "Add your degree". An action that leaves the
    // verdict where it was is worse than no action, because they take it.
    render(
      <JobEligibility
        eligibility={eligibility({
          state: 'uncertain',
          unknowns: [
            {
              dimension: 'degree',
              profile_field: null,
              why: 'the posting accepts equivalent experience in place of the degree, which is not something this system can assess',
            },
          ],
        })}
      />,
    );

    expect(screen.getByTestId('eligibility-unassessable')).toHaveTextContent(
      /accepts equivalent experience/i,
    );
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    // And it must not be filed under the heading that promises an answer.
    expect(screen.queryByTestId('eligibility-unknowns')).not.toBeInTheDocument();
  });

  it('does not promise a fillable answer when there is nothing to fill in', () => {
    // The same defect as the test above, one heading further up, and splitting
    // the sections did not fix it. `uncertain` has two causes; the standing
    // headline and caveat describe only one of them — "not enough in *your
    // profile*", "fill in what is missing and this can answer" — and both are
    // false when every open question came from the posting's own wording.
    // A reader who acts on that sentence does exactly the futile thing the
    // missing link was removed to prevent.
    render(
      <JobEligibility
        eligibility={eligibility({
          state: 'uncertain',
          unknowns: [
            {
              dimension: 'degree',
              profile_field: null,
              why: 'the posting accepts equivalent experience in place of the degree',
            },
          ],
        })}
      />,
    );

    expect(screen.getByTestId('eligibility-state')).toHaveTextContent(/posting.s own wording/i);
    expect(screen.queryByText(/fill in what is missing/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not enough in your profile/i)).not.toBeInTheDocument();
    // Still not a rejection. The correction is to the promised action, not to
    // the reassurance, and dropping the second with the first would be a
    // different harm.
    expect(screen.getByText(/Nothing here is a no/i)).toBeInTheDocument();
  });

  it('still promises the answer when one unknown really is fillable', () => {
    // The guard on the guard: a component that took the unassessable wording
    // whenever *any* unknown was unassessable would stop offering the action to
    // somebody who does have one to take.
    render(
      <JobEligibility
        eligibility={eligibility({
          state: 'uncertain',
          unknowns: [
            {
              dimension: 'degree',
              profile_field: null,
              why: 'the posting accepts equivalent experience in place of the degree',
            },
            {
              dimension: 'graduation_window',
              profile_field: 'graduation_year',
              why: 'the posting wants a graduation date in 2026-2027 and your profile has none',
            },
          ],
        })}
      />,
    );

    expect(screen.getByTestId('eligibility-state')).toHaveTextContent(
      /not enough in your profile/i,
    );
    expect(screen.getByText(/fill in what is missing/i)).toBeInTheDocument();
  });

  it('keeps the two kinds of unknown under separate headings', () => {
    render(
      <JobEligibility
        eligibility={eligibility({
          state: 'uncertain',
          unknowns: [
            {
              dimension: 'degree',
              profile_field: null,
              why: 'the posting accepts equivalent experience in place of the degree',
            },
            {
              dimension: 'graduation_window',
              profile_field: 'graduation_year',
              why: 'the posting wants a graduation date in 2026-2027 and your profile has none',
            },
          ],
        })}
      />,
    );

    expect(screen.getByTestId('eligibility-unknowns')).toHaveTextContent(/graduation date/i);
    expect(screen.getByTestId('eligibility-unknowns')).not.toHaveTextContent(/equivalent/i);
    expect(screen.getByTestId('eligibility-unassessable')).toHaveTextContent(/equivalent/i);
    expect(screen.getAllByRole('link')).toHaveLength(1);
  });

  it('says an unread posting is unread rather than saying you are eligible', () => {
    // The null case. Reporting `eligible` here would be a claim about a person
    // derived from a posting nobody has read.
    render(<JobEligibility eligibility={null} />);

    expect(screen.getByText(/Nothing has been read out of this posting yet/i)).toBeInTheDocument();
    expect(screen.queryByTestId('eligibility-state')).not.toBeInTheDocument();
  });

  it('names the ruleset and says the verdict is not stored', () => {
    render(<JobEligibility eligibility={eligibility()} />);
    expect(screen.getByTestId('eligibility-version')).toHaveTextContent('m3b.1');
    expect(screen.getByTestId('eligibility-version')).toHaveTextContent(/not stored/i);
  });

  it('renders every state as a sentence, not as an enum value', () => {
    // A leaked `likely_ineligible` is jargon on the one verdict a person least
    // wants to read. Checked for all five rather than the two that are easy.
    for (const state of [
      'eligible',
      'likely_eligible',
      'uncertain',
      'likely_ineligible',
      'ineligible',
    ] as const) {
      const { unmount } = render(<JobEligibility eligibility={eligibility({ state })} />);
      expect(screen.getByTestId('eligibility-state').textContent).not.toContain('_');
      unmount();
    }
  });

  it('shows no blocker or gap section when there is nothing to show', () => {
    render(<JobEligibility eligibility={eligibility()} />);
    expect(screen.queryByTestId('eligibility-blockers')).not.toBeInTheDocument();
    expect(screen.queryByTestId('eligibility-gaps')).not.toBeInTheDocument();
    expect(screen.queryByTestId('eligibility-unknowns')).not.toBeInTheDocument();
  });
});
