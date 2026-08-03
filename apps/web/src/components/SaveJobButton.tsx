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
  const { data } = useQuery({
    queryKey: APPLICATIONS_KEY,
    queryFn: () => fetchApplications(),
  });
  const tracked = data?.items.find((item) => item.job.id === jobId) ?? null;

  const save = useMutation({
    mutationFn: () => saveJob(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: APPLICATIONS_KEY }),
  });

  if (tracked !== null) {
    return (
      <Link
        href={`/operate/applications/${tracked.id}`}
        className={`${CHIP} border-signal-400/40 text-signal-400 hover:border-signal-400`}
      >
        {STAGE_LABELS[tracked.current_stage]}
      </Link>
    );
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
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
