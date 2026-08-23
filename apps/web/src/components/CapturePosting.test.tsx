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

function aCapture(
  proposed: Partial<Capture['proposed']> = {},
  rest: Partial<Capture> = {},
): Capture {
  return {
    id: '00000000-0000-4000-8000-000000000001',
    status: 'pending',
    source_url: null,
    origin: 'none',
    raw_text: 'pasted text',
    proposed: {
      title: null,
      company_name: null,
      location_text: null,
      employment_type: null,
      ...proposed,
    },
    parser_version: '1',
    assistant: null,
    assistant_rejected_fields: [],
    already_existed: false,
    corpus_check: null,
    job_id: null,
    created_at: '2026-08-19T12:00:00+00:00',
    decided_at: null,
    ...rest,
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

describe('CapturePosting, assisted (M5d)', () => {
  it('names LinkedIn as where it came from', async () => {
    await pasteAndRead(
      aCapture(
        { title: 'Staff Backend Engineer' },
        {
          origin: 'linkedin',
          source_url: 'https://www.linkedin.com/jobs/view/4012345678/',
        },
      ),
    );
    expect(screen.getByTestId('capture-origin')).toHaveTextContent('From LinkedIn');
  });

  it('says which reader filled each field', async () => {
    await pasteAndRead(
      aCapture(
        { title: 'Staff Backend Engineer', company_name: null },
        { assistant: { title: null, company_name: 'Ramp', location_text: null } },
      ),
    );
    expect(screen.getByLabelText(/title/i)).toHaveValue('Staff Backend Engineer');
    expect(screen.getByText(/Read by Nightshift from the text/)).toBeInTheDocument();
    expect(screen.getByLabelText(/employer/i)).toHaveValue('Ramp');
    expect(screen.getByText(/Quoted by Claude from the posting/)).toBeInTheDocument();
  });

  it('leaves a disagreed field blank and shows both readings', async () => {
    // The rule the whole two-reader design turns on. A silent winner here is
    // a default, and a default is what gets accepted without being read.
    await pasteAndRead(
      aCapture(
        { company_name: 'Ramp' },
        { assistant: { title: null, company_name: 'Stripe', location_text: null } },
      ),
    );
    expect(screen.getByLabelText(/employer/i)).toHaveValue('');
    const note = screen.getByText(/Two readings disagreed/);
    expect(note).toHaveTextContent('Ramp');
    expect(note).toHaveTextContent('Stripe');
  });

  it('explains a refused quote as the check working', async () => {
    await pasteAndRead(aCapture({}, { assistant_rejected_fields: ['company_name'] }));
    expect(screen.getByTestId('capture-refused-quotes')).toHaveTextContent(
      /not in the text you pasted/,
    );
  });

  it('leads with a job the corpus already holds', async () => {
    await pasteAndRead(
      aCapture(
        { title: 'Staff Backend Engineer', company_name: 'Ramp' },
        {
          corpus_check: {
            checked: true,
            why_not: null,
            matches: [
              {
                job_id: '00000000-0000-4000-8000-0000000000aa',
                title: 'Staff Backend Engineer',
                company_name: 'Ramp',
                status: 'closed',
                reason: 'same_company_and_title',
              },
            ],
          },
        },
      ),
    );
    const block = screen.getByTestId('capture-already-have');
    expect(block).toHaveTextContent('Nightshift already has this');
    expect(screen.getByRole('link', { name: /Staff Backend Engineer — Ramp/ })).toHaveAttribute(
      'href',
      '/explore/jobs/00000000-0000-4000-8000-0000000000aa',
    );
    // The single most useful thing this block can say.
    expect(block).toHaveTextContent('closed');
  });

  it('says nobody looked rather than showing nothing', async () => {
    // I3 in a new place: an empty match list rendered silently reads as "this
    // is new to Nightshift", which nobody established.
    await pasteAndRead(
      aCapture(
        {},
        {
          corpus_check: {
            checked: false,
            why_not: 'Nothing could be read from this posting as a company name.',
            matches: [],
          },
        },
      ),
    );
    expect(screen.getByTestId('capture-not-checked')).toHaveTextContent(
      /Nothing could be read from this posting as a company name/,
    );
    expect(screen.queryByTestId('capture-already-have')).not.toBeInTheDocument();
  });

  it('says nothing at all when the corpus was checked and found nothing', async () => {
    await pasteAndRead(
      aCapture({}, { corpus_check: { checked: true, why_not: null, matches: [] } }),
    );
    expect(screen.queryByTestId('capture-not-checked')).not.toBeInTheDocument();
    expect(screen.queryByTestId('capture-already-have')).not.toBeInTheDocument();
  });

  it('says a repeat paste is the same proposal', async () => {
    await pasteAndRead(aCapture({}, { already_existed: true }));
    expect(screen.getByTestId('capture-already-existed')).toHaveTextContent(/not a second one/);
  });
});
