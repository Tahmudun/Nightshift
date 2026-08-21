import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CapturePosting } from './CapturePosting';
import type { Capture } from '@/lib/schemas';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    capturePosting: vi.fn(),
    confirmCapture: vi.fn(),
    discardCapture: vi.fn(),
  };
});

const { capturePosting, confirmCapture } = await import('@/lib/api');

function aCapture(proposed: Partial<Capture['proposed']> = {}): Capture {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    status: 'pending',
    source_url: null,
    raw_text: 'pasted text',
    proposed: {
      title: null,
      company_name: null,
      location_text: null,
      employment_type: null,
      ...proposed,
    },
    parser_version: '1',
    job_id: null,
    created_at: '2026-08-19T12:00:00+00:00',
    decided_at: null,
  };
}

function renderCapture() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CapturePosting />
    </QueryClientProvider>,
  );
}

async function pasteAndRead(capture: Capture) {
  vi.mocked(capturePosting).mockResolvedValue(capture);
  renderCapture();
  fireEvent.change(screen.getByLabelText(/the posting/i), {
    target: { value: 'Staff Engineer\nRamp · New York, NY' },
  });
  fireEvent.click(screen.getByRole('button', { name: /read it/i }));
  await waitFor(() => expect(screen.getByTestId('capture-review')).toBeInTheDocument());
}

describe('CapturePosting', () => {
  it('says nothing is saved yet on the review step', async () => {
    // The whole point of the two-step. A person who thinks the paste already
    // saved something will not read the fields, which is exactly the case the
    // confirmation exists to prevent.
    await pasteAndRead(aCapture({ title: 'Staff Engineer', company_name: 'Ramp' }));
    expect(screen.getByTestId('capture-review')).toHaveTextContent(/nothing is saved yet/i);
  });

  it('leaves a declined field empty and says it was not read', async () => {
    // A10, and the one place it decides more than a label: a guessed employer
    // is a job standing on somebody else's building (I1).
    await pasteAndRead(aCapture({ title: 'Staff Engineer', company_name: null }));

    expect(screen.getByLabelText(/employer/i)).toHaveValue('');
    expect(screen.getByTestId('capture-review')).toHaveTextContent(/not read from the text/i);
  });

  it('will not confirm without a title and an employer', async () => {
    await pasteAndRead(aCapture({ title: 'Staff Engineer', company_name: null }));
    expect(screen.getByRole('button', { name: /this is right/i })).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/employer/i), { target: { value: 'Ramp' } });
    expect(screen.getByRole('button', { name: /this is right/i })).toBeEnabled();
  });

  it('sends what the person left in the boxes, not what the parser proposed', async () => {
    // The correction path. If this ever sends `proposed`, a parser mistake the
    // person visibly fixed goes into the corpus anyway.
    await pasteAndRead(aCapture({ title: 'Staff Engineer', company_name: 'Ramp' }));
    vi.mocked(confirmCapture).mockResolvedValue({
      ...aCapture(),
      status: 'confirmed',
      job_id: '00000000-0000-4000-8000-000000000002',
    });

    fireEvent.change(screen.getByLabelText(/employer/i), { target: { value: 'Not Ramp' } });
    fireEvent.click(screen.getByRole('button', { name: /this is right/i }));

    await waitFor(() => expect(confirmCapture).toHaveBeenCalled());
    const [, approved] = vi.mocked(confirmCapture).mock.calls.at(0) ?? [];
    expect(approved).toMatchObject({
      title: 'Staff Engineer',
      company_name: 'Not Ramp',
    });
  });

  it('says the saved posting is not on a building, and why', async () => {
    // I1 and I7 at the moment a person is most likely to assume otherwise:
    // they just added a job to a product whose whole surface is a 3D city.
    await pasteAndRead(aCapture({ title: 'Staff Engineer', company_name: 'Ramp' }));
    vi.mocked(confirmCapture).mockResolvedValue({
      ...aCapture(),
      status: 'confirmed',
      job_id: '00000000-0000-4000-8000-000000000002',
    });

    fireEvent.click(screen.getByRole('button', { name: /this is right/i }));

    await waitFor(() => expect(screen.getByTestId('capture-done')).toBeInTheDocument());
    expect(screen.getByTestId('capture-done')).toHaveTextContent(/will not guess/i);
  });
});
