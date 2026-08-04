import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SkillList } from './SkillList';
import type { UserSkill } from '@/lib/schemas';

vi.mock('@/lib/api', () => ({
  addSkill: vi.fn(),
  removeSkill: vi.fn(),
}));

const { addSkill } = await import('@/lib/api');

const FROM_RESUME: UserSkill = {
  id: '00000000-0000-4000-8000-000000000001',
  name: 'Python',
  proficiency_level: 'unspecified',
  source_type: 'resume',
  source_reference: 'resume:9f1c2b3a-0000-4000-8000-000000000009#238-244',
  vocabulary_version: '2026-08-03.1',
  created_at: '2026-08-03T12:00:00Z',
};

const BY_HAND: UserSkill = {
  ...FROM_RESUME,
  id: '00000000-0000-4000-8000-000000000002',
  name: 'Kubernetes',
  source_type: 'manual',
  source_reference: 'manual',
  vocabulary_version: null,
};

const RESUME_ID = '9f1c2b3a-0000-4000-8000-000000000009';

function renderList(skills: UserSkill[], liveResumeIds?: Set<string>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SkillList skills={skills} liveResumeIds={liveResumeIds} />
    </QueryClientProvider>,
  );
}

describe('SkillList', () => {
  it('says where every skill came from', () => {
    // I2's visible surface. A skill with no stated origin is indistinguishable
    // from one the system decided about you, which is the whole failure mode.
    renderList([FROM_RESUME, BY_HAND]);
    expect(screen.getByText('Python').closest('li')).toHaveTextContent(/from your resume/i);
    expect(screen.getByText('Kubernetes').closest('li')).toHaveTextContent(/added by you/i);
  });

  it('points a resume skill back at the characters it was confirmed from', () => {
    // The `source_reference` is a real pointer, so it is rendered as one. A
    // provenance that cannot be followed is decoration.
    renderList([FROM_RESUME]);
    const link = screen.getByRole('link', { name: /238–244/ });
    expect(link).toHaveAttribute('href', '/operate/resumes/9f1c2b3a-0000-4000-8000-000000000009');
  });

  it('states the provenance but withholds the link when the resume is gone', () => {
    // A confirmed skill outlives the resume it came from — that is the product
    // decision. So the pointer outlives its target too, and a link to a deleted
    // resume is a 404 dressed up as evidence.
    renderList([FROM_RESUME], new Set());
    expect(screen.queryByRole('link', { name: /238–244/ })).toBeNull();
    expect(screen.getByText(/since deleted/i)).toBeInTheDocument();
    expect(screen.getByText('Python').closest('li')).toHaveTextContent(/from your resume/i);
  });

  it('offers the link when the resume is still there', () => {
    renderList([FROM_RESUME], new Set([RESUME_ID]));
    expect(screen.getByRole('link', { name: /238–244/ })).toBeInTheDocument();
  });

  it('says nothing is confirmed rather than rendering an empty list', () => {
    renderList([]);
    expect(screen.getByText(/no skills confirmed yet/i)).toBeInTheDocument();
  });

  it('adds a skill only when a name was actually typed', async () => {
    renderList([]);
    const button = screen.getByRole('button', { name: /add skill/i });

    fireEvent.click(button);
    expect(addSkill).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/skill name/i), { target: { value: '  Rust  ' } });
    fireEvent.click(button);
    await waitFor(() => expect(addSkill).toHaveBeenCalledWith('Rust', undefined));
  });
});
