import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RankedMatches } from './RankedMatches';
import { matchRankingSchema, type EligibilityState, type MatchRanking } from '@/lib/schemas';

vi.mock('@/lib/api', () => ({
  fetchMatches: vi.fn(),
}));

const { fetchMatches } = await import('@/lib/api');

const BAND_ORDER: readonly EligibilityState[] = [
  'eligible',
  'likely_eligible',
  'uncertain',
  'likely_ineligible',
  'ineligible',
];

function job(id: string, title: string) {
  return {
    id,
    title,
    company: {
      id: '22222222-2222-4222-8222-222222222222',
      canonical_name: 'Example Inc.',
      website: null,
    },
    employment_type: 'full_time',
    remote_policy: 'hybrid',
    status: 'open',
    locations: [],
    salary: { provided: false, minimum: null, maximum: null, currency: null, period: null },
    source_published_at: null,
    source_updated_at: null,
    first_seen_at: '2026-08-01T00:00:00+00:00',
    last_seen_at: '2026-08-03T00:00:00+00:00',
    application_deadline: null,
  };
}

function match(overall: number, outOf: number, state: EligibilityState) {
  return {
    overall_score: overall,
    assessed_out_of: outOf,
    fraction: outOf === 0 ? null : overall / outOf,
    eligibility_status: state,
    components: [],
    penalty_score: 0,
    penalties: [],
    deferred_components: [],
    ruleset_version: '1+2026-08-09.1',
    model_version: null,
    computed_at: '2026-08-09T00:00:00+00:00',
  };
}

/**
 * The order here is the API's, and this component renders it rather than
 * re-sorting: `terse` is 40 of 50 and `verbose` is 45 of 100, so a list sorted
 * on the raw totals would have them the other way round. The test below asserts
 * the rendering preserves what it was handed — the ordering itself is asserted
 * against a real database in `test_match_ranking_routes.py`.
 */
const RANKING: MatchRanking = matchRankingSchema.parse({
  bands: BAND_ORDER.map((state) => ({
    state,
    items:
      state === 'eligible'
        ? [
            {
              job: job('00000000-0000-4000-8000-000000000001', 'Terse posting'),
              match: match(40, 50, 'eligible'),
            },
            {
              job: job('00000000-0000-4000-8000-000000000002', 'Verbose posting'),
              match: match(45, 100, 'eligible'),
            },
          ]
        : state === 'uncertain'
          ? [
              {
                job: job('00000000-0000-4000-8000-000000000003', 'Nothing to assess'),
                match: match(0, 0, 'uncertain'),
              },
            ]
          : state === 'ineligible'
            ? [
                {
                  job: job('00000000-0000-4000-8000-000000000004', 'Blocked posting'),
                  match: match(48, 50, 'ineligible'),
                },
              ]
            : [],
    unassessed: state === 'uncertain' ? 1 : 0,
  })),
  total: 4,
  not_yet_scored: 7,
  ruleset_version: '1+2026-08-09.1',
  unassessed_sort_last: true,
  deferred_components: [
    {
      name: 'company_preference',
      weight: 5,
      blocked_on: 'a preferred-companies field on users',
      reason: 'there is no stated taste to score against',
    },
    {
      name: 'application_urgency',
      weight: 5,
      blocked_on: 'a populated application_deadline',
      reason: 'deadlines are rarely published',
    },
  ],
});

function renderList(ranking: MatchRanking = RANKING) {
  vi.mocked(fetchMatches).mockResolvedValue(ranking);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RankedMatches />
    </QueryClientProvider>,
  );
}

describe('RankedMatches', () => {
  it('parses its own fixture through the real schema', () => {
    expect(matchRankingSchema.safeParse(RANKING).success).toBe(true);
  });

  it('renders every band as a heading, in the order the API sent', async () => {
    renderList();
    await screen.findByTestId('ranked-matches');
    const rendered = [...document.querySelectorAll('[data-testid^="band-"]')].map(
      (node) => node.getAttribute('data-testid') ?? '',
    );
    expect(rendered).toEqual(BAND_ORDER.map((state) => `band-${state}`));
  });

  it('keeps an empty band on the page', async () => {
    // §3.3's promise that an ineligible posting is shown rather than hidden is
    // only checkable if the heading is there when there is nothing under it.
    renderList();
    await screen.findByTestId('ranked-matches');
    expect(screen.getByTestId('band-likely_eligible').textContent ?? '').toMatch(
      /nothing in this group/i,
    );
  });

  it('shows an ineligible posting with its score intact', async () => {
    // §5.2: the verdict sits beside the number and never inside it. A posting
    // that scores 96% and is blocked shows both, unreconciled.
    renderList();
    await screen.findByTestId('ranked-matches');
    const band = screen.getByTestId('band-ineligible');
    expect(band.textContent ?? '').toContain('Blocked posting');
    expect(band.textContent ?? '').toContain('96%');
  });

  it('does not re-sort the rows it was given', async () => {
    // The API sorts on the fraction, so 40 of 50 arrives before 45 of 100. A
    // component that sorted by `overall_score` for tidiness would silently undo
    // the one ordering decision this list is about.
    renderList();
    await screen.findByTestId('ranked-matches');
    const titles = [...screen.getByTestId('band-eligible').querySelectorAll('h4')].map(
      (node) => node.textContent ?? '',
    );
    expect(titles).toEqual(['Terse posting', 'Verbose posting']);
  });

  it('shows each row against what it was assessed out of', async () => {
    // The percentage alone is not checkable: two rows showing 80% can be 40 of
    // 50 and 80 of 100, and the reader is entitled to know which.
    renderList();
    await screen.findByTestId('ranked-matches');
    const totals = [
      ...screen.getByTestId('band-eligible').querySelectorAll('[data-testid="row-total"]'),
    ].map((node) => node.textContent ?? '');
    expect(totals).toEqual(['40 of 50', '45 of 100']);
  });

  it('never prints a percentage for a pair nothing could be assessed on', async () => {
    // `fraction: null` is deliberately not `0.0`; 0% is a measurement and this
    // pair was not measured.
    renderList();
    await screen.findByTestId('ranked-matches');
    const band = screen.getByTestId('band-uncertain');
    expect(band.textContent ?? '').toMatch(/nothing to assess/i);
    expect(band.textContent ?? '').not.toMatch(/\b0%/);
    expect(screen.getByTestId('unassessed-note').textContent ?? '').toMatch(/1 of these/i);
  });

  it('says how many open postings are not in this list at all', async () => {
    // A ranked list covering 4 of 11 postings renders identically to one
    // covering all 11 — this number is the only thing that says which it is,
    // and it is above the list because a reader who has scrolled to the bottom
    // has already drawn a conclusion.
    renderList();
    await screen.findByTestId('ranked-matches');
    expect(screen.getByTestId('not-yet-scored').textContent ?? '').toContain('7');
  });

  it('names the points no score here contains', async () => {
    renderList();
    await screen.findByTestId('ranked-matches');
    const text = screen.getByTestId('ranked-matches').textContent ?? '';
    expect(text).toMatch(/company preference/i);
    expect(text).toMatch(/application urgency/i);
    expect(text).toMatch(/10 points/i);
  });
});
