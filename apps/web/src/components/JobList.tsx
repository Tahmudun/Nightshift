'use client';

/**
 * The jobs list. Fetches, and delegates rendering of each row.
 *
 * Kept small on purpose — CLAUDE.md §8 calls out the 400-line component that
 * renders a map, fetches data, and holds filter state. This one fetches and
 * renders a list; the row knows how to draw a job, and the ladder knows how to
 * draw a confidence.
 */

import { useQuery } from '@tanstack/react-query';

import { JobRow } from './JobRow';
import { fetchJobs } from '@/lib/api';

export function JobList() {
  const { data, error, isPending } = useQuery({
    queryKey: ['jobs', { limit: 50 }],
    queryFn: () => fetchJobs({ limit: 50 }),
  });

  if (isPending) {
    return (
      <p className="px-5 py-8 font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
        Loading roles…
      </p>
    );
  }

  if (error !== null) {
    // §25: a failure states what happened and what to do, in the interface's
    // voice. It does not apologise and it is not vague.
    return (
      <div className="m-5 border border-alert-900 bg-alert-900/30 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
          Could not load roles
        </p>
        <p className="mt-1.5 text-[13px] text-paper-dim">{error.message}</p>
      </div>
    );
  }

  if (data.items.length === 0) {
    // An empty screen is an invitation to act.
    return (
      <div className="m-5 border border-ink-700 px-4 py-6">
        <p className="text-[14px] text-paper">No roles ingested yet.</p>
        <p className="mt-1.5 text-[13px] text-paper-dim">
          Run{' '}
          <code className="border border-ink-700 bg-ink-900 px-1 py-0.5 font-mono text-[11px] text-signal-400">
            make seed
          </code>{' '}
          to load the committed Greenhouse fixture, or{' '}
          <code className="border border-ink-700 bg-ink-900 px-1 py-0.5 font-mono text-[11px] text-signal-400">
            make ingest
          </code>{' '}
          to poll the live board.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-baseline justify-between border-b border-ink-700 px-5 py-2">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Roles
        </h2>
        <p className="font-mono text-[10px] tracking-wide text-paper-faint tnum">
          showing {data.items.length} of {data.total}
        </p>
      </div>
      {data.items.map((job) => (
        <JobRow key={job.id} job={job} />
      ))}
    </div>
  );
}
