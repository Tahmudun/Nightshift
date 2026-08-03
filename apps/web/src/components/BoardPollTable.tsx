'use client';

/**
 * Per-board polling state. M1d, ADR 0007 and ADR 0011.
 *
 * Sorted by the API so the boards we have heard from least recently come
 * first, and boards nobody has ever reached come first of all. "Which boards
 * are we not hearing from" is the operational question; a table sorted by name
 * makes an operator scan for trouble instead of being shown it.
 *
 * Two things this table is careful about.
 *
 * A `304` is **success**. It means the board answered and nothing had changed,
 * at the cost of one request and no body — the outcome the whole milestone is
 * built to produce. Rendering it as a warning would train people to ignore
 * warnings, so it is styled as healthy and labelled "unchanged".
 *
 * Freshness reads `last_success_at` from the board, never a posting's
 * timestamp. A board that has answered 304 for sixty days leaves its postings'
 * timestamps sixty days old while those postings are open and correctly so.
 */

import { useQuery } from '@tanstack/react-query';

import { fetchBoardPollState } from '@/lib/api';
import type { BoardPollState } from '@/lib/schemas';

function formatWhen(iso: string | null): string {
  if (iso === null) return 'never';
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/**
 * The last answer, as a word.
 *
 * §12.4: no essential information available only through colour. Every state
 * here reads as text first — "unchanged", "updated", "never polled" — and the
 * colour only reinforces it.
 */
function LastAnswer({ board }: { readonly board: BoardPollState }) {
  if (board.last_status === null) {
    return <span className="font-mono text-[10px] text-paper-faint">never polled</span>;
  }
  if (board.consecutive_failures > 0) {
    return (
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-alert-400">
        failing ×{board.consecutive_failures}
      </span>
    );
  }
  if (board.last_status === 304) {
    return (
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400">
        unchanged
      </span>
    );
  }
  return (
    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-signal-400">
      updated
    </span>
  );
}

function Tier({ tier }: { readonly tier: BoardPollState['tier'] }) {
  return (
    <span
      className={`font-mono text-[10px] uppercase tracking-[0.14em] ${
        tier === 'hot' ? 'text-gold-400' : 'text-paper-dim'
      }`}
      title={
        tier === 'hot'
          ? 'Produced an NYC posting recently — polled hourly'
          : 'No recent NYC postings — polled daily'
      }
    >
      {tier}
    </span>
  );
}

export function BoardPollTable() {
  const { data, isPending, isError } = useQuery({
    queryKey: ['boards'],
    queryFn: fetchBoardPollState,
    refetchInterval: 30_000,
  });

  if (isPending) {
    return <p className="text-[13px] text-paper-dim">Loading board state…</p>;
  }
  if (isError) {
    return (
      <p className="text-[13px] text-alert-400">
        The API is unreachable, so the state of each board is unknown — not healthy.
      </p>
    );
  }
  if (data.length === 0) {
    return (
      <p className="text-[13px] text-paper-dim">
        No board has a polling schedule yet. The scheduler creates one per registry board on its
        next run.
      </p>
    );
  }

  return (
    <section className="border border-ink-700 bg-ink-900/40">
      <header className="border-b border-ink-700 px-5 py-3">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
          Boards ({data.length})
        </h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          Least recently heard from first. <span className="text-signal-400">Unchanged</span> means
          the board answered and nothing had moved — that is the cheap, healthy case, not a problem.
          Freshness here is when the <em>board</em> last answered, which is not the same as when its
          roles were last edited.
        </p>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left">
          <thead>
            <tr className="border-b border-ink-800 font-mono text-[10px] uppercase tracking-[0.14em] text-paper-faint">
              <th className="px-5 py-2 font-normal">Board</th>
              <th className="px-5 py-2 font-normal">Tier</th>
              <th className="px-5 py-2 font-normal">Last answer</th>
              <th className="px-5 py-2 font-normal">Last heard from</th>
              <th className="px-5 py-2 font-normal">Next poll</th>
            </tr>
          </thead>
          <tbody>
            {data.map((board) => (
              <tr key={`${board.ats}:${board.token}`} className="border-b border-ink-800/60">
                <td className="px-5 py-2.5">
                  <span className="text-[13px] text-paper">{board.token}</span>{' '}
                  <span className="font-mono text-[10px] text-paper-faint">{board.ats}</span>
                </td>
                <td className="px-5 py-2.5">
                  <Tier tier={board.tier} />
                </td>
                <td className="px-5 py-2.5">
                  <LastAnswer board={board} />
                </td>
                <td className="px-5 py-2.5 font-mono text-[11px] text-paper-dim">
                  {formatWhen(board.last_success_at)}
                </td>
                <td className="px-5 py-2.5 font-mono text-[11px] text-paper-dim">
                  {formatWhen(board.next_poll_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
