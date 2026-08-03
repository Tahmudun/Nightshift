import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PipelineBoard } from './PipelineBoard';

vi.mock('@/lib/api', () => ({
  fetchApplications: vi.fn(),
}));

const { fetchApplications } = await import('@/lib/api');

function renderBoard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PipelineBoard />
    </QueryClientProvider>,
  );
}

const ZERO_COUNTS = {
  discovered: 0,
  saved: 0,
  preparing: 0,
  applied: 0,
  assessment: 0,
  interview: 0,
  offer: 0,
  rejected: 0,
  withdrawn: 0,
  closed: 0,
};

const EMPTY = {
  items: [],
  total: 0,
  limit: 100,
  offset: 0,
  stage_counts: ZERO_COUNTS,
  archived_count: 0,
  deferred_fields: [],
};

function anApplication(id: string, stage: string, title: string) {
  return {
    id,
    job: {
      id: `job-${id}`,
      title,
      company: { id: 'c-1', canonical_name: 'Example Inc.', website: null },
      employment_type: 'full_time',
      remote_policy: 'on_site',
      status: 'open',
      locations: [],
      salary: { provided: false, minimum: null, maximum: null, currency: null, period: null },
      source_published_at: null,
      source_updated_at: null,
      first_seen_at: '2026-08-01T00:00:00Z',
      last_seen_at: '2026-08-01T00:00:00Z',
      application_deadline: null,
    },
    current_stage: stage,
    priority: 'normal',
    applied_at: null,
    next_action_at: null,
    application_url: null,
    source_of_application: null,
    archived_at: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
  };
}

describe('PipelineBoard', () => {
  beforeEach(() => vi.resetAllMocks());

  it('says what to do instead of rendering an empty grid', async () => {
    vi.mocked(fetchApplications).mockResolvedValue(EMPTY as never);
    renderBoard();
    // Ten empty stage columns read as a broken page, not as an empty pipeline.
    expect(await screen.findByText(/nothing saved yet/i)).toBeVisible();
    expect(screen.getByRole('link', { name: /explore/i })).toHaveAttribute('href', '/explore');
    expect(screen.queryByRole('heading', { name: /^interview$/i })).toBeNull();
  });

  it('groups applications under the stage they are actually at', async () => {
    vi.mocked(fetchApplications).mockResolvedValue({
      ...EMPTY,
      total: 2,
      items: [
        anApplication('a1', 'saved', 'Backend Engineer'),
        anApplication('a2', 'offer', 'SRE'),
      ],
      stage_counts: { ...ZERO_COUNTS, saved: 1, offer: 1 },
    } as never);
    renderBoard();

    expect(await screen.findByRole('heading', { name: /^saved$/i })).toBeVisible();
    expect(screen.getByRole('heading', { name: /^offer$/i })).toBeVisible();
    // A stage nobody is at is not rendered as an empty box.
    expect(screen.queryByRole('heading', { name: /^assessment$/i })).toBeNull();
    expect(screen.getByRole('link', { name: /Backend Engineer/ })).toHaveAttribute(
      'href',
      '/operate/applications/a1',
    );
  });

  it('states the archived count rather than hiding archived rows silently', async () => {
    vi.mocked(fetchApplications).mockResolvedValue({
      ...EMPTY,
      total: 1,
      items: [anApplication('a1', 'saved', 'Backend Engineer')],
      stage_counts: { ...ZERO_COUNTS, saved: 1 },
      archived_count: 2,
    } as never);
    renderBoard();

    const toggle = await screen.findByRole('button', { name: /archived/i });
    expect(toggle).toHaveTextContent('2');

    fireEvent.click(toggle);
    // The toggle re-queries with archived included, rather than filtering a
    // list that never contained them.
    expect(vi.mocked(fetchApplications).mock.calls.at(-1)?.[0]).toMatchObject({ archived: true });
  });
});
