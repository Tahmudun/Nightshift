import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ExtractionReview } from './ExtractionReview';
import { resumeDetailSchema, type ResumeDetail } from '@/lib/schemas';

vi.mock('@/lib/api', () => ({ confirmExtractions: vi.fn(), deleteResume: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

const { confirmExtractions } = await import('@/lib/api');

const TEXT = 'Hunter College\nBachelor of Science\nPython';

const RESUME: ResumeDetail = {
  id: '00000000-0000-4000-8000-0000000000aa',
  name: 'my resume',
  variant_type: 'custom',
  source_kind: 'paste',
  original_filename: null,
  content_hash: 'a'.repeat(64),
  is_default: true,
  extraction_counts: { pending: 2, confirmed: 0, rejected: 0 },
  created_at: '2026-08-03T12:00:00Z',
  updated_at: '2026-08-03T12:00:00Z',
  parsed_text: TEXT,
  nothing_proven: false,
  extractions: [
    {
      id: '00000000-0000-4000-8000-000000000001',
      kind: 'school',
      value: { school: 'Hunter College' },
      char_start: 0,
      char_end: 14,
      quoted_text: 'Hunter College',
      status: 'pending',
      extractor_version: 'm2c.1',
      decided_at: null,
    },
    {
      id: '00000000-0000-4000-8000-000000000002',
      kind: 'skill',
      value: { name: 'Python' },
      char_start: 35,
      char_end: 41,
      quoted_text: 'Python',
      status: 'pending',
      extractor_version: 'm2c.1',
      decided_at: null,
    },
  ],
};

const PROVES_NOTHING: ResumeDetail = {
  ...RESUME,
  parsed_text: 'To whom it may concern,',
  extractions: [],
  extraction_counts: { pending: 0, confirmed: 0, rejected: 0 },
  nothing_proven: true,
};

function renderReview(resume: ResumeDetail) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ExtractionReview resume={resume} />
    </QueryClientProvider>,
  );
}

describe('ExtractionReview', () => {
  beforeEach(() => vi.clearAllMocks());

  it('is tested against data the API could actually send', () => {
    // Not ceremony. The first version of the fixture above put Python at
    // 34–40, which is "\nPytho" — the right *length*, the wrong words, and
    // exactly the row `resumeDetailSchema` exists to refuse. A component test
    // fed impossible data proves nothing about the component.
    expect(() => resumeDetailSchema.parse(RESUME)).not.toThrow();
    expect(() => resumeDetailSchema.parse(PROVES_NOTHING)).not.toThrow();
  });

  it('shows each proposal with its kind, its value and the words it came from', () => {
    renderReview(RESUME);
    const row = screen.getByTestId('proposal-00000000-0000-4000-8000-000000000001');
    expect(row).toHaveTextContent(/school/i);
    expect(row).toHaveTextContent('Hunter College');
    expect(row).toHaveTextContent(/“Hunter College”/);
  });

  it('confirms nothing until somebody says so', async () => {
    // Invariant I2, in the browser. This is the assertion the whole slice is
    // for: the screen opens with every proposal undecided and says out loud
    // that the profile has not changed.
    renderReview(RESUME);

    expect(screen.getByTestId('review-status')).toHaveTextContent(/nothing.*saved|not.*changed/i);
    for (const button of screen.getAllByRole('button', { name: /^confirm$/i })) {
      expect(button).toHaveAttribute('aria-pressed', 'false');
    }

    fireEvent.click(screen.getByRole('button', { name: /save these decisions/i }));
    await waitFor(() => expect(confirmExtractions).not.toHaveBeenCalled());
  });

  it('sends only the proposals that were decided', async () => {
    vi.mocked(confirmExtractions).mockResolvedValue({
      confirmed: 1,
      rejected: 1,
      skipped: 0,
      skills_added: 0,
      projects_added: 0,
      profile_fields_set: ['school'],
    });
    renderReview(RESUME);

    const school = screen.getByTestId('proposal-00000000-0000-4000-8000-000000000001');
    const python = screen.getByTestId('proposal-00000000-0000-4000-8000-000000000002');
    fireEvent.click(within(school, /^confirm$/i));
    fireEvent.click(within(python, /^reject$/i));
    fireEvent.click(screen.getByRole('button', { name: /save these decisions/i }));

    await waitFor(() =>
      expect(confirmExtractions).toHaveBeenCalledWith(RESUME.id, [
        { extraction_id: '00000000-0000-4000-8000-000000000001', decision: 'confirm' },
        { extraction_id: '00000000-0000-4000-8000-000000000002', decision: 'reject' },
      ]),
    );
  });

  it('leaves an undecided proposal out of the request entirely', async () => {
    // Silence is not consent. An undecided row stays pending rather than being
    // swept into either answer.
    vi.mocked(confirmExtractions).mockResolvedValue({
      confirmed: 1,
      rejected: 0,
      skipped: 0,
      skills_added: 1,
      projects_added: 0,
      profile_fields_set: [],
    });
    renderReview(RESUME);
    const python = screen.getByTestId('proposal-00000000-0000-4000-8000-000000000002');
    fireEvent.click(within(python, /^confirm$/i));
    fireEvent.click(screen.getByRole('button', { name: /save these decisions/i }));

    await waitFor(() =>
      expect(confirmExtractions).toHaveBeenCalledWith(RESUME.id, [
        { extraction_id: '00000000-0000-4000-8000-000000000002', decision: 'confirm' },
      ]),
    );
  });

  it('makes a clicked proposal the active highlight', () => {
    renderReview(RESUME);
    const marks = () =>
      screen.getByTestId('highlighted-text').querySelectorAll('[data-active="true"]');
    expect(marks()).toHaveLength(0);

    fireEvent.click(screen.getByTestId('proposal-00000000-0000-4000-8000-000000000002'));
    expect(marks()[0]).toHaveTextContent('Python');
  });

  it('says a resume proved nothing instead of rendering an empty list', () => {
    // §6.2 and I7. The failure is stated and the manual form is offered; the
    // one thing that must never happen is a tidy empty pane implying success.
    renderReview(PROVES_NOTHING);
    expect(screen.getByText(/nothing could be proven from this file/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /add them yourself/i })).toHaveAttribute(
      'href',
      '/operate/profile',
    );
    expect(screen.queryByRole('button', { name: /save these decisions/i })).toBeNull();
  });

  it('still shows the text it read when it could prove nothing', () => {
    // The point of showing the text: "we read this and found nothing" is a
    // checkable claim, and "we found nothing" alone is not.
    renderReview(PROVES_NOTHING);
    expect(screen.getByTestId('highlighted-text')).toHaveTextContent('To whom it may concern');
  });
});

/** The nearest button inside `row` whose accessible name matches. */
function within(row: HTMLElement, name: RegExp): HTMLElement {
  const match = [...row.querySelectorAll('button')].find((button) =>
    name.test(button.textContent ?? ''),
  );
  if (match === undefined) throw new Error(`no button matching ${name} in the row`);
  return match;
}
