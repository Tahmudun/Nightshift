import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SaveJobButton } from './SaveJobButton';

// `fireEvent`, not `@testing-library/user-event` — the latter is not a
// dependency of this project and a click is the only interaction here.
vi.mock('@/lib/api', () => ({
  fetchApplications: vi.fn(),
  saveJob: vi.fn(),
}));

const { fetchApplications, saveJob } = await import('@/lib/api');

function renderButton(jobId: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SaveJobButton jobId={jobId} />
    </QueryClientProvider>,
  );
}

const EMPTY = {
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
  deferred_fields: [],
};

describe('SaveJobButton', () => {
  beforeEach(() => vi.resetAllMocks());

  it('offers to save a job that is not in the pipeline', async () => {
    vi.mocked(fetchApplications).mockResolvedValue(EMPTY);
    renderButton('job-1');
    expect(await screen.findByRole('button', { name: /save/i })).toBeEnabled();
  });

  it('shows the stage instead of a save button once the job is tracked', async () => {
    vi.mocked(fetchApplications).mockResolvedValue({
      ...EMPTY,
      total: 1,
      items: [{ id: 'app-1', job: { id: 'job-1' }, current_stage: 'applied', archived_at: null }],
    } as never);
    renderButton('job-1');
    // Not "Saved". The control tells the truth about where the role actually
    // is, so a job at `interview` does not read as merely bookmarked.
    expect(await screen.findByText(/applied/i)).toBeVisible();
    expect(screen.queryByRole('button', { name: /^save$/i })).toBeNull();
  });

  it('still reports an archived application instead of offering to save it again', async () => {
    // Without `archived: true` on the query the row is invisible here, the
    // button says "Save", and clicking it returns 200 and changes nothing —
    // a control that looks broken because it is describing the wrong state.
    vi.mocked(fetchApplications).mockResolvedValue({
      ...EMPTY,
      total: 1,
      items: [
        {
          id: 'app-1',
          job: { id: 'job-1' },
          current_stage: 'saved',
          archived_at: '2026-08-03T00:00:00Z',
        },
      ],
    } as never);
    renderButton('job-1');

    expect(await screen.findByRole('link')).toHaveTextContent(/archived/i);
    expect(screen.queryByRole('button', { name: /^save$/i })).toBeNull();
    expect(vi.mocked(fetchApplications).mock.calls[0]?.[0]).toMatchObject({ archived: true });
  });

  it('saves once per click and does not go blank while it waits', async () => {
    vi.mocked(fetchApplications).mockResolvedValue(EMPTY);
    vi.mocked(saveJob).mockResolvedValue({ id: 'app-1' } as never);
    renderButton('job-1');

    fireEvent.click(await screen.findByRole('button', { name: /save/i }));

    await waitFor(() => expect(saveJob).toHaveBeenCalledTimes(1));
    expect(saveJob).toHaveBeenCalledWith('job-1');
    // The control never disappears mid-flight. A button that vanishes while a
    // request is in the air reads as a click that did nothing.
    expect(screen.getByRole('button')).toBeVisible();
  });

  it('says what went wrong instead of silently doing nothing', async () => {
    vi.mocked(fetchApplications).mockResolvedValue(EMPTY);
    vi.mocked(saveJob).mockRejectedValue(new Error('cannot reach the API'));
    renderButton('job-1');

    fireEvent.click(await screen.findByRole('button', { name: /save/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/cannot reach the API/i);
  });
});
