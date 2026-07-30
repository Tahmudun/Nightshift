/**
 * One job in the list.
 *
 * Every honesty rule in the spec shows up as a concrete rendering decision here:
 *
 * - The confidence ladder is per-location, not per-job, because a posting that
 *   names Manhattan and "Texas, remote" knows different things about each
 *   (AMENDMENTS A2). Collapsing them to one badge would hide that.
 * - An absent salary renders as "not provided by source", not as a hidden row
 *   and not as a zero (AMENDMENTS A10).
 * - Dates are labelled for what they are. "First seen" is our observation;
 *   "Published" is the source's claim. They are never merged into "Posted".
 */

import { ConfidenceLadder } from './ConfidenceLadder';
import type { JobSummary } from '@/lib/schemas';

const EMPLOYMENT_LABELS: Record<JobSummary['employment_type'], string> = {
  full_time: 'Full time',
  part_time: 'Part time',
  internship: 'Internship',
  contract: 'Contract',
  temporary: 'Temporary',
  unknown: 'Type not stated',
};

const REMOTE_LABELS: Record<JobSummary['remote_policy'], string> = {
  on_site: 'On site',
  hybrid: 'Hybrid',
  remote: 'Remote',
  unknown: 'Policy not stated',
};

function formatDate(iso: string | null): string {
  if (iso === null) return '—';
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function formatSalary(salary: JobSummary['salary']): string {
  if (!salary.provided) return 'Not provided by source';
  const currency = salary.currency ?? '';
  const format = (value: number) =>
    value >= 1000 ? `${Math.round(value / 1000)}k` : String(Math.round(value));
  const range =
    salary.minimum !== null && salary.maximum !== null
      ? `${format(salary.minimum)}–${format(salary.maximum)}`
      : format(salary.minimum ?? salary.maximum ?? 0);
  // A10: Greenhouse states no period, so we do not invent one.
  const period = salary.period ?? 'period not stated';
  return `${currency} ${range} · ${period}`.trim();
}

function Field({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="font-mono text-[9px] uppercase tracking-[0.16em] text-paper-faint">{label}</dt>
      <dd className="mt-0.5 text-[12px] text-paper-dim tnum">{children}</dd>
    </div>
  );
}

export function JobRow({ job }: { readonly job: JobSummary }) {
  const stale = job.status !== 'open';

  return (
    <article
      className={[
        'group border-b border-ink-800 px-5 py-4 transition-colors hover:bg-ink-900/60',
        // AMENDMENTS A7: a stale listing is rendered with reduced legibility and
        // an explicit label, never with a simulated glitch.
        stale ? 'opacity-60' : '',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[15px] font-medium tracking-tight text-paper">
            {job.title}
          </h3>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.12em] text-signal-600">
            {job.company.canonical_name}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <span className="border border-ink-700 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint">
            {EMPLOYMENT_LABELS[job.employment_type]}
          </span>
          <span className="border border-ink-700 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint">
            {REMOTE_LABELS[job.remote_policy]}
          </span>
          {stale ? (
            <span className="border border-gold-400/40 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-gold-400">
              {job.status.replace('_', ' ')}
            </span>
          ) : null}
        </div>
      </div>

      {/* One row per location the posting actually names. */}
      <ul className="mt-3 space-y-1.5">
        {job.locations.length === 0 ? (
          <li className="font-mono text-[11px] text-paper-faint">
            No location stated by the source
          </li>
        ) : (
          job.locations.map((location) => (
            <li key={location.id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <ConfidenceLadder confidence={location.location_confidence} />
              <span className="text-[12px] text-paper-dim">{location.raw_text}</span>
              {location.is_primary && job.locations.length > 1 ? (
                <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-paper-faint">
                  primary
                </span>
              ) : null}
            </li>
          ))
        )}
      </ul>

      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        <Field label="Compensation">{formatSalary(job.salary)}</Field>
        <Field label="Published by source">{formatDate(job.source_published_at)}</Field>
        <Field label="Source last updated">{formatDate(job.source_updated_at)}</Field>
        <Field label="First seen by us">{formatDate(job.first_seen_at)}</Field>
      </dl>
    </article>
  );
}
