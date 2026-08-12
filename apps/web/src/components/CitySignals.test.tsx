import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type * as ApiModuleNamespace from '@/lib/api';
import { CitySignals } from './CitySignals';
import { useCityScene } from '@/lib/city/scene';
import { signalFixture } from '@/lib/city/signal.fixture';

/**
 * The census panel, and the one way it can lie.
 *
 * It reports the corpus the API returned. §6's archive toggle removes roles
 * from the *city* without removing them from that corpus, so the moment
 * anything is hidden this panel's totals stop matching the roster's — and two
 * counts disagreeing on one screen is worse than either being absent.
 */

type ApiModule = typeof ApiModuleNamespace;

const payload = {
  signals: [] as ReturnType<typeof signalFixture>[],
  counts: { building: 0, area: 0, unresolved: 2, total: 2 },
  limit: 5000,
  truncated: false,
};

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<ApiModule>('@/lib/api');
  return { ...actual, fetchCitySignals: vi.fn(async () => payload) };
});

function show(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CitySignals />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  act(() => {
    useCityScene.setState({ signals: [], treatments: new Map(), showArchived: false });
  });
});

describe('the census panel', () => {
  it('says how many roles the city is holding back', async () => {
    const corpus = [signalFixture({ job_id: 'a' }), signalFixture({ job_id: 'b' })];
    payload.signals = corpus;
    act(() =>
      useCityScene.setState({
        signals: corpus,
        treatments: new Map([
          ['b', { track: 'archived', pulse: 'none', beam: 'none', dimmed: false }],
        ]),
      }),
    );

    show();

    expect(await screen.findByText(/1 of these is archived/i)).toBeInTheDocument();
  });

  it('says nothing about archiving when nothing is archived', async () => {
    payload.signals = [signalFixture({ job_id: 'a' })];
    act(() => useCityScene.setState({ signals: payload.signals }));

    show();

    await screen.findByText(/roles, grouped by employer/i);
    expect(screen.queryByText(/archived/i)).toBeNull();
  });
});
