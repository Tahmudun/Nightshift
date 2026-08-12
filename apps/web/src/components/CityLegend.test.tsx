import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CityLegend, countTreatments } from './CityLegend';
import { useCityScene } from '@/lib/city/scene';
import { signalFixture } from '@/lib/city/signal.fixture';
import { treatmentFor, TREATMENTS, type TreatmentContext } from '@/lib/city/treatments';

/**
 * The legend, which is a deliverable rather than a nicety.
 *
 * PRODUCT-SPEC §4.3's last line asks for §6's meanings to be documented **in
 * the interface**. What these assert is the two ways that requirement can be
 * met dishonestly: a legend that lists only the rows the renderer happens to
 * draw, and a legend whose counts disagree with the city.
 */

/**
 * The applications the legend's own hook fetches.
 *
 * Driven through the mocked API rather than by writing treatments into the
 * store, and that is not a stylistic choice: `useCityTreatments` recomputes the
 * whole map from these two queries and writes it, so a treatment set by hand in
 * a test is overwritten on the next tick. Going through the fetch tests the
 * path the product actually takes.
 */
const tracked: { items: { id: string; job: { id: string }; current_stage: string }[] } = {
  items: [],
};

vi.mock('@/lib/api', () => ({
  fetchApplications: vi.fn(async () => tracked),
  fetchMatches: vi.fn(async () => ({
    bands: [],
    total: 0,
    not_yet_scored: 0,
    ruleset_version: 'test',
  })),
}));

const NOW = Date.parse('2026-08-12T12:00:00Z');

function context(overrides: Partial<TreatmentContext> = {}): TreatmentContext {
  return { stages: new Map(), matches: new Map(), now: NOW, ...overrides };
}

function show(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CityLegend />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  tracked.items = [];
  act(() => {
    useCityScene.setState({
      signals: [],
      treatments: new Map(),
      showArchived: false,
      status: { kind: 'ready' },
    });
  });
});

describe('the legend', () => {
  it('says nothing while the city is still loading', () => {
    act(() => useCityScene.setState({ status: { kind: 'loading' } }));
    show();

    expect(screen.queryByRole('heading', { name: /what the marks mean/i })).toBeNull();
  });

  it('opens to every row of §6, including the ones this city cannot draw', () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: /what the marks mean/i }));

    for (const row of TREATMENTS) {
      expect(screen.getByText(row.label)).toBeInTheDocument();
    }
  });

  it('marks an undrawable row as undrawn, with its reason', () => {
    // I7: a mock presented as working functionality is the worst failure
    // available, and a legend is the easiest place in a product to commit it.
    show();
    fireEvent.click(screen.getByRole('button', { name: /what the marks mean/i }));

    const deferred = TREATMENTS.filter((row) => row.status.kind === 'deferred');
    expect(deferred.length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Not drawn on this city/)).toHaveLength(deferred.length);
  });

  it('counts what is actually on the city', async () => {
    vi.setSystemTime(NOW);
    act(() =>
      useCityScene.setState({
        signals: [
          signalFixture({ job_id: 'a', first_seen_at: new Date(NOW).toISOString() }),
          signalFixture({ job_id: 'b', first_seen_at: '2026-01-01T00:00:00Z' }),
        ],
      }),
    );

    show();
    fireEvent.click(screen.getByRole('button', { name: /what the marks mean/i }));

    // One of the two is new. A legend teaching a language nobody hears spoken
    // is worse than no legend, so the count is the row's own evidence.
    await vi.waitFor(() => {
      expect(screen.getByText('New role').closest('li')).toHaveTextContent('1');
    });
    expect(screen.getByText('New internship').closest('li')).toHaveTextContent('0');
    vi.useRealTimers();
  });

  it('offers the archive toggle, off, and says how many it is hiding', async () => {
    act(() => useCityScene.setState({ signals: [signalFixture({ job_id: 'a' })] }));
    tracked.items = [{ id: 'app-1', job: { id: 'a' }, current_stage: 'rejected' }];

    show();
    fireEvent.click(screen.getByRole('button', { name: /what the marks mean/i }));

    const toggle = screen.getByRole('checkbox', { name: /rejected and withdrawn/i });
    expect(toggle).not.toBeChecked();
    // The count arrives with the applications fetch, one tick after the paint.
    expect(await screen.findByText(/1 hidden/)).toBeInTheDocument();
  });

  it('puts the archived roles back when the toggle is turned on', () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: /what the marks mean/i }));
    fireEvent.click(screen.getByRole('checkbox', { name: /rejected and withdrawn/i }));

    // The store is what the renderer reads, so this is the whole of the
    // toggle's effect — the layer subscribes outside React.
    expect(useCityScene.getState().showArchived).toBe(true);
  });
});

describe('countTreatments', () => {
  it('counts a role under every row it actually carries', () => {
    // The rows are not exclusive: a stale role you applied to is both, and a
    // count that picked one would make two rows of the legend wrong at once.
    const signal = signalFixture({ job_id: 'a', status: 'possibly_stale' });
    const counts = countTreatments(
      [signal],
      new Map([['a', treatmentFor(signal, context({ stages: new Map([['a', 'applied']]) }))]]),
    );

    expect(counts.applied).toBe(1);
    expect(counts.stale).toBe(1);
    expect(counts.unresolved).toBe(1);
  });

  it('counts nothing for a role with no treatment yet', () => {
    const signal = signalFixture({ job_id: 'a' });

    expect(countTreatments([signal], new Map())).toEqual({});
  });
});
