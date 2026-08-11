import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { QueuePanel } from './QueuePanel';
import { dailyQueueSchema, type DailyQueue } from '@/lib/schemas';

vi.mock('@/lib/api', () => ({
  fetchQueue: vi.fn(),
}));

const { fetchQueue } = await import('@/lib/api');

/** An empty section, so a fixture states only what it is about. */
function bare(
  key: DailyQueue['sections'][number]['key'],
  title: string,
): DailyQueue['sections'][number] {
  return { key, title, rows: [], total: 0, blind_spots: [], note: null };
}

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
          eligibility: null,
        },
      ],
      total: 24,
      blind_spots: [],
      note: null,
    },
    bare('interviews_approaching', 'Interviews approaching'),
    bare('stale_saved', 'Saved and going quiet'),
    bare('closed_while_saved', 'Closed while you were tracking it'),
    {
      key: 'requirement_gaps',
      title: 'Gaps on roles you are tracking',
      rows: [
        {
          application_id: '00000000-0000-4000-8000-000000000004',
          job_id: '00000000-0000-4000-8000-000000000005',
          job_title: 'Platform Engineer',
          company_name: 'Datadog',
          current_stage: 'saved',
          // A gap is not an event and has no date.
          at: null,
          because:
            'asks for Kubernetes, Go and Terraform — nothing you have confirmed answers them',
          eligibility: 'eligible',
        },
      ],
      total: 1,
      blind_spots: [
        { name: 'not_yet_scored', count: 0, because: 'tracked roles with no score yet.' },
      ],
      note:
        'What these postings state they require that nothing in your confirmed skills ' +
        'answers. Read from your profile, never from a file you uploaded.',
    },
    {
      key: 'best_new_internships',
      title: 'New internships worth a look',
      rows: [
        {
          // M3d Task 7: a posting the reader is not tracking, so there is no
          // application behind it.
          application_id: null,
          job_id: '00000000-0000-4000-8000-000000000003',
          job_title: 'Software Engineer Internship',
          company_name: 'Ramp',
          current_stage: null,
          at: '2026-08-01T12:00:00+00:00',
          because: 'internship for summer 2027, first listed 3 days ago',
          eligibility: 'uncertain',
        },
      ],
      total: 1,
      blind_spots: [
        { name: 'not_yet_scored', count: 4, because: 'recent internships with no score yet.' },
        {
          name: 'level_not_read',
          count: 0,
          because: 'recent postings whose level was unreadable.',
        },
      ],
      note: 'Internships first listed in the last 14 days that you are not already tracking.',
    },
  ],
  total_rows: 25,
  deferred_rows: [
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

  it('names every deferred row without anything being expanded', async () => {
    renderPanel(QUEUE);
    const deferred = await screen.findByTestId('deferred-queue-rows');
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

  // --- M3d Task 7: rows about postings nobody is tracking yet ---------------

  it('links a row with no application to the posting instead', async () => {
    // There is no application to open. Linking to the job is also where the
    // sentence behind the eligibility state lives.
    renderPanel(QUEUE);
    const link = await screen.findByRole('link', { name: /Software Engineer Internship/i });
    expect(link).toHaveAttribute('href', '/explore/jobs/00000000-0000-4000-8000-000000000003');
  });

  it('shows a suggested row as a state and never as a number', async () => {
    // I4: a bare score with no breakdown behind it is a bug. The band the row
    // came out of is a verdict, and the posting page carries its reason.
    renderPanel(QUEUE);
    const section = await screen.findByTestId('queue-section-best_new_internships');
    expect(section).toHaveTextContent(/not enough stated to tell/i);
    expect(section.textContent ?? '').not.toMatch(/\d+\s*%/);
  });

  it('states what a section could not see', async () => {
    // A row computed from scores shows fewer items when the sweep is behind,
    // and that looks exactly like having less to do.
    renderPanel(QUEUE);
    const spots = await screen.findByTestId('queue-blind-spots-best_new_internships');
    expect(spots).toHaveTextContent(/4/);
    expect(spots).toHaveTextContent(/recent internships with no score yet/i);
  });

  it('does not print a blind spot nobody has', async () => {
    // The API sends every spot so the shape is stable. A permanent "0 hidden"
    // line is noise, and noise is what stops the non-zero one being read.
    renderPanel(QUEUE);
    const spots = await screen.findByTestId('queue-blind-spots-best_new_internships');
    expect(spots).not.toHaveTextContent(/unreadable/i);
  });

  it('names the gaps on a tracked role rather than counting them', async () => {
    renderPanel(QUEUE);
    const section = await screen.findByTestId('queue-section-requirement_gaps');
    expect(section).toHaveTextContent(/asks for Kubernetes, Go and Terraform/i);
  });

  it('never calls a requirement gap a resume problem', async () => {
    // ADR 0019. The list comes from confirmed skills; a resume proposal is not
    // a fact about anybody until they say it is (I2). The old spec name for
    // this row would make a true statement about a database read as a false
    // one about a document.
    renderPanel(QUEUE);
    const section = await screen.findByTestId('queue-section-requirement_gaps');
    expect(section.textContent ?? '').not.toMatch(/resume/i);
    expect(section).toHaveTextContent(/confirmed skills/i);
  });

  it('explains a section whose rows cannot explain themselves', async () => {
    renderPanel(QUEUE);
    const section = await screen.findByTestId('queue-section-best_new_internships');
    expect(section).toHaveTextContent(/first listed in the last 14 days/i);
  });

  it('renders no control that changes anything', async () => {
    // §7.3: the queue suggests and never acts. If a button appears here, it
    // is a decision to be made deliberately rather than by accident.
    renderPanel(QUEUE);
    await screen.findByText('Backend Engineer');
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });
});
