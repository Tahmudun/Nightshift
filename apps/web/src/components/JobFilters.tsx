'use client';

/**
 * The filter controls. Renders and reports; it does not fetch and it does not
 * own state — CLAUDE.md §8 names the component that does all three as an
 * anti-pattern by example.
 *
 * Deferred filters render disabled with their reason visible, rather than
 * being left out. An absent control is an invisible gap; a disabled one with a
 * sentence attached is a decision a reader can check. Same move as
 * `/analyze/coverage`.
 */

import type { JobQuery } from '@/lib/api';
import type { DeferredFilter } from '@/lib/schemas';

const EMPLOYMENT_TYPES = [
  ['full_time', 'Full time'],
  ['part_time', 'Part time'],
  ['internship', 'Internship'],
  ['contract', 'Contract'],
  ['temporary', 'Temporary'],
  ['unknown', 'Type not stated'],
] as const;

const REMOTE_POLICIES = [
  ['on_site', 'On site'],
  ['hybrid', 'Hybrid'],
  ['remote', 'Remote'],
  ['unknown', 'Policy not stated'],
] as const;

const LABEL = 'block font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';
const FIELD =
  'mt-1 w-full border border-ink-700 bg-ink-900 px-2 py-1.5 text-[13px] text-paper ' +
  'placeholder:text-paper-faint focus-visible:outline focus-visible:outline-1 ' +
  'focus-visible:outline-signal-400 disabled:cursor-not-allowed disabled:text-paper-faint';

export interface JobFiltersProps {
  readonly value: JobQuery;
  readonly onChange: (next: JobQuery) => void;
  readonly deferred: readonly DeferredFilter[];
}

export function JobFilters({ value, onChange, deferred }: JobFiltersProps) {
  /** Empty means absent. An empty string in the URL is a filter matching nothing. */
  function set(key: keyof JobQuery, raw: string): void {
    const next: JobQuery = { ...value };
    if (raw === '') {
      delete next[key];
    } else if (key === 'salary_at_least') {
      next.salary_at_least = Number(raw);
    } else {
      (next as Record<string, string>)[key] = raw;
    }
    onChange(next);
  }

  function toggleDescription(checked: boolean): void {
    const next: JobQuery = { ...value };
    if (checked) next.include_description = true;
    else delete next.include_description;
    onChange(next);
  }

  return (
    <div className="border border-ink-700 bg-ink-900/40 p-5">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <label className={LABEL} htmlFor="filter-q">
            Search
          </label>
          <input
            id="filter-q"
            className={FIELD}
            type="search"
            placeholder="job title"
            value={value.q ?? ''}
            onChange={(event) => set('q', event.target.value)}
          />
          <label className="mt-2 flex items-center gap-2 text-[12px] text-paper-dim">
            <input
              type="checkbox"
              className="accent-signal-400"
              checked={value.include_description === true}
              onChange={(event) => toggleDescription(event.target.checked)}
            />
            Also search descriptions
          </label>
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-company">
            Company
          </label>
          <input
            id="filter-company"
            className={FIELD}
            value={value.company ?? ''}
            onChange={(event) => set('company', event.target.value)}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-city">
            City
          </label>
          <input
            id="filter-city"
            className={FIELD}
            placeholder="as the posting wrote it"
            value={value.city ?? ''}
            onChange={(event) => set('city', event.target.value)}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-employment-type">
            Employment type
          </label>
          <select
            id="filter-employment-type"
            className={FIELD}
            value={value.employment_type ?? ''}
            onChange={(event) => set('employment_type', event.target.value)}
          >
            <option value="">Any</option>
            {EMPLOYMENT_TYPES.map(([token, label]) => (
              <option key={token} value={token}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-remote-policy">
            Remote policy
          </label>
          <select
            id="filter-remote-policy"
            className={FIELD}
            value={value.remote_policy ?? ''}
            onChange={(event) => set('remote_policy', event.target.value)}
          >
            <option value="">Any</option>
            {REMOTE_POLICIES.map(([token, label]) => (
              <option key={token} value={token}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="filter-salary">
            Pays at least
          </label>
          <input
            id="filter-salary"
            className={FIELD}
            type="number"
            min={0}
            placeholder="e.g. 90000"
            value={value.salary_at_least ?? ''}
            onChange={(event) => set('salary_at_least', event.target.value)}
          />
        </div>
      </div>

      {deferred.length > 0 && (
        <div className="mt-6 border-t border-ink-700 pt-4">
          <h3 className={LABEL}>Not available yet</h3>
          <p className="mt-2 max-w-2xl text-[12px] leading-relaxed text-paper-dim">
            These filters are in the spec and are not built. They are shown disabled with the reason
            rather than left out, because a filter that is simply missing is a gap nobody can see.
          </p>
          <ul className="mt-4 grid gap-4 sm:grid-cols-2">
            {deferred.map((entry) => (
              <li key={entry.name}>
                <label className={LABEL} htmlFor={`filter-${entry.name}`}>
                  {entry.name.replace(/_/g, ' ')}
                </label>
                <input
                  id={`filter-${entry.name}`}
                  className={FIELD}
                  disabled
                  value=""
                  readOnly
                  aria-describedby={`reason-${entry.name}`}
                />
                <p
                  id={`reason-${entry.name}`}
                  className="mt-1 text-[12px] leading-relaxed text-paper-dim"
                >
                  {entry.reason}{' '}
                  <span className="text-paper-faint">(arrives at {entry.blocked_on})</span>
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
