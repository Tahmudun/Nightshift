import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CityDetail, daysSince } from './CityDetail';
import { useCityScene } from '@/lib/city/scene';
import { signalFixture } from '@/lib/city/signal.fixture';
import type { CitySignal } from '@/lib/schemas';

/**
 * The router and the query string, faked at the module boundary.
 *
 * `replace` is the assertion target for half of this file: §5.6 asks a
 * selection to be shareable and to preserve filters, and the only observable
 * form of "shareable" in jsdom is the URL this component asks the router for.
 */
const replace = vi.fn();
let query = '';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace }),
  usePathname: () => '/explore/city',
  useSearchParams: () => new URLSearchParams(query),
}));

vi.mock('@/lib/api', () => ({
  fetchApplications: vi.fn(async () => ({ items: [], total: 0 })),
  saveJob: vi.fn(),
}));

const JOB = '3f9a1c22-9b4e-4c7a-9f1d-2b6e5a8c0d31';
const OTHER = '11111111-2222-4333-8444-555555555555';

function signal(overrides: Partial<CitySignal> = {}): CitySignal {
  return signalFixture({
    job_id: JOB,
    title: 'Infrastructure Engineer',
    company_id: '99999999-8888-4777-8666-555555555555',
    employment_type: 'internship',
    remote_policy: 'hybrid',
    first_seen_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
    ...overrides,
  });
}

function show(): void {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <CityDetail />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  replace.mockClear();
  query = '';
  useCityScene.setState({
    signals: [],
    status: { kind: 'loading' },
    sort: 'company',
    camera: null,
    mapReady: false,
    selected: null,
  });
});

describe('the detail panel', () => {
  it('shows nothing at all when nothing is selected', () => {
    show();

    expect(screen.queryByTestId('city-detail')).toBeNull();
  });

  it('describes the selected role', () => {
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: JOB });

    show();

    expect(screen.getByRole('heading', { name: 'Infrastructure Engineer' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Alloy' })).toBeInTheDocument();
    expect(screen.getByText('Internship')).toBeInTheDocument();
    expect(screen.getByText('Hybrid')).toBeInTheDocument();
  });

  it('says the position means the employer and nothing about New York', () => {
    // I1 is not satisfied by a comment in the source. The beacon *is* somewhere,
    // above New York, and a person reads a position as a location unless they
    // are told otherwise in the place they are looking.
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: JOB });

    show();

    expect(screen.getByText(/Floating — no confirmed address/)).toBeInTheDocument();
    expect(screen.getByText(/nothing whatsoever about where in New York/)).toBeInTheDocument();
  });

  it('quotes the source’s own words for where the role is', () => {
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: JOB });

    show();

    expect(screen.getByText('“New York, NY”')).toBeInTheDocument();
  });

  it('glosses a stale status rather than leaving the enum to be misread', () => {
    // "Possibly stale" reads as "probably gone", which is the opposite of what
    // I3 records: a source going quiet is not evidence a job closed.
    useCityScene.setState({
      signals: [signal({ status: 'possibly_stale' })],
      status: { kind: 'ready' },
      selected: JOB,
    });

    show();

    expect(screen.getByText(/not a statement that it closed/)).toBeInTheDocument();
  });

  it('offers a way out that is a word rather than a symbol', () => {
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: JOB });
    show();

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(useCityScene.getState().selected).toBeNull();
  });

  it('clears the selection on escape, from anywhere on the page', () => {
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: JOB });
    show();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(useCityScene.getState().selected).toBeNull();
  });

  it('says so when a shared link names a role that is not on this city', () => {
    // Reachable two honest ways: a link to a role that has since closed, and a
    // poll that removed one while the panel was open.
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: OTHER });

    show();

    expect(screen.getByText(/That role is not on this city/)).toBeInTheDocument();
  });
});

describe('the selection and the URL', () => {
  it('writes a selection made on the city into the address bar', () => {
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: JOB });

    show();

    expect(replace).toHaveBeenCalledWith(`/explore/city?job=${JOB}`, { scroll: false });
  });

  it('keeps the filters that were already there — §5.6', () => {
    query = 'remote_policy=hybrid';
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: JOB });

    show();

    const href = replace.mock.calls[0]?.[0] as string;
    const params = new URL(href, 'https://example.test').searchParams;
    expect(params.get('remote_policy')).toBe('hybrid');
    expect(params.get('job')).toBe(JOB);
  });

  it('adopts a role named in the URL on the way in', () => {
    query = `job=${JOB}`;
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: null });

    show();

    expect(useCityScene.getState().selected).toBe(JOB);
  });

  it('does not immediately delete the deep link it just adopted', () => {
    // The bug this exists for: with one effect per direction, the store-to-URL
    // effect closes over the selection from the render *before* the deep link
    // was adopted, sees a mismatch, and rewrites the URL to remove `?job=`.
    // The link works for one frame and then destroys itself.
    query = `job=${JOB}`;
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: null });

    show();

    expect(replace).not.toHaveBeenCalled();
  });

  it('drops the parameter entirely when the selection is cleared', () => {
    query = `job=${JOB}`;
    useCityScene.setState({ signals: [signal()], status: { kind: 'ready' }, selected: JOB });
    show();
    replace.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(replace).toHaveBeenCalledWith('/explore/city', { scroll: false });
  });
});

describe('daysSince', () => {
  it('counts whole days', () => {
    const now = Date.parse('2026-08-12T09:00:00Z');
    expect(daysSince('2026-08-12T08:00:00Z', now)).toBe(0);
    expect(daysSince('2026-08-09T08:00:00Z', now)).toBe(3);
  });

  it('never reports a role first seen in the future as negative', () => {
    // Clock skew between a machine and the database is not a reason to render
    // "first seen -1 days ago".
    const now = Date.parse('2026-08-12T09:00:00Z');
    expect(daysSince('2026-08-13T09:00:00Z', now)).toBe(0);
  });
});

describe('the detail panel says how the role is drawn — §5.6’s non-3D equivalent', () => {
  it('names every mark the beacon is carrying', () => {
    // A person who cannot see the canvas, or who cannot tell gold from cyan,
    // gets the encoding in words. §12.4 in a sentence rather than a swatch.
    useCityScene.setState({
      signals: [signal()],
      selected: JOB,
      treatments: new Map([
        [JOB, { track: 'saved', pulse: 'rapid', beam: 'deadline', dimmed: false }],
      ]),
    });
    show();

    expect(screen.getByTestId('city-detail')).toHaveTextContent(/saved/i);
    expect(screen.getByTestId('city-detail')).toHaveTextContent(/new internship/i);
    expect(screen.getByTestId('city-detail')).toHaveTextContent(/deadline/i);
  });

  it('says when a dimmed role was last checked, rather than only dimming it', () => {
    // §6's stale row in full: "reduced opacity + an explicit 'last verified N
    // days ago'". The dimming alone reads as a rendering fault.
    useCityScene.setState({
      signals: [
        signal({
          status: 'possibly_stale',
          last_seen_at: new Date(Date.now() - 9 * 86_400_000).toISOString(),
        }),
      ],
      selected: JOB,
      treatments: new Map([[JOB, { track: 'none', pulse: 'none', beam: 'none', dimmed: true }]]),
    });
    show();

    expect(screen.getByTestId('city-detail')).toHaveTextContent(/9 days ago/);
  });

  it('separates being listed from being read, when the two differ', () => {
    // ADR 0007's phase-2 polling never refetches an unchanged posting, so a
    // role can be listed daily and last read months ago. Printing the weaker
    // observation under the stronger one's name would invent an observation.
    useCityScene.setState({
      signals: [
        signal({
          status: 'possibly_stale',
          last_seen_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
          last_verified_at: new Date(Date.now() - 40 * 86_400_000).toISOString(),
        }),
      ],
      selected: JOB,
      treatments: new Map([[JOB, { track: 'none', pulse: 'none', beam: 'none', dimmed: true }]]),
    });
    show();

    const panel = screen.getByTestId('city-detail');
    expect(panel).toHaveTextContent(/listed on its board 2 days ago/i);
    expect(panel).toHaveTextContent(/read 40 days ago/i);
  });

  it('says a role has never been read, rather than saying nothing', () => {
    useCityScene.setState({
      signals: [signal({ status: 'unverified', last_verified_at: null })],
      selected: JOB,
      treatments: new Map([[JOB, { track: 'none', pulse: 'none', beam: 'none', dimmed: true }]]),
    });
    show();

    expect(screen.getByTestId('city-detail')).toHaveTextContent(/never been re-read/i);
  });

  it('says nothing about marks for a role that carries none', () => {
    useCityScene.setState({
      signals: [signal()],
      selected: JOB,
      treatments: new Map([[JOB, { track: 'none', pulse: 'none', beam: 'none', dimmed: false }]]),
    });
    show();

    expect(screen.getByTestId('city-detail')).not.toHaveTextContent(/how this role is drawn/i);
  });
});
