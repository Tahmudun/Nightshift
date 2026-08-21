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
  payload.counts = { building: 0, area: 0, unresolved: 2, total: 2 };
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

  /**
   * A role the renderer counts and does not draw is counted here and drawn
   * nowhere, and the honest form of that is a sentence rather than a silence —
   * see the comment beside `undrawn` in the component.
   *
   * The set shrank on 2026-08-17. Roles on a building are now drawn on it, so
   * only `area` remains, and this test was rewritten rather than deleted: the
   * sentence is the guard, and the guard has to keep naming the right rows or
   * it starts lying in the other direction — claiming a role is missing from a
   * sky it is standing in.
   */
  it('names the roles it counts but cannot place, rather than counting them and drawing nothing', async () => {
    payload.signals = [signalFixture({ job_id: 'a' })];
    payload.counts = { building: 3, area: 1, unresolved: 5, total: 9 };
    act(() => useCityScene.setState({ signals: payload.signals }));

    show();

    expect(await screen.findByText(/1 of these is not drawn on this map yet/i)).toBeInTheDocument();
  });

  it('stops calling a placed role undrawn now that it is drawn on its building', async () => {
    payload.signals = [signalFixture({ job_id: 'a' })];
    payload.counts = { building: 4, area: 0, unresolved: 5, total: 9 };
    act(() => useCityScene.setState({ signals: payload.signals }));

    show();

    await screen.findByText(/roles, grouped by employer/i);
    expect(screen.queryByText(/not drawn on this map/i)).toBeNull();
  });

  it('says nothing about undrawn roles when the whole corpus is in the field', async () => {
    payload.signals = [signalFixture({ job_id: 'a' })];
    act(() => useCityScene.setState({ signals: payload.signals }));

    show();

    await screen.findByText(/roles, grouped by employer/i);
    expect(screen.queryByText(/not drawn on this map/i)).toBeNull();
  });

  it('says nothing about archiving when nothing is archived', async () => {
    payload.signals = [signalFixture({ job_id: 'a' })];
    act(() => useCityScene.setState({ signals: payload.signals }));

    show();

    await screen.findByText(/roles, grouped by employer/i);
    expect(screen.queryByText(/archived/i)).toBeNull();
  });
});
