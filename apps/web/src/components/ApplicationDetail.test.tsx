import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApplicationDetailView } from './ApplicationDetail';

vi.mock('@/lib/api', () => ({
  fetchApplication: vi.fn(),
  fetchApplications: vi.fn(),
  changeStage: vi.fn(),
  addNote: vi.fn(),
  scheduleInterview: vi.fn(),
  patchApplication: vi.fn(),
  setArchived: vi.fn(),
}));

const { fetchApplication, fetchApplications } = await import('@/lib/api');

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ApplicationDetailView applicationId="app-1" />
    </QueryClientProvider>,
  );
}

const DEFERRED = {
  items: [],
  total: 0,
  limit: 100,
  offset: 0,
  stage_counts: {
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
  },
  archived_count: 0,
  deferred_fields: [
    {
      name: 'Selected resume',
      blocked_on: 'M2c',
      reason: 'there is no resumes table yet',
    },
  ],
};

const APPLICATION = {
  id: 'app-1',
  job: {
    id: 'job-1',
    title: 'Software Engineer',
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
  current_stage: 'applied',
  priority: 'normal',
  applied_at: '2026-08-02T00:00:00Z',
  next_action_at: null,
  application_url: 'https://boards.example.test/apply/1',
  source_of_application: null,
  archived_at: null,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-02T00:00:00Z',
  events: [],
};

describe('ApplicationDetailView', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(fetchApplications).mockResolvedValue(DEFERRED as never);
  });

  it('renders the whole history, oldest first', async () => {
    vi.mocked(fetchApplication).mockResolvedValue({
      ...APPLICATION,
      events: [
        {
          id: 'e1',
          event_type: 'saved',
          actor: 'user',
          occurred_at: '2026-08-01T00:00:00Z',
          from_stage: null,
          to_stage: 'saved',
          transition_class: 'advance',
          body: null,
          payload: {},
          created_at: '2026-08-01T00:00:00Z',
        },
        {
          id: 'e2',
          event_type: 'note_added',
          actor: 'user',
          occurred_at: '2026-08-02T00:00:00Z',
          from_stage: null,
          to_stage: null,
          transition_class: null,
          body: 'Referred by Sam',
          payload: {},
          created_at: '2026-08-02T00:00:00Z',
        },
      ],
    } as never);

    renderDetail();
    expect(await screen.findByText('Referred by Sam')).toBeVisible();
    const items = screen.getAllByTestId('history-entry');
    expect(items[0]).toHaveTextContent(/saved/i);
    expect(items[1]).toHaveTextContent(/Referred by Sam/);
  });

  it('shows a closed listing as a prompt, not as a stage', async () => {
    // The assertion for §3's last paragraph. If this ever renders as "stage:
    // closed", the system has decided something for the user.
    vi.mocked(fetchApplication).mockResolvedValue({
      ...APPLICATION,
      events: [
        {
          id: 'e1',
          event_type: 'listing_closed',
          actor: 'system',
          occurred_at: '2026-08-03T00:00:00Z',
          from_stage: null,
          to_stage: null,
          transition_class: null,
          body: 'the source stopped listing this role: 3 misses',
          payload: {},
          created_at: '2026-08-03T00:00:00Z',
        },
      ],
    } as never);

    renderDetail();
    expect(await screen.findByRole('status')).toHaveTextContent(/no longer listed/i);
    expect(screen.getByTestId('current-stage')).toHaveTextContent(/applied/i);
  });

  it('drops the prompt once the user has answered it', async () => {
    // A prompt that survives the answer is a prompt people learn to ignore.
    vi.mocked(fetchApplication).mockResolvedValue({
      ...APPLICATION,
      current_stage: 'withdrawn',
      events: [
        {
          id: 'e1',
          event_type: 'listing_closed',
          actor: 'system',
          occurred_at: '2026-08-03T00:00:00Z',
          from_stage: null,
          to_stage: null,
          transition_class: null,
          body: 'the source stopped listing this role',
          payload: {},
          created_at: '2026-08-03T00:00:00Z',
        },
        {
          id: 'e2',
          event_type: 'stage_changed',
          actor: 'user',
          occurred_at: '2026-08-04T00:00:00Z',
          from_stage: 'applied',
          to_stage: 'withdrawn',
          transition_class: 'advance',
          body: null,
          payload: {},
          created_at: '2026-08-04T00:00:00Z',
        },
      ],
    } as never);

    renderDetail();
    await screen.findByTestId('current-stage');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('opens the source posting in a new tab rather than applying', async () => {
    // Invariant I5 at the last place a user could misread it.
    vi.mocked(fetchApplication).mockResolvedValue(APPLICATION as never);
    renderDetail();

    const link = await screen.findByRole('link', { name: /open the posting/i });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('href', 'https://boards.example.test/apply/1');
    expect(screen.queryByRole('button', { name: /^apply$/i })).toBeNull();
  });

  it('offers "I applied" only before the application has been applied', async () => {
    // The API answers 409 for a no-op stage change, and a button that always
    // errors is worse than no button.
    vi.mocked(fetchApplication).mockResolvedValue({
      ...APPLICATION,
      current_stage: 'saved',
    } as never);
    renderDetail();
    expect(await screen.findByRole('button', { name: /i applied/i })).toBeVisible();
  });

  it('hides "I applied" once the stage is already applied or later', async () => {
    vi.mocked(fetchApplication).mockResolvedValue(APPLICATION as never);
    renderDetail();
    await screen.findByTestId('current-stage');
    expect(screen.queryByRole('button', { name: /i applied/i })).toBeNull();
  });

  it('names what tracking cannot record yet', async () => {
    vi.mocked(fetchApplication).mockResolvedValue(APPLICATION as never);
    renderDetail();
    // I7: listed rather than hidden, for the same reason JobDetail lists its
    // seven uncomputed fields.
    expect(await screen.findByTestId('deferred-tracking')).toHaveTextContent(/resume/i);
  });

  it('labels a system-recorded event so nobody thinks they did it', async () => {
    vi.mocked(fetchApplication).mockResolvedValue({
      ...APPLICATION,
      events: [
        {
          id: 'e1',
          event_type: 'listing_closed',
          actor: 'system',
          occurred_at: '2026-08-03T00:00:00Z',
          from_stage: null,
          to_stage: null,
          transition_class: null,
          body: 'the source stopped listing this role',
          payload: {},
          created_at: '2026-08-03T00:00:00Z',
        },
      ],
    } as never);

    renderDetail();
    const entry = await screen.findByTestId('history-entry');
    expect(entry).toHaveTextContent(/recorded by Nightshift/i);
  });
});
