'use client';

/**
 * Save, and then tell the truth about where the role got to.
 *
 * Once a job is tracked this stops being a save button and becomes a link to
 * the application, labelled with its actual stage. A control that keeps saying
 * "Saved" for a role you have an interview for is a control that has stopped
 * describing anything.
 *
 * There is no unsave. Removing an application would mean deleting its history,
 * which the database refuses (`application_events` is append-only and the
 * events cascade). Archive is the reversible path and it lives on the
 * application page, where the history it hides is visible.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';

import { fetchApplications, saveJob } from '@/lib/api';
import type { ApplicationStage } from '@/lib/schemas';

export const APPLICATIONS_KEY = ['applications'] as const;

/**
 * Every application, archived included. Invalidating `APPLICATIONS_KEY`
 * prefix-matches this, so one invalidation still refreshes every list.
 */
export const TRACKED_KEY = [...APPLICATIONS_KEY, { archived: true }] as const;

export const STAGE_LABELS: Record<ApplicationStage, string> = {
  discovered: 'Discovered',
  saved: 'Saved',
  preparing: 'Preparing',
  applied: 'Applied',
  assessment: 'Assessment',
  interview: 'Interview',
  offer: 'Offer',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  closed: 'Closed',
};

const CHIP = 'inline-block border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em]';

export function SaveJobButton({ jobId }: { readonly jobId: string }) {
  const queryClient = useQueryClient();

  // One query key for the whole page: TanStack dedupes, so thirty job rows
  // make one request, not thirty.
  //
  // `archived: true` means "do not filter archived out", not "only archived".
  // Without it an archived application is invisible here, so the control offers
  // to save a role that is already tracked — and the save succeeds with a 200
  // that changes nothing, which reads as a dead button.
  const { data, isPending } = useQuery({
    queryKey: TRACKED_KEY,
    queryFn: () => fetchApplications({ archived: true }),
  });
  const tracked = data?.items.find((item) => item.job.id === jobId) ?? null;

  const save = useMutation({
    mutationFn: () => saveJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: APPLICATIONS_KEY }),
  });

  // Until the answer is in, this control does not know whether the job is
  // tracked — and rendering "Save" meanwhile means an already-tracked role
  // shows an actionable button for a moment and then swaps it out. That is a
  // click a person can land, and a save they did not mean to make. Found by a
  // browser test catching the element mid-swap.
  if (isPending) {
    return (
      <span
        className={`${CHIP} border-ink-700 text-paper-faint`}
        aria-busy="true"
        data-testid="save-or-track"
      >
        …
      </span>
    );
  }

  if (tracked !== null) {
    return (
      <Link
        data-testid="save-or-track"
        href={`/operate/applications/${tracked.id}`}
        className={`${CHIP} ${
          tracked.archived_at !== null
            ? 'border-gold-400/40 text-gold-400 hover:border-gold-400'
            : 'border-signal-400/40 text-signal-400 hover:border-signal-400'
        }`}
      >
        {STAGE_LABELS[tracked.current_stage]}
        {tracked.archived_at !== null ? ' · archived' : ''}
      </Link>
    );
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        data-testid="save-or-track"
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className={`${CHIP} border-ink-700 text-paper-dim hover:border-signal-400 hover:text-signal-400 disabled:opacity-50`}
      >
        {save.isPending ? 'Saving…' : 'Save'}
      </button>
      {save.error !== null ? (
        <span role="alert" className="text-[11px] text-alert-400">
          {save.error.message}
        </span>
      ) : null}
    </span>
  );
}
