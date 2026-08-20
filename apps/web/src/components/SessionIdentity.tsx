'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchMe, signOut } from '@/lib/api';

/**
 * Who you are, in the header, with a way out.
 *
 * It reads the same `['session']` query the gate does rather than taking a
 * prop, so there is one answer to "who is signed in" and both places move
 * together. Signing out clears the whole cache and not just this key — the
 * pages behind it hold another person's applications and résumés, and leaving
 * those in memory for the next sign-in is exactly the leak this milestone is
 * about, one layer up from the database.
 */
export function SessionIdentity() {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ['session'], queryFn: fetchMe, retry: false });

  const leave = useMutation({
    mutationFn: signOut,
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(['session'], null);
    },
  });

  if (!data) return null;

  return (
    <div className="flex items-center gap-3">
      <span
        className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint"
        title={data.email}
      >
        {data.display_name ?? data.email}
      </span>
      <button
        type="button"
        onClick={() => leave.mutate()}
        disabled={leave.isPending}
        className="border border-ink-700 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-paper-dim hover:border-ink-500 hover:text-paper disabled:opacity-40"
      >
        {leave.isPending ? 'Signing out…' : 'Sign out'}
      </button>
    </div>
  );
}
