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
    return <span className="font-mono text-[10px] text-ink-500">never run</span>;
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

export function SourceHealthTable() {
  const { data, error, isPending } = useQuery({
    queryKey: ['sources'],
    queryFn: fetchSourceHealth,
  });

  if (isPending) {
    return (
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-500">
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
            {['Source', 'Kind', 'Roles', 'Last run', 'Last success', 'Last failure'].map(
              (heading) => (
                <th
                  key={heading}
                  scope="col"
                  className="px-4 py-2 font-mono text-[9px] font-normal uppercase tracking-[0.16em] text-ink-500"
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
                  className={source.last_failure_at !== null ? 'text-alert-400' : 'text-ink-500'}
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
