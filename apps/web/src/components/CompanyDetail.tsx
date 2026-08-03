'use client';

/**
 * One employer: who they are, and every role we have seen from them.
 *
 * Counts are by closure state rather than a single total. A company page
 * showing only open roles makes the closure machine invisible, and the closure
 * machine is the part of this system most likely to be quietly wrong. Same
 * reasoning as /operate's admin table.
 */

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { JobRow } from './JobRow';
import { fetchCompany, fetchJobs } from '@/lib/api';
import type { CompanyDetail } from '@/lib/schemas';

const TERM = 'font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';

const STATES = [
  ['open', 'Open'],
  ['possibly_stale', 'Possibly stale'],
  ['unverified', 'Unverified'],
  ['closed', 'Closed'],
] as const;

export function CompanyCounts({ counts }: { readonly counts: CompanyDetail['job_status_counts'] }) {
  return (
    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {STATES.map(([state, label]) => (
        <div key={state}>
          <dt className={TERM}>{label}</dt>
          <dd
            data-testid={`count-${state}`}
            className="mt-1 text-[20px] font-medium text-paper tnum"
          >
            {counts[state]}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function CompanyDetailView({ companyId }: { readonly companyId: string }) {
  const company = useQuery({
    queryKey: ['company', companyId],
    queryFn: () => fetchCompany(companyId),
  });

  const companyName = company.data?.canonical_name;
  const jobs = useQuery({
    queryKey: ['jobs', { company: companyName }],
    // `enabled` guarantees this only runs once the name is known, but the type
    // does not know that — and under exactOptionalPropertyTypes, passing an
    // explicit undefined to an optional field is an error rather than an
    // omission. The fallback is unreachable, not a default.
    queryFn: () => fetchJobs({ company: companyName ?? '', limit: 50 }),
    enabled: companyName !== undefined,
  });

  if (company.isPending) {
    return (
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
        Loading employer…
      </p>
    );
  }

  if (company.error !== null) {
    return (
      <div className="border border-alert-900 bg-alert-900/30 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
          Could not load this employer
        </p>
        <p className="mt-1.5 text-[13px] text-paper-dim">{company.error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header>
        <Link
          className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint hover:text-paper-dim"
          href="/explore"
        >
          ← Back to roles
        </Link>
        <h1 className="mt-3 text-[22px] font-medium tracking-tight text-paper">
          {company.data.canonical_name}
        </h1>
        {company.data.website !== null && (
          <a
            className="mt-1 inline-block text-[14px] text-signal-400 underline underline-offset-2"
            href={company.data.website}
            target="_blank"
            rel="noreferrer"
          >
            {company.data.website}
          </a>
        )}
      </header>

      <section className="border border-ink-700 bg-ink-900/40 p-5">
        <h2 className={TERM}>Roles by state</h2>
        <div className="mt-4">
          <CompanyCounts counts={company.data.job_status_counts} />
        </div>
        <p className="mt-4 text-[12px] leading-relaxed text-paper-dim">
          Closed roles are counted, not hidden. A page that showed only open roles would make the
          closure machine invisible.
        </p>
      </section>

      <section className="border border-ink-700 bg-ink-900/40">
        <div className="border-b border-ink-700 px-5 py-2">
          <h2 className={TERM}>Roles</h2>
        </div>
        {jobs.data === undefined ? (
          <p className="px-5 py-8 font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
            Loading roles…
          </p>
        ) : jobs.data.items.length === 0 ? (
          <p className="px-5 py-8 text-[13px] text-paper-dim">
            No roles currently listed for this employer.
          </p>
        ) : (
          jobs.data.items.map((job) => <JobRow key={job.id} job={job} />)
        )}
      </section>
    </div>
  );
}
