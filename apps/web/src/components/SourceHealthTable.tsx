'use client';

/**
 * Source health. §2.6, and M1's "ingestion failures are visible in the UI".
 *
 * A `fixture` source is labelled as such, loudly. That label is what keeps
 * `make demo` on the right side of invariant I7 — the data is real, recorded
 * Greenhouse output, but it did not come from a live poll, and the interface
 * says so rather than letting a demo look like production.
 */

import { useQuery } from '@tanstack/react-query';

import { fetchSourceHealth } from '@/lib/api';
import type { SourceHealth } from '@/lib/schemas';

function RunStatus({ status }: { readonly status: SourceHealth['last_run_status'] }) {
  if (status === null) {
    return <span className="font-mono text-[10px] text-paper-faint">never run</span>;
  }
  const tone =
    status === 'succeeded'
      ? 'text-signal-400'
      : status === 'partial'
        ? 'text-gold-400'
        : status === 'failed'
          ? 'text-alert-400'
          : 'text-paper-dim';
  return (
    <span className={`font-mono text-[10px] uppercase tracking-[0.14em] ${tone}`}>{status}</span>
  );
}

function formatWhen(iso: string | null): string {
  if (iso === null) return '—';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/**
 * The per-source closure breakdown.
 *
 * `job_count` next to this cannot show it: a provenance link survives a
 * closure, so a source whose every job has aged out reports exactly the same
 * total as a healthy one. Without this column the table would say a dead board
 * is fine.
 *
 * States at zero are omitted here rather than rendered as "0" — the row is
 * dense and the full four-way breakdown with its explanations lives on the job
 * table. `all open` is spelled out rather than left blank so an empty-looking
 * cell never has to be interpreted.
 */
function StatusBreakdown({ counts }: { readonly counts: SourceHealth['job_status_counts'] }) {
  const total = counts.open + counts.possibly_stale + counts.unverified + counts.closed;
  if (total === 0) {
    return <span className="font-mono text-[10px] text-paper-faint">—</span>;
  }
  if (counts.open === total) {
    return <span className="font-mono text-[10px] text-signal-400">all open</span>;
  }
  const parts: string[] = [];
  if (counts.open > 0) parts.push(`${counts.open} open`);
  if (counts.possibly_stale > 0) parts.push(`${counts.possibly_stale} stale`);
  if (counts.unverified > 0) parts.push(`${counts.unverified} unverified`);
  if (counts.closed > 0) parts.push(`${counts.closed} closed`);
  return (
    <span className="font-mono text-[10px] tnum text-paper-dim">{parts.join(' · ')}</span>
  );
}

export function SourceHealthTable() {
  const { data, error, isPending } = useQuery({
    queryKey: ['sources'],
    queryFn: fetchSourceHealth,
  });

  if (isPending) {
    return (
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
        Loading sources…
      </p>
    );
  }

  if (error !== null) {
    return (
      <div className="border border-alert-900 bg-alert-900/30 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
          Could not load source health
        </p>
        <p className="mt-1.5 text-[13px] text-paper-dim">{error.message}</p>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="border border-ink-700 px-4 py-6">
        <p className="text-[14px] text-paper">No sources registered yet.</p>
        <p className="mt-1.5 text-[13px] text-paper-dim">
          Run{' '}
          <code className="border border-ink-700 bg-ink-900 px-1 py-0.5 font-mono text-[11px] text-signal-400">
            make seed
          </code>{' '}
          to register the fixture source and load the committed board.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto border border-ink-700 bg-ink-900/40">
      <table className="w-full min-w-[640px] text-left">
        <caption className="sr-only">Job source health and last ingestion run</caption>
        <thead>
          <tr className="border-b border-ink-700">
            {['Source', 'Kind', 'Roles', 'By status', 'Last run', 'Last success', 'Last failure'].map(
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
          {data.map((source) => (
            <tr key={source.name} className="border-b border-ink-800 last:border-b-0">
              <th scope="row" className="px-4 py-3 text-[13px] font-normal text-paper">
                {source.name}
              </th>
              <td className="px-4 py-3">
                {source.source_type === 'fixture' ? (
                  <span className="border border-gold-400/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-gold-400">
                    committed fixture
                  </span>
                ) : (
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
                    live
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-[13px] text-paper-dim tnum">{source.job_count}</td>
              <td className="px-4 py-3">
                <StatusBreakdown counts={source.job_status_counts} />
              </td>
              <td className="px-4 py-3">
                <RunStatus status={source.last_run_status} />
                {source.last_run_error !== null ? (
                  <p className="mt-1 max-w-[280px] truncate font-mono text-[10px] text-alert-400">
                    {source.last_run_error}
                  </p>
                ) : null}
              </td>
              <td className="px-4 py-3 font-mono text-[11px] text-paper-dim tnum">
                {formatWhen(source.last_success_at)}
              </td>
              <td className="px-4 py-3 font-mono text-[11px] tnum">
                <span
                  className={
                    source.last_failure_at !== null ? 'text-alert-400' : 'text-paper-faint'
                  }
                >
                  {formatWhen(source.last_failure_at)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
