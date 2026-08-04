import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { QueuePanel } from './QueuePanel';
import { dailyQueueSchema, type DailyQueue } from '@/lib/schemas';

vi.mock('@/lib/api', () => ({
  fetchQueue: vi.fn(),
}));

const { fetchQueue } = await import('@/lib/api');

const QUEUE: DailyQueue = {
  generated_at: '2026-08-04T12:00:00+00:00',
  sections: [
    {
      key: 'follow_up',
      title: 'Follow up',
      rows: [
        {
          application_id: '00000000-0000-4000-8000-000000000001',
          job_id: '00000000-0000-4000-8000-000000000002',
          job_title: 'Backend Engineer',
          company_name: 'Example Inc.',
          current_stage: 'applied',
          at: '2026-07-26T12:00:00+00:00',
          because: 'no activity from you in 9 days',
        },
      ],
      total: 24,
    },
    { key: 'interviews_approaching', title: 'Interviews approaching', rows: [], total: 0 },
    { key: 'stale_saved', title: 'Saved and going quiet', rows: [], total: 0 },
    { key: 'closed_while_saved', title: 'Closed while you were tracking it', rows: [], total: 0 },
  ],
  total_rows: 24,
  deferred_rows: [
    {
      name: 'Best new internships',
      blocked_on: 'milestone 3',
      reason: 'there is no match score yet',
    },
    { name: 'High-match roles closing soon', blocked_on: 'milestone 3', reason: 'needs a score' },
    { name: 'Resume mismatch warnings', blocked_on: 'milestone 3', reason: 'needs extraction' },
    { name: 'The one thing to do today', blocked_on: 'milestone 3', reason: 'needs ranking' },
  ],
  thresholds: {
    follow_up_silent_days: 7,
    stale_saved_days: 21,
    interview_horizon_days: 14,
    row_cap: 20,
  },
};

function renderPanel(queue: DailyQueue) {
  vi.mocked(fetchQueue).mockResolvedValue(queue);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <QueuePanel />
    </QueryClientProvider>,
  );
}

describe('QueuePanel', () => {
  it('parses its own fixture through the real schema', () => {
    // M2c shipped a component fixture the API could not produce, sitting
    // inside the test for the schema that would have refused it.
    expect(dailyQueueSchema.safeParse(QUEUE).success).toBe(true);
  });

  it('shows each row with the reason it is there', async () => {
    renderPanel(QUEUE);
    expect(await screen.findByText('Backend Engineer')).toBeInTheDocument();
    expect(screen.getByText(/no activity from you in 9 days/i)).toBeInTheDocument();
  });

  it('links each row to its application', async () => {
    renderPanel(QUEUE);
    const link = await screen.findByRole('link', { name: /Backend Engineer/i });
    expect(link).toHaveAttribute(
      'href',
      '/operate/applications/00000000-0000-4000-8000-000000000001',
    );
  });

  it('names every section, including the empty ones', async () => {
    renderPanel(QUEUE);
    expect(await screen.findByText('Follow up')).toBeInTheDocument();
    expect(screen.getByText('Interviews approaching')).toBeInTheDocument();
    expect(screen.getByText('Saved and going quiet')).toBeInTheDocument();
    expect(screen.getByText('Closed while you were tracking it')).toBeInTheDocument();
  });

  it('says how many rows it capped rather than truncating quietly', async () => {
    renderPanel(QUEUE);
    expect(await screen.findByText(/23 more/i)).toBeInTheDocument();
  });

  it('names all four deferred rows without anything being expanded', async () => {
    renderPanel(QUEUE);
    const deferred = await screen.findByTestId('deferred-queue-rows');
    expect(deferred).toHaveTextContent(/best new internships/i);
    expect(deferred).toHaveTextContent(/resume mismatch/i);
    expect(deferred).toHaveTextContent(/one thing to do today/i);
    expect(deferred).toHaveTextContent(/milestone 3/i);
  });

  it('shows no number beside a deferred row', async () => {
    // A count next to a deferred row reads as a real, empty result.
    renderPanel(QUEUE);
    const deferred = await screen.findByTestId('deferred-queue-rows');
    expect(deferred.textContent ?? '').not.toMatch(/\(\s*\d+\s*\)/);
  });

  it('distinguishes an empty section from an empty queue', async () => {
    const empty: DailyQueue = {
      ...QUEUE,
      sections: QUEUE.sections.map((section) => ({ ...section, rows: [], total: 0 })),
      total_rows: 0,
    };
    renderPanel(empty);
    expect(await screen.findByTestId('queue-empty')).toHaveTextContent(/nothing needs you today/i);
  });

  it('does not claim an empty queue when a section has rows', async () => {
    // The inverse of the test above. Without it, a component that always
    // rendered the empty block would pass.
    renderPanel(QUEUE);
    await screen.findByText('Backend Engineer');
    expect(screen.queryByTestId('queue-empty')).toBeNull();
  });

  it('explains the thresholds using the numbers the API sent', async () => {
    // Not hardcoded in TypeScript. The API is the authority on what it
    // filtered by, and M2c's defect was two copies of one vocabulary drifting.
    renderPanel(QUEUE);
    const explainer = await screen.findByTestId('queue-thresholds');
    expect(explainer).toHaveTextContent(/7 days/);
    expect(explainer).toHaveTextContent(/21 days/);
    expect(explainer).toHaveTextContent(/14 days/);
  });

  it('renders no control that changes anything', async () => {
    // §7.3: the queue suggests and never acts. If a button appears here, it
    // is a decision to be made deliberately rather than by accident.
    renderPanel(QUEUE);
    await screen.findByText('Backend Engineer');
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });
});
