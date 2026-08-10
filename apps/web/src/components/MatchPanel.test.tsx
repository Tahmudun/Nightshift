import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MatchPanel } from './MatchPanel';
import { matchSchema, unmetRequirementSchema, type Match } from '@/lib/schemas';

/**
 * Every fixture goes through the real schema rather than being cast to its type.
 * A cast asserts the shape; the schema checks it — and M2c shipped a component
 * test fed a row its own schema would have refused.
 */
function score(overrides: Record<string, unknown> = {}): Match {
  return matchSchema.parse({
    overall_score: 42,
    assessed_out_of: 100,
    fraction: 0.42,
    eligibility_status: 'uncertain',
    components: [
      {
        component: 'role',
        points: 20,
        weight: 20,
        assessable: true,
        why: 'this is a software engineering posting and you prefer software engineering',
        evidence: [
          {
            component: 'role',
            points: 20,
            job_span_text: 'Software Engineer',
            job_span_field: 'title',
            job_char_start: 0,
            job_char_end: 17,
            user_span_text: 'software engineer',
            user_skill_id: null,
            user_project_id: null,
            compared: {},
            proposed_by: 'rule',
            job_requirement_id: null,
          },
        ],
      },
      {
        component: 'skill',
        points: 10,
        weight: 30,
        assessable: true,
        why: '1 of 3 required technologies confirmed',
        evidence: [],
      },
      {
        component: 'project',
        points: 0,
        weight: 20,
        assessable: false,
        why: 'this posting names no required technologies to look for',
        evidence: [],
      },
      {
        component: 'location',
        points: 10,
        weight: 10,
        assessable: true,
        why: 'this posting is in New York, which you prefer',
        evidence: [
          {
            component: 'location',
            points: 10,
            job_span_text: null,
            job_span_field: null,
            job_char_start: null,
            job_char_end: null,
            user_span_text: null,
            user_skill_id: null,
            user_project_id: null,
            compared: { job: 'New York, NY', preferred: 'New York' },
            proposed_by: 'rule',
            job_requirement_id: null,
          },
        ],
      },
      {
        component: 'freshness',
        points: 2,
        weight: 10,
        assessable: true,
        why: 'published 21 days ago',
        evidence: [],
      },
      {
        component: 'priority',
        points: 0,
        weight: 10,
        assessable: true,
        why: 'this posting is not pitched at early career',
        evidence: [],
      },
    ],
    penalty_score: -12,
    penalties: [
      {
        name: 'missing_requirement',
        points: -12,
        applicable: true,
        why: '2 of 3 required technologies have no evidence',
        compared: { required: ['Python', 'Go', 'Rust'], missing: ['Go', 'Rust'] },
      },
      {
        name: 'seniority_mismatch',
        points: 0,
        applicable: false,
        why: 'this profile states no years of experience',
        compared: {},
      },
    ],
    deferred_components: [
      {
        name: 'company_preference',
        weight: 5,
        blocked_on: 'a preferred-companies field on users',
        reason: 'there is no stated taste to score against',
      },
    ],
    ruleset_version: '1+2026-08-09.1',
    model_version: null,
    computed_at: '2026-08-09T00:00:00+00:00',
    ...overrides,
  });
}

const UNMET = [
  {
    kind: 'technology',
    value: 'Go',
    raw_text: 'Go',
    char_start: 10,
    char_end: 12,
    necessity: 'required',
    has_equivalence: false,
  },
  {
    kind: 'technology',
    value: 'Kubernetes',
    raw_text: 'Kubernetes',
    char_start: 40,
    char_end: 50,
    necessity: 'preferred',
    has_equivalence: false,
  },
].map((row) => unmetRequirementSchema.parse(row));

describe('MatchPanel', () => {
  it('never shows a total without what it is out of', () => {
    // I4. "42" invites the reader to supply the missing "of 100" themselves, and
    // `assessed_out_of` is not always 100.
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    expect(screen.getByTestId('match-score').textContent).toMatch(/42\s*of 100/);
  });

  it('renders all six components with their own sentences', () => {
    // A response carrying a total and five components is I4 failing while the
    // page looks entirely normal.
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    for (const component of ['role', 'skill', 'project', 'location', 'freshness', 'priority']) {
      expect(screen.getByTestId(`component-${component}`)).toBeVisible();
    }
    expect(screen.getByText(/1 of 3 required technologies confirmed/i)).toBeVisible();
  });

  it('prints no number at all for a component nobody could assess', () => {
    // §5.1.1. "0 of 20" beside "this posting names no required technologies" is
    // the two statements the distinction exists to keep apart, on one line.
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    const project = screen.getByTestId('component-project');
    expect(project.textContent ?? '').toMatch(/not assessed/i);
    expect(project.textContent ?? '').not.toMatch(/0 of 20/);
  });

  it('quotes both sides of a claim about the person', () => {
    // §2.1: role, skill and project assert something about somebody's
    // qualifications, and each must trace to two quotable strings.
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    const role = screen.getByTestId('component-role');
    expect(role.textContent ?? '').toContain('Software Engineer');
    expect(role.textContent ?? '').toContain('software engineer');
    expect(role.textContent ?? '').toMatch(/in the title/i);
  });

  it('shows what an exempt component compared instead of inventing a span', () => {
    // §2.1's other half: location asserts nothing about the person, so there is
    // no user-side span to quote and requiring one would mean inventing it.
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    const location = screen.getByTestId('component-location');
    expect(location.textContent ?? '').toContain('New York, NY');
    expect(location.textContent ?? '').not.toMatch(/you have confirmed/i);
  });

  it('names each penalty with what it cost', () => {
    // §4.2 stores the two as one column. Before Task 10 the page could show
    // "-12" and nothing else — a bare number, which is what I4 forbids.
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    const missing = screen.getByTestId('penalty-missing_requirement');
    expect(missing.textContent ?? '').toMatch(/2 of 3 required technologies/i);
    expect(missing.textContent ?? '').toContain('-12');
    expect(screen.getByTestId('penalty-total').textContent).toContain('-12');
  });

  it('says a penalty had nothing to ask rather than printing a zero', () => {
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    const seniority = screen.getByTestId('penalty-seniority_mismatch');
    expect(seniority.textContent ?? '').toMatch(/states no years of experience/i);
    expect(seniority.textContent ?? '').toMatch(/nothing to ask/i);
  });

  it('separates a required gap from a nice-to-have', () => {
    // §4.1: `preferred` never produces a penalty and is never a gap in the
    // score. Rendered under one heading, a nice-to-have reads as a bar.
    render(<MatchPanel match={score()} unmetRequirements={UNMET} />);
    expect(screen.getByTestId('unmet-required').textContent ?? '').toContain('Go');
    expect(screen.getByTestId('unmet-preferred').textContent ?? '').toContain('Kubernetes');
    expect(screen.getByTestId('unmet-required').textContent ?? '').not.toContain('Kubernetes');
  });

  it('says what the denominator is short of a hundred and why', () => {
    // §5.1.1. Without this the page shows 30 of 50 with no account of the other
    // 50 points, which reads as a score that has been quietly reduced.
    render(
      <MatchPanel
        match={score({ assessed_out_of: 50, overall_score: 30, fraction: 0.6 })}
        unmetRequirements={null}
      />,
    );
    const note = screen.getByTestId('partial-denominator');
    expect(note.textContent ?? '').toMatch(/out of 50, not 100/i);
    expect(note.textContent ?? '').toMatch(/what you have built/i);
  });

  it('shows no percentage for a pair nothing could be assessed on', () => {
    // `fraction: null` is not `0.0`, and 0% is a measurement.
    render(
      <MatchPanel
        match={score({ assessed_out_of: 0, overall_score: 0, fraction: null })}
        unmetRequirements={null}
      />,
    );
    expect(screen.queryByTestId('match-fraction')).toBeNull();
    expect(screen.getByTestId('match').textContent ?? '').not.toMatch(/\b0%/);
  });

  it('names the deferred components rather than omitting them', () => {
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    expect(screen.getByTestId('deferred-components').textContent ?? '').toMatch(
      /company preference/i,
    );
  });

  it('names the elements it does not compute, including the recommended resume', () => {
    // §6's nine elements. `match_results.resume_id` has a column, a foreign key
    // and no writer, and a section naming "your general resume" from nothing
    // would be the most plausible-looking fabrication on the page.
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    const notBuilt = screen.getByTestId('match-not-built').textContent ?? '';
    expect(notBuilt).toMatch(/recommended resume/i);
    expect(notBuilt).toMatch(/recommended emphasis/i);
    expect(notBuilt).toMatch(/suggested next action/i);
  });

  it('says the score came from rules alone when no model touched it', () => {
    // What makes the semantic layer auditable, on the surface a person reads.
    render(<MatchPanel match={score()} unmetRequirements={null} />);
    expect(screen.getByTestId('match-version').textContent ?? '').toMatch(/rules only/i);
  });

  it('says a confirmed nice-to-have is worth nothing, rather than printing a bare 0', () => {
    // The rows added at M3c Task 12 (`score_skill_overlap`'s zero-point
    // preferred evidence). They exist so a confirmed nice-to-have stops being
    // reported as a gap, and they arrive worth zero — which is a statement about
    // §4.1's necessity column and not about the reader. "0 · matched by a
    // vocabulary rule" underneath a skill somebody confirmed reads as the second
    // thing.
    render(
      <MatchPanel
        match={score({
          components: score().components.map((component) =>
            component.component === 'skill'
              ? {
                  ...component,
                  evidence: [
                    {
                      component: 'skill',
                      points: 0,
                      job_span_text: 'React',
                      job_span_field: 'description_text',
                      job_char_start: 10,
                      job_char_end: 15,
                      user_span_text: 'React',
                      user_skill_id: null,
                      user_project_id: null,
                      compared: { requirement: 'React', necessity: 'preferred' },
                      proposed_by: 'rule',
                      job_requirement_id: null,
                    },
                  ],
                }
              : component,
          ),
        })}
        unmetRequirements={null}
      />,
    );
    const skill = screen.getByTestId('component-skill').textContent ?? '';
    expect(skill).toMatch(/nice-to-have/i);
    expect(skill).not.toMatch(/0 · matched by a vocabulary rule/);
  });

  it('says a missing score is not computed rather than showing zeroes', () => {
    render(<MatchPanel match={null} unmetRequirements={null} />);
    const panel = screen.getByTestId('match');
    expect(panel.textContent ?? '').toMatch(/not scored yet/i);
    expect(panel.textContent ?? '').toMatch(/not a zero/i);
  });
});
