import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SessionGate } from './SessionGate';
import type * as api from '@/lib/api';
import { ApiError } from '@/lib/api';

/**
 * The gate, and the three states it must keep apart.
 *
 * "Signed out" and "the API is dead" are the pair worth testing. They arrive at
 * this component one line apart and mean opposite things: one is answered by
 * typing a password, the other by starting a server. A gate that shows a
 * sign-in form to somebody whose API is down sends them to type credentials at
 * something that cannot check them, and they will conclude their password is
 * wrong.
 */

const fetchMe = vi.fn();
const signIn = vi.fn();

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof api>('@/lib/api');
  return {
    ...actual,
    fetchMe: (...args: unknown[]) => fetchMe(...args),
    signIn: (...args: unknown[]) => signIn(...args),
  };
});

function renderGate() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SessionGate>
        <p>the application</p>
      </SessionGate>
    </QueryClientProvider>,
  );
}

function fill(email: string, password: string) {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } });
}

beforeEach(() => {
  fetchMe.mockReset();
  signIn.mockReset();
});

describe('SessionGate', () => {
  it('renders the application when somebody is signed in', async () => {
    fetchMe.mockResolvedValue({ id: 'u1', email: 'a@example.test', display_name: 'A' });
    renderGate();
    expect(await screen.findByText('the application')).toBeInTheDocument();
  });

  it('shows the sign-in form, and not the application, when nobody is', async () => {
    fetchMe.mockResolvedValue(null);
    renderGate();

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByText('the application')).not.toBeInTheDocument();
  });

  it('renders the application, not a sign-in form, when the API is unreachable', async () => {
    // The distinction this component exists to keep. A dead server is not a
    // wrong password: offering a sign-in form here teaches somebody to doubt
    // credentials that are fine, and it destroys the degraded path M0 built —
    // the shell, the nav, and each region saying it could not load. The first
    // draft of this component got it wrong in exactly that direction.
    fetchMe.mockRejectedValue(new ApiError('cannot reach the API at /api/ns', null));
    renderGate();

    expect(await screen.findByText('the application')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Sign in' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument();
  });

  it('shows the application once a sign-in succeeds, without a second fetch', async () => {
    fetchMe.mockResolvedValue(null);
    signIn.mockResolvedValue({
      id: 'u1',
      email: 'a@example.test',
      display_name: 'A',
      expires_at: '2026-09-20T12:00:00Z',
    });

    renderGate();
    await screen.findByRole('heading', { name: 'Sign in' });

    fill('a@example.test', 'a-password-long-enough');
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('the application')).toBeInTheDocument();
    // One call — the initial check. The sign-in response already carries the
    // identity, so refetching would only add a flash of the loading state.
    expect(fetchMe).toHaveBeenCalledTimes(1);
  });

  it('gives one message for a wrong password and an unknown address', async () => {
    // The API answers both identically on purpose, so that sign-in cannot be
    // used to ask whether somebody has an account. A friendlier message here
    // would hand back the distinction the API withholds.
    fetchMe.mockResolvedValue(null);
    signIn.mockRejectedValue(new ApiError('/auth/sign-in failed: …', 401));

    renderGate();
    await screen.findByRole('heading', { name: 'Sign in' });

    fill('a@example.test', 'wrong');
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('That email and password do not match an account.');
    // Neither half of the pair may be named.
    expect(alert.textContent).not.toMatch(/no such|unknown|not found|no account/i);
  });

  it('says registration is closed rather than linking to a sign-up that is not there', async () => {
    fetchMe.mockResolvedValue(null);
    renderGate();

    await screen.findByRole('heading', { name: 'Sign in' });
    expect(screen.getByText(/There is no sign-up yet/)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /sign up|create an account|register/i })).toBeNull();
  });

  it('refuses to submit an empty form', async () => {
    fetchMe.mockResolvedValue(null);
    renderGate();

    await screen.findByRole('heading', { name: 'Sign in' });
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@example.test' } });
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'x' } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).not.toBeDisabled());
  });
});
