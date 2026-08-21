'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, fetchMe, signIn } from '@/lib/api';

/**
 * The front door: a signed-out browser gets a sign-in form instead of the app.
 *
 * "Signed out" specifically, not "something went wrong" — see the comment on
 * the `isError` branch, which is the part of this component that was wrong in
 * its first draft.
 *
 * **Why a gate in the layout rather than a redirect per page.** The same
 * argument `main.py` makes for attaching `require_session` to the router: a
 * page added later is protected because it exists, not because whoever added
 * it remembered a guard. Seventeen pages, one gate, and no route file to edit
 * when the eighteenth arrives.
 *
 * It also mirrors the API rather than duplicating it. This gate is a
 * convenience — it decides what a person *sees*. The API's 401 is the actual
 * boundary and holds whether or not this component exists, which is why
 * removing it would be a usability regression and not a security hole.
 */
export function SessionGate({ children }: { readonly children: React.ReactNode }) {
  const { data, isPending, isError } = useQuery({
    queryKey: ['session'],
    queryFn: fetchMe,
    // A signed-out answer is not a failure to retry — `fetchMe` already
    // distinguishes "nobody" (null) from "the API is unreachable" (throws).
    retry: false,
    staleTime: 60_000,
  });

  if (isPending) {
    return (
      <p className="px-5 py-8 text-[13px] text-paper-dim" role="status">
        Checking your session…
      </p>
    );
  }

  /*
   * An unreachable API renders the application anyway, and this is the one
   * decision in this component worth arguing about.
   *
   * The first draft blocked here too, and it was wrong. M0 built the degraded
   * path on purpose: with no API the shell still renders, the nav still works,
   * the telemetry strip says "api unreachable", and each data region says it
   * could not load rather than showing an empty state that would falsely read
   * as "there are no jobs". `e2e/shell.spec.ts` is entirely about that
   * behaviour. A gate that replaces the whole application whenever it cannot
   * ask the question throws all of it away — and it does so in the case where
   * a person most needs the interface to tell them what is wrong.
   *
   * It is also not a security decision. The API's own 401 is the boundary and
   * holds regardless; this component only chooses what to draw. Rendering
   * chrome around data that never arrives discloses nothing.
   *
   * So: gate on a definite "you are not signed in", never on "I could not ask".
   */
  if (isError) return <>{children}</>;

  if (data === null) return <SignInForm />;

  return <>{children}</>;
}

function SignInForm() {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const submit = useMutation({
    mutationFn: () => signIn(email, password),
    onSuccess: (session) => {
      // Seed the cache rather than refetching: the sign-in response carries the
      // same identity `/auth/me` would return, so a second round trip would
      // only add a flash of the loading state.
      queryClient.setQueryData(['session'], {
        id: session.id,
        email: session.email,
        display_name: session.display_name,
      });
    },
  });

  const rejected = submit.error instanceof ApiError && submit.error.status === 401;

  return (
    <div className="mx-auto max-w-sm px-5 py-16">
      <h1 className="text-[22px] font-medium tracking-tight text-paper">Sign in</h1>
      <p className="mt-1 text-[13px] leading-relaxed text-paper-dim">
        Nightshift keeps your applications, résumés and profile behind an account. The postings
        themselves are shared; what you did about them is not.
      </p>

      <form
        className="mt-6 space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          submit.mutate();
        }}
      >
        <div className="space-y-1.5">
          <label
            htmlFor="sign-in-email"
            className="block font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint"
          >
            Email
          </label>
          <input
            id="sign-in-email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="w-full border border-ink-700 bg-ink-900/60 px-3 py-2 text-[14px] text-paper focus:border-signal-500 focus:outline-none"
          />
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="sign-in-password"
            className="block font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint"
          >
            Password
          </label>
          <input
            id="sign-in-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full border border-ink-700 bg-ink-900/60 px-3 py-2 text-[14px] text-paper focus:border-signal-500 focus:outline-none"
          />
        </div>

        {submit.isError && (
          <p role="alert" className="text-[13px] leading-relaxed text-alert-400">
            {/* One message for a wrong password and for an unknown address, because
             * the API answers both identically on purpose — telling them apart here
             * would hand back the distinction it withholds. */}
            {rejected
              ? 'That email and password do not match an account.'
              : submit.error instanceof ApiError
                ? submit.error.message
                : String(submit.error)}
          </p>
        )}

        <button
          type="submit"
          disabled={submit.isPending || email.trim() === '' || password === ''}
          className="w-full border border-signal-600 bg-signal-950/40 px-3 py-2 text-[13px] text-paper hover:border-signal-400 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {submit.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      <p className="mt-6 text-[12px] leading-relaxed text-paper-faint">
        {/* Stated rather than hidden behind a dead "Sign up" link. Registration is
         * closed on purpose (ADR 0037) and a link to nowhere is worse than a
         * sentence saying so. */}
        There is no sign-up yet. Accounts are created from the command line with{' '}
        <code className="font-mono">nightshift users create</code>, and{' '}
        <code className="font-mono">make seed</code> makes one for the demo.
      </p>
    </div>
  );
}
