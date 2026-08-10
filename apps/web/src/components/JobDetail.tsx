'use client';

/**
 * One job, in full.
 *
 * Two kinds of absence appear here, and they are different claims:
 *
 *   "not provided by source"  — the posting did not say it (A10)
 *   "not yet computed"        — M3 has not been built (I4)
 *
 * Collapsing them into one blank field is the lie this file exists to avoid.
 * The second group is listed by name rather than hidden, because a reader
 * cannot check for a field that was never mentioned.
 */

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';

import { ConfidenceLadder } from './ConfidenceLadder';
import { JobEligibility } from './JobEligibility';
import { JobRequirements } from './JobRequirements';
import { MatchPanel } from './MatchPanel';
import { SaveJobButton } from './SaveJobButton';
import { fetchJob } from '@/lib/api';
import type { JobDetail } from '@/lib/schemas';

/**
 * What this page still cannot compute. **`Eligibility` went at M3b and five of
 * the six went at M3c Task 10** — the milestone that built them. Each time this
 * list had otherwise been about to make a claim beside a section answering it.
 *
 * That is not a hypothetical tidy-up. A stale "not built yet" list has gone
 * unnoticed for a whole milestone three times in this project, always in the
 * same direction: nobody re-reads the list when the thing it waits on lands.
 * The M3b case was caught only because the new section put the word
 * "Eligibility" on the page twice and an existing test could no longer tell
 * them apart, and `JobDetail.test.tsx` now asserts the list against the sections
 * rather than trusting a reader to notice.
 *
 * *Recommended resume* is deliberately **not** here. It is one of `matching.md`
 * §6's nine elements, and `MatchPanel` names it beside the other two that are
 * not built — a score's missing parts belong with the score, where somebody
 * reading the breakdown will see them.
 */
const DEFERRED_FACTS = ['Similar jobs'] as const;

const TERM = 'font-mono text-[10px] uppercase tracking-[0.16em] text-paper-faint';
const VALUE = 'mt-1 text-[14px] text-paper';
const ABSENT = 'mt-1 text-[13px] italic text-paper-dim';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function formatSalary(salary: JobDetail['salary']): string {
  const currency = salary.currency ?? '';
  const format = (value: number) =>
    value >= 1000 ? `${Math.round(value / 1000)}k` : String(Math.round(value));
  const range =
    salary.minimum !== null && salary.maximum !== null
      ? `${format(salary.minimum)}–${format(salary.maximum)}`
      : format(salary.minimum ?? salary.maximum ?? 0);
  // A10: the source states no period, so we do not invent one.
  return `${currency} ${range} · ${salary.period ?? 'period not stated'}`.trim();
}

export function JobFacts({ job }: { readonly job: JobDetail }) {
  return (
    <div className="space-y-8">
      <dl className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <dt className={TERM}>Employment type</dt>
          <dd className={VALUE}>{job.employment_type.replace('_', ' ')}</dd>
        </div>
        <div>
          <dt className={TERM}>Remote policy</dt>
          <dd className={VALUE}>{job.remote_policy.replace('_', ' ')}</dd>
        </div>
        <div>
          <dt className={TERM}>Status</dt>
          <dd className={VALUE}>{job.status.replace('_', ' ')}</dd>
        </div>
        <div>
          <dt className={TERM}>Salary</dt>
          {job.salary.provided ? (
            <dd className={VALUE}>{formatSalary(job.salary)}</dd>
          ) : (
            <dd className={ABSENT}>Not provided by source</dd>
          )}
        </div>
        <div>
          <dt className={TERM}>Application deadline</dt>
          {job.application_deadline !== null ? (
            <dd className={VALUE}>{formatDate(job.application_deadline)}</dd>
          ) : (
            <dd className={ABSENT}>Not provided by source</dd>
          )}
        </div>
        <div>
          <dt className={TERM}>Published by source</dt>
          {job.source_published_at !== null ? (
            <dd className={VALUE}>{formatDate(job.source_published_at)}</dd>
          ) : (
            <dd className={ABSENT}>Not provided by source</dd>
          )}
        </div>
        <div>
          {/* Ours, not the source's. Never labelled "posted" (A10). */}
          <dt className={TERM}>First seen by Nightshift</dt>
          <dd className={VALUE}>{formatDate(job.first_seen_at)}</dd>
        </div>
        <div>
          <dt className={TERM}>Last verified</dt>
          <dd className={VALUE}>{formatDate(job.last_seen_at)}</dd>
        </div>
      </dl>

      <section>
        <h2 className={TERM}>Locations</h2>
        {job.locations.length === 0 ? (
          <p className={ABSENT}>No location stated by the source</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {job.locations.map((location) => (
              <li key={location.id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <ConfidenceLadder confidence={location.location_confidence} />
                <span className="text-[13px] text-paper-dim">{location.raw_text}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Above "not yet computed" and "sources", not below the description as
          the plan had it. Every row here quotes a sentence from the description,
          so a reader who has already scrolled the whole posting has read them
          once and is being shown them again; the other way round, the section
          tells them what to look for. It also keeps the things this page
          actually knows together, with the deferred list and the provenance
          after them rather than wedged in between. */}
      <JobRequirements
        requirements={job.requirements}
        descriptionText={job.description_text}
        extractorVersion={job.requirements_extractor_version}
      />

      {/* Directly under the requirements, because it is the same evidence read
          a second way: the section above says what the posting asks for, this
          one says how that lands for you. Above the description rather than
          below it for the reason JobRequirements is — a reader who has already
          scrolled the posting is being told what they just read. */}
      <JobEligibility eligibility={job.eligibility} />

      {/* Directly under eligibility, and that ordering is §5.2 rendered as a
          layout: whether this posting is open to you and how well it matches are
          two separate answers that are never reconciled into one. Reading them
          in that order is also the order they are worth knowing in — a hard
          blocker matters before a number does. */}
      <MatchPanel match={job.match} unmetRequirements={job.unmet_requirements} />

      <section data-testid="deferred-facts">
        <h2 className={TERM}>Not yet computed</h2>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-paper-dim">
          Listed rather than hidden, because a reader cannot check for a section that was never
          mentioned.
        </p>
        <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-1">
          {DEFERRED_FACTS.map((fact) => (
            <li key={fact} className="text-[13px] text-paper-dim">
              {fact}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className={TERM}>Sources</h2>
        {job.sources.length === 0 ? (
          <p className={ABSENT}>No provenance recorded</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {job.sources.map((source) => (
              <li key={`${source.source_name}-${source.source_job_id}`}>
                {source.canonical_url !== null ? (
                  <a
                    className="text-[14px] text-signal-400 underline underline-offset-2"
                    href={source.canonical_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {source.source_name}
                  </a>
                ) : (
                  <span className="text-[14px] text-paper">{source.source_name}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {job.description_text !== null && (
        <section>
          <h2 className={TERM}>Description</h2>
          <p
            data-testid="job-description"
            className="mt-3 max-w-3xl whitespace-pre-line text-[14px] leading-relaxed text-paper-dim"
          >
            {job.description_text}
          </p>
        </section>
      )}
    </div>
  );
}

export function JobDetailView({ jobId }: { readonly jobId: string }) {
  const { data, error, isPending } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => fetchJob(jobId),
  });

  if (isPending) {
    return (
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-paper-faint">
        Loading role…
      </p>
    );
  }

  if (error !== null) {
    return (
      <div className="border border-alert-900 bg-alert-900/30 px-4 py-3">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert-400">
          Could not load this role
        </p>
        <p className="mt-1.5 text-[13px] text-paper-dim">{error.message}</p>
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
        <h1 className="mt-3 text-[22px] font-medium tracking-tight text-paper">{data.title}</h1>
        <Link
          className="mt-1 inline-block text-[14px] text-signal-400 underline underline-offset-2"
          href={`/explore/companies/${data.company.id}`}
        >
          {data.company.canonical_name}
        </Link>
        <div className="mt-3">
          <SaveJobButton jobId={data.id} />
        </div>
      </header>
      <JobFacts job={data} />
    </div>
  );
}
