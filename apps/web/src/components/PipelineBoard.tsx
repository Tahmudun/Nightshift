'use client';

/**
 * The pipeline: every saved role, grouped by where it actually got to.
 *
 * Two rendering decisions carry the design rather than decorate it.
 *
 * A stage nobody is at is not rendered. Ten empty columns read as a broken
 * page; the counts live in one summary line instead, so "0 in interview" is
 * stated once rather than drawn ten times.
 *
 * Archived applications are counted in the open, never hidden silently. That
 * is AMENDMENTS A7's rule about stale things — label them, do not style them
 * out of existence.
 */

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { APPLICATIONS_KEY, STAGE_LABELS } from './SaveJobButton';
import { fetchApplications } from '@/lib/api';
import type { Application, ApplicationStage } from '@/lib/schemas';

/** The seven working stages in order, then the three outcomes. */
const STAGE_ORDER: readonly ApplicationStage[] = [
  'discovered',
  'saved',
  'preparing',
  'applied',
  'assessment',
  'interview',
  'offer',
  'rejected',
  'withdrawn',
  'closed',
];

function StageGroup({
  stage,
  items,
}: {
  readonly stage: ApplicationStage;
  readonly items: readonly Application[];
}) {
  return (
    <section>
      <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
        {STAGE_LABELS[stage]}
      </h2>
      <ul className="mt-2 space-y-1.5">
        {items.map((application) => (
          <li key={application.id}>
            <Link
              href={`/operate/applications/${application.id}`}
              className={`block border border-ink-700 px-3 py-2 hover:border-signal-400 ${
                application.archived_at !== null ? 'opacity-60' : ''
              }`}
            >
              <span className="text-[14px] text-paper">{application.job.title}</span>
              <span className="ml-2 text-[12px] text-paper-dim">
                {application.job.company.canonical_name}
              </span>
              {application.archived_at !== null ? (
                <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.14em] text-gold-400">
                  archived
                </span>
              ) : null}
              {application.next_action_at !== null ? (
                <span className="ml-2 font-mono text-[10px] text-paper-faint">
                  next action {application.next_action_at.slice(0, 10)}
                </span>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function PipelineBoard() {
  const [showArchived, setShowArchived] = useState(false);
  const { data, isPending, error } = useQuery({
    queryKey: [...APPLICATIONS_KEY, { archived: showArchived }],
    queryFn: () => fetchApplications({ archived: showArchived }),
  });

  if (isPending) {
    return <p className="font-mono text-[12px] text-paper-faint">Loading the pipeline…</p>;
  }
  if (error !== null) {
    return (
      <p role="alert" className="text-[13px] text-alert-400">
        {error.message}
      </p>
    );
  }

  const grouped = STAGE_ORDER.map((stage) => ({
    stage,
    items: data.items.filter((item) => item.current_stage === stage),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="space-y-6">
      {data.total === 0 && !showArchived ? (
        <p className="text-[14px] leading-relaxed text-paper-dim">
          Nothing saved yet.{' '}
          <Link href="/explore" className="text-signal-400 underline underline-offset-2">
            Find a role in Explore
          </Link>{' '}
          and save it.
        </p>
      ) : (
        <>
          <p className="font-mono text-[11px] text-paper-faint">
            {data.total} tracked ·{' '}
            {STAGE_ORDER.map((stage) => `${STAGE_LABELS[stage]} ${data.stage_counts[stage]}`).join(
              ' · ',
            )}
          </p>
          {grouped.map((group) => (
            <StageGroup key={group.stage} stage={group.stage} items={group.items} />
          ))}
        </>
      )}

      <button
        type="button"
        onClick={() => setShowArchived((current) => !current)}
        className="border border-ink-700 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-paper-dim hover:border-signal-400 hover:text-signal-400"
      >
        {showArchived ? 'Hide' : 'Show'} archived ({data.archived_count})
      </button>
    </div>
  );
}
