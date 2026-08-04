import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ResumeUpload } from './ResumeUpload';

// `importActual` keeps the real `ApiError`, which is the class the failure test
// throws — a hand-rolled stand-in would not prove the component renders what
// the client actually produces.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, pasteResume: vi.fn(), uploadResume: vi.fn() };
});

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

const { pasteResume, uploadResume, ApiError } = await import('@/lib/api');

function renderUpload() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ResumeUpload />
    </QueryClientProvider>,
  );
}

describe('ResumeUpload', () => {
  it('names .docx as unsupported before anyone tries it', () => {
    // I7 and §6.2: a format we cannot read is a fact worth stating up front.
    // Learning it from a 415 after picking a file is a worse experience than
    // being told, and the paste box is right there.
    renderUpload();
    expect(screen.getByTestId('upload-formats')).toHaveTextContent(/\.docx/);
    expect(screen.getByTestId('upload-formats')).toHaveTextContent(/paste/i);
  });

  it('offers paste and a file side by side', () => {
    renderUpload();
    expect(screen.getByLabelText(/paste the text/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/choose a file/i)).toBeInTheDocument();
  });

  it('sends nothing when the paste box is empty', () => {
    renderUpload();
    fireEvent.click(screen.getByRole('button', { name: /read this text/i }));
    expect(pasteResume).not.toHaveBeenCalled();
  });

  it('pastes what was typed', async () => {
    vi.mocked(pasteResume).mockResolvedValue({ id: 'r-1' } as never);
    renderUpload();
    fireEvent.change(screen.getByLabelText(/paste the text/i), {
      target: { value: 'Python, PostgreSQL' },
    });
    fireEvent.click(screen.getByRole('button', { name: /read this text/i }));
    await waitFor(() => expect(pasteResume).toHaveBeenCalledWith('Python, PostgreSQL', undefined));
  });

  it("renders the API's own message when a file cannot be read, and keeps paste available", async () => {
    // The message is the product. "Unsupported file" would strand somebody;
    // the API's sentence names the format and offers the way around it.
    vi.mocked(uploadResume).mockRejectedValue(
      new ApiError('.docx files are not supported. Paste the text of your resume instead.', 415),
    );
    renderUpload();
    fireEvent.change(screen.getByLabelText(/choose a file/i), {
      target: { files: [new File(['x'], 'resume.docx')] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(/\.docx files are not supported/);
    expect(screen.getByLabelText(/paste the text/i)).toBeInTheDocument();
  });
});
