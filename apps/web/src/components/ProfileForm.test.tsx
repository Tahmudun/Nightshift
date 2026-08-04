import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProfileForm } from './ProfileForm';
import type { Profile } from '@/lib/schemas';

vi.mock('@/lib/api', () => ({ patchProfile: vi.fn() }));

const { patchProfile } = await import('@/lib/api');

const EMPTY: Profile = {
  id: '00000000-0000-4000-8000-000000000001',
  email: 'someone@example.test',
  display_name: null,
  timezone: 'America/New_York',
  graduation_year: null,
  graduation_month: null,
  degree: null,
  school: null,
  work_authorization: 'unspecified',
  home_location_text: null,
  remote_preference: 'no_preference',
  minimum_salary: null,
  preferred_roles: [],
  preferred_locations: [],
  skills: [],
  projects: [],
  deferred_fields: [],
};

const FILLED: Profile = {
  ...EMPTY,
  display_name: 'Nadia Okonkwo',
  graduation_year: 2027,
  graduation_month: 5,
  degree: 'Bachelor of Science',
  school: 'Hunter College',
};

function renderForm(profile: Profile) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ProfileForm profile={profile} />
    </QueryClientProvider>,
  );
}

describe('ProfileForm', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders every field with the value that is actually stored', () => {
    renderForm(FILLED);
    expect(screen.getByLabelText(/degree/i)).toHaveValue('Bachelor of Science');
    expect(screen.getByLabelText(/school/i)).toHaveValue('Hunter College');
    expect(screen.getByLabelText(/graduation year/i)).toHaveValue(2027);
    expect(screen.getByLabelText(/graduation month/i)).toHaveValue('5');
  });

  it('marks an unconfirmed field "not set" instead of leaving it blank', () => {
    // A blank box and a box holding an empty string look identical, and one of
    // them is a claim. Saying "not set" is the honest rendering of null (A10).
    renderForm(EMPTY);
    expect(screen.getAllByText(/not set/i).length).toBeGreaterThan(4);
  });

  it('sends only the fields that changed', async () => {
    vi.mocked(patchProfile).mockResolvedValue(FILLED as never);
    renderForm(EMPTY);
    fireEvent.change(screen.getByLabelText(/school/i), { target: { value: 'Hunter College' } });
    fireEvent.click(screen.getByRole('button', { name: /save profile/i }));
    await waitFor(() => expect(patchProfile).toHaveBeenCalledWith({ school: 'Hunter College' }));
  });

  it('sends nothing at all when nothing changed', () => {
    // A no-op save that writes anyway is how a "cleared" field appears out of
    // nowhere. The same rule `update_details` follows on the server.
    renderForm(FILLED);
    fireEvent.click(screen.getByRole('button', { name: /save profile/i }));
    expect(patchProfile).not.toHaveBeenCalled();
  });

  it('clears a field with an explicit null rather than an empty string', async () => {
    vi.mocked(patchProfile).mockResolvedValue(EMPTY as never);
    renderForm(FILLED);
    fireEvent.change(screen.getByLabelText(/school/i), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /save profile/i }));
    await waitFor(() => expect(patchProfile).toHaveBeenCalledWith({ school: null }));
  });

  it('refuses a graduation month with no year, before the request is made', async () => {
    // The database has this constraint and so does the Zod schema. Saying it
    // here means the person gets a sentence instead of a 422.
    renderForm(EMPTY);
    fireEvent.change(screen.getByLabelText(/graduation month/i), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: /save profile/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/needs a year/i);
    expect(patchProfile).not.toHaveBeenCalled();
  });
});
