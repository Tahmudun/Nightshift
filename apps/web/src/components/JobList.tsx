'use client';

/**
 * The jobs list. Reads filters from the URL, fetches, and delegates each row.
 *
 * The URL is the state, so a filtered view is a link you can send and the back
 * button works. Kept small on purpose — CLAUDE.md §8 names the 400-line
 * component that renders, fetches and holds filter state as an anti-pattern.
 * Here: `JobFilters` renders, this fetches, the URL holds.
 */

import { useQuery } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo } from 'react';

import { JobFilters } from './JobFilters';
import { JobRow } from './JobRow';
import { SearchCaveats } from './SearchCaveats';
import { fetchJobs, type JobQuery } from '@/lib/api';

const TEXT_KEYS = [
  'q',
  'company',
  'city',
  'employment_type',
  'remote_policy',
  'status',
  'confidence',
  'source',
  'skill',
  'internship_season',
] as const;

export function JobList() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const filters = useMemo<JobQuery>(() => {
    const next: JobQuery = {};
    for (const key of TEXT_KEYS) {
      const raw = searchParams.get(key);
      if (raw !== null && raw !== '') (next as Record<string, string>)[key] = raw;
    }
    const salary = searchParams.get('salary_at_least');
    if (salary !== null && salary !== '' && Number.isFinite(Number(salary))) {
      next.salary_at_least = Number(salary);
    }
    const internshipYear = searchParams.get('internship_year');
    if (
      internshipYear !== null &&
      internshipYear !== '' &&
      Number.isFinite(Number(internshipYear))
    ) {
      next.internship_year = Number(internshipYear);
    }
    if (searchParams.get('include_description') === 'true') next.include_description = true;
    return next;
  }, [searchParams]);

  const onChange = useCallback(
    (next: JobQuery) => {
      const params = new URLSearchParams();
      for (const key of TEXT_KEYS) {
        const value = next[key];
        if (value !== undefined && value !== '') params.set(key, String(value));
      }
      if (next.salary_at_least !== undefined) {
        params.set('salary_at_least', String(next.salary_at_least));
      }
      if (next.include_description === true) params.set('include_description', 'true');
      const queryString = params.toString();
      // replace, not push: typing in a search box must not fill the back stack
      // with one entry per keystroke.
      router.replace(queryString === '' ? '/explore' : `/explore?${queryString}`, {
        scroll: false,
      });
    },
    [router],
  );

  const { data, error, isPending } = useQuery({
    queryKey: ['jobs', filters],
    queryFn: () => fetchJobs({ ...filters, limit: 50 }),
  });

  return (
    <div className="space-y-6">
      <JobFilters value={filters} onChange={onChange} deferred={data?.deferred_filters ?? []} />

      <section className="border border-ink-700 bg-ink-900/40">
        {isPending ? (
          <p className="px-5 py-8 font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
            Loading roles…
          </p>
        ) : error !== null ? (
          // §25: a failure states what happened and what to do, in the
          // interface's voice. It does not apologise and it is not vague.
          <div className="m-5 border border-alert-900 bg-alert-900/30 px-4 py-3">
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
              Could not load roles
            </p>
            <p className="mt-1.5 text-[13px] text-paper-dim">{error.message}</p>
          </div>
        ) : data.items.length === 0 ? (
          // The caveats come *first* here, and that ordering is the point.
          // "No roles match these filters" on its own is the product asserting
          // there are no such jobs; the line above it may be the only reason a
          // person knows the filter hid something it could not read.
          <div>
            <SearchCaveats
              excludedNoSalary={data.excluded_no_salary}
              excludedNoRequirements={data.excluded_no_requirements}
              excludedNoSeason={data.excluded_no_season}
            />
            <div className="m-5 border border-ink-700 px-4 py-6">
              <p className="text-[14px] text-paper">No roles match these filters.</p>
              <p className="mt-1.5 text-[13px] text-paper-dim">
                Clear a filter, or run{' '}
                <code className="border border-ink-700 bg-ink-900 px-1 py-0.5 font-mono text-[11px] text-signal-400">
                  make seed
                </code>{' '}
                if the corpus is empty.
              </p>
            </div>
          </div>
        ) : (
          <div>
            <div className="flex items-baseline justify-between border-b border-ink-700 px-5 py-2">
              <h2 className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint">
                Roles
              </h2>
              <p className="font-mono text-[10px] tracking-wide text-paper-faint tnum">
                showing {data.items.length} of {data.total}
              </p>
            </div>
            <SearchCaveats
              excludedNoSalary={data.excluded_no_salary}
              excludedNoRequirements={data.excluded_no_requirements}
              excludedNoSeason={data.excluded_no_season}
            />
            {data.items.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
