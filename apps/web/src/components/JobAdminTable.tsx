'use client';

/**
 * The admin job table. M1's "ingestion failures are visible in the UI, not just
 * logs", for the job side of the pipeline.
 *
 * Shows closed jobs on purpose. The user-facing list at /explore filters them
 * out, which is right there and wrong here: an operational view that hides the
 * closure machine's output makes the closure machine unobservable, and this
 * page exists to observe it.
 *
 * Every status is rendered as a word alongside its colour. §12.4 forbids
 * essential information carried only by a visual channel, and "is this job
 * still open" is as essential as it gets on this screen.
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { fetchJobAdmin } from '@/lib/api';
import { JOB_STATUS_SCALE, jobStatusMeta } from '@/lib/jobStatus';
import type { JobStatus } from '@/lib/schemas';

function formatWhen(iso: string | null): string {
  if (iso === null) return '—';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function StatusTag({ status }: { readonly status: JobStatus }) {
  const meta = jobStatusMeta(status);
  return (
    <span className={`font-mono text-[10px] uppercase tracking-[0.14em] ${meta.tone}`}>
      {meta.label}
    </span>
  );
}

/**
 * The legend. Permanent panel rather than a tooltip, matching the confidence
 * legend at /explore — §12.4 again: no essential information available only
 * through hover.
 */
function StatusLegend({ counts }: { readonly counts: Record<JobStatus, number> }) {
  return (
    <section
      aria-label="What each job status means"
      className="border border-ink-700 bg-ink-900/40 p-5"
    >
      <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
        What each status means
      </h2>
      <dl className="mt-3 space-y-3">
        {JOB_STATUS_SCALE.map((meta) => (
          <div key={meta.value} className="flex flex-col gap-1 sm:flex-row sm:gap-4">
            <dt className="flex shrink-0 items-baseline gap-2 sm:w-40">
              <span className={`font-mono text-[10px] uppercase tracking-[0.14em] ${meta.tone}`}>
                {meta.label}
              </span>
              <span className="tnum font-mono text-[10px] text-paper-faint">
                {counts[meta.value]}
              </span>
            </dt>
            <dd className="max-w-2xl text-[13px] leading-relaxed text-paper-dim">{meta.meaning}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export function JobAdminTable() {
  const [status, setStatus] = useState<JobStatus | 'all'>('all');
  const { data, error, isPending } = useQuery({
    queryKey: ['jobs-admin', status],
    queryFn: () => fetchJobAdmin(status === 'all' ? {} : { status }),
  });

  if (isPending) {
    return (
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
        Loading jobs…
      </p>
    );
  }

  if (error !== null) {
    return (
      <div className="border border-alert-900 bg-alert-900/30 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
          Could not load the job table
        </p>
        <p className="mt-1.5 text-[13px] text-paper-dim">{error.message}</p>
      </div>
    );
  }

  const counts = data.status_counts;

  return (
    <div className="space-y-6">
      <StatusLegend counts={counts} />

      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Filter
        </span>
        {(['all', ...JOB_STATUS_SCALE.map((m) => m.value)] as const).map((value) => {
          const isActive = status === value;
          const label = value === 'all' ? `All (${data.total})` : jobStatusMeta(value).label;
          return (
            <button
              key={value}
              type="button"
              aria-pressed={isActive}
              onClick={() => setStatus(value)}
              className={`border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors ${
                isActive
                  ? 'border-signal-400 text-signal-400'
                  : 'border-ink-700 text-paper-dim hover:border-ink-600 hover:text-paper'
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      {data.items.length === 0 ? (
        <div className="border border-ink-700 px-4 py-6">
          <p className="text-[14px] text-paper">
            {status === 'all'
              ? 'No jobs ingested yet.'
              : `No jobs are ${jobStatusMeta(status).label.toLowerCase()}.`}
          </p>
          <p className="mt-1.5 max-w-2xl text-[13px] text-paper-dim">
            {status === 'all' ? (
              <>
                Run{' '}
                <code className="border border-ink-700 bg-ink-900 px-1 py-0.5 font-mono text-[11px] text-signal-400">
                  make seed
                </code>{' '}
                to load the committed board.
              </>
            ) : (
              'That is a real zero, not a missing filter — the count above comes from the whole table.'
            )}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto border border-ink-700 bg-ink-900/40">
          <table className="w-full min-w-[820px] text-left">
            <caption className="sr-only">
              Every canonical job, its closure state, and its provenance
            </caption>
            <thead>
              <tr className="border-b border-ink-700">
                {['Role', 'Company', 'Status', 'First seen', 'Last seen', 'Sources', 'Merges'].map(
                  (heading) => (
                    <th
                      key={heading}
                      scope="col"
                      className="px-4 py-2 font-mono text-[9px] font-normal uppercase tracking-[0.16em] text-paper-faint"
                    >
                      {heading}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {data.items.map((job) => (
                <tr key={job.id} className="border-b border-ink-800 last:border-b-0">
                  <th scope="row" className="px-4 py-3 text-[13px] font-normal text-paper">
                    {job.title}
                  </th>
                  <td className="px-4 py-3 text-[13px] text-paper-dim">{job.company_name}</td>
                  <td className="px-4 py-3">
                    <StatusTag status={job.status} />
                    {job.closed_at !== null ? (
                      <p className="mt-1 font-mono text-[10px] text-paper-faint tnum">
                        {formatWhen(job.closed_at)}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-paper-dim tnum">
                    {formatWhen(job.first_seen_at)}
                  </td>
                  <td className="px-4 py-3 font-mono text-[11px] text-paper-dim tnum">
                    {formatWhen(job.last_seen_at)}
                  </td>
                  <td className="px-4 py-3 text-[13px] text-paper-dim tnum">{job.source_count}</td>
                  <td className="px-4 py-3 text-[13px] tnum">
                    <span className={job.merge_count > 0 ? 'text-signal-400' : 'text-paper-faint'}>
                      {job.merge_count}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
